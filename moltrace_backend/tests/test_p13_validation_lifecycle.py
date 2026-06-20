"""GAMP 5 / CSA validation lifecycle (Security Prompt 13).

Most of the lifecycle was already shipped (the Validation Center's requirement->risk->test->execution
chain + content-bound release signatures). This covers the genuine additions:
  * a regenerable validation package assembled per release (traceability + IQ/OQ/PQ-from-CI evidence
    + change-control state + release signatures);
  * a validated-state change-control gate (a change to an approved / approved-release-linked project
    requires a reason-for-change);
  * a CI-evidence ingestion seam (refused once the release is approved/released).
Store-level + pure-unit tests (the HTTP routes are added in a separate, contention-safe pass).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nmrcheck import validation_center_store as vcs
from nmrcheck import validation_package as vp
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.models import (
    SystemReleaseApproveRequest,
    SystemReleaseRecordCreate,
    UserRequirementSpecificationCreate,
    ValidationProjectCreate,
    ValidationProjectUpdate,
    ValidationRiskAssessmentCreate,
    ValidationTestCaseCreate,
    ValidationTestProtocolCreate,
)
from nmrcheck.settings import Settings


def _app(tmp_path):
    app = create_app(
        Settings(database_url=f"sqlite:///{tmp_path / 'p13.sqlite3'}", api_key="k")
    )
    init_db(app.state.session_factory)
    return app


def _sf(tmp_path):
    return _app(tmp_path).state.session_factory


def _project(sf):
    return vcs.create_validation_project(
        sf,
        ValidationProjectCreate(
            title="SpectraCheck CSV",
            scope="full_platform",
            validation_type="change_validation",
            intended_use="GxP analytical review",
        ),
    )


def _urs(sf, project_id, code="URS-1", **meta):
    return vcs.create_urs(
        sf,
        project_id,
        UserRequirementSpecificationCreate(
            requirement_code=code,
            module="spectracheck",
            requirement_text="The system shall record reviewer identity.",
            criticality="high",
            gxp_impact="direct",
            metadata_json=meta,
        ),
    )


def _release(sf, project_id, *, summaries=True, version="1.0.0"):
    return vcs.create_system_release(
        sf,
        SystemReleaseRecordCreate(
            release_version=version,
            release_type="backend",
            change_summary="initial",
            validation_project_id=project_id,
            test_summary_json={"passed": 10, "failed": 0} if summaries else {},
            risk_summary_json={"high": 0} if summaries else {},
        ),
    )


# --------------------------------------------------------------------------- pure unit


def test_change_control_truth_table():
    assert vp.is_validated_state("approved", None) is True
    assert vp.is_validated_state("draft", None) is False
    assert vp.is_validated_state("draft", "released") is True
    assert vp.assert_change_control("draft", None, None) is None  # not validated -> no reason
    assert vp.assert_change_control("approved", None, "  fix typo  ") == "fix typo"
    with pytest.raises(vp.ValidatedStateChangeError):
        vp.assert_change_control("approved", None, "   ")


def test_assemble_package_deterministic_and_honest():
    ts = datetime(2026, 6, 20, tzinfo=UTC)
    comp = {
        "project": {"id": 1, "status": "approved"},
        "release": {"id": 9, "approval_status": "approved", "release_version": "1.0", "risk_summary_json": {"high": 0}},
        "traceability": {"status": "complete", "matrix_json": {"rows": []}, "coverage_summary_json": {}, "missing_coverage_json": [], "generated_at": ts},
        "signatures": [{"printed_name": "qa@x.co"}],
        "test_summary": {"passed": 10, "failed": 0, "git_sha": "abc"},
        "deviation_summary": {"open_count": 0, "total_count": 0},
        "counts": {"requirements": 1},
    }
    p1 = vp.assemble_validation_package(comp, generated_at=ts)
    p2 = vp.assemble_validation_package(comp, generated_at=ts)
    assert p1 == p2  # deterministic modulo generated_at (here equal)
    assert p1["iq_oq_pq_evidence"]["oq"]["status"] == "pass"
    assert p1["iq_oq_pq_evidence"]["iq"]["status"] == "customer_supplied"  # honest, not fabricated
    assert p1["change_control_state"]["validated"] is True
    assert p1["package_metadata"]["git_sha"] == "abc"
    assert "SUPPORTS" in p1["notice"]
    fail = vp.assemble_validation_package({**comp, "test_summary": {"passed": 8, "failed": 2}}, generated_at=ts)
    assert fail["iq_oq_pq_evidence"]["oq"]["status"] == "fail"
    none_tr = vp.assemble_validation_package({**comp, "traceability": None}, generated_at=ts)
    assert none_tr["requirement_risk_test_traceability"]["status"] == "no_traceability_generated"


# --------------------------------------------------------------------------- regenerable package


def test_build_validation_package_assembles_release(tmp_path):
    sf = _sf(tmp_path)
    project = _project(sf)
    req = _urs(sf, project.id)
    vcs.create_risk_assessment(
        sf,
        project.id,
        ValidationRiskAssessmentCreate(
            target_type="requirement",
            target_id=req.id,
            risk_description="Reviewer identity could be lost.",
            severity="high",
            probability="medium",
            detectability="medium",
            mitigation="Server-side attribution + audit chain.",
            testing_rigor="automated",
        ),
    )
    protocol = vcs.create_test_protocol(
        sf,
        project.id,
        ValidationTestProtocolCreate(
            protocol_code="OQ-1", title="OQ", module="spectracheck", protocol_type="operational"
        ),
    )
    vcs.create_test_case(
        sf,
        protocol.id,
        ValidationTestCaseCreate(
            test_case_code="TC-1",
            title="reviewer identity recorded",
            preconditions="logged in",
            expected_results="identity stored",
            linked_requirement_ids_json=[req.id],
        ),
    )
    vcs.generate_traceability(sf, project.id)
    release = _release(sf, project.id)
    vcs.approve_system_release(
        sf, release.id, SystemReleaseApproveRequest(signer_name="QA Lead", reason="approved", release=True)
    )

    pkg = vcs.build_validation_package(sf, release.id)
    assert pkg["package_metadata"]["release_version"] == "1.0.0"
    assert pkg["requirement_risk_test_traceability"]["status"] in ("complete", "gaps_identified")
    assert pkg["iq_oq_pq_evidence"]["oq"]["passed"] == 10
    assert pkg["change_control_state"]["validated"] is True
    assert pkg["change_control_state"]["counts"]["requirements"] == 1
    # the release approval signature manifestation is embedded
    assert pkg["signatures"] and pkg["signatures"][0]["target_type"] == "system_release"


def test_build_package_no_project_is_honest(tmp_path):
    sf = _sf(tmp_path)
    release = vcs.create_system_release(
        sf,
        SystemReleaseRecordCreate(
            release_version="9.9.9", release_type="backend", change_summary="no project",
            test_summary_json={"passed": 1}, risk_summary_json={"high": 0},
        ),
    )
    pkg = vcs.build_validation_package(sf, release.id)
    assert pkg["requirement_risk_test_traceability"]["status"] == "no_traceability_generated"
    assert pkg["change_control_state"]["validated"] is False


# --------------------------------------------------------------------------- change-control gate


def test_change_control_gate_on_approved_project(tmp_path):
    sf = _sf(tmp_path)
    project = _project(sf)
    _urs(sf, project.id, code="URS-DRAFT")  # draft project: freely mutable, no reason needed
    vcs.update_validation_project(sf, project.id, ValidationProjectUpdate(status="approved"))
    # Now validated: a child mutation without a reason is blocked...
    with pytest.raises(vcs.ValidationCenterError):
        _urs(sf, project.id, code="URS-2")
    # ...and succeeds with a reason_for_change in metadata_json.
    created = _urs(sf, project.id, code="URS-2", reason_for_change="Add missing requirement (CR-42).")
    assert created.requirement_code == "URS-2"


def test_change_control_gate_via_linked_approved_release(tmp_path):
    sf = _sf(tmp_path)
    project = _project(sf)  # stays 'draft'
    release = _release(sf, project.id)
    vcs.approve_system_release(
        sf, release.id, SystemReleaseApproveRequest(signer_name="QA", reason="approved", release=True)
    )
    # Project is draft but has an approved release -> validated baseline; child mutation gated.
    with pytest.raises(vcs.ValidationCenterError):
        vcs.create_test_protocol(
            sf,
            project.id,
            ValidationTestProtocolCreate(
                protocol_code="P-2", title="late", module="spectracheck", protocol_type="operational"
            ),
        )
    ok = vcs.create_test_protocol(
        sf,
        project.id,
        ValidationTestProtocolCreate(
            protocol_code="P-2", title="late", module="spectracheck", protocol_type="operational",
            metadata_json={"reason_for_change": "Post-release protocol addition (CR-7)."},
        ),
    )
    assert ok.protocol_code == "P-2"


def test_draft_project_is_freely_mutable(tmp_path):
    sf = _sf(tmp_path)
    project = _project(sf)
    # No reason required while draft.
    assert _urs(sf, project.id, code="A").requirement_code == "A"
    assert _urs(sf, project.id, code="B").requirement_code == "B"


# --------------------------------------------------------------------------- CI evidence ingestion


def test_ingest_evidence_then_blocked_after_approval(tmp_path):
    sf = _sf(tmp_path)
    project = _project(sf)
    release = _release(sf, project.id, summaries=False)
    updated = vcs.ingest_release_evidence(
        sf,
        release.id,
        test_summary_json={"passed": 42, "failed": 0, "duration_s": 12.3},
        risk_summary_json={"high": 0, "medium": 2},
        source="ci",
    )
    assert updated.test_summary_json["passed"] == 42
    vcs.approve_system_release(
        sf, release.id, SystemReleaseApproveRequest(signer_name="QA", reason="approved", release=True)
    )
    # Once approved, the §11.70-bound evidence snapshot is change-controlled.
    with pytest.raises(vcs.ValidationCenterError):
        vcs.ingest_release_evidence(
            sf, release.id, test_summary_json={"passed": 1}, risk_summary_json={"high": 9}
        )


# --------------------------------------------------------------------------- HTTP routes


def test_routes_evidence_and_package(tmp_path):
    app = _app(tmp_path)
    sf = app.state.session_factory
    project = _project(sf)
    release = _release(sf, project.id, summaries=False)
    with TestClient(app) as client:
        headers = {"x-api-key": "k"}
        ingested = client.post(
            f"/system-releases/{release.id}/evidence",
            headers=headers,
            json={"test_summary_json": {"passed": 5, "failed": 0}, "risk_summary_json": {"high": 0}},
        )
        assert ingested.status_code == 200, ingested.text
        assert ingested.json()["test_summary_json"]["passed"] == 5
        pkg = client.get(f"/system-releases/{release.id}/validation-package", headers=headers)
        assert pkg.status_code == 200, pkg.text
        body = pkg.json()
        assert body["iq_oq_pq_evidence"]["oq"]["passed"] == 5
        assert "SUPPORTS" in body["notice"]
        assert client.get("/system-releases/999999/validation-package", headers=headers).status_code == 404


def test_change_control_gate_via_http(tmp_path):
    app = _app(tmp_path)
    sf = app.state.session_factory
    project = _project(sf)
    vcs.update_validation_project(sf, project.id, ValidationProjectUpdate(status="approved"))
    with TestClient(app) as client:
        headers = {"x-api-key": "k"}
        body = {
            "requirement_code": "URS-HTTP",
            "module": "spectracheck",
            "requirement_text": "recorded",
            "criticality": "high",
            "gxp_impact": "direct",
        }
        blocked = client.post(
            f"/validation-center/projects/{project.id}/urs", headers=headers, json=body
        )
        assert blocked.status_code == 400, blocked.text  # change control: reason required
        ok = client.post(
            f"/validation-center/projects/{project.id}/urs",
            headers=headers,
            json={**body, "metadata_json": {"reason_for_change": "Post-approval addition (CR-9)."}},
        )
        assert ok.status_code == 201, ok.text
