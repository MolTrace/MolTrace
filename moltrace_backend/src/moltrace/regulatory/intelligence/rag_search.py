"""RAG search over the regulatory guidance corpus (Prompt 10).

Retrieve the most relevant guidance chunks for a query and synthesise an answer grounded ONLY in
those chunks, with explicit citations. Built on the Prompt 20 corpus pipeline: the retriever runs
over :class:`~moltrace.regulatory.data.IndexChunk` records, so every result carries its source
document, section, effective date, official-source url, and licence.

* :func:`regulatory_search` — top-k retrieval with optional ``filter_source`` ('ICH' / 'FDA' /
  'EMA' / 'WHO'); each hit is annotated with the MolTrace calculator/module it maps to and a
  minimal, attributed excerpt (verbatim text is kept short; a citation + link is always present).
* :func:`synthesize_answer` — composes an answer from the retrieved chunks. The native path is
  extractive (no LLM); supplying an :class:`LLMClient` (e.g. :class:`AnthropicLLM`, Claude
  ``claude-sonnet-4-6``) produces an LLM synthesis whose system prompt forbids any knowledge outside
  the retrieved chunks and requires explicit citations. Any specific numeric limit is deferred to
  the deterministic calculators — the LLM must not state a regulated number not present verbatim in
  the excerpts.
* :func:`evaluate_faq_pairs` — the validation harness: run a set of (question, expected source,
  expected keywords) pairs and check retrieval + synthesis cite the right guidance.

Licences are honoured: ICH/EMA/WHO chunks are internal-only, excerpted minimally, and always cited.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from moltrace.regulatory.data import CorpusSource, IndexChunk

__all__ = [
    "AnthropicLLM",
    "FaqEvalReport",
    "LLMClient",
    "LexicalRetriever",
    "RegulatoryFaqPair",
    "RegulatorySearchResult",
    "RetrievedChunk",
    "Retriever",
    "SynthesizedAnswer",
    "VectorRetriever",
    "evaluate_faq_pairs",
    "regulatory_search",
    "synthesize_answer",
    "workflow_relevance",
]

_DEFAULT_MODEL = "claude-sonnet-4-6"  # current Sonnet; the prompt's dated id is deprecated
_MAX_EXCERPT_CHARS = 240  # keep verbatim quotes minimal (esp. for internal-only sources)

_RAG_DISCLAIMER = (
    "Decision-support only. This answer is generated from retrieved regulatory excerpts and "
    "must be verified against the cited official sources. Specific numeric limits/thresholds "
    "must be computed by MolTrace's deterministic calculators, not taken from this synthesis."
)

# The grounding contract handed to any LLM synthesiser.
_SYNTHESIS_SYSTEM = (
    "You are a regulatory-affairs assistant. Answer the question using ONLY the numbered "
    "regulatory excerpts provided below. Do not use any knowledge outside these excerpts. "
    "Cite every claim with its excerpt marker, e.g. [S1]. If the excerpts do not contain the "
    "answer, say so explicitly and do not guess. Do NOT state any specific numeric limit, "
    "threshold, PDE, TTC, or acceptable intake unless it appears verbatim in an excerpt — "
    "instead, direct the reader to MolTrace's deterministic calculator for that value. Keep "
    "verbatim quotes minimal; prefer a short summary plus the citation."
)


# --------------------------------------------------------------------------- #
# filter_source ('ICH'/'FDA'/'EMA'/'WHO') -> CorpusSource values
# --------------------------------------------------------------------------- #
_SOURCE_FILTER: dict[str, tuple[str, ...]] = {
    "FDA": (CorpusSource.FDA_GUIDANCE.value, CorpusSource.FDA_NDSRI.value),
    "ICH": (CorpusSource.ICH_GUIDELINE.value,),
    "EMA": (CorpusSource.EMA_GUIDANCE.value,),
    "WHO": (CorpusSource.WHO_TECHNICAL_REPORT.value,),
}


def _matches_filter(chunk: IndexChunk, filter_source: str | None) -> bool:
    if not filter_source:
        return True
    key = filter_source.strip().upper()
    allowed = _SOURCE_FILTER.get(key)
    if allowed is not None:
        return chunk.source.value in allowed
    # Fall back to a prefix match so an unmapped abbreviation still behaves sensibly.
    return chunk.source.value.startswith(filter_source.strip().lower())


# --------------------------------------------------------------------------- #
# MolTrace workflow relevance — which calculator/module a chunk maps to
# --------------------------------------------------------------------------- #
_WORKFLOW_RELEVANCE: tuple[tuple[tuple[str, ...], str], ...] = (
    (("nitrosamine", "ndsri", "cpca", "cohort of concern"), "FDA CPCA nitrosamine classifier"),
    (
        ("mutagenic", "genotoxic", "dna reactive", "ttc", "m7"),
        "ICH M7 mutagenic-impurity classifier",
    ),
    (
        ("residual solvent", "class 1 solvent", "class 2 solvent", "q3c"),
        "ICH Q3C residual-solvent classifier",
    ),
    (
        ("elemental impurit", "heavy metal", "elemental pde", "q3d"),
        "ICH Q3D elemental-impurity PDEs",
    ),
    (("specification", "acceptance criteri", "q6a"), "ICH Q6A specification builder"),
    (
        ("stability", "shelf life", "shelf-life", "climate zone", "q1a"),
        "ICH Q1A stability protocol generator",
    ),
    # Matched against OOS-normalised text (see workflow_relevance) so "out-of-specification" does
    # not also trip the Q6A "specification" keyword above.
    (("oos-marker", "oos"), "FDA OOS investigation engine"),
    (("control chart", "process capability", "cpk", "spc"), "SPC / process-capability dashboard"),
    (
        (
            "reporting threshold",
            "identification threshold",
            "qualification threshold",
            "q3a",
            "q3b",
        ),
        "ICH Q3A/B threshold calculator",
    ),
)


def workflow_relevance(text: str) -> tuple[str, ...]:
    """Return the MolTrace calculators/modules a guidance excerpt is relevant to."""

    low = text.lower()
    # "out-of-specification" contains the substring "specification"; collapse the OOS phrases to a
    # dedicated marker so OOS guidance maps to the OOS engine without also tripping the Q6A
    # "specification" keyword. Bare "oos" still matches via the OOS keyword tuple.
    scan = low.replace("out-of-specification", " oos-marker ").replace(
        "out of specification", " oos-marker "
    )
    hits: list[str] = []
    for keywords, module in _WORKFLOW_RELEVANCE:
        if any(k in scan for k in keywords) and module not in hits:
            hits.append(module)
    return tuple(hits)


# --------------------------------------------------------------------------- #
# Tokenisation + TF-IDF (native lexical retriever)
# --------------------------------------------------------------------------- #
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _tf(tokens: Sequence[str]) -> dict[str, float]:
    counts: dict[str, float] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0.0) + 1.0
    return counts


# --------------------------------------------------------------------------- #
# Retrievers
# --------------------------------------------------------------------------- #
@runtime_checkable
class Retriever(Protocol):
    """Scores a corpus of chunks against a query, returning (chunk, score) pairs, best first."""

    def search(
        self, query: str, chunks: Sequence[IndexChunk]
    ) -> list[tuple[IndexChunk, float]]: ...


class LexicalRetriever:
    """Zero-dependency TF-IDF cosine retriever. Deterministic; the default backend."""

    def search(self, query: str, chunks: Sequence[IndexChunk]) -> list[tuple[IndexChunk, float]]:
        if not chunks:
            return []
        docs_tokens = [_tokens(c.text) for c in chunks]
        n = len(chunks)
        doc_freq: dict[str, int] = {}
        for toks in docs_tokens:
            for tok in set(toks):
                doc_freq[tok] = doc_freq.get(tok, 0) + 1
        idf = {tok: math.log((n + 1) / (df + 1)) + 1.0 for tok, df in doc_freq.items()}

        def vec(tokens: Sequence[str]) -> dict[str, float]:
            return {
                tok: tf * idf.get(tok, math.log(n + 1) + 1.0) for tok, tf in _tf(tokens).items()
            }

        q_vec = vec(_tokens(query))
        q_norm = math.sqrt(sum(w * w for w in q_vec.values())) or 1.0
        scored: list[tuple[IndexChunk, float]] = []
        for chunk, toks in zip(chunks, docs_tokens, strict=True):
            d_vec = vec(toks)
            d_norm = math.sqrt(sum(w * w for w in d_vec.values())) or 1.0
            dot = sum(q_vec.get(tok, 0.0) * w for tok, w in d_vec.items())
            scored.append((chunk, dot / (q_norm * d_norm)))
        # Sort by score, tie-break by chunk_id for determinism.
        scored.sort(key=lambda cs: (-cs[1], cs[0].chunk_id))
        return scored


class VectorRetriever:
    """Cosine retriever over embeddings. Uses each chunk's stored embedding, or an injectable
    ``embedder`` (a callable ``str -> Sequence[float]``, e.g. OpenAI text-embedding-3-small)."""

    def __init__(self, embedder=None) -> None:
        self._embedder = embedder

    @staticmethod
    def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)

    def search(self, query: str, chunks: Sequence[IndexChunk]) -> list[tuple[IndexChunk, float]]:
        if self._embedder is None:
            raise ValueError(
                "VectorRetriever needs an embedder, or pre-embedded chunks via a custom flow; "
                "install the 'rag' extra and pass an embedder (e.g. OpenAI text-embedding-3-small)"
            )
        q = list(self._embedder(query))
        scored = [(c, self._cosine(q, c.embedding)) for c in chunks if c.embedding is not None]
        scored.sort(key=lambda cs: (-cs[1], cs[0].chunk_id))
        return scored


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrievedChunk:
    """One retrieved chunk with its score, citation, minimal excerpt, and workflow relevance."""

    rank: int
    score: float
    chunk: IndexChunk
    workflow_relevance: tuple[str, ...]

    @property
    def source_document(self) -> str:
        return f"{self.chunk.document_id}, {self.chunk.section}"

    def excerpt(self, max_chars: int = _MAX_EXCERPT_CHARS) -> str:
        """A short attributed excerpt — kept minimal, especially for internal-only sources."""

        text = self.chunk.text.strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"

    def citation(self) -> str:
        return self.chunk.citation()

    def as_dict(self) -> dict:
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "source_document": self.source_document,
            "section": self.chunk.section,
            "effective_date": self.chunk.effective_date,
            "url": self.chunk.url,
            "source": self.chunk.source.value,
            "redistributable": self.chunk.redistributable,
            "excerpt": self.excerpt(),
            "citation": self.citation(),
            "workflow_relevance": list(self.workflow_relevance),
        }


@dataclass(frozen=True)
class RegulatorySearchResult:
    """The top-k retrieval result for a query."""

    query: str
    top_k: int
    filter_source: str | None
    results: tuple[RetrievedChunk, ...]

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "top_k": self.top_k,
            "filter_source": self.filter_source,
            "results": [r.as_dict() for r in self.results],
        }


def regulatory_search(
    query: str,
    top_k: int = 5,
    filter_source: str | None = None,
    *,
    corpus: Sequence[IndexChunk],
    retriever: Retriever | None = None,
) -> RegulatorySearchResult:
    """Return the ``top_k`` most relevant regulatory chunks for *query*.

    ``corpus`` is the indexed chunk set from the Prompt 20 pipeline (``data.index(...)``).
    ``filter_source`` restricts to 'ICH' / 'FDA' / 'EMA' / 'WHO'. ``retriever`` defaults to the
    zero-dependency :class:`LexicalRetriever`. Each result carries its source document/section,
    effective date, official-source url, a minimal attributed excerpt, and the MolTrace
    calculator/module it maps to.
    """

    if top_k < 1:
        raise ValueError("top_k must be >= 1")
    candidates = [c for c in corpus if _matches_filter(c, filter_source)]
    backend = retriever or LexicalRetriever()
    scored = backend.search(query, candidates)
    results = tuple(
        RetrievedChunk(
            rank=i + 1,
            score=score,
            chunk=chunk,
            workflow_relevance=workflow_relevance(chunk.text),
        )
        for i, (chunk, score) in enumerate(scored[:top_k])
        if score > 0.0
    )
    return RegulatorySearchResult(
        query=query, top_k=top_k, filter_source=filter_source, results=results
    )


# --------------------------------------------------------------------------- #
# LLM synthesis (grounded, cited)
# --------------------------------------------------------------------------- #
@runtime_checkable
class LLMClient(Protocol):
    """A minimal LLM completion interface so the synthesiser is backend-agnostic + testable."""

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> str: ...


class AnthropicLLM:
    """Claude synthesis via the Anthropic SDK (optional ``rag`` extra). Defaults to Sonnet 4.6.

    Lazy-imports ``anthropic`` so the module loads without the dependency; the deterministic
    extractive path in :func:`synthesize_answer` runs with no LLM at all.
    """

    def __init__(self, client=None, *, model: str = _DEFAULT_MODEL) -> None:
        self._client = client
        self.model = model

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised via the extra
            raise ModuleNotFoundError(
                "AnthropicLLM requires the anthropic SDK; install the optional extra: "
                "pip install 'moltrace[rag]'"
            ) from exc
        self._client = anthropic.Anthropic()
        return self._client

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 1024) -> str:
        client = self._ensure_client()
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


@dataclass(frozen=True)
class SynthesizedAnswer:
    """An answer grounded in the retrieved chunks, with explicit citations."""

    query: str
    answer: str
    citations: tuple[str, ...]
    used_llm: bool
    model: str | None
    grounded_in: tuple[str, ...]  # chunk_ids the answer is grounded in
    disclaimer: str = _RAG_DISCLAIMER
    human_review_required: bool = True
    # Programmatic grounding-violation warnings from the post-hoc check on an LLM answer:
    # invalid [S#] citation markers and regulated numbers not present verbatim in the excerpts.
    # Empty on the deterministic extractive path (grounded by construction).
    grounding_warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "answer": self.answer,
            "citations": list(self.citations),
            "used_llm": self.used_llm,
            "model": self.model,
            "grounded_in": list(self.grounded_in),
            "disclaimer": self.disclaimer,
            "human_review_required": self.human_review_required,
            "grounding_warnings": list(self.grounding_warnings),
        }


def _numbered_excerpts(result: RegulatorySearchResult) -> tuple[str, tuple[str, ...]]:
    """Render the retrieved chunks as numbered excerpts + the matching citation list."""

    lines: list[str] = []
    citations: list[str] = []
    for i, r in enumerate(result.results, start=1):
        lines.append(
            f"[S{i}] ({r.source_document}, effective {r.chunk.effective_date})\n{r.excerpt()}"
        )
        citations.append(f"[S{i}] {r.citation()}")
    return "\n\n".join(lines), tuple(citations)


# A regulated quantity = a number adjacent to a dose/concentration unit, optionally per day/kg/dose.
# Used to catch an LLM stating a limit/threshold/PDE/TTC that is not present in the excerpts.
_NUMERIC_LIMIT_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s?(?:µg|ug|mcg|mg|ng|kg|ppm|ppb|%|g)\b(?:\s?/\s?(?:day|kg|ml|l|dose))?",
    re.IGNORECASE,
)


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _verify_llm_grounding(answer: str, result: RegulatorySearchResult) -> tuple[str, ...]:
    """Post-hoc check that an LLM answer stays grounded in the retrieved excerpts.

    The grounding contract is enforced in the system prompt, but a misbehaving/jailbroken model
    can ignore it. This is the programmatic backstop: it flags (a) ``[S#]`` citation markers that
    reference no retrieved excerpt and (b) any regulated number (limit/threshold/PDE/TTC, with a
    dose/concentration unit) that does not appear verbatim in the excerpts the model was shown.
    Findings are surfaced as warnings — the deferral to the deterministic calculators remains the
    hard guarantee for regulated values.
    """

    warnings: list[str] = []
    n = len(result.results)
    cited = {int(m) for m in re.findall(r"\[S(\d+)\]", answer)}
    invalid = sorted(c for c in cited if c < 1 or c > n)
    if invalid:
        markers = ", ".join(f"[S{c}]" for c in invalid)
        warnings.append(
            f"answer cites {markers} but only {n} excerpt(s) were retrieved — invalid citation"
        )
    # Compare regulated numbers against the excerpts the model saw (whitespace-insensitive).
    excerpt_blob = _strip_ws(" ".join(r.excerpt() for r in result.results)).lower()
    seen: set[str] = set()
    for match in _NUMERIC_LIMIT_RE.finditer(answer):
        token = match.group(0)
        norm = _strip_ws(token).lower()
        if norm in seen:
            continue
        seen.add(norm)
        if norm not in excerpt_blob:
            warnings.append(
                f"answer states {token!r}, not present in the retrieved excerpts — compute this "
                "value with the deterministic calculator rather than trusting the synthesis"
            )
    return tuple(warnings)


def synthesize_answer(
    query: str,
    result: RegulatorySearchResult,
    *,
    llm: LLMClient | None = None,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1024,
) -> SynthesizedAnswer:
    """Synthesise an answer grounded ONLY in the retrieved chunks, with explicit citations.

    With no ``llm`` the answer is extractive (the retrieved excerpts + citations, deterministic).
    Supplying an :class:`LLMClient` (e.g. :class:`AnthropicLLM`) produces an LLM synthesis under a
    system prompt that forbids outside knowledge, requires citations, and defers any numeric limit
    to the deterministic calculators.
    """

    grounded_in = tuple(r.chunk.chunk_id for r in result.results)
    excerpts, citations = _numbered_excerpts(result)

    if not result.results:
        return SynthesizedAnswer(
            query=query,
            answer=(
                "The regulatory corpus returned no relevant excerpts for this query. No answer can "
                "be grounded; broaden the query or confirm the corpus covers this topic."
            ),
            citations=(),
            used_llm=False,
            model=None,
            grounded_in=(),
        )

    if llm is None:
        # Deterministic extractive synthesis — purely the retrieved evidence + citations.
        body = "\n".join(
            f"- {r.source_document} (effective {r.chunk.effective_date}) [S{i}]: {r.excerpt()}"
            for i, r in enumerate(result.results, start=1)
        )
        answer = (
            f"Grounded in the retrieved regulatory guidance for: {query!r}\n\n{body}\n\n"
            "Confirm each point against the cited official source; compute any specific limit with "
            "the relevant MolTrace deterministic calculator."
        )
        return SynthesizedAnswer(
            query=query,
            answer=answer,
            citations=citations,
            used_llm=False,
            model=None,
            grounded_in=grounded_in,
        )

    prompt = (
        f"Question: {query}\n\nRegulatory excerpts (cite by marker):\n\n{excerpts}\n\n"
        "Answer the question using only these excerpts, citing each claim by its [S#] marker."
    )
    answer = llm.complete(
        system=_SYNTHESIS_SYSTEM, prompt=prompt, model=model, max_tokens=max_tokens
    )
    return SynthesizedAnswer(
        query=query,
        answer=answer,
        citations=citations,
        used_llm=True,
        model=model,
        grounded_in=grounded_in,
        grounding_warnings=_verify_llm_grounding(answer, result),
    )


# --------------------------------------------------------------------------- #
# Validation harness (ICH M7 Q&A + FDA nitrosamine Q&A reproduction)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegulatoryFaqPair:
    """A regulatory FAQ pair: a question whose answer should retrieve a specific source."""

    question: str
    expected_source: CorpusSource
    expected_keywords: tuple[str, ...] = ()
    expected_document_id: str | None = None


@dataclass(frozen=True)
class FaqEvalResult:
    question: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FaqEvalReport:
    """The outcome of running a set of FAQ pairs through retrieval."""

    results: tuple[FaqEvalResult, ...]

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def n_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    def failures(self) -> tuple[FaqEvalResult, ...]:
        return tuple(r for r in self.results if not r.passed)


def evaluate_faq_pairs(
    pairs: Sequence[RegulatoryFaqPair],
    *,
    corpus: Sequence[IndexChunk],
    top_k: int = 5,
    retriever: Retriever | None = None,
) -> FaqEvalReport:
    """Validate retrieval against FAQ pairs: the expected source must appear in the top-k results,
    its expected keywords present, and (if given) the expected document id retrieved.

    Supply the real ICH M7 Q&A + FDA nitrosamine Q&A pairs (the corpus the user ingested) to
    reproduce the 20 + 10 acceptance set; the harness asserts each is grounded in the right source.
    """

    out: list[FaqEvalResult] = []
    for pair in pairs:
        result = regulatory_search(pair.question, top_k=top_k, corpus=corpus, retriever=retriever)
        # Select the expected hit by document when an id is given (many documents can share one
        # CorpusSource — e.g. ICH M7/Q3C/Q3D/Q6A/Q1A are all CorpusSource.ICH_GUIDELINE — so
        # matching on source alone would fail a pair whose expected document is in top-k but
        # outranked by a sibling document of the same source). Fall back to source-only otherwise.
        if pair.expected_document_id is not None:
            hit = next(
                (
                    r
                    for r in result.results
                    if r.chunk.source is pair.expected_source
                    and r.chunk.document_id == pair.expected_document_id
                ),
                None,
            )
            miss_detail = (
                f"expected document {pair.expected_document_id} "
                f"({pair.expected_source.value}) not in top-k results"
            )
        else:
            hit = next(
                (r for r in result.results if r.chunk.source is pair.expected_source), None
            )
            miss_detail = f"expected source {pair.expected_source.value} not in top-k results"
        if hit is None:
            out.append(FaqEvalResult(pair.question, False, miss_detail))
            continue
        text_low = hit.chunk.text.lower()
        missing = [k for k in pair.expected_keywords if k.lower() not in text_low]
        if missing:
            out.append(FaqEvalResult(pair.question, False, f"top hit missing keywords: {missing}"))
            continue
        out.append(FaqEvalResult(pair.question, True, f"grounded in {hit.source_document}"))
    return FaqEvalReport(results=tuple(out))
