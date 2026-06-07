"""Retrieval-augmented structure reasoning (Prompt 14).

This module wraps a large language model (Anthropic Claude) in a **retrieval
layer** over the Prompt 8 spectral similarity index, so that proposed molecular
structures are *grounded in known precedent* rather than free-generated.

The contract is deliberately conservative — the LLM is a **proposer**, never the
arbiter:

#. :func:`build_reasoning_context` retrieves the ``top_k`` nearest known spectra
   from the (injectable) Prompt 8 index, joins each hit back to its metadata
   (SMILES / shift summary / multiplet summary / license) via an injectable
   *resolver*, converts the L2 distance to a bounded similarity, applies an
   optional license allow-list, and packs the result into a **token-bounded**
   :class:`RAGContext`.
#. :func:`propose_structures` renders that context into a prompt, asks the LLM
   for a strict-JSON list of ``{smiles, rationale, cited_analogue_ids,
   self_confidence}`` candidates, **schema-validates with a single retry**,
   drops any candidate that is neither cited against a real retrieved analogue
   nor otherwise supported (the **hallucination guard**), and then scores every
   survivor with the Prompt 7 verifier — which is the sole authority on
   pass/fail. The model's ``self_confidence`` is advisory only and is *never*
   fed to the verifier as a prior, so it can never override the evidence-based
   posterior.

Every invocation records the retrieved analogue ids, the exact prompt, and the
raw completion(s) for the Prompt 12 audit trail (see :class:`RAGAudit` and the
``audit_recorder`` hook on :func:`propose_structures`).

Guardrails (Prompt 14 acceptance criteria):

* **Retrieval-grounded, not free generation** — candidates must cite a real
  retrieved analogue or match one structurally; ungrounded candidates are
  dropped before they ever reach the verifier.
* **The verifier decides** — ``accepted`` / ``posterior_confidence`` / ``verdict``
  come purely from :func:`moltrace.spectroscopy.verification.scorer.verify_structure`.
* **Full auditability** — retrieved ids + prompt + raw completion are captured.

Design notes:

* The LLM, the index, the metadata resolver, the verifier, and the structural
  support check are **all injectable**. With fakes for each, the whole pipeline
  runs deterministically on a CPU-only host with no network, no FAISS, no
  ``anthropic`` package, and no model weights — exactly the way the tests use it.
* ``anthropic`` is an **optional** dependency (lazy-imported only inside the
  default Claude wrapper); it is intentionally *not* declared in
  ``pyproject.toml`` — the same posture as ``matchms`` in the datasets pipeline.

References:

* Retrieval grounding follows the NMR-Solver methodology (Jin et al.,
  arXiv:2509.00640, 2025) reused from :mod:`moltrace.spectroscopy.similarity`.
* The reasoning model is Anthropic Claude (``claude-opus-4-8``) accessed through
  the official ``anthropic`` Python SDK Messages API with structured outputs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "DEFAULT_LLM_MAX_TOKENS",
    "DEFAULT_MAX_CANDIDATES",
    "DEFAULT_MODEL",
    "DEFAULT_TOKEN_BUDGET",
    "DEFAULT_TOP_K",
    "Candidate",
    "ProposalResult",
    "RAGAudit",
    "RAGContext",
    "RAGError",
    "RAGLLMUnavailable",
    "RAGSchemaError",
    "RetrievedAnalogue",
    "build_reasoning_context",
    "propose_structures",
]


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
#: Production reasoning model — Anthropic Claude Opus 4.8 (Messages API).
DEFAULT_MODEL = "claude-opus-4-8"

#: Default number of nearest known spectra to retrieve as precedent.
DEFAULT_TOP_K = 50

#: Default cap on candidate structures the LLM may propose per call.
DEFAULT_MAX_CANDIDATES = 5

#: Token budget for the retrieved-precedent block packed into the prompt.
#: Analogues are included greedily until this budget is reached, then the
#: context is marked ``truncated``.
DEFAULT_TOKEN_BUDGET = 12_000

#: ``max_tokens`` for the default Claude wrapper (non-streaming, safe under the
#: SDK HTTP timeout; leaves ample room for adaptive thinking + a small JSON body).
DEFAULT_LLM_MAX_TOKENS = 16_000

#: Rough chars-per-token heuristic for the token-budget estimate (avoids a hard
#: dependency on a tokenizer; deliberately conservative).
_CHARS_PER_TOKEN = 4


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RAGError(Exception):
    """Base class for retrieval-augmented-reasoning errors."""


class RAGSchemaError(RAGError):
    """The LLM completion did not match the required candidate JSON schema."""


class RAGLLMUnavailable(RAGError):
    """The reasoning model backend is unavailable (e.g. ``anthropic`` missing)."""


# --------------------------------------------------------------------------- #
# Retrieval data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrievedAnalogue:
    """A single known spectrum retrieved as precedent for the query.

    ``similarity`` is a bounded (0, 1] transform of the index L2 distance
    (1.0 = identical encoding); ``license`` carries the redistribution terms of
    the source record so downstream consumers can honour them.
    """

    analogue_id: str
    smiles: str
    l2_distance: float
    similarity: float
    rank: int
    license: str = "unknown"
    shift_summary: str | None = None
    multiplet_summary: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "analogue_id": self.analogue_id,
            "smiles": self.smiles,
            "l2_distance": self.l2_distance,
            "similarity": self.similarity,
            "rank": self.rank,
            "license": self.license,
            "shift_summary": self.shift_summary,
            "multiplet_summary": self.multiplet_summary,
            "source": self.source,
        }

    def to_prompt_lines(self) -> str:
        head = (
            f"[analogue_id={self.analogue_id} | similarity={self.similarity:.3f} "
            f"| license={self.license}] SMILES: {self.smiles}"
        )
        lines = [head]
        lines.append(f"    shifts: {self.shift_summary or 'n/a'}")
        lines.append(f"    multiplets: {self.multiplet_summary or 'n/a'}")
        return "\n".join(lines)


@dataclass
class RAGContext:
    """Token-bounded retrieval context handed to the reasoning model.

    ``allowed_analogue_ids`` is the set of ids the model is permitted to cite;
    the :func:`propose_structures` hallucination guard treats any other cited id
    as fabricated.
    """

    query_nucleus: str
    query_fingerprint: str
    analogues: list[RetrievedAnalogue]
    top_k: int
    index_size: int
    token_estimate: int
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def allowed_analogue_ids(self) -> set[str]:
        return {a.analogue_id for a in self.analogues}

    @property
    def analogue_smiles(self) -> list[str]:
        return [a.smiles for a in self.analogues if a.smiles]

    def to_prompt_block(self) -> str:
        if not self.analogues:
            return "(no precedent spectra were retrieved)"
        return "\n".join(a.to_prompt_lines() for a in self.analogues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_nucleus": self.query_nucleus,
            "query_fingerprint": self.query_fingerprint,
            "top_k": self.top_k,
            "index_size": self.index_size,
            "token_estimate": self.token_estimate,
            "truncated": self.truncated,
            "analogues": [a.to_dict() for a in self.analogues],
            "warnings": list(self.warnings),
        }


# --------------------------------------------------------------------------- #
# Candidate / proposal data model
# --------------------------------------------------------------------------- #
@dataclass
class Candidate:
    """A structure proposed by the LLM, after grounding + verification.

    The ``self_confidence`` is the model's own (advisory) estimate and is *never*
    used as the verifier prior. ``posterior_confidence`` / ``verdict`` /
    ``accepted`` come from the Prompt 7 verifier and are authoritative.
    ``dropped_reason`` is set when the candidate was rejected before or by
    verification (e.g. ``"hallucination_guard"`` or ``"invalid_smiles"``); such
    candidates have ``accepted=False`` and usually no ``verification``.
    """

    smiles: str
    rationale: str
    cited_analogue_ids: list[str]
    self_confidence: float
    cited_valid_ids: list[str] = field(default_factory=list)
    retrieval_supported: bool = False
    verification: Any | None = None  # VerificationResult | None
    posterior_confidence: float | None = None
    verdict: str | None = None
    accepted: bool = False
    dropped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        ver: dict[str, Any] | None = None
        if self.verification is not None and hasattr(self.verification, "to_audit_dict"):
            try:
                ver = self.verification.to_audit_dict()
            except Exception:  # pragma: no cover - defensive
                ver = None
        return {
            "smiles": self.smiles,
            "rationale": self.rationale,
            "cited_analogue_ids": list(self.cited_analogue_ids),
            "cited_valid_ids": list(self.cited_valid_ids),
            "self_confidence": self.self_confidence,
            "retrieval_supported": self.retrieval_supported,
            "posterior_confidence": self.posterior_confidence,
            "verdict": self.verdict,
            "accepted": self.accepted,
            "dropped_reason": self.dropped_reason,
            "verification": ver,
        }


@dataclass
class RAGAudit:
    """Full prompt / completion / retrieval record for the Prompt 12 audit trail."""

    model: str
    query_fingerprint: str
    retrieved_ids: list[str]
    system_prompt: str
    user_prompt: str
    raw_completions: list[str]
    retry_used: bool
    parsed_candidate_count: int
    dropped_candidate_count: int
    accepted_candidate_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "query_fingerprint": self.query_fingerprint,
            "retrieved_ids": list(self.retrieved_ids),
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "raw_completions": list(self.raw_completions),
            "retry_used": self.retry_used,
            "parsed_candidate_count": self.parsed_candidate_count,
            "dropped_candidate_count": self.dropped_candidate_count,
            "accepted_candidate_count": self.accepted_candidate_count,
            "warnings": list(self.warnings),
        }


@dataclass
class ProposalResult:
    """Outcome of :func:`propose_structures`.

    ``candidates`` includes *every* evaluated candidate (accepted, verifier-
    rejected, and guard-dropped) with its flags, so callers can audit exactly
    what the model proposed and why each one was kept or dropped. ``audit`` holds
    the Prompt 12 record (retrieved ids + prompt + raw completion).
    """

    candidates: list[Candidate]
    context: RAGContext
    audit: RAGAudit

    @property
    def accepted(self) -> list[Candidate]:
        """Verifier-accepted candidates, ranked by posterior confidence (desc)."""
        passed = [c for c in self.candidates if c.accepted]
        return sorted(
            passed,
            key=lambda c: (c.posterior_confidence or 0.0, c.retrieval_supported),
            reverse=True,
        )

    @property
    def dropped(self) -> list[Candidate]:
        return [c for c in self.candidates if c.dropped_reason is not None]


# --------------------------------------------------------------------------- #
# Similarity / encoding helpers
# --------------------------------------------------------------------------- #
def _l2_to_similarity(l2_distance: float) -> float:
    """Map an L2 distance to a bounded (0, 1] similarity (1.0 at distance 0)."""
    d = max(0.0, float(l2_distance))
    return 1.0 / (1.0 + d)


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)


def _default_query_encoder(spectrum: Any) -> np.ndarray:
    """Encode a query spectrum into the canonical 256-D similarity vector.

    Tries, in order: (a) ``spectrum`` is already an encoding vector; (b) its
    ``metadata`` carries explicit ``shifts_1h`` / ``shifts_13c`` lists; (c) peak-
    pick the spectrum via Global Spectral Deconvolution and encode the resulting
    shift list, bucketed by nucleus. Raises :class:`RAGError` if none apply —
    pass ``query_encoder`` to :func:`build_reasoning_context` for full control.
    """

    from moltrace.spectroscopy.similarity import ENCODING_DIM, encode_spectrum

    # (a) already an encoding vector
    arr = np.asarray(spectrum, dtype=np.float32) if _looks_like_vector(spectrum) else None
    if arr is not None and arr.ndim == 1 and arr.shape[0] == ENCODING_DIM:
        return arr

    # (b) explicit shift lists in metadata
    metadata = getattr(spectrum, "metadata", None)
    if isinstance(metadata, Mapping):
        shifts_1h = metadata.get("shifts_1h")
        shifts_13c = metadata.get("shifts_13c")
        if shifts_1h is not None or shifts_13c is not None:
            return encode_spectrum(list(shifts_1h or []), list(shifts_13c or []))

    # (c) peak-pick + encode
    try:
        from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

        peaks = gsd_peak_pick(spectrum)
    except Exception as exc:  # pragma: no cover - environment/data guard
        raise RAGError(
            "Could not encode the query spectrum; pass an explicit `query_encoder` "
            "or provide `shifts_1h`/`shifts_13c` in spectrum.metadata."
        ) from exc

    nucleus = str(getattr(spectrum, "nucleus", "") or "").strip().lower()
    shifts_1h: list[float] = []
    shifts_13c: list[float] = []
    for peak in peaks:
        if getattr(peak, "category", "compound") != "compound":
            continue
        ppm = float(peak.position_ppm)
        if nucleus in ("1h", "h", "proton"):
            shifts_1h.append(ppm)
        elif nucleus in ("13c", "c", "carbon"):
            shifts_13c.append(ppm)
        elif ppm > 30.0:  # nucleus unknown: classify by ppm range
            shifts_13c.append(ppm)
        else:
            shifts_1h.append(ppm)
    return encode_spectrum(shifts_1h, shifts_13c)


def _looks_like_vector(obj: Any) -> bool:
    if isinstance(obj, np.ndarray):
        return True
    if isinstance(obj, (list, tuple)) and obj and all(isinstance(x, (int, float)) for x in obj):
        return True
    return False


def _coerce_analogue(
    resolved: Any, *, analogue_id: str, l2_distance: float, rank: int, default_license: str
) -> RetrievedAnalogue | None:
    """Coerce a resolver return value into a :class:`RetrievedAnalogue`."""
    similarity = _l2_to_similarity(l2_distance)
    if resolved is None:
        return None
    if isinstance(resolved, RetrievedAnalogue):
        # Trust the resolver's metadata but stamp the index-derived fields.
        return RetrievedAnalogue(
            analogue_id=resolved.analogue_id or analogue_id,
            smiles=resolved.smiles,
            l2_distance=float(l2_distance),
            similarity=similarity,
            rank=rank,
            license=resolved.license or default_license,
            shift_summary=resolved.shift_summary,
            multiplet_summary=resolved.multiplet_summary,
            source=resolved.source,
        )
    if isinstance(resolved, Mapping):
        smiles = str(resolved.get("smiles", "") or "")
        return RetrievedAnalogue(
            analogue_id=str(resolved.get("analogue_id", analogue_id) or analogue_id),
            smiles=smiles,
            l2_distance=float(l2_distance),
            similarity=similarity,
            rank=rank,
            license=str(resolved.get("license") or default_license),
            shift_summary=_opt_str(resolved.get("shift_summary")),
            multiplet_summary=_opt_str(resolved.get("multiplet_summary")),
            source=_opt_str(resolved.get("source")),
        )
    # A bare string is treated as the SMILES.
    return RetrievedAnalogue(
        analogue_id=analogue_id,
        smiles=str(resolved),
        l2_distance=float(l2_distance),
        similarity=similarity,
        rank=rank,
        license=default_license,
    )


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


# --------------------------------------------------------------------------- #
# build_reasoning_context
# --------------------------------------------------------------------------- #
def build_reasoning_context(
    spectrum: Any,
    *,
    index: Any,
    resolver: Callable[[str], Any] | None = None,
    top_k: int = DEFAULT_TOP_K,
    query_encoder: Callable[[Any], np.ndarray] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    allowed_licenses: Sequence[str] | None = None,
    default_license: str = "unknown",
) -> RAGContext:
    """Retrieve the ``top_k`` nearest known spectra and pack a token-bounded context.

    Parameters
    ----------
    spectrum:
        The query — an :class:`~moltrace.spectroscopy.io.fid_reader.NMRSpectrum`,
        a precomputed 256-D encoding, or anything ``query_encoder`` understands.
    index:
        The Prompt 8 similarity index (duck-typed: any object with
        ``search(query, k) -> [(id, l2_distance), ...]`` and ``__len__``).
    resolver:
        Maps an index id to analogue metadata (a :class:`RetrievedAnalogue`, a
        mapping with ``smiles`` / ``license`` / ``shift_summary`` / ..., a bare
        SMILES string, or ``None`` to skip). When omitted, each index id is
        treated as a SMILES string with ``default_license``.
    top_k:
        Number of nearest neighbours to request from the index.
    query_encoder:
        Optional override for turning ``spectrum`` into the query vector.
    token_budget:
        Greedily include analogues until their rendered size reaches this many
        (estimated) tokens; the remainder are dropped and ``truncated`` is set.
    allowed_licenses:
        Optional allow-list; analogues whose license is not listed are dropped
        (license-aware retrieval). ``None`` keeps everything.

    Returns
    -------
    RAGContext
    """

    warnings: list[str] = []
    encoder = query_encoder or _default_query_encoder
    query = encoder(spectrum)
    query = np.ascontiguousarray(np.asarray(query, dtype=np.float32))

    try:
        index_size = int(len(index))
    except Exception:  # pragma: no cover - duck-typed index without __len__
        index_size = 0

    hits = index.search(query, k=int(top_k))
    # A 2-D batch query would return a list of lists; we only ever pass one row.
    if hits and isinstance(hits[0], list):
        hits = hits[0]

    license_filter = {str(x) for x in allowed_licenses} if allowed_licenses is not None else None

    analogues: list[RetrievedAnalogue] = []
    rank = 0
    token_estimate = 0
    truncated = False
    for identifier, distance in hits:
        ident = str(identifier)
        resolved = resolver(ident) if resolver is not None else ident
        analogue = _coerce_analogue(
            resolved,
            analogue_id=ident,
            l2_distance=float(distance),
            rank=rank,
            default_license=default_license,
        )
        if analogue is None:
            warnings.append(f"resolver returned no metadata for id={ident!r}; skipped")
            continue
        if license_filter is not None and analogue.license not in license_filter:
            warnings.append(
                f"analogue id={ident!r} dropped: license {analogue.license!r} "
                "not in allow-list"
            )
            continue
        cost = _estimate_tokens(analogue.to_prompt_lines())
        if analogues and token_estimate + cost > token_budget:
            truncated = True
            break
        analogues.append(analogue)
        token_estimate += cost
        rank += 1

    if truncated:
        warnings.append(
            f"retrieval context truncated to {len(analogues)} analogues "
            f"(token budget {token_budget})"
        )

    return RAGContext(
        query_nucleus=str(getattr(spectrum, "nucleus", "") or "unknown"),
        query_fingerprint=str(
            getattr(spectrum, "fingerprint", "")
            or getattr(spectrum, "fingerprint_hash", "")
            or ""
        ),
        analogues=analogues,
        top_k=int(top_k),
        index_size=index_size,
        token_estimate=token_estimate,
        truncated=truncated,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Prompt construction + strict-JSON schema
# --------------------------------------------------------------------------- #
#: JSON schema enforced both at the API layer (``output_config.format``) and by
#: the application-level validator (defence in depth, and so injected non-Claude
#: LLMs are still held to the contract).
_CANDIDATES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "smiles",
                    "rationale",
                    "cited_analogue_ids",
                    "self_confidence",
                ],
                "properties": {
                    "smiles": {"type": "string"},
                    "rationale": {"type": "string"},
                    "cited_analogue_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "self_confidence": {"type": "number"},
                },
            },
        }
    },
}

_SYSTEM_PROMPT = (
    "You are a structure-elucidation assistant for analytical NMR. You are given "
    "an experimental query spectrum and a set of RETRIEVED PRECEDENT spectra of "
    "known structures, each with an analogue_id, a similarity score, a license, "
    "and (where available) shift and multiplet summaries.\n\n"
    "Propose candidate molecular structures for the query, grounded ONLY in the "
    "retrieved precedent. Hard rules:\n"
    "1. Every candidate MUST cite at least one analogue_id taken verbatim from "
    "the retrieved set in `cited_analogue_ids`. Never invent or guess an "
    "analogue_id.\n"
    "2. Do not free-generate structures unsupported by the precedent. If the "
    "precedent is weak, return fewer candidates (an empty list is acceptable).\n"
    "3. `self_confidence` is your own rough estimate in [0, 1]; it is advisory "
    "only and will not be used to score the candidate.\n"
    "4. Return STRICT JSON only — an object {\"candidates\": [...]} matching the "
    "schema. No prose, no markdown, no code fences."
)


def _build_user_prompt(context: RAGContext, *, max_candidates: int) -> str:
    return (
        f"QUERY SPECTRUM: nucleus={context.query_nucleus}, "
        f"fingerprint={context.query_fingerprint or 'n/a'}.\n\n"
        f"RETRIEVED PRECEDENT ({len(context.analogues)} analogues; "
        f"index_size={context.index_size}):\n"
        f"{context.to_prompt_block()}\n\n"
        f"Propose up to {max_candidates} candidate structures as JSON "
        '{"candidates": [{"smiles": ..., "rationale": ..., '
        '"cited_analogue_ids": [...], "self_confidence": ...}]}. '
        "Cite only analogue_ids that appear above."
    )


_RETRY_SUFFIX = (
    "\n\nYour previous response was not valid against the required schema. "
    'Respond with STRICT JSON ONLY: an object {"candidates": [ ... ]} where each '
    "candidate has exactly the keys smiles (string), rationale (string), "
    "cited_analogue_ids (array of strings), and self_confidence (number). "
    "No prose, no markdown, no code fences."
)


# --------------------------------------------------------------------------- #
# Strict-JSON parsing / validation
# --------------------------------------------------------------------------- #
def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """Parse + validate the LLM completion into a list of candidate dicts.

    Accepts either a bare JSON array or an object with a ``candidates`` array
    (liberal in what it accepts from arbitrary LLM callables). Raises
    :class:`RAGSchemaError` on any structural violation.
    """

    if raw is None:
        raise RAGSchemaError("empty completion")
    text = raw.strip()
    if not text:
        raise RAGSchemaError("empty completion")
    # Tolerate a fenced ```json block from non-structured-output backends.
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise RAGSchemaError(f"completion is not valid JSON: {exc}") from exc

    if isinstance(payload, Mapping):
        items = payload.get("candidates")
        if items is None:
            raise RAGSchemaError("JSON object missing required 'candidates' key")
    elif isinstance(payload, list):
        items = payload
    else:
        raise RAGSchemaError("top-level JSON must be an object or array")

    if not isinstance(items, list):
        raise RAGSchemaError("'candidates' must be an array")

    parsed: list[dict[str, Any]] = []
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise RAGSchemaError(f"candidate[{i}] is not an object")
        smiles = item.get("smiles")
        rationale = item.get("rationale")
        cited = item.get("cited_analogue_ids")
        conf = item.get("self_confidence")
        if not isinstance(smiles, str) or not smiles.strip():
            raise RAGSchemaError(f"candidate[{i}].smiles must be a non-empty string")
        if not isinstance(rationale, str):
            raise RAGSchemaError(f"candidate[{i}].rationale must be a string")
        if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
            raise RAGSchemaError(
                f"candidate[{i}].cited_analogue_ids must be an array of strings"
            )
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            raise RAGSchemaError(f"candidate[{i}].self_confidence must be a number")
        parsed.append(
            {
                "smiles": smiles.strip(),
                "rationale": rationale,
                "cited_analogue_ids": [c for c in cited],
                "self_confidence": _clip01(float(conf)),
            }
        )
    return parsed


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


# --------------------------------------------------------------------------- #
# Default Claude wrapper (guarded / optional)
# --------------------------------------------------------------------------- #
def _default_claude_llm(
    system: str,
    user: str,
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    schema: Mapping[str, Any] | None = None,
) -> str:
    """Call Anthropic Claude via the official SDK Messages API; return raw text.

    ``anthropic`` is imported lazily and is an optional dependency: when it is
    not installed, :class:`RAGLLMUnavailable` is raised rather than failing at
    import time. Structured outputs (``output_config.format``) constrain the
    response to the candidate schema; adaptive thinking is enabled for the
    chemistry reasoning.
    """

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - exercised only without anthropic
        raise RAGLLMUnavailable(
            "The 'anthropic' package is required for the default Claude reasoning "
            "backend; install it or pass an explicit `llm` callable."
        ) from exc

    client = anthropic.Anthropic()
    output_config: dict[str, Any] = {"effort": "high"}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": dict(schema)}
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        thinking={"type": "adaptive"},
        output_config=output_config,
        messages=[{"role": "user", "content": user}],
    )
    return next(
        (b.text for b in response.content if getattr(b, "type", None) == "text"),
        "",
    )


# --------------------------------------------------------------------------- #
# Structural support check (hallucination guard, second leg)
# --------------------------------------------------------------------------- #
def _normalize_smiles(smiles: str) -> str | None:
    """Canonical SMILES via RDKit, or ``None`` if RDKit is absent / SMILES invalid."""
    try:
        from rdkit import Chem
    except ImportError:  # pragma: no cover - RDKit is a core dep in practice
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def _default_support_check(smiles: str, context: RAGContext) -> bool:
    """A candidate is *structurally supported* if it matches a retrieved analogue.

    Uses canonical SMILES equality when RDKit is available, falling back to a
    normalised string comparison otherwise. This is the second leg of the
    hallucination guard: a candidate that cites no real analogue is kept only if
    it is structurally one of the retrieved precedents.
    """

    cand = _normalize_smiles(smiles)
    if cand is None:
        cand = smiles.strip()
        return any(cand == (a.smiles or "").strip() for a in context.analogues)
    for analogue in context.analogues:
        norm = _normalize_smiles(analogue.smiles)
        if norm is not None and norm == cand:
            return True
    return False


# --------------------------------------------------------------------------- #
# Backend resolution (injectable defaults)
# --------------------------------------------------------------------------- #
def _resolve_llm(
    llm: Callable[[str, str], str] | None, *, model: str, max_tokens: int
) -> Callable[[str, str], str]:
    if llm is not None:
        return llm

    def _claude(system: str, user: str) -> str:
        return _default_claude_llm(
            system, user, model=model, max_tokens=max_tokens, schema=_CANDIDATES_SCHEMA
        )

    return _claude


def _resolve_verifier(verifier: Callable[..., Any] | None) -> Callable[..., Any]:
    if verifier is not None:
        return verifier

    def _verify(spec: Any, smiles: str, **kwargs: Any) -> Any:
        from moltrace.spectroscopy.verification.scorer import verify_structure

        return verify_structure(spec, smiles, **kwargs)

    return _verify


# --------------------------------------------------------------------------- #
# propose_structures
# --------------------------------------------------------------------------- #
def propose_structures(
    spectrum: Any,
    context: RAGContext,
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
    llm: Callable[[str, str], str] | None = None,
    verifier: Callable[..., Any] | None = None,
    prior_confidence: float = 0.5,
    verification_options: Any | None = None,
    support_check: Callable[[str, RAGContext], bool] | None = None,
    model: str = DEFAULT_MODEL,
    llm_max_tokens: int = DEFAULT_LLM_MAX_TOKENS,
    audit_recorder: Any | None = None,
    audit_user_id: str | None = None,
) -> ProposalResult:
    """Propose retrieval-grounded structures and have the verifier arbitrate.

    Flow: render ``context`` → ask the LLM for strict-JSON candidates
    (schema-validate, single retry on failure) → drop candidates that neither
    cite a real retrieved analogue nor structurally match one (hallucination
    guard) → score each survivor with the Prompt 7 verifier (the arbiter).

    The model's ``self_confidence`` is recorded as advisory metadata and is
    **never** used as the verifier prior — ``prior_confidence`` (a fixed,
    caller-controlled neutral value) is used instead, so LLM confidence can never
    override the evidence-based posterior.

    Parameters
    ----------
    llm:
        ``llm(system, user) -> raw_completion``. Defaults to the guarded Claude
        wrapper (lazy ``anthropic``, ``claude-opus-4-8``, structured outputs).
    verifier:
        ``verifier(spectrum, smiles, prior_confidence=..., options=...) ->
        VerificationResult``. Defaults to Prompt 7
        :func:`~moltrace.spectroscopy.verification.scorer.verify_structure`.
    support_check:
        Second leg of the hallucination guard; defaults to canonical-SMILES
        match against the retrieved analogues.
    audit_recorder:
        Optional Prompt 12 recorder (duck-typed: ``record(operation, user_id,
        input_obj, result_obj, parameters)``). When supplied (with
        ``audit_user_id``), the prompt / completion / retrieved-ids are written
        to the signed audit chain. The :class:`RAGAudit` is also always returned
        on the result.

    Returns
    -------
    ProposalResult
    """

    warnings: list[str] = list(context.warnings)

    # --- 1. Build prompts ------------------------------------------------- #
    system_prompt = _SYSTEM_PROMPT
    user_prompt = _build_user_prompt(context, max_candidates=max_candidates)

    call_llm = _resolve_llm(llm, model=model, max_tokens=llm_max_tokens)

    # --- 2. Call the LLM, validate, retry once ---------------------------- #
    raw_completions: list[str] = []
    retry_used = False
    raw = call_llm(system_prompt, user_prompt)
    raw_completions.append(raw if isinstance(raw, str) else str(raw))
    try:
        parsed = _parse_candidates(raw_completions[-1])
    except RAGSchemaError as first_exc:
        retry_used = True
        warnings.append(f"LLM completion failed schema validation; retrying once ({first_exc})")
        retry_user = user_prompt + _RETRY_SUFFIX
        raw2 = call_llm(system_prompt, retry_user)
        raw_completions.append(raw2 if isinstance(raw2, str) else str(raw2))
        try:
            parsed = _parse_candidates(raw_completions[-1])
        except RAGSchemaError as second_exc:
            warnings.append(
                f"LLM completion failed schema validation after retry ({second_exc}); "
                "no candidates produced"
            )
            parsed = []

    if len(parsed) > max_candidates:
        warnings.append(
            f"LLM returned {len(parsed)} candidates; truncating to {max_candidates}"
        )
        parsed = parsed[:max_candidates]

    # --- 3. Resolve verifier / support check ------------------------------ #
    if support_check is None:
        support_check = _default_support_check

    run_verifier = _resolve_verifier(verifier)

    allowed_ids = context.allowed_analogue_ids

    # --- 4. Guard + verify each candidate --------------------------------- #
    candidates: list[Candidate] = []
    dropped = 0
    accepted = 0
    for item in parsed:
        cited = list(item["cited_analogue_ids"])
        cited_valid = [c for c in cited if c in allowed_ids]
        supported = support_check(item["smiles"], context)
        cand = Candidate(
            smiles=item["smiles"],
            rationale=item["rationale"],
            cited_analogue_ids=cited,
            self_confidence=item["self_confidence"],
            cited_valid_ids=cited_valid,
            retrieval_supported=supported,
        )

        # Hallucination guard: ungrounded => drop BEFORE verification.
        if not cited_valid and not supported:
            cand.dropped_reason = "hallucination_guard"
            cand.accepted = False
            dropped += 1
            candidates.append(cand)
            continue

        # Pre-screen obviously invalid SMILES (saves a verifier call).
        if _normalize_smiles(item["smiles"]) is None and not _rdkit_absent():
            cand.dropped_reason = "invalid_smiles"
            cand.accepted = False
            dropped += 1
            candidates.append(cand)
            continue

        # The verifier (Prompt 7) is the arbiter. self_confidence is NOT the
        # prior — a fixed neutral prior is used so LLM confidence cannot override.
        try:
            result = run_verifier(
                spectrum,
                item["smiles"],
                prior_confidence=prior_confidence,
                options=verification_options,
            )
        except Exception as exc:  # pragma: no cover - defensive
            cand.dropped_reason = f"verifier_error:{type(exc).__name__}"
            cand.accepted = False
            dropped += 1
            candidates.append(cand)
            continue

        cand.verification = result
        cand.posterior_confidence = float(getattr(result, "posterior_confidence", 0.0))
        cand.verdict = getattr(result, "verdict", None)
        cand.accepted = cand.verdict == "consistent"
        if cand.accepted:
            accepted += 1
        candidates.append(cand)

    # --- 5. Audit (Prompt 12) --------------------------------------------- #
    audit = RAGAudit(
        model=model,
        query_fingerprint=context.query_fingerprint,
        retrieved_ids=[a.analogue_id for a in context.analogues],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        raw_completions=raw_completions,
        retry_used=retry_used,
        parsed_candidate_count=len(parsed),
        dropped_candidate_count=dropped,
        accepted_candidate_count=accepted,
        warnings=warnings,
    )

    if audit_recorder is not None:
        if not audit_user_id:
            warnings.append("audit_recorder supplied without audit_user_id; not recorded")
        else:
            try:
                audit_recorder.record(
                    operation="spectrum.rag.propose",
                    user_id=audit_user_id,
                    input_obj={
                        "query_fingerprint": context.query_fingerprint,
                        "retrieved_ids": audit.retrieved_ids,
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                    },
                    result_obj=[c.to_dict() for c in candidates],
                    parameters={
                        "model": model,
                        "top_k": context.top_k,
                        "max_candidates": max_candidates,
                        "retry_used": retry_used,
                        "raw_completions": raw_completions,
                        "accepted": accepted,
                        "dropped": dropped,
                    },
                )
            except Exception as exc:  # pragma: no cover - audit must not break proposal
                warnings.append(f"audit recording failed: {type(exc).__name__}")

    return ProposalResult(candidates=candidates, context=context, audit=audit)


def _rdkit_absent() -> bool:
    try:
        import rdkit  # noqa: F401
    except ImportError:
        return True
    return False
