"""Annex 22 AI-decision records surfaced via the dossier API (Prompt 12 wiring).

Covers create + chained list, the HITL review flow (approve / double-review / non-high-risk),
chain verification incl. DB-level tamper detection, confidence validation, per-user owner
scoping, and the OpenAPI contract.
"""

from __future__ import annotations


def _sign_up(client, email: str = "annex22@example.com") -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _dossier(client, headers: dict) -> int:
    res = client.post("/regulatory/dossiers", headers=headers, json={"title": "Annex 22 dossier"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _decision_payload(risk: str = "medium", **over) -> dict:
    base = {
        "decision_type": "cpca_classification",
        "model_name": "deterministic:fda_cpca_nitrosamine",
        "model_version": "sha256:abc123",
        "regulatory_basis": "FDA Nitrosamine Rev 2",
        "risk_level": risk,
        "confidence": 1.0,
        "output_json": {"category": 3, "ai_limit_ng_per_day": 100.0},
        "feature_attribution_json": {"engine": "deterministic"},
    }
    base.update(over)
    return base


def test_create_list_and_chain(client):
    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        hashes = []
        for i in range(3):
            r = client.post(
                f"/regulatory/dossiers/{did}/ai-decisions",
                headers=headers,
                json=_decision_payload(decision_type=f"decision_{i}"),
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["entry_hash"].startswith("sha256:")
            assert body["disclaimer"]  # draft disclaimer surfaced for the UI
            assert body["compliance_checklist"]["regulatory_basis_cited"] is True
            assert body["user_id"]  # taken from the authenticated caller, not the payload
            hashes.append(body["entry_hash"])

        listed = client.get(f"/regulatory/dossiers/{did}/ai-decisions", headers=headers)
        assert listed.status_code == 200, listed.text
        assert [row["entry_hash"] for row in listed.json()] == list(reversed(hashes))

        verify = client.get(f"/regulatory/dossiers/{did}/ai-decisions/verify", headers=headers)
        assert verify.status_code == 200, verify.text
        assert verify.json() == {"ok": True, "count": 3, "breaks": []}


def test_high_risk_hitl_review_flow(client):
    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        created = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions",
            headers=headers,
            json=_decision_payload(risk="high"),
        )
        assert created.status_code == 201, created.text
        decision = created.json()
        assert decision["hitl_required"] is True
        assert decision["hitl_approved"] is None
        entry_hash = decision["entry_hash"]

        review = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions/{entry_hash}/review",
            headers=headers,
            json={"approved": True, "reason": "toxicologist sign-off"},
        )
        assert review.status_code == 201, review.text
        review_body = review.json()
        assert review_body["hitl_approved"] is True
        assert review_body["reviews_entry_hash"] == entry_hash
        assert review_body["decision_type"].endswith(".hitl_review")

        # A second review of the same decision is rejected.
        again = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions/{entry_hash}/review",
            headers=headers,
            json={"approved": True},
        )
        assert again.status_code == 400, again.text

        # The review is appended; the chain still verifies (decision + review = 2 rows).
        verify = client.get(f"/regulatory/dossiers/{did}/ai-decisions/verify", headers=headers)
        assert verify.json() == {"ok": True, "count": 2, "breaks": []}


def test_review_of_non_high_risk_is_rejected(client):
    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        created = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions",
            headers=headers,
            json=_decision_payload(risk="low"),
        )
        entry_hash = created.json()["entry_hash"]
        review = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions/{entry_hash}/review",
            headers=headers,
            json={"approved": True},
        )
        assert review.status_code == 400, review.text


def test_confidence_out_of_range_is_422(client):
    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        res = client.post(
            f"/regulatory/dossiers/{did}/ai-decisions",
            headers=headers,
            json=_decision_payload(confidence=1.5),
        )
        assert res.status_code == 422, res.text


def test_verify_detects_db_tampering(client):
    from sqlalchemy import select

    from nmrcheck.orm import RegulatoryAIDecisionORM

    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        for i in range(3):
            client.post(
                f"/regulatory/dossiers/{did}/ai-decisions",
                headers=headers,
                json=_decision_payload(decision_type=f"d{i}"),
            )
        assert client.get(
            f"/regulatory/dossiers/{did}/ai-decisions/verify", headers=headers
        ).json()["ok"] is True

        # Tamper with a stored row's output but leave its entry_hash unchanged.
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            row = session.scalars(
                select(RegulatoryAIDecisionORM).where(
                    RegulatoryAIDecisionORM.dossier_id == did
                )
            ).first()
            row.output_json = '{"tampered": true}'
            session.add(row)
            session.commit()

        verify = client.get(
            f"/regulatory/dossiers/{did}/ai-decisions/verify", headers=headers
        ).json()
        assert verify["ok"] is False
        assert any("tampered" in b for b in verify["breaks"])


def test_ai_decisions_are_owner_scoped(client):
    with client:
        alice = _sign_up(client, "alice-a22@example.com")
        bob = _sign_up(client, "bob-a22@example.com")
        did = _dossier(client, alice)
        client.post(
            f"/regulatory/dossiers/{did}/ai-decisions", headers=alice, json=_decision_payload()
        )

        assert client.get(f"/regulatory/dossiers/{did}/ai-decisions", headers=alice).status_code == 200
        # Non-owner: non-leaking 404 on both read and create.
        assert client.get(f"/regulatory/dossiers/{did}/ai-decisions", headers=bob).status_code == 404
        assert (
            client.post(
                f"/regulatory/dossiers/{did}/ai-decisions", headers=bob, json=_decision_payload()
            ).status_code
            == 404
        )
        # System api key sees all.
        assert (
            client.get(
                f"/regulatory/dossiers/{did}/ai-decisions", headers={"x-api-key": "test-key"}
            ).status_code
            == 200
        )


def test_ai_decisions_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    base = "/regulatory/dossiers/{dossier_id}/ai-decisions"
    assert base in paths
    assert "get" in paths[base] and "post" in paths[base]
    assert f"{base}/{{entry_hash}}/review" in paths
    assert f"{base}/verify" in paths


def test_nitrosamine_watch_auto_records_cpca_decision(client):
    # Creating a nitrosamine-watch with a parseable nitrosamine SMILES runs a CPCA
    # categorization, which is auto-recorded (best-effort) as a high-risk HITL AI decision.
    with client:
        headers = _sign_up(client)
        did = _dossier(client, headers)
        watch = client.post(
            f"/regulatory/dossiers/{did}/nitrosamine-watch",
            headers=headers,
            json={"structure_text": "CN(C)N=O", "measured_ng_per_day": 10.0},
        )
        assert watch.status_code == 201, watch.text

        decisions = client.get(
            f"/regulatory/dossiers/{did}/ai-decisions", headers=headers
        ).json()
        cpca = [d for d in decisions if d["decision_type"] == "cpca_classification"]
        assert len(cpca) == 1
        decision = cpca[0]
        assert decision["confidence"] == 1.0  # deterministic categorization
        assert decision["risk_level"] == "high"
        assert decision["hitl_required"] is True  # CPCA needs toxicologist sign-off
        assert decision["input_smiles"] == "CN(C)N=O"
        assert decision["output_json"].get("cpca_category")
        assert decision["compliance_checklist"]["hitl_opportunity_for_high_risk"] is True

        verify = client.get(
            f"/regulatory/dossiers/{did}/ai-decisions/verify", headers=headers
        ).json()
        assert verify["ok"] is True
