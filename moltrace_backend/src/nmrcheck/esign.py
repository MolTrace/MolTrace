"""21 CFR Part 11 e-signature binding & manifestation (Security Prompt 11).

The platform already persisted electronic-signature *records* (``ElectronicSignatureRecordORM`` +
``validation_center_store.create_signature``) and gated signing behind a fresh MFA step-up. This
module closes the two Part 11 gaps that remained:

* **§11.70 (signature-to-record linking).** The legacy ``signature_hash`` covered the signer +
  meaning + ``target_id`` but *not the record's content*, so a signature could be transferred to a
  different record/version. ``compute_signature_digest`` binds a SHA-256 ``record_content_hash`` of
  the exact record snapshot into the signed payload, making the signature non-transferable.
* **§11.50 (signature manifestation).** ``build_manifestation`` / ``render_manifestation_html``
  produce the durable, human-readable manifestation (printed name, UTC date/time, meaning) that
  rides on the record and its inspection / printable copy.

The module is intentionally pure — no DB, no FastAPI, no model imports — mirroring
``audit_chain.py``'s keyless-canonical-hash style so behaviour is identical across the codebase and
the logic stays off the parallel-session-contended shared files. Identity (``signer_user_id`` /
``signer_display_name``) is supplied by the caller from the authenticated server principal, never
from the client (the §11.100 attribution fix lives at the call site in the route).

Grounded framing: MolTrace *supports* Part 11; configuration, identity governance, and validation
remain the customer's responsibility.
"""

from __future__ import annotations

import hashlib
import hmac
import html as _html
import json
from datetime import UTC, datetime
from typing import Any

SIGNATURE_HASH_PREFIX = "sha256:"

# Human-readable manifestation labels per signature meaning. Kept parallel to the
# ``SignatureMeaning`` Literal in ``models.py`` so this module needs no model import; the route
# layer validates the meaning against that Literal before it reaches here.
_MEANING_LABELS: dict[str, str] = {
    "reviewed": "Reviewed by",
    "approved": "Approved by",
    "rejected": "Rejected by",
    "authored": "Authored by",
    "verified": "Verified by",
    "released": "Released by",
    "locked": "Locked by",
    "override": "Overridden by",
    "other": "Signed by",
}

_COMPLIANCE_NOTICE = (
    "Supports 21 CFR Part 11 §11.50 signature manifestation. Configuration, identity "
    "governance, and validation remain the customer's responsibility."
)


# --------------------------------------------------------------------------- canonical hashing


def _iso_utc(dt: datetime | None) -> str | None:
    """UTC-ISO with explicit None handling — same normalization as ``audit_chain._iso_utc`` so a
    SQLite (naive, assumed-UTC) and a Postgres (tz-aware) timestamp hash identically."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _canon(payload: dict[str, Any]) -> bytes:
    """Deterministic JSON (sorted keys, no whitespace) — identical to ``audit_chain._canon``."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def compute_record_content_hash(content: dict[str, Any] | str) -> str:
    """SHA-256 over a canonical snapshot of the exact record being signed -> ``sha256:`` + hex.

    Pass a dict (preferred — canonicalized) or an already-serialized string. This is the §11.70
    binding: a signature digest computed over this value cannot be transferred to a different
    record or a later version of the same record, because the content hash would no longer match.
    The snapshot MUST be a deterministic, business-meaningful field set for the record type — never
    include volatile fields (``updated_at``, derived counts) or verification will spuriously fail.
    """
    raw = content.encode("utf-8") if isinstance(content, str) else _canon(content)
    return SIGNATURE_HASH_PREFIX + hashlib.sha256(raw).hexdigest()


def canonical_signature_payload(
    *,
    signer_user_id: int | None,
    signer_email: str | None,
    signer_display_name: str | None,
    signature_meaning: str,
    target_type: str,
    target_id: int,
    record_content_hash: str | None,
    reason: str,
    signed_at: datetime | str | None,
    step_up_factor: str | None = None,
    step_up_aal: str | None = None,
) -> dict[str, Any]:
    """The exact fields covered by the content-bound signature digest, in reproducible form.

    ``record_content_hash`` is the load-bearing §11.70 binding; ``signer_user_id`` is the §11.100
    server-principal attribution. ``signed_at`` accepts a datetime (normalized to UTC-ISO) or an
    already-ISO string (used by verification, which reads the persisted ISO value back)."""
    signed_at_iso = (
        signed_at if isinstance(signed_at, str) or signed_at is None else _iso_utc(signed_at)
    )
    return {
        "signer_user_id": signer_user_id,
        "signer_email": signer_email,
        "signer_display_name": signer_display_name,
        "signature_meaning": signature_meaning,
        "target_type": target_type,
        "target_id": target_id,
        "record_content_hash": record_content_hash,
        "reason": reason,
        "signed_at": signed_at_iso,
        "step_up_factor": step_up_factor,
        "step_up_aal": step_up_aal,
    }


def compute_signature_digest(payload: dict[str, Any]) -> str:
    """``sha256:`` + hex digest of the canonical signature payload (the content-bound signature)."""
    return SIGNATURE_HASH_PREFIX + hashlib.sha256(_canon(payload)).hexdigest()


def verify_signature(
    stored: dict[str, Any], *, recomputed_content_hash: str | None = None
) -> dict[str, Any]:
    """Re-derive the digest from the stored binding fields and compare (detects row tampering).

    When ``recomputed_content_hash`` is supplied, also confirm the signature still binds the
    *current* record content (detects record mutation after signing — §11.70 non-transferability).

    ``stored`` is a plain dict carrying the binding fields plus ``signature_digest``. Returns
    ``{bound, valid, hash_matches, content_matches, reason}``:

    * ``bound=False`` — a legacy signature written before content binding existed; nothing can be
      cryptographically verified, so ``valid``/``hash_matches``/``content_matches`` are ``None``
      and ``reason="legacy_unbound_signature"`` (honest: not tampered, just unverifiable).
    * ``bound=True`` — ``hash_matches`` is the constant-time digest comparison; ``content_matches``
      is ``True``/``False`` when a current content hash was supplied (``None`` if not, or if the
      stored row carries no bound hash). ``valid`` is the conjunction.
    """
    stored_digest = stored.get("signature_digest")
    if not stored_digest:
        return {
            "bound": False,
            "valid": None,
            "hash_matches": None,
            "content_matches": None,
            "reason": "legacy_unbound_signature",
        }
    payload = canonical_signature_payload(
        signer_user_id=stored.get("signer_user_id"),
        signer_email=stored.get("signer_email"),
        signer_display_name=stored.get("signer_display_name") or stored.get("signer_name"),
        signature_meaning=stored.get("signature_meaning"),
        target_type=stored.get("target_type"),
        target_id=stored.get("target_id"),
        record_content_hash=stored.get("record_content_hash"),
        reason=stored.get("reason"),
        signed_at=stored.get("signed_at"),
        step_up_factor=stored.get("step_up_factor"),
        step_up_aal=stored.get("step_up_aal"),
    )
    recomputed = compute_signature_digest(payload)
    hash_matches = hmac.compare_digest(recomputed, str(stored_digest))
    content_matches: bool | None = None
    if recomputed_content_hash is not None:
        bound_hash = stored.get("record_content_hash")
        if bound_hash is not None:
            content_matches = hmac.compare_digest(str(bound_hash), str(recomputed_content_hash))
    valid = bool(hash_matches) and content_matches is not False
    if not hash_matches:
        reason = "digest_mismatch"
    elif content_matches is False:
        reason = "record_content_changed"
    else:
        reason = "ok"
    return {
        "bound": True,
        "valid": valid,
        "hash_matches": hash_matches,
        "content_matches": content_matches,
        "reason": reason,
    }


# --------------------------------------------------------------------------- manifestation (§11.50)


def _human_meaning(meaning: str) -> str:
    return _MEANING_LABELS.get(meaning, "Signed by")


def build_manifestation(
    *,
    signer_display_name: str | None,
    signer_email: str | None,
    signature_meaning: str,
    reason: str,
    signed_at: datetime | str | None,
    target_type: str,
    target_id: int,
    record_content_hash: str | None,
    signature_digest: str | None,
    authentication_method: str | None = None,
    step_up_factor: str | None = None,
    step_up_aal: str | None = None,
) -> dict[str, Any]:
    """Structured §11.50 manifestation: printed name, meaning, UTC date/time, bound-record hash."""
    label = _human_meaning(signature_meaning)
    signed_at_iso = (
        signed_at if isinstance(signed_at, str) or signed_at is None else _iso_utc(signed_at)
    )
    bound_desc = record_content_hash or "unbound (legacy signature)"
    email_suffix = f" <{signer_email}>" if signer_email else ""
    attestation = (
        f"{label} {signer_display_name or 'unknown signer'}{email_suffix} — "
        f"meaning: {signature_meaning}; signed (UTC) {signed_at_iso}; "
        f"bound to {target_type}#{target_id} content {bound_desc}."
    )
    return {
        "printed_name": signer_display_name,
        "signer_email": signer_email,
        "signature_meaning": signature_meaning,
        "meaning_label": label,
        "signed_at_utc": signed_at_iso,
        "reason": reason,
        "target_type": target_type,
        "target_id": target_id,
        "record_content_hash": record_content_hash,
        "signature_digest": signature_digest,
        "authentication_method": authentication_method,
        "step_up_factor": step_up_factor,
        "step_up_aal": step_up_aal,
        "attestation_text": attestation,
        "compliance_notice": _COMPLIANCE_NOTICE,
    }


def render_manifestation_html(manifestation: dict[str, Any]) -> str:
    """A self-contained ``<section>`` block (no external CSS) suitable to append to any report HTML
    or print to PDF via the browser — the durable §11.50 stamp on the inspection copy."""

    def esc(value: Any) -> str:
        return _html.escape(str(value)) if value not in (None, "") else "&mdash;"

    meaning = f"{esc(manifestation.get('meaning_label'))} ({esc(manifestation.get('signature_meaning'))})"  # noqa: E501
    bound = f"{esc(manifestation.get('target_type'))} #{esc(manifestation.get('target_id'))}"
    rows: list[tuple[str, str]] = [
        ("Signed by", esc(manifestation.get("printed_name"))),
        ("Email", esc(manifestation.get("signer_email"))),
        ("Meaning", meaning),
        ("Date / time (UTC)", esc(manifestation.get("signed_at_utc"))),
        ("Reason", esc(manifestation.get("reason"))),
        ("Bound record", bound),
        ("Record content hash", esc(manifestation.get("record_content_hash"))),
        ("Signature digest", esc(manifestation.get("signature_digest"))),
        ("Authentication", esc(manifestation.get("authentication_method"))),
    ]
    row_html = "".join(
        f'<tr><th style="text-align:left;padding:2px 12px 2px 0;white-space:nowrap;'
        f'vertical-align:top;font-weight:600">{label}</th>'
        f'<td style="padding:2px 0;word-break:break-all">{value}</td></tr>'
        for label, value in rows
    )
    attestation = esc(manifestation.get("attestation_text"))
    notice = esc(manifestation.get("compliance_notice"))
    return (
        '<section class="mt-esign-manifestation" '
        'style="border:1px solid #cbd5e1;border-radius:8px;padding:12px 16px;margin:16px 0;'
        'font-family:system-ui,Segoe UI,Roboto,sans-serif;font-size:13px;color:#0f172a">'
        '<h3 style="margin:0 0 8px;font-size:14px">Electronic signature</h3>'
        f'<table style="border-collapse:collapse">{row_html}</table>'
        f'<p style="margin:10px 0 4px;font-style:italic">{attestation}</p>'
        f'<p style="margin:0;font-size:11px;color:#475569">{notice}</p>'
        "</section>"
    )
