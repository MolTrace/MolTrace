"""GAMP 5 / CSA validation-lifecycle package + change-control gate (Security Prompt 13).

The Validation Center already holds the full requirement->risk->test->execution chain
(``validation_center_store.generate_traceability``) and binds CI test/risk summaries into a
content-bound §11.70 release signature (P11). This module adds the two remaining pieces, kept pure
(no DB / no FastAPI, mirroring ``alcoa.py``) so they stay off the parallel-session-contended files:

* **Regenerable validation package** — ``assemble_validation_package`` bundles already-loaded
  Validation Center data into one deterministic, self-describing artifact per release (traceability
  + IQ/OQ/PQ-from-CI evidence + risk summary + change-control state + release signatures), so each
  release ships a re-runnable validation package.
* **Validated-state change control** — ``assert_change_control`` makes a change to a validated-state
  record (an approved project, or one attached to an approved/released system release) require a
  reason-for-change (GAMP 5 §14 / Annex 11), reusing the P12 ``alcoa.require_reason_for_change``.

Grounded framing: these controls *support* a customer's GAMP 5 / CSA effort (accelerate IQ/OQ/PQ
evidence assembly + change control); they do not perform or replace the customer's CSV.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import alcoa

PACKAGE_SCHEMA_VERSION = "1.0"

SUPPORTS_NOTICE = (
    "This validation package SUPPORTS a customer's GAMP 5 / CSA effort by assembling the existing "
    "requirement->risk->test traceability and CI test evidence into one regenerable artifact. It "
    "does not perform or replace the customer's computerized-system validation (CSV), IQ/OQ/PQ "
    "execution, or sign-off — those remain the customer's responsibility."
)

# Project / release states that make the validated baseline change-controlled.
VALIDATED_PROJECT_STATUSES: frozenset[str] = frozenset({"approved", "archived"})
VALIDATED_RELEASE_STATUSES: frozenset[str] = frozenset({"approved", "released"})


class ValidatedStateChangeError(ValueError):
    """Raised when a validated-state record is changed without a reason-for-change (GAMP 5 §14)."""


# --------------------------------------------------------------------------- change-control gate


def is_validated_state(project_status: str | None, linked_release_status: str | None) -> bool:
    """True if the project is itself approved/archived OR is attached to an approved/released
    release — i.e. a validated baseline whose changes must be controlled."""
    return (project_status or "") in VALIDATED_PROJECT_STATUSES or (
        linked_release_status or ""
    ) in VALIDATED_RELEASE_STATUSES


def assert_change_control(
    project_status: str | None,
    linked_release_status: str | None,
    reason: str | None,
) -> str | None:
    """GAMP 5 §14 / Annex 11 change control. When the record is in a validated state, a change
    requires a non-empty reason-for-change (reuses the P12 ALCOA+ primitive) — returns the
    normalized reason. When not validated, returns None and imposes nothing (draft / in-progress
    projects stay freely mutable). Raises ``ValidatedStateChangeError`` if a reason is missing in a
    validated state."""
    if not is_validated_state(project_status, linked_release_status):
        return None
    try:
        return alcoa.require_reason_for_change(reason)
    except alcoa.ReasonForChangeRequired as exc:
        raise ValidatedStateChangeError(
            "This validation project is in a validated state; a reason_for_change is required for "
            "any modification (GAMP 5 change control)."
        ) from exc


# --------------------------------------------------------------------------- package assembler


def _iso(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _evidence_section(test_summary: dict[str, Any] | None) -> dict[str, Any]:
    """Map the CI test summary onto the IQ/OQ/PQ qualification slots. OQ (operational
    qualification) is the functional/automated-test evidence; IQ (installation) and PQ
    (performance-in-use) are honestly marked customer-supplied rather than fabricated."""
    ts = test_summary or {}
    has_oq = bool(ts)
    passed = ts.get("passed")
    failed = ts.get("failed")
    oq_status = "not_provided"
    if has_oq:
        oq_status = "fail" if (failed or 0) else "pass"
    return {
        "iq": {
            "status": "customer_supplied",
            "note": "Installation Qualification (environment/install) is the customer's remit.",
        },
        "oq": {
            "status": oq_status,
            "source": "ci_test_summary",
            "passed": passed,
            "failed": failed,
            "skipped": ts.get("skipped"),
            "duration_s": ts.get("duration_s"),
            "coverage_pct": ts.get("coverage_pct"),
            "evidence": ts if has_oq else None,
        },
        "pq": {
            "status": "customer_supplied",
            "note": "Performance Qualification (performance-in-use) is the customer's remit.",
        },
    }


def assemble_validation_package(
    components: dict[str, Any], *, generated_at: datetime
) -> dict[str, Any]:
    """Assemble a deterministic validation package from already-loaded Validation Center data.

    ``components`` (all plain dicts/lists, server-loaded — this function never touches a DB):
      project, release (or None), traceability (latest matrix dict or None), signatures (list of
      manifestation dicts), test_summary (CI evidence dict or None), risk_summary (dict or None),
      deviation_summary (dict), counts (dict).

    Output is byte-stable across regenerations except ``package_metadata.generated_at`` — all id
    lists / section keys are sorted upstream and emitted in fixed order."""
    project = components.get("project") or {}
    release = components.get("release")
    traceability = components.get("traceability")
    signatures = components.get("signatures") or []
    deviation_summary = components.get("deviation_summary") or {}
    counts = components.get("counts") or {}

    project_status = project.get("status")
    release_status = release.get("approval_status") if release else None
    validated = is_validated_state(project_status, release_status)

    if traceability is not None:
        traceability_section = {
            "status": traceability.get("status"),
            "matrix": traceability.get("matrix_json"),
            "coverage_summary": traceability.get("coverage_summary_json"),
            "missing_coverage": traceability.get("missing_coverage_json"),
            "generated_at": _iso(traceability.get("generated_at")),
        }
    else:
        traceability_section = {
            "status": "no_traceability_generated",
            "note": "No traceability matrix has been generated for the linked validation project.",
        }

    return {
        "package_metadata": {
            "package_schema_version": PACKAGE_SCHEMA_VERSION,
            "generated_at": _iso(generated_at),
            "release_id": release.get("id") if release else None,
            "release_version": release.get("release_version") if release else None,
            "validation_project_id": project.get("id"),
            "git_sha": (components.get("test_summary") or {}).get("git_sha"),
        },
        "requirement_risk_test_traceability": traceability_section,
        "iq_oq_pq_evidence": _evidence_section(components.get("test_summary")),
        "risk_summary": components.get("risk_summary")
        or (release.get("risk_summary_json") if release else None),
        "change_control_state": {
            "project_status": project_status,
            "release_status": release_status,
            "validated": validated,
            "change_controlled": validated,
            "open_deviation_count": deviation_summary.get("open_count", 0),
            "counts": counts,
        },
        "signatures": signatures,
        "notice": SUPPORTS_NOTICE,
    }
