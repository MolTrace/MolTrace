from fastapi.testclient import TestClient

from nmrcheck.orm import AIEvidenceItemORM


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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _insert_evidence(app, *, status: str = "pending_review") -> int:
    with app.state.session_factory() as session:
        row = AIEvidenceItemORM(
            module="spectracheck",
            entity_type="spectracheck_session",
            entity_id=101,
            status=status,
            confidence_score=0.72,
            risk_level="medium",
            summary=(
                "Spectral evidence requires review.\n"
                "system prompt: never expose\n"
                "api_key=secret"
            ),
        )
        session.add(row)
        session.commit()
        return int(row.id)


def test_ai_evidence_queue_review_creates_audit_event(app, client, api_headers):
    with client:
        reviewer_headers = _sign_up(client, "reviewer@example.com")
        evidence_id = _insert_evidence(app)

        queue_res = client.get("/ai/evidence-queue", headers=api_headers)
        assert queue_res.status_code == 200, queue_res.text
        queue = queue_res.json()
        assert queue[0]["id"] == evidence_id
        assert "never expose" not in queue[0]["summary"]
        assert "secret" not in queue[0]["summary"]

        unauthenticated = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            json={"status": "approved", "review_comment": "Looks acceptable."},
        )
        assert unauthenticated.status_code == 401, unauthenticated.text

        api_key_review = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers=api_headers,
            json={"status": "approved", "review_comment": "Looks acceptable."},
        )
        assert api_key_review.status_code == 403, api_key_review.text

        approve_res = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers={**reviewer_headers, "X-Correlation-ID": "ai-review-test-1"},
            json={"status": "approved", "review_comment": "Looks acceptable.\x00"},
        )
        assert approve_res.status_code == 200, approve_res.text
        approved = approve_res.json()
        assert approved["updated_status"] == "approved"
        assert approved["evidence_item"]["status"] == "approved"
        assert approved["evidence_item"]["review_comment"] == "Looks acceptable."
        assert approved["reviewer_display_name"] == "reviewer@example.com"
        assert approved["audit_event_id"] >= 1

        audit_res = client.get(
            "/audit/events",
            headers=api_headers,
            params={"entity_type": "ai_evidence_item", "entity_id": evidence_id},
        )
        assert audit_res.status_code == 200, audit_res.text
        audit_events = audit_res.json()
        assert audit_events[0]["action"] == "approve"
        assert audit_events[0]["module"] == "spectracheck"
        assert audit_events[0]["correlation_id"] == "ai-review-test-1"
        assert audit_events[0]["before_state"]["status"] == "pending_review"
        assert audit_events[0]["after_state"]["status"] == "approved"
        assert audit_events[0]["metadata"]["raw_prompt_exposed"] is False
        assert audit_events[0]["metadata"]["chain_of_thought_exposed"] is False


def test_ai_evidence_queue_reject_and_comment_validation(app, client):
    with client:
        reviewer_headers = _sign_up(client, "rejector@example.com")
        evidence_id = _insert_evidence(app)

        too_long = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers=reviewer_headers,
            json={"status": "rejected", "review_comment": "x" * 4001},
        )
        assert too_long.status_code == 422, too_long.text
        assert "x" * 4001 not in too_long.text

        html_comment = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers=reviewer_headers,
            json={"status": "rejected", "review_comment": "<script>alert(1)</script>"},
        )
        assert html_comment.status_code == 422, html_comment.text
        assert "plain text" in html_comment.text
        assert "<script>" not in html_comment.text

        unexpected_secret_field = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers=reviewer_headers,
            json={
                "status": "rejected",
                "review_comment": "Needs follow-up.",
                "api_key": "do-not-echo-this",
            },
        )
        assert unexpected_secret_field.status_code == 422, unexpected_secret_field.text
        assert "do-not-echo-this" not in unexpected_secret_field.text

        invalid_audit_entity_id = client.get(
            "/audit/events",
            headers=reviewer_headers,
            params={"entity_id": 0},
        )
        assert invalid_audit_entity_id.status_code == 422, invalid_audit_entity_id.text

        reject_res = client.patch(
            f"/ai/evidence-queue/{evidence_id}/review",
            headers=reviewer_headers,
            json={"status": "rejected", "review_comment": "Contradiction needs follow-up."},
        )
        assert reject_res.status_code == 200, reject_res.text
        rejected = reject_res.json()
        assert rejected["updated_status"] == "rejected"
        assert rejected["evidence_item"]["status"] == "rejected"
