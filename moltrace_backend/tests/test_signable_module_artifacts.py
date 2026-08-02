"""Each product has an artifact a signature is actually bound to (§11.70).

An electronic signature is only worth anything if it is bound to *what was signed*. Until now only
controlled records and system releases had a server-side content snapshot, so signing a
SpectraCheck evidence report — the flagship product's whole deliverable — produced a deliberately
**unbound** signature. Honest, but a thin Part 11 story for the one artifact customers care about.

The artifacts made bindable here are point-in-time reports, not the living records behind them.
You do not sign a dossier or a session; they keep changing. You sign the report generated from one
at a moment in time.

What these tests pin is the property that makes a binding meaningful: a signature over unchanged
content re-verifies, and a signature over changed content does not.
"""

import pytest
from fastapi.testclient import TestClient

from nmrcheck import validation_center_store as vc


def _project_sample_session(client: TestClient, headers: dict) -> dict:
    project = client.post("/projects", headers=headers, json={"name": "Signable"})
    assert project.status_code == 201, project.text
    sample = client.post(
        f"/projects/{project.json()['id']}/samples",
        headers=headers,
        json={"sample_id": "MT-SIGN-001", "display_name": "Fraction A"},
    )
    assert sample.status_code == 201, sample.text
    session = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project.json()["id"],
            "sample_pk": sample.json()["id"],
            "sample_id": sample.json()["sample_id"],
            "title": "Signable session",
        },
    )
    assert session.status_code == 201, session.text
    return session.json()


def _report(client: TestClient, headers: dict, session_id: int, verdict: str = "pass") -> dict:
    res = client.post(
        f"/spectracheck/sessions/{session_id}/reports",
        headers=headers,
        json={
            "report_title": "Evidence report",
            "report_json": {"verdict": verdict, "purity_percent": 99.1},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_a_spectracheck_report_is_bindable(app, client, api_headers):
    """The flagship deliverable now has a real content binding rather than an unbound signature."""
    with client:
        session = _project_sample_session(client, api_headers)
        report = _report(client, api_headers, session["id"])

    with app.state.session_factory() as db:
        content_hash = vc._resolve_record_content_hash(db, "spectracheck_report", report["id"])
    assert content_hash, "a signable report must resolve to a content hash"


def test_the_binding_actually_tracks_the_report_contents(app, client, api_headers):
    """The property that makes a binding worth having: different content, different hash.

    Two reports whose bodies differ must not share a content hash, or a signature over one would
    verify against the other.
    """
    with client:
        session = _project_sample_session(client, api_headers)
        first = _report(client, api_headers, session["id"], verdict="pass")
        second = _report(client, api_headers, session["id"], verdict="fail")

    with app.state.session_factory() as db:
        first_hash = vc._resolve_record_content_hash(db, "spectracheck_report", first["id"])
        second_hash = vc._resolve_record_content_hash(db, "spectracheck_report", second["id"])
    assert first_hash and second_hash
    assert first_hash != second_hash


def test_the_binding_is_stable_across_the_report_lifecycle(app, client, api_headers):
    """A signed report still moves through its normal lifecycle. Recomputing the snapshot must
    give the same answer, or a status change would retroactively invalidate a real signature."""
    with client:
        session = _project_sample_session(client, api_headers)
        report = _report(client, api_headers, session["id"])

    with app.state.session_factory() as db:
        before = vc._resolve_record_content_hash(db, "spectracheck_report", report["id"])

    with app.state.session_factory() as db:
        from nmrcheck.orm import SpectraCheckReportRecordORM

        row = db.get(SpectraCheckReportRecordORM, report["id"])
        row.status = "released"
        db.commit()

    with app.state.session_factory() as db:
        after = vc._resolve_record_content_hash(db, "spectracheck_report", report["id"])
    assert before == after, "the report lifecycle must not invalidate an existing signature"


def test_a_missing_bindable_record_resolves_to_nothing(app):
    """A bindable type with no record must not quietly mint an unbound signature — the caller
    treats None for a bindable type as not-found."""
    with app.state.session_factory() as db:
        assert vc._resolve_record_content_hash(db, "spectracheck_report", 999_999) is None
        assert (
            vc._resolve_record_content_hash(db, "regulatory_readiness_report", 999_999) is None
        )


@pytest.mark.parametrize(
    "target_type", ["controlled_record", "system_release", "spectracheck_report", "regulatory_readiness_report"]
)
def test_each_product_has_a_bindable_artifact(target_type):
    assert target_type in vc._BINDABLE_TARGET_TYPES


def test_an_unsupported_target_is_still_stored_unbound_rather_than_pretending(app):
    """Unchanged, and deliberately so: a type with no server-side snapshot is honest about having
    no binding instead of inventing one."""
    with app.state.session_factory() as db:
        assert vc._resolve_record_content_hash(db, "compound_batch", 1) is None
    assert "compound_batch" not in vc._BINDABLE_TARGET_TYPES
