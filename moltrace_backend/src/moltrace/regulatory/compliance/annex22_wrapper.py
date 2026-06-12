"""EU GMP Draft Annex 22 AI-decision governance wrapper (Prompt 12).

EU GMP Annex 22 is in **DRAFT** (July 2025; final expected 2026, enforcement ~2027-2028).
This wrapper is designed to *support the draft's direction* -- it is not a compliance
certification, and nothing here may be represented to users as "Annex 22 compliant". Reassess
against the final text on publication.

Per the draft, every AI decision in a regulated GMP/regulatory context must be **documented**,
**explainable**, and **subject to human review**. This module gives MolTrace one decorator,
:func:`with_annex22_governance`, to wrap an AI-assisted regulatory function so that each call:

* records an immutable, hash-chained :class:`AIDecisionRecord` -- intended use, model name +
  version, input hash, full output, calibrated confidence, feature attribution, regulatory
  basis, and the criticality risk level;
* for a **high**-risk decision, returns a *pending* :class:`GovernedResult` and blocks the
  downstream consumer (e.g. CTD generation) until a human reviewer approves it;
* for a **low**-risk decision, logs automatically and flags a deterministic ~5% sample for QA
  periodic review.

Tamper evidence reuses the proven chain shape of :mod:`moltrace.spectroscopy.audit.trail`:
``previous_entry_hash`` links every record to the one before it, so insertion, deletion, or
reordering breaks the chain. (That HMAC-signed trail remains the org-wide §11 audit log; an
Annex 22 record can be emitted into it as well -- this module owns the AI-decision-specific
schema + HITL workflow.)

Confidence must come from a *calibrated* source -- the calibration harness in
:mod:`moltrace.spectroscopy.infra.eval` (:func:`expected_calibration_error`) is the ECE gate;
a deterministic rule-engine decision (Prompt 13) carries confidence ``1.0`` and a rule-basis
attribution, since an auditable formula did not estimate anything.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.regulatory.infra.versioning import content_hash

__all__ = [
    "DRAFT_DISCLAIMER",
    "AIDecisionRecord",
    "Annex22Error",
    "Annex22Log",
    "Annex22PendingError",
    "DecisionInputs",
    "GovernedResult",
    "RiskLevel",
    "annex22_compliance_checklist",
    "default_annex22_log",
    "governance_context",
    "with_annex22_governance",
]

DRAFT_DISCLAIMER = (
    "Supports the direction of EU GMP DRAFT Annex 22 (July 2025); the Annex is in draft and "
    "NOT in force. This is decision-support governance, not a compliance certification -- do "
    "not represent it as 'Annex 22 compliant'."
)

#: Genesis link for an empty chain (no prior record).
GENESIS_HASH = "sha256:" + "0" * 64


class Annex22Error(RuntimeError):
    """Base class for Annex 22 governance errors."""


class Annex22PendingError(Annex22Error):
    """Raised when a blocked (pending/rejected) governed result is unwrapped."""


class RiskLevel(StrEnum):
    """Annex 22 criticality. Only ``HIGH`` mandates human-in-the-loop review."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def _hitl_required(risk: RiskLevel) -> bool:
    return RiskLevel(risk) == RiskLevel.HIGH


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


# --------------------------------------------------------------------------- #
# The record
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AIDecisionRecord:
    """One immutable, hash-chained AI-decision record (Annex 22 draft schema).

    Every field except :attr:`entry_hash` is bound into :attr:`entry_hash` (a sha256 content
    address that includes :attr:`previous_entry_hash`), so any edit -- to content or to the
    chain links -- is detectable by :meth:`Annex22Log.verify_chain`. Build instances via
    :meth:`create`, which computes the hash; never set ``entry_hash`` by hand.
    """

    timestamp_utc: datetime
    user_id: str
    decision_type: str  # 'cpca_classification', 'm7_class', 'ctd_section', ...
    model_name: str
    model_version: str
    input_smiles: str | None
    input_data_hash: str  # sha256 content address of the inputs
    output: dict[str, Any]  # full model output
    confidence: float  # calibrated 0-1 (1.0 for a deterministic rule-engine decision)
    feature_attribution: dict[str, Any]  # top features / rule-basis that drove the decision
    regulatory_basis: str
    risk_level: str  # 'low' | 'medium' | 'high' (Annex 22 criticality)
    hitl_required: bool  # per risk_level (True iff high)
    previous_entry_hash: str  # hash chain for tamper evidence
    entry_hash: str
    hitl_reviewer_id: str | None = None
    hitl_review_timestamp: datetime | None = None
    hitl_approved: bool | None = None

    @staticmethod
    def _hashed_payload(fields: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(fields)
        out["timestamp_utc"] = _iso(out["timestamp_utc"])
        out["hitl_review_timestamp"] = _iso(out.get("hitl_review_timestamp"))
        return out

    @classmethod
    def create(
        cls,
        *,
        timestamp_utc: datetime,
        user_id: str,
        decision_type: str,
        model_name: str,
        model_version: str,
        input_smiles: str | None,
        input_data_hash: str,
        output: Mapping[str, Any],
        confidence: float,
        feature_attribution: Mapping[str, Any],
        regulatory_basis: str,
        risk_level: str,
        hitl_required: bool,
        previous_entry_hash: str,
        hitl_reviewer_id: str | None = None,
        hitl_review_timestamp: datetime | None = None,
        hitl_approved: bool | None = None,
    ) -> AIDecisionRecord:
        """Build a record and compute its chained ``entry_hash``."""

        fields: dict[str, Any] = {
            "timestamp_utc": timestamp_utc,
            "user_id": user_id,
            "decision_type": decision_type,
            "model_name": model_name,
            "model_version": model_version,
            "input_smiles": input_smiles,
            "input_data_hash": input_data_hash,
            "output": dict(output),
            "confidence": float(confidence),
            "feature_attribution": dict(feature_attribution),
            "regulatory_basis": regulatory_basis,
            "risk_level": str(risk_level),
            "hitl_required": bool(hitl_required),
            "hitl_reviewer_id": hitl_reviewer_id,
            "hitl_review_timestamp": hitl_review_timestamp,
            "hitl_approved": hitl_approved,
            "previous_entry_hash": previous_entry_hash,
        }
        entry_hash = content_hash(cls._hashed_payload(fields))
        return cls(entry_hash=entry_hash, **fields)

    def recompute_hash(self) -> str:
        """Recompute ``entry_hash`` from current field values (for chain verification)."""

        fields = {
            "timestamp_utc": self.timestamp_utc,
            "user_id": self.user_id,
            "decision_type": self.decision_type,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "input_smiles": self.input_smiles,
            "input_data_hash": self.input_data_hash,
            "output": self.output,
            "confidence": self.confidence,
            "feature_attribution": self.feature_attribution,
            "regulatory_basis": self.regulatory_basis,
            "risk_level": self.risk_level,
            "hitl_required": self.hitl_required,
            "hitl_reviewer_id": self.hitl_reviewer_id,
            "hitl_review_timestamp": self.hitl_review_timestamp,
            "hitl_approved": self.hitl_approved,
            "previous_entry_hash": self.previous_entry_hash,
        }
        return content_hash(self._hashed_payload(fields))

    def as_dict(self) -> dict[str, Any]:
        out = self._hashed_payload(
            {
                "timestamp_utc": self.timestamp_utc,
                "user_id": self.user_id,
                "decision_type": self.decision_type,
                "model_name": self.model_name,
                "model_version": self.model_version,
                "input_smiles": self.input_smiles,
                "input_data_hash": self.input_data_hash,
                "output": self.output,
                "confidence": self.confidence,
                "feature_attribution": self.feature_attribution,
                "regulatory_basis": self.regulatory_basis,
                "risk_level": self.risk_level,
                "hitl_required": self.hitl_required,
                "hitl_reviewer_id": self.hitl_reviewer_id,
                "hitl_review_timestamp": self.hitl_review_timestamp,
                "hitl_approved": self.hitl_approved,
                "previous_entry_hash": self.previous_entry_hash,
            }
        )
        out["entry_hash"] = self.entry_hash
        return out


@dataclass(frozen=True)
class DecisionInputs:
    """The governed call's inputs, captured for hashing + the ``input_smiles`` field."""

    input_data_hash: str
    input_smiles: str | None


@dataclass(frozen=True)
class GovernedResult:
    """What a governed function returns: the decision record + the released output (if any).

    ``output`` is the function's real return value when the decision is approved/logged, and
    ``None`` while a high-risk decision is *pending* HITL review (the full output is preserved
    in ``record.output`` for the reviewer). :meth:`unwrap` raises while blocked, which is how a
    downstream consumer (e.g. CTD generation) is prevented from using an unreviewed decision.
    """

    status: str  # 'logged' | 'approved' | 'pending' | 'released' | 'rejected'
    record: AIDecisionRecord
    output: Any | None = None

    @property
    def is_blocked(self) -> bool:
        return self.status in {"pending", "rejected"}

    @property
    def needs_human_review(self) -> bool:
        return self.status == "pending"

    def unwrap(self) -> Any:
        if self.is_blocked:
            raise Annex22PendingError(
                f"decision {self.record.entry_hash} is {self.status}: it requires human review "
                "before its output may be used downstream"
            )
        return self.output


# --------------------------------------------------------------------------- #
# The append-only, hash-chained decision log + HITL workflow
# --------------------------------------------------------------------------- #
def _default_qa_sampler(record: AIDecisionRecord) -> bool:
    """Deterministic ~5% sampler keyed by the entry hash (1 in 20)."""

    hexpart = record.entry_hash.split(":")[-1]
    return int(hexpart[:8], 16) % 20 == 0


class Annex22Log:
    """Append-only, hash-chained log of AI decisions with a human-review workflow.

    Records are immutable and chained; a HITL review is appended as its own record (the chain
    is never mutated), and a decision's approval state is derived from those review records.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _now,
        qa_sampler: Callable[[AIDecisionRecord], bool] = _default_qa_sampler,
    ) -> None:
        self._records: list[AIDecisionRecord] = []
        self._by_hash: dict[str, AIDecisionRecord] = {}
        self._review_of: dict[str, AIDecisionRecord] = {}  # decision entry_hash -> review record
        self._clock = clock
        self._qa_sampler = qa_sampler

    @property
    def head_hash(self) -> str:
        return self._records[-1].entry_hash if self._records else GENESIS_HASH

    def records(self) -> tuple[AIDecisionRecord, ...]:
        return tuple(self._records)

    def get(self, entry_hash: str) -> AIDecisionRecord:
        record = self._by_hash.get(entry_hash)
        if record is None:
            raise Annex22Error(f"unknown entry_hash: {entry_hash!r}")
        return record

    def _append(self, record: AIDecisionRecord) -> AIDecisionRecord:
        self._records.append(record)
        self._by_hash[record.entry_hash] = record
        return record

    # -- recording ------------------------------------------------------------ #
    def record_decision(
        self,
        *,
        user_id: str,
        decision_type: str,
        risk_level: str,
        model_name: str,
        model_version: str,
        inputs: DecisionInputs,
        output: Mapping[str, Any],
        confidence: float,
        feature_attribution: Mapping[str, Any],
        regulatory_basis: str,
        timestamp_utc: datetime | None = None,
    ) -> AIDecisionRecord:
        """Append an AI-decision record, chained to the current head."""

        risk = RiskLevel(risk_level)
        record = AIDecisionRecord.create(
            timestamp_utc=timestamp_utc or self._clock(),
            user_id=user_id,
            decision_type=decision_type,
            model_name=model_name,
            model_version=model_version,
            input_smiles=inputs.input_smiles,
            input_data_hash=inputs.input_data_hash,
            output=output,
            confidence=confidence,
            feature_attribution=feature_attribution,
            regulatory_basis=regulatory_basis,
            risk_level=risk.value,
            hitl_required=_hitl_required(risk),
            previous_entry_hash=self.head_hash,
        )
        return self._append(record)

    # -- human-in-the-loop ---------------------------------------------------- #
    def submit_review(
        self,
        decision_entry_hash: str,
        *,
        reviewer_id: str,
        approved: bool,
        timestamp_utc: datetime | None = None,
    ) -> AIDecisionRecord:
        """Append a HITL review for a high-risk decision (the chain is never mutated).

        The review is itself a chained :class:`AIDecisionRecord` (``decision_type`` suffixed
        ``.hitl_review``) whose ``feature_attribution`` links back to the reviewed decision, so
        the linkage is tamper-evident too.
        """

        decision = self.get(decision_entry_hash)
        if not decision.hitl_required:
            raise Annex22Error(
                f"decision {decision_entry_hash} is {decision.risk_level}-risk and did not "
                "require HITL review"
            )
        if decision_entry_hash in self._review_of:
            raise Annex22Error(f"decision {decision_entry_hash} has already been reviewed")

        ts = timestamp_utc or self._clock()
        review = AIDecisionRecord.create(
            timestamp_utc=ts,
            user_id=reviewer_id,
            decision_type=f"{decision.decision_type}.hitl_review",
            model_name=decision.model_name,
            model_version=decision.model_version,
            input_smiles=decision.input_smiles,
            input_data_hash=decision.input_data_hash,
            output=decision.output,
            confidence=decision.confidence,
            feature_attribution={"hitl_review_of": decision_entry_hash},
            regulatory_basis=decision.regulatory_basis,
            risk_level=decision.risk_level,
            hitl_required=True,
            previous_entry_hash=self.head_hash,
            hitl_reviewer_id=reviewer_id,
            hitl_review_timestamp=ts,
            hitl_approved=bool(approved),
        )
        self._append(review)
        self._review_of[decision_entry_hash] = review
        return review

    def review_for(self, decision_entry_hash: str) -> AIDecisionRecord | None:
        return self._review_of.get(decision_entry_hash)

    def is_approved(self, decision_entry_hash: str) -> bool:
        """A non-high-risk decision is auto-approved; a high-risk one needs an approving review."""

        decision = self.get(decision_entry_hash)
        if not decision.hitl_required:
            return True
        review = self._review_of.get(decision_entry_hash)
        return bool(review and review.hitl_approved)

    def released_output(self, decision_entry_hash: str) -> dict[str, Any]:
        """The decision's output, once approved -- otherwise raise (the downstream gate)."""

        if not self.is_approved(decision_entry_hash):
            raise Annex22PendingError(
                f"decision {decision_entry_hash} is not approved; output is blocked"
            )
        return self.get(decision_entry_hash).output

    def pending(self) -> list[AIDecisionRecord]:
        """High-risk decisions still awaiting a HITL review."""

        return [
            r
            for r in self._records
            if r.hitl_required
            and r.hitl_reviewer_id is None
            and r.entry_hash not in self._review_of
        ]

    def qa_sample(self) -> list[AIDecisionRecord]:
        """The ~5% deterministic QA sample of low-risk decisions for periodic review."""

        return [
            r
            for r in self._records
            if r.risk_level == RiskLevel.LOW.value
            and not r.decision_type.endswith(".hitl_review")
            and self._qa_sampler(r)
        ]

    # -- tamper detection ----------------------------------------------------- #
    def verify_chain(self) -> tuple[bool, list[str]]:
        """Recompute the chain; return ``(ok, breaks)`` where ``breaks`` names the failures.

        Detects content tampering (an entry's recomputed hash no longer matches) and link
        tampering (an entry's ``previous_entry_hash`` no longer points at the prior entry).
        """

        breaks: list[str] = []
        prev = GENESIS_HASH
        for i, record in enumerate(self._records):
            if record.previous_entry_hash != prev:
                breaks.append(
                    f"record[{i}] {record.entry_hash}: "
                    f"previous_entry_hash {record.previous_entry_hash} != expected {prev}"
                )
            recomputed = record.recompute_hash()
            if recomputed != record.entry_hash:
                breaks.append(
                    f"record[{i}]: entry_hash {record.entry_hash} != "
                    f"recomputed {recomputed} (content tampered)"
                )
            prev = record.entry_hash
        return (not breaks, breaks)


# --------------------------------------------------------------------------- #
# Compliance checklist (per the draft's documented expectations)
# --------------------------------------------------------------------------- #
def annex22_compliance_checklist(record: AIDecisionRecord) -> dict[str, bool]:
    """Evaluate the per-decision Annex 22 (draft) documentation checklist for ``record``.

    These attest that the *governance artifacts* are present for one decision; they are NOT an
    assertion that the product is "Annex 22 compliant" (the Annex is draft and not in force).
    """

    return {
        "intended_use_documented": bool(record.decision_type and record.regulatory_basis),
        "model_version_logged": bool(record.model_version),
        # A calibrated confidence value is present (the ECE<3% gate is enforced upstream by the
        # calibration harness in moltrace.spectroscopy.infra.eval; here we attest a value exists).
        "confidence_calibrated": record.confidence is not None and 0.0 <= record.confidence <= 1.0,
        "feature_attribution_computed": bool(record.feature_attribution),
        # For a high-risk decision a HITL opportunity must exist (hitl_required True).
        "hitl_opportunity_for_high_risk": (record.risk_level != RiskLevel.HIGH.value)
        or record.hitl_required,
        "audit_trail_tamper_evident": bool(record.entry_hash and record.previous_entry_hash),
        "regulatory_basis_cited": bool(record.regulatory_basis),
    }


# --------------------------------------------------------------------------- #
# Governance context + the decorator
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _GovernanceContext:
    user_id: str
    log: Annex22Log


_CURRENT: ContextVar[_GovernanceContext | None] = ContextVar("annex22_context", default=None)

#: Process-wide default log used when no :func:`governance_context` is active.
_DEFAULT_LOG = Annex22Log()


def default_annex22_log() -> Annex22Log:
    """The process-wide default :class:`Annex22Log` (used outside a governance context)."""

    return _DEFAULT_LOG


@contextmanager
def governance_context(user_id: str, log: Annex22Log | None = None):
    """Bind the ``user_id`` (and optionally a specific log) for governed calls in this scope."""

    ctx = _GovernanceContext(user_id=user_id, log=log if log is not None else _DEFAULT_LOG)
    token = _CURRENT.set(ctx)
    try:
        yield ctx.log
    finally:
        _CURRENT.reset(token)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "as_dict"):
        return _jsonable(value.as_dict())
    return str(value)


def _looks_like_routed_result(obj: Any) -> bool:
    return all(
        hasattr(obj, a) for a in ("rule_set_version", "model_versions", "citations", "output")
    )


@dataclass(frozen=True)
class _DecisionMeta:
    model_name: str
    model_version: str
    output: dict[str, Any]
    confidence: float
    feature_attribution: dict[str, Any]
    regulatory_basis: str


def _extract_smiles(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> str | None:
    if "smiles" in kwargs and isinstance(kwargs["smiles"], str):
        return kwargs["smiles"]
    payload = kwargs.get("payload") or kwargs.get("data")
    if isinstance(payload, Mapping) and isinstance(payload.get("smiles"), str):
        return payload["smiles"]
    return None


def _default_extract(
    fn: Callable[..., Any],
    result: Any,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> _DecisionMeta:
    """Best-effort extraction of decision metadata from a governed function's result.

    Understands Prompt 13 ``RoutedResult`` (duck-typed), any engine result with ``as_dict()`` +
    ``rule_set_version``, a plain mapping, or an arbitrary object.
    """

    if _looks_like_routed_result(result):
        model_versions = dict(getattr(result, "model_versions", {}) or {})
        citations = list(getattr(result, "citations", ()) or ())
        deterministic = not model_versions
        basis = (
            getattr(citations[0], "source_guidance", None)
            if citations
            else getattr(result, "operation", "") or fn.__name__
        )
        return _DecisionMeta(
            model_name=str(getattr(result, "engine", "") or fn.__name__),
            model_version=str(
                getattr(result, "rule_set_version", None)
                or ";".join(f"{k}={v}" for k, v in sorted(model_versions.items()))
                or "unversioned"
            ),
            output=_jsonable(getattr(result, "output", result)),
            confidence=1.0 if deterministic else float("nan"),
            feature_attribution={
                "engine": getattr(result, "engine", None),
                "citations": [_jsonable(c) for c in citations],
            },
            regulatory_basis=str(basis or fn.__name__),
        )

    if hasattr(result, "as_dict") and hasattr(result, "rule_set_version"):
        return _DecisionMeta(
            model_name=fn.__name__,
            model_version=str(getattr(result, "rule_set_version", None) or "unversioned"),
            output=_jsonable(result),
            confidence=float(getattr(result, "confidence", 1.0)),
            feature_attribution={
                k: getattr(result, k)
                for k in ("basis", "table_reference", "guideline")
                if getattr(result, k, None)
            },
            regulatory_basis=str(getattr(result, "guideline", None) or fn.__name__),
        )

    if isinstance(result, Mapping):
        return _DecisionMeta(
            model_name=str(result.get("model_name", fn.__name__)),
            model_version=str(result.get("model_version", "unversioned")),
            output=_jsonable(result.get("output", result)),
            confidence=float(result.get("confidence", 1.0)),
            feature_attribution=dict(result.get("feature_attribution", {})),
            regulatory_basis=str(result.get("regulatory_basis", fn.__name__)),
        )

    return _DecisionMeta(
        model_name=fn.__name__,
        model_version="unversioned",
        output={"value": _jsonable(result)},
        confidence=1.0,
        feature_attribution={},
        regulatory_basis=fn.__name__,
    )


def with_annex22_governance(
    risk_level: str = "medium",
    *,
    decision_type: str | None = None,
    regulatory_basis: str | None = None,
    model_name: str | None = None,
    log: Annex22Log | None = None,
    extract: Callable[..., _DecisionMeta] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., GovernedResult]]:
    """Decorator that governs an AI-assisted regulatory function under Draft Annex 22.

    The wrapped function returns a :class:`GovernedResult`. For ``risk_level='high'`` the result
    is **pending** (its output is blocked behind HITL review via :meth:`Annex22Log.submit_review`,
    so downstream CTD generation cannot proceed). For ``'low'`` it is logged automatically and a
    deterministic ~5% sample is exposed via :meth:`Annex22Log.qa_sample` for QA review; ``'medium'``
    is logged + approved automatically.

    Compliance checklist per Annex 22 (draft), asserted by :func:`annex22_compliance_checklist`:
    intended use documented, model version logged, calibrated confidence (ECE-gated upstream),
    feature attribution computed, HITL opportunity for high-risk, tamper-evident audit trail
    (hash chain), and regulatory basis cited.
    """

    risk = RiskLevel(risk_level)

    def decorator(fn: Callable[..., Any]) -> Callable[..., GovernedResult]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> GovernedResult:
            ctx = _CURRENT.get()
            target_log = log if log is not None else (ctx.log if ctx else _DEFAULT_LOG)
            user_id = ctx.user_id if ctx else "system"

            result = fn(*args, **kwargs)  # the AI-assisted decision itself

            meta = (extract or _default_extract)(fn, result, args, kwargs)
            inputs = DecisionInputs(
                input_data_hash=content_hash(
                    {"args": _jsonable(args), "kwargs": _jsonable(dict(kwargs))}
                ),
                input_smiles=_extract_smiles(args, kwargs),
            )
            record = target_log.record_decision(
                user_id=user_id,
                decision_type=decision_type or fn.__name__,
                risk_level=risk.value,
                model_name=model_name or meta.model_name,
                model_version=meta.model_version,
                inputs=inputs,
                output=meta.output,
                confidence=meta.confidence,
                feature_attribution=meta.feature_attribution,
                regulatory_basis=regulatory_basis or meta.regulatory_basis,
            )

            if record.hitl_required:
                # High-risk: block the output behind human review.
                return GovernedResult(status="pending", record=record, output=None)
            status = "logged" if risk == RiskLevel.LOW else "approved"
            return GovernedResult(status=status, record=record, output=result)

        wrapper.__annex22_risk_level__ = risk.value  # type: ignore[attr-defined]
        return wrapper

    return decorator
