"""Retrieval-augmented reasoning over the regulatory corpus (Prompt 14, Roadmap Layer 2).

This is the *reasoning* layer on top of the Prompt 10 corpus RAG: it retrieves the most relevant
guidance passages and then has an LLM answer a regulatory question — or draft a justification —
**grounded only in those passages**, citing and linking the official source for every claim. It
returns a structured :class:`GroundedAnswer` (``answer`` / ``citations`` / ``confidence`` /
``needs_human_review``), validated so that an uncited claim, an invalid citation, or an asserted
regulated number forces ``needs_human_review`` and downgrades confidence.

Consolidation:

* Retrieval reuses Prompt 10 (:func:`moltrace.regulatory.intelligence.regulatory_search`): every
  passage carries its source document, section, effective date, official-source link, and licence.
  Licence tiering is honoured end to end — FDA guidance is US-government public domain; ICH/EMA/WHO
  texts are copyrighted, kept to minimal excerpts, never redistributed, and always cited + linked.
* Deferral reuses Prompt 13 (:mod:`moltrace.regulatory.ai.router`): a numeric question is **never**
  answered from narrative synthesis — it is deferred to the deterministic engine that owns the
  value (the same ``deterministic_operations`` the router dispatches), and citations use the
  router's canonical :class:`~moltrace.regulatory.ai.router.Citation`.

Both retrieval and synthesis have a zero-dependency native path (lexical retrieval + extractive
synthesis) so the engine runs and is tested offline; the production Claude path plugs in through the
injectable :class:`~moltrace.regulatory.intelligence.LLMClient`. Every output is decision-support,
carries the module disclaimer, and is flagged for qualified review.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from moltrace.regulatory.ai.router import (
    Citation,
    RegulatoryTask,
    deterministic_operations,
)
from moltrace.regulatory.intelligence import (
    AnthropicLLM,
    LexicalRetriever,
    LLMClient,
    Retriever,
    regulatory_search,
    workflow_relevance,
)

__all__ = [
    "AnthropicLLM",
    "Confidence",
    "GroundedAnswer",
    "LLMClient",
    "LexicalRetriever",
    "Passage",
    "Retriever",
    "answer_with_citations",
    "reason",
    "retrieve",
    "router_backend",
]

_DEFAULT_MODEL = "claude-sonnet-4-6"  # current Sonnet; the dated id in the prompt is deprecated

_REASONER_DISCLAIMER = (
    "Decision-support only. This answer is generated from retrieved regulatory excerpts, must be "
    "verified against the cited official sources, and requires qualified-reviewer sign-off. Any "
    "specific numeric limit/threshold is computed by MolTrace's deterministic engine, not taken "
    "from this synthesis."
)

# The grounding + JSON instruction set handed to the LLM.
_REASONER_SYSTEM = (
    "You are a regulatory-affairs reasoning assistant for pharmaceutical quality and regulatory "
    "teams. Answer the question using ONLY the numbered guidance passages provided. Do not use any "
    "knowledge outside them.\n"
    "Rules:\n"
    "- Cite the source by its passage marker (e.g. [S1]) for EVERY claim; each sentence that "
    "asserts something must carry at least one marker.\n"
    "- Keep any verbatim quote minimal; prefer a short summary plus the citation.\n"
    "- NEVER state a specific numeric limit, threshold, PDE, TTC, or acceptable intake — these are "
    "computed by MolTrace's deterministic engine. Say the value must be computed by that engine "
    "and cite the passage for context; do not write the number.\n"
    "- If the passages do not support an answer, say so plainly and set needs_human_review to "
    "true.\n"
    "Output ONLY one JSON object, with no prose around it, with exactly these keys: "
    '{"answer": "<text with [S#] markers>", "citations": ["S1", ...], '
    '"confidence": "high"|"medium"|"low", "needs_human_review": true|false}.'
)

# A number adjacent to a dose/concentration unit — a regulated quantity that must defer to the
# deterministic engine rather than be asserted in a narrative answer. Covers abbreviated AND
# spelled-out units (a model that writes "1.5 micrograms per day" must not slip past the guard).
# Kept in sync with rag_search._NUMERIC_LIMIT_RE (the Prompt 10 post-hoc check).
_NUMERIC_TOKEN_RE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s?"
    r"(?:micrograms?|milligrams?|nanograms?|kilograms?|parts per million|parts per billion"
    r"|percent|grams?|µg|mcg|ug|mg|ng|kg|ppm|ppb|%|g)"
    r"(?![a-zA-Z])"
    r"(?:\s?(?:/|per)\s?(?:day|kg|ml|l|dose))?",
    re.IGNORECASE,
)
# Regulated-quantity TERMS — their presence means the question asks for a number that the
# deterministic engine owns. Matched as substrings (case-insensitive).
_NUMERIC_TERMS: tuple[str, ...] = (
    "pde",
    "permitted daily exposure",
    "permitted daily intake",
    "ttc",
    "threshold of toxicological concern",
    "acceptable intake",
    "acceptable daily intake",
    "concentration limit",
)
# Interrogative-for-a-value patterns that are numeric without naming a term above. Deliberately
# narrow so qualitative questions ("how much testing", "maximum number of batches") do NOT match.
_NUMERIC_QUERY_RE = re.compile(
    r"(?:\b(?:limit|threshold)\s+for\b"
    r"|\bwhat(?:'s| is|s)?\s+the\s+(?:limit|threshold|maximum (?:daily|permitted|allowed))\b"
    r"|\bhow\s+(?:much|many)\b[^?]*\b(?:permitted|allowed|acceptable)\b)",
    re.IGNORECASE,
)
_MARKER_RE = re.compile(r"\[S(\d+)\]")

# numeric-query keyword -> (deterministic router operation, rule-engine name)
_DEFER_MAP: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("elemental", "heavy metal", "elemental impurit", "lead", "arsenic", "cadmium",
      "mercury", "q3d"), "q3d_element_pde", "ich_q3d"),
    (("residual solvent", "class 1 solvent", "class 2 solvent", "q3c"),
     "q3c_residual_solvent_limits", "ich_q3c"),
    (("mutagenic", "genotoxic", "dna reactive", "ttc", "m7"), "m7_classify", "ich_m7"),
    (("nitrosamine", "ndsri", "ndma", "ndea", "cpca", "cohort of concern"), "cpca_classify",
     "fda_cpca_nitrosamine"),
    (("reporting threshold", "identification threshold", "qualification threshold", "q3a",
      "q3b"), "q3ab_thresholds", "ich_q3ab"),
)


class Confidence(StrEnum):
    """Confidence in a grounded answer. Ordered HIGH > MEDIUM > LOW for downgrading."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_ORDER: tuple[Confidence, ...] = (Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH)


def _downgrade(c: Confidence) -> Confidence:
    return _ORDER[max(0, _ORDER.index(c) - 1)]


def _coerce_confidence(value: object) -> Confidence | None:
    if isinstance(value, Confidence):
        return value
    if isinstance(value, str):
        try:
            return Confidence(value.strip().lower())
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------- #
# Passage — a retrieved, attributed, licence-aware guidance excerpt
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Passage:
    """One retrieved guidance passage: source, section, effective date, minimal snippet, link."""

    rank: int
    source: str  # document id, e.g. "ICH M7(R2)"
    section: str
    effective_date: str
    url: str
    snippet: str  # minimal excerpt (capped; internal-only sources are never returned in full)
    license: str
    redistributable: bool
    workflow_modules: tuple[str, ...] = ()

    @property
    def marker(self) -> str:
        return f"S{self.rank}"

    @property
    def marker_ref(self) -> str:
        return f"[S{self.rank}]"

    def citation(self) -> str:
        link = f" — {self.url}" if self.url else ""
        return f"{self.source} §{self.section} (effective {self.effective_date}){link}"

    def to_citation(self) -> Citation:
        """The canonical Prompt 13 :class:`Citation` (consistent provenance across the module)."""

        return Citation(
            source_guidance=self.source,
            effective_date=self.effective_date,
            reference=self.section,
        )

    def as_dict(self) -> dict:
        return {
            "rank": self.rank,
            "marker": self.marker,
            "source": self.source,
            "section": self.section,
            "effective_date": self.effective_date,
            "url": self.url,
            "snippet": self.snippet,
            "license": self.license,
            "redistributable": self.redistributable,
            "workflow_modules": list(self.workflow_modules),
        }


@dataclass(frozen=True)
class GroundedAnswer:
    """A regulatory answer grounded only in retrieved passages, with structured provenance."""

    query: str
    answer: str
    citations: tuple[Citation, ...]
    confidence: Confidence
    needs_human_review: bool
    used_llm: bool
    model: str | None = None
    deferred_to_engine: str | None = None
    grounding_warnings: tuple[str, ...] = ()
    disclaimer: str = _REASONER_DISCLAIMER

    def as_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [c.as_dict() for c in self.citations],
            "confidence": self.confidence.value,
            "needs_human_review": self.needs_human_review,
            "used_llm": self.used_llm,
            "model": self.model,
            "deferred_to_engine": self.deferred_to_engine,
            "grounding_warnings": list(self.grounding_warnings),
            "disclaimer": self.disclaimer,
        }


# --------------------------------------------------------------------------- #
# Retrieval (Prompt 10 index)
# --------------------------------------------------------------------------- #
def retrieve(
    query: str,
    top_k: int = 12,
    *,
    corpus: list,
    retriever: Retriever | None = None,
    filter_source: str | None = None,
) -> list[Passage]:
    """Query the Prompt 10 index over the regulatory corpus, returning attributed passages.

    LICENSING: FDA guidance is US-government public domain; ICH/EMA/WHO texts are copyrighted /
    under reuse terms — they are retrieved for INTERNAL use only, kept to minimal excerpts, never
    redistributed, and always carry a citation + a link to the official source. Each
    :class:`Passage` carries ``source``, ``section``, ``effective_date``, ``snippet``, and ``url``.
    """

    result = regulatory_search(
        query, top_k=top_k, filter_source=filter_source, corpus=corpus, retriever=retriever
    )
    return [
        Passage(
            rank=r.rank,
            source=r.chunk.document_id,
            section=r.chunk.section,
            effective_date=r.chunk.effective_date,
            url=r.chunk.url,
            snippet=r.excerpt(),
            license=r.chunk.license,
            redistributable=r.chunk.redistributable,
            workflow_modules=r.workflow_relevance,
        )
        for r in result.results
    ]


# --------------------------------------------------------------------------- #
# Numeric deferral to the deterministic engine (Prompt 13)
# --------------------------------------------------------------------------- #
def _is_numeric_query(query: str) -> bool:
    """True when the question asks for a regulated numeric value (so it must defer to the engine).

    Triggers on a regulated-quantity term (PDE, TTC, acceptable intake, …) or a narrow
    interrogative-for-a-value pattern — but NOT on qualitative ``how much/how many`` questions
    (e.g. "how much testing is required") whose object is not a regulated quantity.
    """

    low = query.lower()
    if any(term in low for term in _NUMERIC_TERMS):
        return True
    return _NUMERIC_QUERY_RE.search(low) is not None


def defer_target(query: str) -> str:
    """Name the deterministic engine/operation a numeric query must be routed to (Prompt 13)."""

    low = query.lower()
    ops = deterministic_operations()
    for keywords, operation, engine in _DEFER_MAP:
        if any(k in low for k in keywords) and operation in ops:
            return f"the deterministic {engine} engine (operation `{operation}`)"
    rel = workflow_relevance(query)
    if rel:
        return f"the deterministic engine for {rel[0]}"
    return "the deterministic regulatory rule engine (moltrace.regulatory.ai.router)"


# --------------------------------------------------------------------------- #
# Answer synthesis
# --------------------------------------------------------------------------- #
def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_answer_json(text: str) -> dict | None:
    """Parse + minimally validate the LLM JSON; return None if it is not the required object."""

    try:
        obj = json.loads(_strip_json_fence(text))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or "answer" not in obj:
        return None
    return obj


def _sentences(text: str) -> list[str]:
    # Split on sentence punctuation, semicolons, and newlines so an uncited clause appended after
    # ';' cannot ride on a cited clause's marker.
    parts = re.split(r"(?<=[.!?])\s+|[;\n]+", text)
    return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]


def _uncited_claim_sentences(answer: str, valid_markers: set[int]) -> list[str]:
    """Substantive clauses that assert something but carry no valid citation marker.

    Deliberately strict: there is no meta-phrase allowlist (a whitelist is exploitable — a model
    can name-drop a phrase to cloak an uncited claim) and the bar for "substantive" is low (>= 2
    content words), so a short false claim like "Lead causes cancer." is still flagged. The cost is
    a trailing procedural sentence may force human review — the safe bias for a regulated layer.
    """

    uncited: list[str] = []
    for sentence in _sentences(answer):
        words = re.findall(r"[A-Za-z]{3,}", sentence)
        if len(words) < 2:
            continue  # a fragment, not a standalone claim
        markers = {int(m) for m in _MARKER_RE.findall(sentence)}
        if not (markers & valid_markers):
            uncited.append(sentence)
    return uncited


def _refusal(query: str) -> GroundedAnswer:
    return GroundedAnswer(
        query=query,
        answer=(
            "The regulatory corpus returned no passages that support an answer to this question. "
            "No grounded answer is possible; broaden the query or confirm the corpus covers this "
            "topic."
        ),
        citations=(),
        confidence=Confidence.LOW,
        needs_human_review=True,
        used_llm=False,
        grounding_warnings=("no supporting passages retrieved",),
    )


def _deferral(query: str, passages: list[Passage], target: str) -> GroundedAnswer:
    markers = " ".join(p.marker_ref for p in passages)
    answer = (
        "This question asks for a regulated numeric value, which MolTrace does not answer from "
        f"narrative synthesis. The authoritative value is computed by {target}, version-pinned to "
        "the cited guidance — run that engine with the specific inputs and use its result. The "
        f"retrieved guidance is provided for context and traceability: {markers}."
    )
    return GroundedAnswer(
        query=query,
        answer=answer,
        citations=tuple(p.to_citation() for p in passages),
        confidence=Confidence.MEDIUM,
        needs_human_review=True,
        used_llm=False,
        deferred_to_engine=target,
        grounding_warnings=("numeric question deferred to the deterministic engine (Prompt 13)",),
    )


def _extractive(query: str, passages: list[Passage]) -> GroundedAnswer:
    body = "\n".join(
        f"- {p.source} (§{p.section}, effective {p.effective_date}) {p.marker_ref}: {p.snippet}"
        for p in passages
    )
    answer = (
        "Based only on the retrieved regulatory guidance:\n"
        f"{body}\n"
        "Confirm each point against the cited official source; any specific regulated number must "
        "be computed by the deterministic engine."
    )
    # A regulated number surfaced from a corpus snippet is still a regulated number — flag it for
    # review and defer the authoritative value to the deterministic engine, rather than presenting
    # a snippet figure as settled.
    numbers = sorted({m.group(0) for m in _NUMERIC_TOKEN_RE.finditer(body)})
    warnings: tuple[str, ...] = ()
    needs_review = False
    if numbers:
        warnings = (
            f"retrieved guidance contains regulated number(s) {numbers} — verify and compute the "
            "authoritative value with the deterministic engine, do not rely on the snippet figure",
        )
        needs_review = True
    return GroundedAnswer(
        query=query,
        answer=answer,
        citations=tuple(p.to_citation() for p in passages),
        confidence=Confidence.MEDIUM,
        needs_human_review=needs_review,
        used_llm=False,
        grounding_warnings=warnings,
    )


def answer_with_citations(
    query: str,
    passages: list[Passage],
    *,
    llm: LLMClient | None = None,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1024,
    defer: str | None = None,
) -> GroundedAnswer:
    """Answer a regulatory question grounded ONLY in ``passages``, with structured citations.

    Guardrails (decision-support, qualified review): the answer is grounded only in the passages; a
    numeric question is deferred to the deterministic engine (Prompt 13), never answered from the
    model; and the resulting JSON is validated — an uncited claim, an invalid citation marker, or an
    asserted regulated number downgrades ``confidence`` and forces ``needs_human_review``.
    """

    if not passages:
        return _refusal(query)
    if _is_numeric_query(query):
        return _deferral(query, passages, defer or defer_target(query))
    if llm is None:
        return _extractive(query, passages)

    prompt = (
        f"Question: {query}\n\nNumbered regulatory passages (cite by marker):\n\n"
        + "\n\n".join(
            f"[S{p.rank}] ({p.source}, §{p.section}, effective {p.effective_date}) {p.snippet}"
            for p in passages
        )
        + "\n\nAnswer ONLY from these passages as instructed, and return the single JSON object."
    )
    raw = llm.complete(system=_REASONER_SYSTEM, prompt=prompt, model=model, max_tokens=max_tokens)
    return _validate_llm_answer(query, passages, raw, model)


def _validate_llm_answer(
    query: str, passages: list[Passage], raw: str, model: str
) -> GroundedAnswer:
    obj = _parse_answer_json(raw)
    if obj is None:
        return GroundedAnswer(
            query=query,
            answer=(
                "The model response could not be parsed as the required grounded-JSON object; "
                "manual review required."
            ),
            citations=(),
            confidence=Confidence.LOW,
            needs_human_review=True,
            used_llm=True,
            model=model,
            grounding_warnings=("unparseable or schema-invalid model output",),
        )

    answer_text = str(obj.get("answer", "")).strip()
    warnings: list[str] = []
    # needs_human_review must be a real boolean; a missing/non-bool value is a schema violation and
    # is treated as "needs review" (never silently coerced to a permissive False).
    raw_review = obj.get("needs_human_review")
    if isinstance(raw_review, bool):
        needs_review = raw_review
    else:
        warnings.append("missing/invalid needs_human_review in model output")
        needs_review = True
    confidence = _coerce_confidence(obj.get("confidence"))
    if confidence is None:
        warnings.append("missing/invalid confidence in model output")
        confidence = Confidence.LOW
        needs_review = True

    used = [int(m) for m in _MARKER_RE.findall(answer_text)]
    valid = {m for m in used if 1 <= m <= len(passages)}
    invalid = sorted({m for m in used if m < 1 or m > len(passages)})
    if invalid:
        markers = ", ".join(f"[S{m}]" for m in invalid)
        warnings.append(f"answer cites {markers} but only {len(passages)} passages were retrieved")
        confidence = _downgrade(confidence)
        needs_review = True
    citations = tuple(passages[m - 1].to_citation() for m in sorted(valid))

    if not answer_text:
        warnings.append("empty answer")
        confidence = Confidence.LOW
        needs_review = True

    uncited = _uncited_claim_sentences(answer_text, valid)
    if uncited:
        warnings.append(f"{len(uncited)} uncited claim sentence(s) — grounding not verifiable")
        confidence = _downgrade(confidence)
        needs_review = True

    numbers = sorted({m.group(0) for m in _NUMERIC_TOKEN_RE.finditer(answer_text)})
    if numbers:
        warnings.append(
            f"answer states regulated number(s) {numbers} — these must be computed by the "
            "deterministic engine, not asserted in synthesis"
        )
        confidence = _downgrade(confidence)
        needs_review = True

    if answer_text and not citations:
        warnings.append("answer contains no valid citation markers")
        confidence = Confidence.LOW
        needs_review = True

    return GroundedAnswer(
        query=query,
        answer=answer_text,
        citations=citations,
        confidence=confidence,
        needs_human_review=needs_review,
        used_llm=True,
        model=model,
        grounding_warnings=tuple(warnings),
    )


def reason(
    query: str,
    *,
    corpus: list,
    top_k: int = 12,
    llm: LLMClient | None = None,
    retriever: Retriever | None = None,
    filter_source: str | None = None,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 1024,
) -> GroundedAnswer:
    """Convenience: retrieve over the corpus, then answer with citations (end-to-end reasoning)."""

    passages = retrieve(
        query, top_k=top_k, corpus=corpus, retriever=retriever, filter_source=filter_source
    )
    return answer_with_citations(query, passages, llm=llm, model=model, max_tokens=max_tokens)


# --------------------------------------------------------------------------- #
# Consolidation with Prompt 13: a generative backend the Router can inject
# --------------------------------------------------------------------------- #
def router_backend(
    corpus: list,
    *,
    llm: LLMClient | None = None,
    top_k: int = 12,
    retriever: Retriever | None = None,
) -> Callable[[RegulatoryTask], Mapping]:
    """Build an ``LlmFn`` for :class:`moltrace.regulatory.ai.router.Router` (retrieval/narrative).

    The router only ever routes NARRATIVE/RETRIEVAL/TRIAGE tasks here (quantitative/classification
    go to the deterministic engine), so this backend answers a ``task.payload['query']`` with a
    grounded, cited :class:`GroundedAnswer` rendered into the router's ``{text, citations,
    warnings}`` shape. The router already stamps ``needs_review=True`` on the generative path.
    """

    def _backend(task: RegulatoryTask) -> Mapping:
        query = str(task.payload.get("query", ""))
        ans = reason(
            query,
            corpus=corpus,
            top_k=int(task.payload.get("top_k", top_k)),
            llm=llm,
            retriever=retriever,
            filter_source=task.payload.get("filter_source"),
        )
        return {
            "text": ans.answer,
            "citations": list(ans.citations),
            "warnings": ans.grounding_warnings,
            "needs_review": ans.needs_human_review,
            "confidence": ans.confidence.value,
        }

    return _backend
