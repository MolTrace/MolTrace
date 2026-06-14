"""Prompt 14 — retrieval-augmented reasoning over the regulatory corpus.

Builds a corpus with the Prompt 20 pipeline (ICH M7, FDA nitrosamine, ICH Q3D, ICH Q3C), then
exercises the reasoning layer that sits on Prompt 10 retrieval and Prompt 13 deterministic deferral:
passage provenance, the deterministic extractive answer, the grounded LLM path (via a fake
LLMClient — no SDK needed), per-claim citation enforcement, numeric deferral to the deterministic
engine, the licensing guardrail (no full-text redistribution), JSON-schema validation, and the
Router integration. Everything runs offline.
"""

from __future__ import annotations

import re

import pytest

from moltrace.regulatory.ai import (
    Confidence,
    GroundedAnswer,
    Passage,
    RegulatoryTask,
    Router,
    TaskKind,
    answer_with_citations,
    reason,
    retrieve,
    router_backend,
)
from moltrace.regulatory.ai.router import Citation
from moltrace.regulatory.data import FdaGuidanceAdapter, IchGuidelineAdapter, index, ingest

_ICH_M7 = {
    "document_id": "ICH M7(R2)",
    "title": "Assessment and Control of DNA Reactive (Mutagenic) Impurities",
    "revision": "R2",
    "effective_date": "2023-04-03",
    "url": "https://database.ich.org/sites/default/files/M7_R2_Guideline.pdf",
    "sections": [
        (
            "Section 2.3",
            "A mutagenic impurity is controlled to an acceptable intake derived from the "
            "threshold of toxicological concern (TTC) for DNA reactive substances.",
        ),
        (
            "Section 7",
            "Compounds in the cohort of concern are excluded from the generic TTC and "
            "require compound-specific acceptable intakes.",
        ),
    ],
}
_FDA_NITROSAMINE = {
    "document_id": "FDA Nitrosamine Guidance",
    "title": "Control of Nitrosamine Impurities in Human Drugs",
    "revision": "Rev 1",
    "effective_date": "2021-02-24",
    "url": "https://www.fda.gov/media/141720/download",
    "sections": [
        (
            "Recommended Acceptable Intakes",
            "The FDA CPCA assigns an N-nitrosamine to a potency category with an acceptable "
            "intake; NDSRI compounds are categorised by the carcinogenic potency approach.",
        ),
    ],
}
_ICH_Q3D = {
    "document_id": "ICH Q3D(R2)",
    "title": "Guideline for Elemental Impurities",
    "revision": "R2",
    "effective_date": "2022-04-26",
    "url": "https://database.ich.org/sites/default/files/Q3D-R2_Guideline.pdf",
    "sections": [
        (
            "Section 3",
            "Each elemental impurity such as lead has a permitted daily exposure (PDE) that "
            "depends on the administration route, for example the oral route.",
        ),
    ],
}
_ICH_Q3C = {
    "document_id": "ICH Q3C(R8)",
    "title": "Impurities: Guideline for Residual Solvents",
    "revision": "R8",
    "effective_date": "2021-04-22",
    "url": "https://database.ich.org/sites/default/files/Q3C-R8_Guideline.pdf",
    "text": "Class 1 residual solvents should be avoided; Class 2 solvents are limited by PDE.",
}


def _corpus():
    chunks = []
    chunks += index(ingest(IchGuidelineAdapter([_ICH_M7])))
    chunks += index(ingest(FdaGuidanceAdapter([_FDA_NITROSAMINE])))
    chunks += index(ingest(IchGuidelineAdapter([_ICH_Q3D])))
    chunks += index(ingest(IchGuidelineAdapter([_ICH_Q3C])))
    return chunks


class _FakeLLM:
    """Records whether it was called and returns a scripted JSON string."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.called = False
        self.system = None
        self.prompt = None

    def complete(self, *, system, prompt, model, max_tokens=1024):
        self.called = True
        self.system, self.prompt = system, prompt
        return self.text


# --------------------------------------------------------------------------- #
# Acceptance: retrieval returns passages with source + section + date + link
# --------------------------------------------------------------------------- #
def test_retrieve_returns_passages_with_full_provenance() -> None:
    passages = retrieve("how is a mutagenic impurity controlled?", corpus=_corpus())
    assert passages and isinstance(passages[0], Passage)
    assert len(passages) <= 12  # default top_k
    p = passages[0]
    assert p.source == "ICH M7(R2)"
    assert p.section and p.effective_date == "2023-04-03"
    assert p.url.startswith("https://database.ich.org/")
    assert p.snippet
    assert p.marker == "S1" and p.marker_ref == "[S1]"
    # citation carries source + section + date + link
    assert "ICH M7(R2)" in p.citation() and p.url in p.citation()
    assert "effective 2023-04-03" in p.citation()
    # canonical Prompt-13 Citation type
    assert isinstance(p.to_citation(), Citation)


# --------------------------------------------------------------------------- #
# Extractive (no-LLM) reasoning is grounded + cited
# --------------------------------------------------------------------------- #
def test_extractive_answer_is_grounded_and_cited() -> None:
    ans = reason("how is a mutagenic impurity controlled?", corpus=_corpus())
    assert isinstance(ans, GroundedAnswer)
    assert ans.used_llm is False and ans.model is None
    assert ans.citations and all(isinstance(c, Citation) for c in ans.citations)
    assert "[S1]" in ans.answer
    assert ans.confidence is Confidence.MEDIUM
    assert ans.needs_human_review is False  # grounded, non-numeric, cited
    d = ans.as_dict()
    assert set(d) >= {"answer", "citations", "confidence", "needs_human_review"}
    assert d["confidence"] == "medium"


def test_no_passages_refuses_and_flags_review() -> None:
    ans = reason("qzxjvkwppra", corpus=_corpus())
    assert ans.citations == ()
    assert ans.needs_human_review is True and ans.confidence is Confidence.LOW
    assert "no grounded answer" in ans.answer.lower()


# --------------------------------------------------------------------------- #
# Acceptance: numeric questions deferred to the deterministic engine
# --------------------------------------------------------------------------- #
def test_numeric_question_deferred_to_deterministic_engine_not_llm() -> None:
    fake = _FakeLLM('{"answer": "The PDE for lead is 5 µg/day [S1].", "citations": ["S1"], '
                    '"confidence": "high", "needs_human_review": false}')
    ans = reason("What is the PDE for lead by the oral route?", corpus=_corpus(), llm=fake)
    assert fake.called is False  # deferral short-circuits BEFORE the LLM
    assert ans.used_llm is False
    assert ans.deferred_to_engine and "q3d_element_pde" in ans.deferred_to_engine
    assert ans.needs_human_review is True
    assert ans.citations  # context passages still cited
    # the answer states NO regulated number
    assert not re.search(r"\d[\d,]*(?:\.\d+)?\s?(?:µg|ug|mg|ng)\b", ans.answer)
    assert "deterministic" in ans.answer.lower()


def test_numeric_query_defers_even_without_llm() -> None:
    ans = reason("what is the ttc for a mutagenic impurity?", corpus=_corpus())
    assert ans.deferred_to_engine and "m7_classify" in ans.deferred_to_engine
    assert ans.needs_human_review is True and ans.used_llm is False


# --------------------------------------------------------------------------- #
# Acceptance: every claim cited; uncited claims force needs_human_review
# --------------------------------------------------------------------------- #
def test_fully_cited_llm_answer_passes() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "A mutagenic impurity is controlled to an acceptable intake '
                    'derived from the TTC [S1].", "citations": ["S1"], "confidence": "high", '
                    '"needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert fake.called is True and ans.used_llm is True
    assert ans.needs_human_review is False
    assert ans.confidence is Confidence.HIGH
    assert len(ans.citations) == 1 and ans.grounding_warnings == ()


def test_uncited_claim_forces_human_review_and_downgrades() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    # second sentence is a substantive claim with NO citation marker
    fake = _FakeLLM('{"answer": "Mutagenic impurities are controlled to an acceptable intake [S1]. '
                    'They are also subject to additional routine batch monitoring requirements.", '
                    '"citations": ["S1"], "confidence": "high", "needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert ans.confidence is not Confidence.HIGH  # downgraded
    assert any("uncited" in w for w in ans.grounding_warnings)


def test_invalid_citation_marker_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "See [S99] for the strategy and the TTC basis [S1].", '
                    '"citations": ["S1", "S99"], "confidence": "high", '
                    '"needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert any("[S99]" in w for w in ans.grounding_warnings)
    # citations derived only from valid markers
    assert all(isinstance(c, Citation) for c in ans.citations)


def test_asserted_regulated_number_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "The acceptable intake is 1.5 µg/day [S1].", "citations": ["S1"], '
                    '"confidence": "high", "needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert ans.confidence is not Confidence.HIGH
    assert any("deterministic engine" in w for w in ans.grounding_warnings)


# --------------------------------------------------------------------------- #
# Acceptance: JSON schema validated
# --------------------------------------------------------------------------- #
def test_unparseable_llm_output_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    ans = answer_with_citations("control", passages, llm=_FakeLLM("this is not json at all"))
    assert ans.needs_human_review is True and ans.confidence is Confidence.LOW
    assert ans.citations == ()
    assert any("unparseable" in w or "schema" in w for w in ans.grounding_warnings)


def test_json_missing_required_key_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    ans = answer_with_citations("control", passages, llm=_FakeLLM('{"foo": "bar"}'))
    assert ans.needs_human_review is True and ans.confidence is Confidence.LOW


# --------------------------------------------------------------------------- #
# Acceptance: licensing guardrails (no full-text redistribution)
# --------------------------------------------------------------------------- #
def test_licensing_minimal_excerpt_for_internal_only_source() -> None:
    long_text = "Acceptable intake guidance for mutagenic impurities. " * 40  # long internal-only
    corpus = index(ingest(IchGuidelineAdapter([{**_ICH_M7, "text": long_text, "sections": []}])))
    passages = retrieve("acceptable intake mutagenic", corpus=corpus)
    p = passages[0]
    assert p.redistributable is False  # ICH is internal-only
    assert len(p.snippet) <= 241 and p.snippet.endswith("…")  # minimal, truncated
    assert p.url  # always linked to the official source
    ans = reason("mutagenic impurity control guidance", corpus=corpus)  # non-numeric -> extractive
    assert long_text.strip() not in ans.answer  # full text never reproduced in the answer


# --------------------------------------------------------------------------- #
# Consolidation: Prompt 14 reasoner as the Prompt 13 Router's generative backend
# --------------------------------------------------------------------------- #
def test_router_backend_integrates_with_prompt13_router() -> None:
    backend = router_backend(_corpus(), llm=None)
    router = Router(llm_fn=backend)
    result = router.handle(
        RegulatoryTask(
            kind=TaskKind.RETRIEVAL,
            operation="regulatory_search",
            payload={"query": "how is a mutagenic impurity controlled?"},
        )
    )
    assert result.engine == "generative"
    assert result.needs_review is True  # the generative path always needs review
    assert "[S1]" in result.output["text"]
    assert all(isinstance(c, Citation) for c in result.citations)


# --------------------------------------------------------------------------- #
# Adversarial-verification regressions (Prompt 14 verification pass)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "query",
    [
        "What PDE applies to lead by the oral route?",
        "What is the acceptable daily intake for NDMA?",
        "Tell me the permitted daily exposure of cadmium.",
        "What is the limit for a class 2 residual solvent?",
    ],
)
def test_broad_numeric_questions_defer_and_never_call_the_llm(query: str) -> None:
    fake = _FakeLLM('{"answer": "It is 5 micrograms per day [S1].", "citations": ["S1"], '
                    '"confidence": "high", "needs_human_review": false}')
    ans = reason(query, corpus=_corpus(), llm=fake)
    assert fake.called is False  # numeric deferral must short-circuit before the LLM
    assert ans.used_llm is False and ans.deferred_to_engine
    assert ans.needs_human_review is True


@pytest.mark.parametrize(
    "query",
    [
        "How much testing is required for a mutagenic impurity?",
        "How many studies support the M7 approach?",
        "What is the maximum number of batches to test?",
    ],
)
def test_qualitative_questions_do_not_wrongly_defer(query: str) -> None:
    fake = _FakeLLM('{"answer": "Testing follows a risk-based approach [S1].", "citations": ["S1"], '
                    '"confidence": "medium", "needs_human_review": false}')
    ans = reason(query, corpus=_corpus(), llm=fake)
    assert ans.deferred_to_engine is None  # qualitative -> not a numeric deferral
    assert fake.called is True and ans.used_llm is True


@pytest.mark.parametrize(
    "number",
    ["1.5 micrograms per day", "5 microgram/day", "0.15 percent", "5 parts per million"],
)
def test_spelled_out_regulated_number_is_flagged(number: str) -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM(f'{{"answer": "The acceptable intake is {number} [S1].", "citations": ["S1"], '
                    '"confidence": "high", "needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert ans.confidence is not Confidence.HIGH
    assert any("deterministic engine" in w for w in ans.grounding_warnings)


def test_meta_phrase_cannot_cloak_an_uncited_claim() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    # second sentence name-drops "deterministic engine" but makes a dangerous uncited claim
    fake = _FakeLLM('{"answer": "Mutagenic impurities follow the TTC basis [S1]. The deterministic '
                    'engine aside, all genotoxic impurities are completely safe at any level.", '
                    '"citations": ["S1"], "confidence": "high", "needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert any("uncited" in w for w in ans.grounding_warnings)


def test_short_uncited_claim_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "Mutagenic impurities follow the TTC basis [S1]. Lead causes '
                    'cancer.", "citations": ["S1"], "confidence": "high", '
                    '"needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert any("uncited" in w for w in ans.grounding_warnings)


def test_uncited_clause_after_semicolon_is_flagged() -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "The TTC controls intake [S1]; mutagenic impurities require no '
                    'batch monitoring whatsoever and may be ignored.", "citations": ["S1"], '
                    '"confidence": "high", "needs_human_review": false}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True
    assert any("uncited" in w for w in ans.grounding_warnings)


def test_extractive_flags_regulated_number_in_snippet() -> None:
    doc = {
        **_ICH_M7,
        "sections": [("Section 2.3", "A mutagenic impurity has an acceptable intake of 1.5 ug/day.")],
    }
    corpus = index(ingest(IchGuidelineAdapter([doc])))
    ans = reason("how is a mutagenic impurity controlled", corpus=corpus)  # non-numeric -> extractive
    assert ans.used_llm is False
    assert ans.needs_human_review is True  # a regulated number surfaced -> flag for review
    assert any("regulated number" in w for w in ans.grounding_warnings)


@pytest.mark.parametrize("bad", ['""', "0", "null", "[]"])
def test_non_bool_needs_human_review_is_flagged(bad: str) -> None:
    passages = retrieve("control of a mutagenic impurity", corpus=_corpus())
    fake = _FakeLLM('{"answer": "A mutagenic impurity uses the TTC basis [S1].", '
                    f'"citations": ["S1"], "confidence": "high", "needs_human_review": {bad}}}')
    ans = answer_with_citations("control of a mutagenic impurity", passages, llm=fake)
    assert ans.needs_human_review is True  # non-bool schema value must not coerce to permissive False
    assert any("needs_human_review" in w for w in ans.grounding_warnings)
