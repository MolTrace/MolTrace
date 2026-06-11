from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project_session_report(client: TestClient, headers: dict[str, str]):
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "Collaboration Project"},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "COLLAB-001", "solvent": "CDCl3"},
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()

    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "Collaboration review session",
        },
    )
    assert session_res.status_code == 201, session_res.text
    session = session_res.json()

    evidence_res = client.post(
        f"/spectracheck/sessions/{session['id']}/evidence",
        headers=headers,
        json={
            "layer": "predicted_nmr",
            "title": "Predicted NMR",
            "source_tab": "spectracheck",
            "status": "ready",
            "response_json": {"sample_id": sample["sample_id"]},
        },
    )
    assert evidence_res.status_code == 201, evidence_res.text
    evidence = evidence_res.json()

    report_res = client.post(
        f"/spectracheck/sessions/{session['id']}/reports",
        headers=headers,
        json={
            "report_title": "Human review report",
            "report_json": {
                "sample_id": sample["sample_id"],
                "summary": "Review draft; not identity confirmation.",
            },
        },
    )
    assert report_res.status_code == 201, report_res.text
    report = report_res.json()
    return project, sample, session, evidence, report


def test_collaboration_rbac_human_review_workflow_and_audit(client, api_headers):
    with client:
        owner_headers = _sign_up(client, "owner@example.com")
        viewer_headers = _sign_up(client, "viewer@example.com")
        reviewer_headers = _sign_up(client, "reviewer@example.com")
        project, _sample, session, evidence, report = _create_project_session_report(
            client,
            owner_headers,
        )

        org_res = client.post(
            "/organizations",
            headers=owner_headers,
            json={"name": "Review Org", "metadata_json": {"suite": "collaboration"}},
        )
        assert org_res.status_code == 201, org_res.text
        organization = org_res.json()
        assert organization["metadata_json"]["suite"] == "collaboration"

        member_res = client.post(
            f"/organizations/{organization['id']}/members",
            headers=owner_headers,
            json={
                "user_email": "reviewer@example.com",
                "display_name": "Reviewer",
                "role": "reviewer",
            },
        )
        assert member_res.status_code == 201, member_res.text
        assert member_res.json()["role"] == "reviewer"

        org_reviewer_approval = client.post(
            f"/spectracheck/sessions/{session['id']}/approvals",
            headers=reviewer_headers,
            json={
                "report_id": report["id"],
                "decision": "deferred",
                "rationale": "Organization membership alone should not approve project work.",
            },
        )
        assert org_reviewer_approval.status_code == 403, org_reviewer_approval.text

        permission_res = client.post(
            f"/projects/{project['id']}/permissions",
            headers=owner_headers,
            json={"user_email": "viewer@example.com", "role": "viewer"},
        )
        assert permission_res.status_code == 201, permission_res.text
        assert permission_res.json()["role"] == "viewer"

        reviewer_res = client.post(
            f"/spectracheck/sessions/{session['id']}/reviewers",
            headers=owner_headers,
            json={"reviewer_email": "reviewer@example.com"},
        )
        assert reviewer_res.status_code == 201, reviewer_res.text
        assert reviewer_res.json()["status"] == "assigned"

        comment_res = client.post(
            f"/spectracheck/sessions/{session['id']}/comments",
            headers=owner_headers,
            json={
                "evidence_id": evidence["id"],
                "comment": "Please review the predicted NMR layer.",
                "comment_type": "question",
            },
        )
        assert comment_res.status_code == 201, comment_res.text
        comment = comment_res.json()
        assert comment["resolved"] is False

        resolved_res = client.patch(
            f"/spectracheck/sessions/{session['id']}/comments/{comment['id']}",
            headers=owner_headers,
            json={"resolved": True},
        )
        assert resolved_res.status_code == 200, resolved_res.text
        assert resolved_res.json()["resolved"] is True

        task_res = client.post(
            f"/spectracheck/sessions/{session['id']}/review-tasks",
            headers=owner_headers,
            json={
                "title": "Check report language",
                "description": "Keep language human-review cautious.",
                "assigned_to": "reviewer@example.com",
                "priority": "high",
            },
        )
        assert task_res.status_code == 201, task_res.text
        assert task_res.json()["status"] == "open"

        premature_release = client.post(
            f"/reports/{report['id']}/release",
            headers=owner_headers,
            json={},
        )
        assert premature_release.status_code == 400, premature_release.text
        assert "approved_confirmed" in premature_release.text

        approval_res = client.post(
            f"/spectracheck/sessions/{session['id']}/approvals",
            headers=owner_headers,
            json={
                "report_id": report["id"],
                "decision": "approved_confirmed",
                "rationale": "Reviewed evidence and report language for release.",
            },
        )
        assert approval_res.status_code == 201, approval_res.text
        assert approval_res.json()["rationale"]

        viewer_approval = client.post(
            f"/spectracheck/sessions/{session['id']}/approvals",
            headers=viewer_headers,
            json={
                "report_id": report["id"],
                "decision": "approved_plausible",
                "rationale": "Viewer should not be able to approve.",
            },
        )
        assert viewer_approval.status_code == 403, viewer_approval.text

        lock_res = client.post(
            f"/reports/{report['id']}/lock",
            headers=owner_headers,
            json={"lock_reason": "Awaiting final release"},
        )
        assert lock_res.status_code == 200, lock_res.text
        assert lock_res.json()["status"] == "locked"

        release_res = client.post(
            f"/reports/{report['id']}/release",
            headers=owner_headers,
            json={},
        )
        assert release_res.status_code == 200, release_res.text
        assert release_res.json()["status"] == "released"
        assert release_res.json()["metadata_json"]["approval_confirmed"] is True

        share_res = client.post(
            "/share-links",
            headers=owner_headers,
            json={"session_id": session["id"], "permission": "review"},
        )
        assert share_res.status_code == 201, share_res.text
        share = share_res.json()
        assert share["token"]

        share_get = client.get(f"/share-links/{share['token']}")
        assert share_get.status_code == 200, share_get.text
        assert share_get.json()["permission"] == "review"

        audit_res = client.get(
            "/audit",
            headers=api_headers,
            params={"limit": 100, "entity_type": "approval_record"},
        )
        assert audit_res.status_code == 200, audit_res.text
        assert any(
            event["event_type"] == "collaboration.approval.create"
            for event in audit_res.json()
        )


def test_collaboration_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/organizations",
        "/organizations/{organization_id}",
        "/organizations/{organization_id}/members",
        "/organizations/{organization_id}/members/{member_id}",
        "/projects/{project_id}/permissions",
        "/projects/{project_id}/permissions/{permission_id}",
        "/spectracheck/sessions/{session_id}/reviewers",
        "/spectracheck/sessions/{session_id}/reviewers/{reviewer_id}",
        "/spectracheck/sessions/{session_id}/comments",
        "/spectracheck/sessions/{session_id}/comments/{comment_id}",
        "/spectracheck/sessions/{session_id}/review-tasks",
        "/spectracheck/sessions/{session_id}/review-tasks/{task_id}",
        "/spectracheck/sessions/{session_id}/approvals",
        "/reports/{report_id}/lock",
        "/reports/{report_id}/unlock",
        "/reports/{report_id}/release",
        "/share-links",
        "/share-links/{token}",
        "/share-links/{share_id}/revoke",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/organizations"]
    assert "patch" in paths["/spectracheck/sessions/{session_id}/comments/{comment_id}"]
    assert "post" in paths["/reports/{report_id}/release"]
