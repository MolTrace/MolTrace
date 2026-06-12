"""Deterministic-first regulatory task router (Prompt 13, Roadmap Layers 1-3).

First principle: anything **quantitative** or **classification**-based -- ICH thresholds,
Q3C/Q3D PDEs, M7 class assignment, CPCA potency category, spec-limit math -- is computed
by the deterministic engine **only**. No LLM ever touches the numeric path. LLMs are used
solely for **narrative** drafting, **retrieval**, and **triage**, always with citations and
a ``needs_review`` flag.

Every :class:`RoutedResult` carries the exact ``rule_set_version`` + ``model_versions`` +
``citations`` -- the provenance the Annex 22 audit wrapper (Prompt 12) records. A
deterministic result has ``model_versions == {}``: that emptiness *is* the audit guarantee
that no stochastic model produced the number, paired with the named guidance revision that
did.

DIFFERENTIATION: deterministic-first is the opposite of the common "wrap everything in an
LLM" approach. Regulators and QA trust numbers that come from auditable formulas tied to a
named guidance revision -- not from a model that might hallucinate a limit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from moltrace.regulatory.ai.registry import (
    ArtifactKind,
    Registry,
    default_regulatory_registry,
)
from moltrace.regulatory.impurities import (
    cpca_classifier,
    m7_classifier,
    q3ab_calculator,
    q3c_solvents,
    q3d_elements,
)

__all__ = [
    "Citation",
    "RegulatoryTask",
    "RoutedResult",
    "Router",
    "RoutingError",
    "TaskKind",
    "deterministic_operations",
]


class RoutingError(RuntimeError):
    """Raised on an unknown task kind / operation, or a kind/operation mismatch."""


# --------------------------------------------------------------------------- #
# Task taxonomy
# --------------------------------------------------------------------------- #
class TaskKind(StrEnum):
    """What a task asks for. The first two are deterministic-only; the rest are generative."""

    QUANTITATIVE = "quantitative"  # PDE, AI limit, threshold / spec-limit math
    CLASSIFICATION = "classification"  # M7 class, CPCA category, solvent class
    NARRATIVE = "narrative"  # LLM drafting of prose
    RETRIEVAL = "retrieval"  # RAG lookup
    TRIAGE = "triage"  # LLM triage / routing of free text


#: Kinds that MUST be computed deterministically -- never an LLM.
DETERMINISTIC_KINDS: frozenset[TaskKind] = frozenset(
    {TaskKind.QUANTITATIVE, TaskKind.CLASSIFICATION}
)
#: Kinds handled by the LLM + RAG path (Prompts 14-15), always with needs_review.
GENERATIVE_KINDS: frozenset[TaskKind] = frozenset(
    {TaskKind.NARRATIVE, TaskKind.RETRIEVAL, TaskKind.TRIAGE}
)


@dataclass(frozen=True)
class RegulatoryTask:
    """A unit of work to route.

    ``operation`` selects the engine/template; ``payload`` carries its inputs.
    """

    kind: TaskKind
    operation: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Citation:
    """A source-guidance citation attached to a routed result."""

    source_guidance: str
    effective_date: str | None = None
    reference: str | None = None  # table/section ref (deterministic) or document id (RAG)
    validation_doc_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_guidance": self.source_guidance,
            "effective_date": self.effective_date,
            "reference": self.reference,
            "validation_doc_id": self.validation_doc_id,
        }


@dataclass(frozen=True)
class RoutedResult:
    """A routed result plus its complete provenance -- the Annex 22 audit record.

    ``model_versions`` is ``{}`` for a deterministic result (no stochastic model touched
    the number) and ``{entry_id: code_sha}`` for a generative one. ``rule_set_version`` is
    set for deterministic results and ``None`` for generative ones.
    """

    task_kind: TaskKind
    operation: str
    engine: str  # "deterministic" | "generative"
    output: Any
    rule_set_version: str | None
    model_versions: dict[str, str]
    citations: tuple[Citation, ...]
    needs_review: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind.value,
            "operation": self.operation,
            "engine": self.engine,
            "output": self.output,
            "rule_set_version": self.rule_set_version,
            "model_versions": dict(sorted(self.model_versions.items())),
            "citations": [c.as_dict() for c in self.citations],
            "needs_review": self.needs_review,
            "warnings": list(self.warnings),
            "provenance": self.provenance,
        }


# --------------------------------------------------------------------------- #
# Deterministic dispatch table: operation -> (kind, rule-engine name, adapter)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _OpSpec:
    kind: TaskKind
    engine_name: str  # registry name of the rule-engine that owns this op
    adapter: Callable[[Mapping[str, Any]], Any]


def _q3ab_thresholds(p: Mapping[str, Any]) -> Any:
    return q3ab_calculator.calculate_q3ab_thresholds(
        daily_dose_g=float(p["daily_dose_g"]),
        substance_type=p.get("substance_type", "drug_substance"),
        route=p.get("route", "oral"),
    )


def _q3c_residual_solvent_limits(p: Mapping[str, Any]) -> Any:
    return q3c_solvents.check_residual_solvent_limits(
        product_spec=p["product_spec"],
        daily_dose_g=float(p["daily_dose_g"]),
        route=p.get("route", "oral"),
    )


def _q3c_classify_solvent(p: Mapping[str, Any]) -> Any:
    return q3c_solvents.classify_solvent(p["solvent_identifier"], route=p.get("route", "oral"))


def _q3d_element_pde(p: Mapping[str, Any]) -> Any:
    return q3d_elements.get_element_pde(p["element"], p["route"])


def _q3d_concentration_limit(p: Mapping[str, Any]) -> Any:
    return q3d_elements.calculate_concentration_limit(
        p["element"], p["route"], float(p["max_daily_dose_g"])
    )


def _q3d_risk_assessment(p: Mapping[str, Any]) -> Any:
    return q3d_elements.risk_assessment_report(
        drug_product_components=p["drug_product_components"],
        manufacturing_equipment=list(p.get("manufacturing_equipment", [])),
        route=p["route"],
        max_daily_dose_g=float(p["max_daily_dose_g"]),
    )


def _m7_classify(p: Mapping[str, Any]) -> Any:
    return m7_classifier.classify_m7(
        smiles=p["smiles"],
        duration_months=float(p.get("duration_months", 120)),
        in_silico_result_expert=p.get("in_silico_result_expert"),
        in_silico_result_statistical=p.get("in_silico_result_statistical"),
        experimental_ames=p.get("experimental_ames"),
    )


def _cpca_classify(p: Mapping[str, Any]) -> Any:
    return cpca_classifier.classify_cpca(p["smiles"], authority=p.get("authority", "FDA"))


def _cpca_cumulative_risk(p: Mapping[str, Any]) -> Any:
    nitrosamines = [(str(s), float(v)) for s, v in p["nitrosamines"]]
    return cpca_classifier.calculate_cumulative_risk(
        nitrosamines=nitrosamines, authority=p.get("authority", "FDA")
    )


_DETERMINISTIC_OPS: dict[str, _OpSpec] = {
    "q3ab_thresholds": _OpSpec(TaskKind.QUANTITATIVE, "ich_q3ab", _q3ab_thresholds),
    "q3c_residual_solvent_limits": _OpSpec(
        TaskKind.QUANTITATIVE, "ich_q3c", _q3c_residual_solvent_limits
    ),
    "q3c_classify_solvent": _OpSpec(TaskKind.CLASSIFICATION, "ich_q3c", _q3c_classify_solvent),
    "q3d_element_pde": _OpSpec(TaskKind.QUANTITATIVE, "ich_q3d", _q3d_element_pde),
    "q3d_concentration_limit": _OpSpec(
        TaskKind.QUANTITATIVE, "ich_q3d", _q3d_concentration_limit
    ),
    "q3d_risk_assessment": _OpSpec(TaskKind.QUANTITATIVE, "ich_q3d", _q3d_risk_assessment),
    "m7_classify": _OpSpec(TaskKind.CLASSIFICATION, "ich_m7", _m7_classify),
    "cpca_classify": _OpSpec(
        TaskKind.CLASSIFICATION, "fda_cpca_nitrosamine", _cpca_classify
    ),
    "cpca_cumulative_risk": _OpSpec(
        TaskKind.QUANTITATIVE, "fda_cpca_nitrosamine", _cpca_cumulative_risk
    ),
}


def deterministic_operations() -> dict[str, dict[str, str]]:
    """Introspect the deterministic dispatch table: ``op -> {kind, engine}``.

    Every entry's ``kind`` is in :data:`DETERMINISTIC_KINDS` by construction, so no
    quantitative/classification operation can ever reach the LLM path.
    """

    return {
        op: {"kind": spec.kind.value, "engine": spec.engine_name}
        for op, spec in sorted(_DETERMINISTIC_OPS.items())
    }


# A generative backend (Prompts 14-15), injected. Returns a mapping with at least
# ``"text"`` and optionally ``"citations"`` / ``"warnings"``.
LlmFn = Callable[[RegulatoryTask], Mapping[str, Any]]


def _as_dict(obj: Any) -> Any:
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if isinstance(obj, Mapping):
        return dict(obj)
    return obj


def _first_attr(objs: Sequence[Any], name: str) -> Any:
    for o in objs:
        value = getattr(o, name, None)
        if value:
            return value
    return None


def _coerce_citation(c: Any) -> Citation:
    if isinstance(c, Citation):
        return c
    if isinstance(c, Mapping):
        return Citation(
            source_guidance=str(c.get("source_guidance") or c.get("source") or "(uncited)"),
            effective_date=c.get("effective_date"),
            reference=c.get("reference") or c.get("document_id"),
            validation_doc_id=c.get("validation_doc_id"),
        )
    return Citation(source_guidance=str(c))


# --------------------------------------------------------------------------- #
# The router
# --------------------------------------------------------------------------- #
class Router:
    """Route a :class:`RegulatoryTask` deterministic-first.

    Quantitative / classification tasks are dispatched to the deterministic engine and
    **never** reference ``llm_fn``; narrative / retrieval / triage tasks go to ``llm_fn``
    (Prompts 14-15). Both paths assemble provenance from the registry, so every result is
    audit-ready.
    """

    def __init__(self, registry: Registry | None = None, *, llm_fn: LlmFn | None = None) -> None:
        self.registry = registry if registry is not None else default_regulatory_registry()
        self._llm_fn = llm_fn

    def handle(self, task: RegulatoryTask) -> RoutedResult:
        if not isinstance(task, RegulatoryTask):  # pragma: no cover - defensive
            raise RoutingError("handle() expects a RegulatoryTask")
        if task.kind in DETERMINISTIC_KINDS:
            return self._handle_deterministic(task)
        if task.kind in GENERATIVE_KINDS:
            return self._handle_generative(task)
        raise RoutingError(f"unknown task kind: {task.kind!r}")  # pragma: no cover

    # -- deterministic path (NO llm_fn reference) ----------------------------- #
    def _handle_deterministic(self, task: RegulatoryTask) -> RoutedResult:
        spec = _DETERMINISTIC_OPS.get(task.operation)
        if spec is None:
            raise RoutingError(
                f"unknown deterministic operation {task.operation!r}; "
                f"known: {sorted(_DETERMINISTIC_OPS)}"
            )
        if task.kind != spec.kind:
            raise RoutingError(
                f"operation {task.operation!r} is {spec.kind.value}, not {task.kind.value}"
            )

        result = spec.adapter(task.payload)
        if isinstance(result, (list, tuple)):
            items = list(result)
            output: Any = [_as_dict(r) for r in items]
            result_rsv = _first_attr(items, "rule_set_version")
            reference = _first_attr(items, "table_reference")
        else:
            output = _as_dict(result)
            result_rsv = getattr(result, "rule_set_version", None)
            reference = getattr(result, "table_reference", None)
            if isinstance(output, Mapping):
                result_rsv = result_rsv or output.get("rule_set_version")
                reference = reference or output.get("table_reference")

        entry = self.registry.resolve(ArtifactKind.RULE_ENGINE, spec.engine_name)
        warnings: list[str] = []
        if entry is None:
            warnings.append(
                f"rule-engine {spec.engine_name!r} is not registered as production; "
                "provenance is incomplete (no validation_doc_id / guidance)"
            )
            rule_set_version = result_rsv
            citations: tuple[Citation, ...] = ()
        else:
            rule_set_version = result_rsv or entry.rule_set_version
            citations = (
                Citation(
                    source_guidance=entry.source_guidance or spec.engine_name,
                    effective_date=entry.effective_date,
                    reference=reference,
                    validation_doc_id=entry.validation_doc_id,
                ),
            )

        provenance = {
            "engine": "deterministic",
            "operation": task.operation,
            "rule_engine": spec.engine_name,
            "rule_engine_entry_id": entry.entry_id if entry else None,
            "rule_set_version": rule_set_version,
            "code_sha": entry.code_sha if entry else None,
            "validation_doc_id": entry.validation_doc_id if entry else None,
            "source_guidance": entry.source_guidance if entry else None,
            "effective_date": entry.effective_date if entry else None,
            "model_versions": {},  # the audit guarantee: NO model on the numeric path
        }
        return RoutedResult(
            task_kind=task.kind,
            operation=task.operation,
            engine="deterministic",
            output=output,
            rule_set_version=rule_set_version,
            model_versions={},
            citations=citations,
            needs_review=False,
            warnings=tuple(warnings),
            provenance=provenance,
        )

    # -- generative path (LLM + RAG, Prompts 14-15) --------------------------- #
    def _handle_generative(self, task: RegulatoryTask) -> RoutedResult:
        if self._llm_fn is None:
            raise RoutingError(
                f"task {task.operation!r} is {task.kind.value} (narrative/retrieval/triage) "
                "but no generative backend is configured; inject an llm_fn (Prompts 14-15)."
            )

        prompt = self.registry.resolve(ArtifactKind.LLM_PROMPT, task.operation) or (
            self.registry.resolve(ArtifactKind.LLM_PROMPT, "default")
        )
        rag = self.registry.resolve(ArtifactKind.RAG_INDEX, "default")
        adapter = self.registry.resolve(ArtifactKind.NARRATIVE_ADAPTER, task.operation)
        model_versions = {
            e.entry_id: e.code_sha for e in (prompt, rag, adapter) if e is not None
        }

        gen = self._llm_fn(task)
        gen_map = dict(gen) if isinstance(gen, Mapping) else {"text": str(gen)}
        text = gen_map.get("text", "")
        citations = tuple(_coerce_citation(c) for c in gen_map.get("citations", ()) or ())
        warnings = tuple(gen_map.get("warnings", ()) or ())
        if not model_versions:
            warnings = warnings + (
                "no production LLM_PROMPT/RAG_INDEX registered; model provenance incomplete",
            )

        provenance = {
            "engine": "generative",
            "operation": task.operation,
            "rule_set_version": None,
            "model_versions": dict(sorted(model_versions.items())),
            "prompt_entry_id": prompt.entry_id if prompt else None,
            "rag_entry_id": rag.entry_id if rag else None,
            "adapter_entry_id": adapter.entry_id if adapter else None,
        }
        return RoutedResult(
            task_kind=task.kind,
            operation=task.operation,
            engine="generative",
            output={"text": text},
            rule_set_version=None,
            model_versions=model_versions,
            citations=citations,
            needs_review=True,  # LLM output ALWAYS needs human review
            warnings=warnings,
            provenance=provenance,
        )
