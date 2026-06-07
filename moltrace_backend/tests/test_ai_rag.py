"""Tests for retrieval-augmented structure reasoning (Prompt 14, ai/rag.py).

Everything is exercised with fakes — a fake similarity index (no FAISS), a fake
metadata resolver, a fake LLM (no ``anthropic``), and a fake verifier — so the
whole pipeline runs deterministically on a CPU-only host with no network and no
model weights. The guardrails under test are the Prompt 14 acceptance criteria:

* ``build_reasoning_context`` returns ``top_k`` analogues with SMILES, a bounded
  similarity, and a license; it is token-bounded and license-aware.
* The completion is schema-validated with exactly one retry.
* The hallucination guard drops uncited + unsupported candidates *before*
  verification (tested with an adversarial completion).
* The Prompt 7 verifier — not the LLM — decides pass/fail; ``self_confidence`` is
  advisory and is never used as the verifier prior.
* The full prompt + raw completion(s) + retrieved ids are captured for audit.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from moltrace.spectroscopy.ai.rag import (
    RAGSchemaError,
    RetrievedAnalogue,
    _parse_candidates,
    build_reasoning_context,
    propose_structures,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeIndex:
    """Duck-typed Prompt 8 index: ``search(query, k) -> [(id, l2), ...]``."""

    def __init__(self, hits, size=None):
        self._hits = list(hits)
        self._size = size if size is not None else len(hits)

    def __len__(self):
        return self._size

    def search(self, query, k=100):  # query is ignored — deterministic hits
        return list(self._hits[:k])


def _resolver(table):
    def resolve(identifier):
        return table.get(identifier)

    return resolve


def _spectrum(nucleus="1H", fingerprint="fp-test"):
    return SimpleNamespace(nucleus=nucleus, fingerprint=fingerprint, metadata={})


def _triv_encoder(_spectrum_obj):
    return np.zeros(8, dtype=np.float32)


def _llm(responses):
    """Return an ``llm(system, user)`` that yields ``responses`` in order."""
    state = {"n": 0}
    calls = []

    def call(system, user):
        calls.append({"system": system, "user": user})
        idx = min(state["n"], len(responses) - 1)
        state["n"] += 1
        return responses[idx]

    call.calls = calls
    return call


def _verifier(verdict_by_smiles, posterior_by_smiles):
    """Fake Prompt 7 verifier; records the prior it was called with."""
    seen = []

    def verify(spectrum, smiles, *, prior_confidence=0.5, options=None):
        seen.append({"smiles": smiles, "prior_confidence": prior_confidence})
        return SimpleNamespace(
            proposed_smiles=smiles,
            verdict=verdict_by_smiles.get(smiles, "inconclusive"),
            posterior_confidence=posterior_by_smiles.get(smiles, 0.0),
        )

    verify.seen = seen
    return verify


_VALID = (
    '{"candidates": [{"smiles": "CCO", "rationale": "ethanol analogue", '
    '"cited_analogue_ids": ["AID1"], "self_confidence": 0.99}]}'
)


# --------------------------------------------------------------------------- #
# build_reasoning_context
# --------------------------------------------------------------------------- #
def test_build_context_topk_with_structures_scores_and_license():
    table = {
        "AID1": {"smiles": "CCO", "license": "CC-BY-SA", "shift_summary": "1.2, 3.7"},
        "AID2": {"smiles": "CCC", "license": "CC0", "shift_summary": "0.9"},
        "AID3": {"smiles": "CCCO", "license": "CC-BY", "shift_summary": "1.1"},
    }
    index = FakeIndex([("AID1", 0.0), ("AID2", 1.0), ("AID3", 3.0)], size=4521)

    ctx = build_reasoning_context(
        _spectrum(),
        index=index,
        resolver=_resolver(table),
        top_k=3,
        query_encoder=_triv_encoder,
    )

    assert len(ctx.analogues) == 3
    assert ctx.index_size == 4521
    assert ctx.top_k == 3
    # SMILES + license carried through; similarity is a bounded transform of L2.
    assert [a.smiles for a in ctx.analogues] == ["CCO", "CCC", "CCCO"]
    assert [a.license for a in ctx.analogues] == ["CC-BY-SA", "CC0", "CC-BY"]
    assert ctx.analogues[0].similarity == pytest.approx(1.0)  # L2 == 0
    assert ctx.analogues[1].similarity == pytest.approx(0.5)  # 1/(1+1)
    assert ctx.analogues[0].similarity > ctx.analogues[2].similarity
    assert [a.rank for a in ctx.analogues] == [0, 1, 2]
    assert ctx.allowed_analogue_ids == {"AID1", "AID2", "AID3"}
    block = ctx.to_prompt_block()
    assert "CCO" in block and "CC-BY-SA" in block and "AID1" in block


def test_build_context_resolver_omitted_treats_id_as_smiles():
    index = FakeIndex([("CCO", 0.0), ("c1ccccc1", 2.0)])
    ctx = build_reasoning_context(
        _spectrum(), index=index, top_k=5, query_encoder=_triv_encoder
    )
    assert [a.smiles for a in ctx.analogues] == ["CCO", "c1ccccc1"]
    assert all(a.license == "unknown" for a in ctx.analogues)


def test_build_context_license_allowlist_filters():
    table = {
        "AID1": {"smiles": "CCO", "license": "CC-BY-SA"},
        "AID2": {"smiles": "CCC", "license": "proprietary"},
    }
    index = FakeIndex([("AID1", 0.0), ("AID2", 1.0)])
    ctx = build_reasoning_context(
        _spectrum(),
        index=index,
        resolver=_resolver(table),
        allowed_licenses=["CC-BY-SA"],
        query_encoder=_triv_encoder,
    )
    assert [a.analogue_id for a in ctx.analogues] == ["AID1"]
    assert any("license" in w for w in ctx.warnings)


def test_build_context_token_budget_truncates():
    hits = [(f"AID{i}", float(i)) for i in range(40)]
    table = {f"AID{i}": {"smiles": "C" * 20, "license": "CC0"} for i in range(40)}
    index = FakeIndex(hits)
    ctx = build_reasoning_context(
        _spectrum(),
        index=index,
        resolver=_resolver(table),
        top_k=40,
        token_budget=40,  # tiny budget forces truncation
        query_encoder=_triv_encoder,
    )
    assert ctx.truncated is True
    assert 0 < len(ctx.analogues) < 40
    assert ctx.token_estimate <= 40 + 1
    assert any("truncated" in w for w in ctx.warnings)


def test_build_context_empty_index():
    ctx = build_reasoning_context(
        _spectrum(), index=FakeIndex([]), query_encoder=_triv_encoder
    )
    assert ctx.analogues == []
    assert ctx.to_prompt_block() == "(no precedent spectra were retrieved)"


# --------------------------------------------------------------------------- #
# Strict-JSON parsing / validation
# --------------------------------------------------------------------------- #
def test_parse_candidates_object_and_array_forms():
    obj = _parse_candidates(_VALID)
    assert obj[0]["smiles"] == "CCO"
    assert obj[0]["cited_analogue_ids"] == ["AID1"]

    arr = _parse_candidates(
        '[{"smiles": "CCC", "rationale": "x", "cited_analogue_ids": [], '
        '"self_confidence": 0.3}]'
    )
    assert arr[0]["smiles"] == "CCC"


def test_parse_candidates_tolerates_code_fence():
    fenced = "```json\n" + _VALID + "\n```"
    assert _parse_candidates(fenced)[0]["smiles"] == "CCO"


def test_parse_candidates_clips_self_confidence():
    out = _parse_candidates(
        '{"candidates": [{"smiles": "CCO", "rationale": "x", '
        '"cited_analogue_ids": [], "self_confidence": 9.0}]}'
    )
    assert out[0]["self_confidence"] == 1.0


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not json",
        '{"nope": []}',  # missing 'candidates'
        '{"candidates": [{"rationale": "x", "cited_analogue_ids": [], "self_confidence": 0.1}]}',  # no smiles
        '{"candidates": [{"smiles": "CCO", "rationale": "x", "cited_analogue_ids": "AID1", "self_confidence": 0.1}]}',  # cited not a list
        '{"candidates": [{"smiles": "CCO", "rationale": "x", "cited_analogue_ids": [], "self_confidence": "high"}]}',  # conf not number
        '{"candidates": [{"smiles": "CCO", "rationale": "x", "cited_analogue_ids": [], "self_confidence": true}]}',  # bool not number
        "42",  # not object/array
    ],
)
def test_parse_candidates_rejects_malformed(bad):
    with pytest.raises(RAGSchemaError):
        _parse_candidates(bad)


# --------------------------------------------------------------------------- #
# propose_structures — verifier is the arbiter
# --------------------------------------------------------------------------- #
def _context_with(table, hits):
    return build_reasoning_context(
        _spectrum(),
        index=FakeIndex(hits),
        resolver=_resolver(table),
        top_k=len(hits),
        query_encoder=_triv_encoder,
    )


def test_verifier_decides_not_llm_confidence():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    # LLM proposes two cited candidates with high self_confidence (0.99 / 0.9).
    completion = (
        '{"candidates": ['
        '{"smiles": "CCO", "rationale": "a", "cited_analogue_ids": ["AID1"], "self_confidence": 0.99},'
        '{"smiles": "c1ccccc1", "rationale": "b", "cited_analogue_ids": ["AID1"], "self_confidence": 0.9}'
        "]}"
    )
    verifier = _verifier(
        verdict_by_smiles={"CCO": "consistent", "c1ccccc1": "inconsistent"},
        posterior_by_smiles={"CCO": 0.80, "c1ccccc1": 0.05},
    )
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([completion]),
        verifier=verifier,
        support_check=lambda smiles, c: True,
    )

    by_smiles = {c.smiles: c for c in result.candidates}
    # The verifier's posterior/verdict are authoritative — not self_confidence.
    assert by_smiles["CCO"].accepted is True
    assert by_smiles["CCO"].posterior_confidence == pytest.approx(0.80)
    assert by_smiles["c1ccccc1"].accepted is False  # high self_confidence ignored
    assert by_smiles["c1ccccc1"].posterior_confidence == pytest.approx(0.05)
    # self_confidence was NEVER fed to the verifier as the prior.
    assert all(call["prior_confidence"] == 0.5 for call in verifier.seen)
    # advisory self_confidence is still recorded.
    assert by_smiles["CCO"].self_confidence == pytest.approx(0.99)
    # accepted ranking exposes only the consistent candidate.
    assert [c.smiles for c in result.accepted] == ["CCO"]


def test_hallucination_guard_drops_uncited_unsupported_before_verification():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    # One grounded candidate (cites AID1) + one adversarial candidate that cites a
    # fabricated id and is structurally unsupported.
    completion = (
        '{"candidates": ['
        '{"smiles": "CCO", "rationale": "grounded", "cited_analogue_ids": ["AID1"], "self_confidence": 0.5},'
        '{"smiles": "C1CC1", "rationale": "hallucinated", "cited_analogue_ids": ["FAKE-999"], "self_confidence": 0.99}'
        "]}"
    )
    verifier = _verifier(
        verdict_by_smiles={"CCO": "consistent"},
        posterior_by_smiles={"CCO": 0.7},
    )
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([completion]),
        verifier=verifier,
        support_check=lambda smiles, c: False,  # nothing is structurally supported
    )

    by_smiles = {c.smiles: c for c in result.candidates}
    # Adversarial candidate dropped by the guard, never verified.
    dropped = by_smiles["C1CC1"]
    assert dropped.dropped_reason == "hallucination_guard"
    assert dropped.accepted is False
    assert dropped.verification is None
    # The verifier was only ever asked about the grounded candidate.
    assert [s["smiles"] for s in verifier.seen] == ["CCO"]
    assert by_smiles["CCO"].accepted is True
    assert "C1CC1" in {c.smiles for c in result.dropped}


def test_unsupported_but_structurally_matched_candidate_survives_guard():
    # A candidate that cites a fake id but IS structurally one of the analogues
    # (support_check True) is kept and verified — grounding via structure.
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    completion = (
        '{"candidates": [{"smiles": "CCO", "rationale": "x", '
        '"cited_analogue_ids": ["FAKE"], "self_confidence": 0.4}]}'
    )
    verifier = _verifier({"CCO": "consistent"}, {"CCO": 0.6})
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([completion]),
        verifier=verifier,
        support_check=lambda smiles, c: True,
    )
    cand = result.candidates[0]
    assert cand.dropped_reason is None
    assert cand.retrieval_supported is True
    assert cand.cited_valid_ids == []  # the cited id was fabricated
    assert cand.accepted is True


# --------------------------------------------------------------------------- #
# Schema validation + single retry
# --------------------------------------------------------------------------- #
def test_single_retry_on_malformed_then_valid():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    llm = _llm(["this is not json", _VALID])
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=llm,
        verifier=_verifier({"CCO": "consistent"}, {"CCO": 0.7}),
        support_check=lambda smiles, c: True,
    )
    assert result.audit.retry_used is True
    assert len(result.audit.raw_completions) == 2
    assert len(llm.calls) == 2
    # The retry prompt carries the corrective suffix.
    assert "STRICT JSON" in llm.calls[1]["user"]
    assert [c.smiles for c in result.candidates] == ["CCO"]


def test_malformed_both_attempts_yields_no_candidates():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    llm = _llm(["nope", "still nope"])
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=llm,
        verifier=_verifier({}, {}),
        support_check=lambda smiles, c: True,
    )
    assert result.candidates == []
    assert result.audit.retry_used is True
    assert len(result.audit.raw_completions) == 2
    assert any("after retry" in w for w in result.audit.warnings)


def test_max_candidates_truncates_proposal():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])
    many = ",".join(
        '{"smiles": "CCO", "rationale": "r", "cited_analogue_ids": ["AID1"], "self_confidence": 0.5}'
        for _ in range(6)
    )
    completion = '{"candidates": [' + many + "]}"
    result = propose_structures(
        _spectrum(),
        ctx,
        max_candidates=2,
        llm=_llm([completion]),
        verifier=_verifier({"CCO": "consistent"}, {"CCO": 0.7}),
        support_check=lambda smiles, c: True,
    )
    assert len(result.candidates) == 2
    assert any("truncating" in w for w in result.audit.warnings)


# --------------------------------------------------------------------------- #
# Audit capture (Prompt 12)
# --------------------------------------------------------------------------- #
def test_audit_captures_prompt_completion_and_retrieved_ids():
    table = {
        "AID1": {"smiles": "CCO", "license": "CC0"},
        "AID2": {"smiles": "CCC", "license": "CC0"},
    }
    ctx = _context_with(table, [("AID1", 0.0), ("AID2", 1.0)])
    result = propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([_VALID]),
        verifier=_verifier({"CCO": "consistent"}, {"CCO": 0.7}),
        support_check=lambda smiles, c: True,
    )
    audit = result.audit
    assert audit.retrieved_ids == ["AID1", "AID2"]
    assert audit.model == "claude-opus-4-8"
    assert "AID1" in audit.user_prompt
    assert audit.raw_completions == [_VALID]
    assert audit.parsed_candidate_count == 1
    assert audit.accepted_candidate_count == 1
    d = audit.to_dict()
    assert d["retrieved_ids"] == ["AID1", "AID2"]
    assert d["system_prompt"]


def test_audit_recorder_hook_invoked():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])

    recorded = {}

    class FakeRecorder:
        def record(self, *, operation, user_id, input_obj, result_obj, parameters=None):
            recorded.update(
                operation=operation,
                user_id=user_id,
                input_obj=input_obj,
                result_obj=result_obj,
                parameters=parameters,
            )
            return SimpleNamespace(operation=operation)

    propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([_VALID]),
        verifier=_verifier({"CCO": "consistent"}, {"CCO": 0.7}),
        support_check=lambda smiles, c: True,
        audit_recorder=FakeRecorder(),
        audit_user_id="user-42",
    )
    assert recorded["operation"] == "spectrum.rag.propose"
    assert recorded["user_id"] == "user-42"
    assert recorded["input_obj"]["retrieved_ids"] == ["AID1"]
    assert recorded["parameters"]["model"] == "claude-opus-4-8"
    assert recorded["parameters"]["raw_completions"] == [_VALID]


def test_audit_recorder_without_user_id_is_skipped_with_warning():
    table = {"AID1": {"smiles": "CCO", "license": "CC0"}}
    ctx = _context_with(table, [("AID1", 0.0)])

    class BoomRecorder:
        def record(self, **kwargs):  # must NOT be called
            raise AssertionError("recorder called without a user id")

    result = propose_structures(
        _spectrum(),
        ctx,
        llm=_llm([_VALID]),
        verifier=_verifier({"CCO": "consistent"}, {"CCO": 0.7}),
        support_check=lambda smiles, c: True,
        audit_recorder=BoomRecorder(),
        audit_user_id=None,
    )
    assert any("without audit_user_id" in w for w in result.audit.warnings)


# --------------------------------------------------------------------------- #
# RetrievedAnalogue rendering
# --------------------------------------------------------------------------- #
def test_retrieved_analogue_prompt_lines_and_dict():
    a = RetrievedAnalogue(
        analogue_id="AID1",
        smiles="CCO",
        l2_distance=0.0,
        similarity=1.0,
        rank=0,
        license="CC-BY-SA",
        shift_summary="1.2, 3.7",
        multiplet_summary="t, q",
    )
    lines = a.to_prompt_lines()
    assert "AID1" in lines and "CCO" in lines and "CC-BY-SA" in lines
    assert "1.2, 3.7" in lines and "t, q" in lines
    assert a.to_dict()["similarity"] == 1.0
