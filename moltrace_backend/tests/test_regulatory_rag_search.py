"""Prompt 10 — RAG search over the regulatory corpus.

Builds a small corpus with the Prompt 20 pipeline (ICH M7, FDA nitrosamine guidance, EMA Q&A, WHO
TRS, ICH Q3C), then exercises retrieval (top-k, source filter, workflow relevance, citation
provenance, minimal excerpts), the deterministic extractive synthesis, the grounded LLM-synthesis
contract (via a fake LLMClient — no SDK needed), the AnthropicLLM adapter shape, and the FAQ
validation harness. Everything runs offline.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.data import (
    CorpusSource,
    EmaGuidanceAdapter,
    FdaGuidanceAdapter,
    IchGuidelineAdapter,
    WhoTechnicalReportAdapter,
    index,
    ingest,
)
from moltrace.regulatory.intelligence import (
    AnthropicLLM,
    RegulatoryFaqPair,
    RegulatorySearchResult,
    SynthesizedAnswer,
    VectorRetriever,
    evaluate_faq_pairs,
    regulatory_search,
    synthesize_answer,
    workflow_relevance,
)

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
            "The FDA CPCA assigns an N-nitrosamine to a potency "
            "category with an acceptable intake limit; NDSRI compounds "
            "are categorised by the carcinogenic potency approach.",
        ),
    ],
}
_EMA_QA = {
    "document_id": "EMA Nitrosamines Q&A",
    "title": "Questions and answers on nitrosamine impurities",
    "revision": "Rev 17",
    "effective_date": "2024-07-01",
    "url": "https://www.ema.europa.eu/en/documents/nitrosamines-qa.pdf",
    "text": "The EMA Q&A describes acceptable intakes for N-nitrosamine impurities and the CPCA.",
}
_WHO_TRS = {
    "document_id": "WHO TRS 1010 Annex 10",
    "title": "Stability testing of active pharmaceutical ingredients and finished products",
    "revision": "TRS 1010",
    "effective_date": "2018-01-01",
    "url": "https://www.who.int/publications/m/item/trs1010-annex10",
    "text": "Stability testing follows climate-zone storage conditions over the proposed shelf life.",
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
    chunks += index(ingest(EmaGuidanceAdapter([_EMA_QA])))
    chunks += index(ingest(WhoTechnicalReportAdapter([_WHO_TRS])))
    chunks += index(ingest(IchGuidelineAdapter([_ICH_Q3C])))
    return chunks


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def test_search_returns_relevant_chunk_with_full_provenance() -> None:
    res = regulatory_search("how is a mutagenic impurity TTC controlled?", corpus=_corpus())
    assert isinstance(res, RegulatorySearchResult) and len(res) >= 1
    top = res.results[0]
    assert top.chunk.source is CorpusSource.ICH_GUIDELINE
    assert top.chunk.document_id == "ICH M7(R2)"
    assert top.chunk.effective_date == "2023-04-03"
    assert top.chunk.url.startswith("https://database.ich.org/")
    # citation + minimal excerpt + workflow relevance
    assert "effective 2023-04-03" in top.citation() and top.chunk.url in top.citation()
    assert "ICH M7 mutagenic-impurity classifier" in top.workflow_relevance


def test_top_k_is_respected_and_must_be_positive() -> None:
    res = regulatory_search("nitrosamine acceptable intake", top_k=2, corpus=_corpus())
    assert len(res) <= 2
    with pytest.raises(ValueError):
        regulatory_search("x", top_k=0, corpus=_corpus())


def test_filter_source_restricts_results() -> None:
    corpus = _corpus()
    ich = regulatory_search("nitrosamine acceptable intake", filter_source="ICH", corpus=corpus)
    assert ich.results and all(r.chunk.source is CorpusSource.ICH_GUIDELINE for r in ich.results)
    who = regulatory_search("stability climate zone", filter_source="WHO", corpus=corpus)
    assert who.results and all(
        r.chunk.source is CorpusSource.WHO_TECHNICAL_REPORT for r in who.results
    )
    fda = regulatory_search("nitrosamine", filter_source="FDA", corpus=corpus)
    assert fda.results and all(r.chunk.source.value.startswith("fda") for r in fda.results)


def test_workflow_relevance_keyword_mapping() -> None:
    assert "FDA CPCA nitrosamine classifier" in workflow_relevance("an N-nitrosamine NDSRI")
    assert "ICH Q3C residual-solvent classifier" in workflow_relevance("a class 2 residual solvent")
    assert "ICH M7 mutagenic-impurity classifier" in workflow_relevance("genotoxic / mutagenic")
    assert workflow_relevance("the weather is nice") == ()


def test_internal_only_excerpt_is_minimal_and_attributed() -> None:
    long_text = "Acceptable intake guidance. " * 50  # long ICH (internal-only) body
    corpus = index(ingest(IchGuidelineAdapter([{**_ICH_M7, "text": long_text, "sections": []}])))
    res = regulatory_search("acceptable intake", corpus=corpus)
    top = res.results[0]
    assert top.chunk.redistributable is False  # ICH is internal-only
    assert len(top.excerpt()) <= 241 and top.excerpt().endswith("…")  # truncated, minimal
    assert top.as_dict()["redistributable"] is False and top.as_dict()["url"]


def test_lexical_retriever_is_deterministic() -> None:
    corpus = _corpus()
    a = [r.chunk.chunk_id for r in regulatory_search("residual solvent PDE", corpus=corpus)]
    b = [r.chunk.chunk_id for r in regulatory_search("residual solvent PDE", corpus=corpus)]
    assert a == b and a  # identical ordering across runs


# --------------------------------------------------------------------------- #
# Vector retriever (embeddings)
# --------------------------------------------------------------------------- #
def _toy_embed(text: str):
    low = text.lower()
    return [
        float(low.count("mutagenic") + low.count("ttc")),
        float(low.count("nitrosamine") + low.count("cpca")),
        float(low.count("solvent")),
    ]


def test_vector_retriever_ranks_by_embedding_similarity() -> None:
    # index with the toy embedder so chunks carry embeddings
    chunks = index(ingest(IchGuidelineAdapter([_ICH_M7])), embedder=_toy_embed)
    chunks += index(ingest(FdaGuidanceAdapter([_FDA_NITROSAMINE])), embedder=_toy_embed)
    chunks += index(ingest(IchGuidelineAdapter([_ICH_Q3C])), embedder=_toy_embed)
    res = regulatory_search(
        "nitrosamine cpca", corpus=chunks, retriever=VectorRetriever(embedder=_toy_embed)
    )
    assert res.results[0].chunk.source is CorpusSource.FDA_GUIDANCE  # nitrosamine doc ranks first


def test_vector_retriever_requires_an_embedder() -> None:
    with pytest.raises(ValueError, match="embedder"):
        VectorRetriever().search("q", _corpus())


# --------------------------------------------------------------------------- #
# Synthesis — extractive (no LLM)
# --------------------------------------------------------------------------- #
def test_extractive_synthesis_is_grounded_and_cited() -> None:
    res = regulatory_search("mutagenic impurity control", corpus=_corpus())
    ans = synthesize_answer("mutagenic impurity control", res)
    assert isinstance(ans, SynthesizedAnswer)
    assert ans.used_llm is False and ans.model is None
    assert ans.citations and all(c.startswith("[S") for c in ans.citations)
    assert ans.grounded_in == tuple(r.chunk.chunk_id for r in res.results)
    assert ans.human_review_required is True
    assert "deterministic calculator" in ans.answer.lower()


def test_synthesis_with_no_results_refuses_to_answer() -> None:
    empty = regulatory_search("zzzz-no-such-topic-qqqq", corpus=_corpus())
    ans = synthesize_answer("zzzz-no-such-topic-qqqq", empty)
    assert ans.citations == () and "no answer can be grounded" in ans.answer.lower()


# --------------------------------------------------------------------------- #
# Synthesis — LLM path (grounding contract verified with a fake client)
# --------------------------------------------------------------------------- #
class _FakeLLM:
    def __init__(self) -> None:
        self.system = None
        self.prompt = None
        self.model = None

    def complete(self, *, system, prompt, model, max_tokens=1024):
        self.system, self.prompt, self.model = system, prompt, model
        return "Mutagenic impurities are controlled to an acceptable intake [S1]."


def test_llm_synthesis_enforces_the_grounding_contract() -> None:
    res = regulatory_search("how is a mutagenic impurity controlled?", corpus=_corpus())
    fake = _FakeLLM()
    ans = synthesize_answer(
        "how is a mutagenic impurity controlled?", res, llm=fake, model="claude-sonnet-4-6"
    )
    assert ans.used_llm is True and ans.model == "claude-sonnet-4-6"
    assert "[S1]" in ans.answer
    # the system prompt forbids outside knowledge + numeric invention, requires citations
    assert "ONLY" in fake.system and "outside these excerpts" in fake.system
    assert "Cite every claim" in fake.system and "numeric limit" in fake.system
    assert "deterministic calculator" in fake.system
    # the retrieved excerpts + markers are in the user prompt
    assert "[S1]" in fake.prompt and "effective 2023-04-03" in fake.prompt


def test_anthropic_llm_adapter_uses_injected_client() -> None:
    class _Block:
        type = "text"
        text = "grounded answer [S1]"

    class _Resp:
        content = [_Block()]

    class _Messages:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return _Resp()

    class _Client:
        def __init__(self):
            self.messages = _Messages()

    client = _Client()
    llm = AnthropicLLM(client=client)
    out = llm.complete(system="S", prompt="P", model="claude-sonnet-4-6", max_tokens=512)
    assert out == "grounded answer [S1]"
    assert client.messages.kwargs["model"] == "claude-sonnet-4-6"
    assert client.messages.kwargs["system"] == "S"
    assert client.messages.kwargs["messages"][0]["content"] == "P"


def test_anthropic_llm_without_sdk_raises_with_install_hint() -> None:
    pytest.importorskip  # noqa: B018 - just referencing
    try:
        import anthropic  # noqa: F401
    except ModuleNotFoundError:
        with pytest.raises(ModuleNotFoundError, match=r"moltrace\[rag\]"):
            AnthropicLLM().complete(system="s", prompt="p", model="claude-sonnet-4-6")
    else:
        pytest.skip("anthropic SDK installed; the no-SDK path is not exercised")


# --------------------------------------------------------------------------- #
# FAQ validation harness
# --------------------------------------------------------------------------- #
def test_faq_harness_validates_grounding() -> None:
    pairs = [
        RegulatoryFaqPair(
            "What is the acceptable intake basis for a mutagenic impurity?",
            expected_source=CorpusSource.ICH_GUIDELINE,
            expected_keywords=("ttc",),
            expected_document_id="ICH M7(R2)",
        ),
        RegulatoryFaqPair(
            "How are N-nitrosamine acceptable intakes assigned?",
            expected_source=CorpusSource.FDA_GUIDANCE,
            expected_keywords=("cpca",),
        ),
    ]
    report = evaluate_faq_pairs(pairs, corpus=_corpus())
    assert report.ok, report.failures()
    assert report.n == 2 and report.n_passed == 2


def test_faq_harness_flags_wrong_grounding() -> None:
    bad = [
        RegulatoryFaqPair(
            "residual solvent limits",
            expected_source=CorpusSource.EMA_GUIDANCE,  # wrong source for this query
            expected_keywords=("pde",),
        )
    ]
    report = evaluate_faq_pairs(bad, corpus=_corpus())
    assert not report.ok and report.failures()


def test_faq_harness_grounds_on_expected_document_not_just_source() -> None:
    # ICH M7 and ICH Q3C are BOTH CorpusSource.ICH_GUIDELINE. A query that ranks Q3C above M7
    # while still surfacing M7 in top-k must still ground an M7 pair on the M7 chunk — not on the
    # higher-ranked Q3C sibling (which lacks the M7 keyword). Regression for the source-only bug.
    query = "residual solvent class pde limited avoided mutagenic"
    corpus = _corpus()
    res = regulatory_search(query, top_k=5, corpus=corpus)
    docs = [r.chunk.document_id for r in res.results]
    assert "ICH Q3C(R8)" in docs and "ICH M7(R2)" in docs  # both ICH docs retrieved
    assert docs.index("ICH Q3C(R8)") < docs.index("ICH M7(R2)")  # sibling outranks the expected doc
    pair = RegulatoryFaqPair(
        query,
        expected_source=CorpusSource.ICH_GUIDELINE,
        expected_keywords=("ttc",),  # present only in the M7 chunk, not the top-ranked Q3C chunk
        expected_document_id="ICH M7(R2)",
    )
    report = evaluate_faq_pairs([pair], top_k=5, corpus=corpus)
    assert report.ok, report.failures()


def test_faq_harness_reports_missing_expected_document() -> None:
    # expected_document_id not in top-k -> clear document-level failure detail (not a source miss).
    pair = RegulatoryFaqPair(
        "mutagenic impurity TTC",
        expected_source=CorpusSource.ICH_GUIDELINE,
        expected_document_id="ICH NONEXISTENT",
    )
    report = evaluate_faq_pairs([pair], corpus=_corpus())
    assert not report.ok
    assert any("ICH NONEXISTENT" in f.detail for f in report.failures())


# --------------------------------------------------------------------------- #
# workflow_relevance — OOS / Q6A substring-collision guard
# --------------------------------------------------------------------------- #
def test_oos_text_does_not_overmap_to_q6a_specification() -> None:
    for text in ("an out-of-specification (OOS) result", "an out of specification result"):
        rel = workflow_relevance(text)
        assert "FDA OOS investigation engine" in rel
        assert "ICH Q6A specification builder" not in rel  # 'specification' substring must not leak


def test_bare_specification_still_maps_to_q6a() -> None:
    rel = workflow_relevance("the drug substance specification and acceptance criteria")
    assert "ICH Q6A specification builder" in rel
    assert "FDA OOS investigation engine" not in rel


# --------------------------------------------------------------------------- #
# Configurable chunking (chunk size / overlap)
# --------------------------------------------------------------------------- #
def test_chunk_size_and_overlap_window_large_bodies() -> None:
    body = " ".join(f"w{i}" for i in range(100))  # 100-token section
    doc = {**_ICH_M7, "sections": [("Big Section", body)]}
    whole = index(ingest(IchGuidelineAdapter([doc])))
    assert len(whole) == 1  # default: one chunk per section (no regression)

    windowed = index(ingest(IchGuidelineAdapter([doc])), chunk_size=40, chunk_overlap=10)
    assert len(windowed) == 3  # ceil over step=30: tokens 0-39, 30-69, 60-99
    assert all(len(c.text.split()) <= 40 for c in windowed)
    assert [c.section for c in windowed] == ["Big Section#1", "Big Section#2", "Big Section#3"]
    # overlap: last 10 tokens of window 1 == first 10 tokens of window 2
    assert windowed[0].text.split()[-10:] == windowed[1].text.split()[:10]
    # distinct, citable chunk ids
    assert len({c.chunk_id for c in windowed}) == 3


def test_chunk_params_are_validated() -> None:
    doc = {**_ICH_M7, "sections": [("S", "a b c d e")]}
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        index(ingest(IchGuidelineAdapter([doc])), chunk_size=0)
    with pytest.raises(ValueError, match="chunk_overlap"):
        index(ingest(IchGuidelineAdapter([doc])), chunk_size=10, chunk_overlap=10)


# --------------------------------------------------------------------------- #
# Post-hoc grounding verification on the LLM path
# --------------------------------------------------------------------------- #
class _ScriptedLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, *, system, prompt, model, max_tokens=1024):
        return self._text


def test_llm_answer_with_grounded_text_has_no_warnings() -> None:
    res = regulatory_search("mutagenic impurity control", corpus=_corpus())
    llm = _ScriptedLLM("Mutagenic impurities are held to an acceptable intake [S1].")
    ans = synthesize_answer("mutagenic impurity control", res, llm=llm)
    assert ans.grounding_warnings == ()
    assert ans.as_dict()["grounding_warnings"] == []


def test_llm_fabricated_regulated_number_is_flagged() -> None:
    res = regulatory_search("mutagenic impurity control", corpus=_corpus())
    # 1.5 µg/day appears in no excerpt -> the post-hoc check must flag it and defer to the calculator
    llm = _ScriptedLLM("The acceptable intake is 1.5 µg/day [S1].")
    ans = synthesize_answer("mutagenic impurity control", res, llm=llm)
    assert ans.grounding_warnings
    joined = " ".join(ans.grounding_warnings)
    assert "1.5 µg/day" in joined and "deterministic calculator" in joined


def test_llm_invalid_citation_marker_is_flagged() -> None:
    res = regulatory_search("mutagenic impurity control", top_k=2, corpus=_corpus())
    llm = _ScriptedLLM("See [S9] and [S1] for the details.")
    ans = synthesize_answer("mutagenic impurity control", res, llm=llm)
    assert any("[S9]" in w and "invalid citation" in w for w in ans.grounding_warnings)
