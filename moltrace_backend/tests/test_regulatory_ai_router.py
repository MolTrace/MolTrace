"""Prompt 13 — deterministic-first registry + router.

Acceptance:
- registry tracks rule-set versions tied to guidance + effective date,
- router sends 100% of quantitative/classification tasks to the deterministic engine
  (no LLM call on the numeric path),
- every result carries rule_set_version + model_versions + citations,
- validation_doc_id linkage present for each rule-set version.
"""

from __future__ import annotations

from typing import Any

import pytest

from moltrace.regulatory.ai import (
    AppendOnlyViolation,
    ArtifactKind,
    ArtifactStatus,
    Registry,
    RegulatoryTask,
    Router,
    RoutingError,
    TaskKind,
    build_registry_entry,
    default_regulatory_registry,
    deterministic_operations,
)
from moltrace.regulatory.infra.versioning import rule_set_version


class _SpyLlm:
    """A generative backend that records whether it was ever called."""

    def __init__(self, text: str = "draft", citations: list[dict[str, Any]] | None = None) -> None:
        self.calls = 0
        self._text = text
        self._citations = citations or []

    def __call__(self, task: RegulatoryTask) -> dict[str, Any]:
        self.calls += 1
        return {"text": self._text, "citations": self._citations}


# --------------------------------------------------------------------------- #
# Registry: rule-set versions tied to guidance + effective date + validation doc
# --------------------------------------------------------------------------- #
def test_registry_tracks_rule_set_versions_with_guidance_and_effective_date() -> None:
    reg = default_regulatory_registry()

    q3c = reg.resolve(ArtifactKind.RULE_ENGINE, "ich_q3c")
    assert q3c is not None
    assert q3c.source_guidance == "ICH Q3C(R8)"
    assert q3c.effective_date == "2021"
    assert q3c.rule_set_version is not None and q3c.rule_set_version.startswith("sha256:")
    assert q3c.code_sha  # the git revision implementing the formula set

    m7 = reg.resolve(ArtifactKind.RULE_ENGINE, "ich_m7")
    assert m7 is not None
    assert m7.source_guidance == "ICH M7(R2)"
    assert m7.effective_date == "2023"


def test_every_rule_engine_has_validation_doc_id_and_is_production() -> None:
    reg = default_regulatory_registry()
    engines = reg.list_entries(kind=ArtifactKind.RULE_ENGINE)
    assert {e.name for e in engines} == {
        "ich_q3ab",
        "ich_q3c",
        "ich_q3d",
        "ich_m7",
        "fda_cpca_nitrosamine",
    }
    assert all(e.validation_doc_id for e in engines)  # GxP validation linkage present
    assert all(
        reg.current_status(e.entry_id) == ArtifactStatus.PRODUCTION for e in engines
    )


def test_registry_rule_set_version_matches_engine_source_of_truth() -> None:
    from moltrace.regulatory.impurities.q3d_elements import q3d_rule_set

    reg = default_regulatory_registry()
    entry = reg.resolve(ArtifactKind.RULE_ENGINE, "ich_q3d")
    assert entry is not None
    # The registry never invents a version: it is the content hash of the engine's rule-set.
    assert entry.rule_set_version == rule_set_version(q3d_rule_set())


def test_registry_is_append_only() -> None:
    reg = default_regulatory_registry()
    existing = reg.list_entries(kind=ArtifactKind.RULE_ENGINE)[0]
    with pytest.raises(AppendOnlyViolation):
        reg.register(existing)


def test_promote_new_revision_supersedes_incumbent() -> None:
    reg = default_regulatory_registry()
    v1 = reg.resolve(ArtifactKind.RULE_ENGINE, "ich_q3c")
    assert v1 is not None
    reg.register(
        build_registry_entry(
            kind=ArtifactKind.RULE_ENGINE,
            name="ich_q3c",
            semver="2.0.0",
            code_sha="future-sha",
            source_guidance="ICH Q3C(R9)",
            effective_date="2099",
            validation_doc_id="GAMP5-CSV-ICH-Q3C-R9",
            status=ArtifactStatus.CANDIDATE,
        )
    )
    reg.promote("rule_engine:ich_q3c:2.0.0")
    current = reg.resolve(ArtifactKind.RULE_ENGINE, "ich_q3c")
    assert current is not None and current.semver == "2.0.0"
    assert reg.current_status(v1.entry_id) == ArtifactStatus.RETIRED


# --------------------------------------------------------------------------- #
# Router: 100% of quantitative/classification go deterministic, NO LLM
# --------------------------------------------------------------------------- #
def test_quantitative_task_uses_deterministic_engine_and_never_calls_llm() -> None:
    spy = _SpyLlm()
    router = Router(llm_fn=spy)

    result = router.handle(
        RegulatoryTask(TaskKind.QUANTITATIVE, "q3d_element_pde", {"element": "As", "route": "oral"})
    )

    assert spy.calls == 0  # the differentiator: no LLM on the numeric path
    assert result.engine == "deterministic"
    assert result.model_versions == {}  # the audit guarantee: no stochastic model
    assert result.rule_set_version is not None and result.rule_set_version.startswith("sha256:")
    assert result.needs_review is False
    assert result.citations
    assert result.citations[0].source_guidance == "ICH Q3D(R2)"
    assert result.citations[0].validation_doc_id == "GAMP5-CSV-ICH-Q3D-R2"


def test_classification_task_uses_deterministic_engine_and_never_calls_llm() -> None:
    spy = _SpyLlm()
    router = Router(llm_fn=spy)

    result = router.handle(
        RegulatoryTask(
            TaskKind.CLASSIFICATION, "q3c_classify_solvent", {"solvent_identifier": "acetonitrile"}
        )
    )

    assert spy.calls == 0
    assert result.engine == "deterministic"
    assert result.model_versions == {}
    assert result.rule_set_version is not None and result.rule_set_version.startswith("sha256:")
    assert result.citations[0].source_guidance == "ICH Q3C(R8)"
    assert result.citations[0].validation_doc_id == "GAMP5-CSV-ICH-Q3C-R8"


def test_all_deterministic_operations_are_deterministic_kinds() -> None:
    # Static guarantee covering EVERY numeric/classification op (incl. m7 + cpca, which
    # need rdkit to execute): no operation in the table could ever reach the LLM path.
    ops = deterministic_operations()
    assert ops
    for meta in ops.values():
        assert meta["kind"] in {TaskKind.QUANTITATIVE.value, TaskKind.CLASSIFICATION.value}
    assert {meta["engine"] for meta in ops.values()} == {
        "ich_q3ab",
        "ich_q3c",
        "ich_q3d",
        "ich_m7",
        "fda_cpca_nitrosamine",
    }


def test_routed_result_as_dict_is_audit_ready() -> None:
    router = Router()
    result = router.handle(
        RegulatoryTask(TaskKind.QUANTITATIVE, "q3ab_thresholds", {"daily_dose_g": 1.0})
    )
    d = result.as_dict()
    assert d["engine"] == "deterministic"
    assert d["model_versions"] == {}
    assert d["rule_set_version"].startswith("sha256:")
    assert d["citations"][0]["validation_doc_id"] == "GAMP5-CSV-ICH-Q3AB-R2"
    assert d["provenance"]["model_versions"] == {}
    assert d["provenance"]["source_guidance"].startswith("ICH Q3A(R2)")
    assert d["provenance"]["code_sha"]


def test_unknown_operation_raises() -> None:
    router = Router()
    with pytest.raises(RoutingError):
        router.handle(RegulatoryTask(TaskKind.QUANTITATIVE, "does_not_exist", {}))


def test_kind_operation_mismatch_raises() -> None:
    router = Router()
    # q3d_element_pde is QUANTITATIVE; sending it as CLASSIFICATION must fail loudly.
    with pytest.raises(RoutingError):
        router.handle(
            RegulatoryTask(
                TaskKind.CLASSIFICATION, "q3d_element_pde", {"element": "As", "route": "oral"}
            )
        )


# --------------------------------------------------------------------------- #
# Router: generative path (narrative/retrieval/triage) -> LLM + RAG with provenance
# --------------------------------------------------------------------------- #
def test_narrative_task_routes_to_llm_with_versions_citations_and_needs_review() -> None:
    reg = default_regulatory_registry()
    reg.register(
        build_registry_entry(
            kind=ArtifactKind.LLM_PROMPT,
            name="default",
            semver="1.0.0",
            code_sha="prompt-sha",
            status=ArtifactStatus.PRODUCTION,
        )
    )
    reg.register(
        build_registry_entry(
            kind=ArtifactKind.RAG_INDEX,
            name="default",
            semver="1.0.0",
            code_sha="rag-sha",
            status=ArtifactStatus.PRODUCTION,
        )
    )
    spy = _SpyLlm(
        text="A narrative summary.",
        citations=[{"source_guidance": "ICH Q3C(R8)", "document_id": "EMA-CHMP-12345"}],
    )
    router = Router(registry=reg, llm_fn=spy)

    result = router.handle(RegulatoryTask(TaskKind.NARRATIVE, "summary", {"prompt": "summarise"}))

    assert spy.calls == 1
    assert result.engine == "generative"
    assert result.needs_review is True  # LLM output always needs review
    assert result.rule_set_version is None  # no rule-set on the narrative path
    assert result.model_versions  # prompt + rag versions recorded
    assert "llm_prompt:default:1.0.0" in result.model_versions
    assert "rag_index:default:1.0.0" in result.model_versions
    assert result.citations and result.citations[0].source_guidance == "ICH Q3C(R8)"
    assert result.output["text"] == "A narrative summary."


def test_generative_task_without_backend_raises() -> None:
    router = Router(llm_fn=None)
    with pytest.raises(RoutingError):
        router.handle(RegulatoryTask(TaskKind.TRIAGE, "triage", {"text": "is this in scope?"}))


def test_router_accepts_a_custom_registry() -> None:
    reg = Registry()  # empty: no rule-engines registered
    router = Router(registry=reg)
    result = router.handle(
        RegulatoryTask(TaskKind.QUANTITATIVE, "q3d_element_pde", {"element": "As", "route": "oral"})
    )
    # Engine still computes deterministically, but provenance flags the missing registration.
    assert result.engine == "deterministic"
    assert result.model_versions == {}
    assert any("not registered" in w for w in result.warnings)
