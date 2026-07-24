"""API tests for R14 forward cross-checks (pure frozen-engine overlay; owner-scoped)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_AZIDE = "CCN=[N+]=[N-]"

_CHECK = {
    "reactants_smiles": ["CC(O)=O", "CCO"],
    "products_smiles": ["CCOC(C)=O"],
    "confidence": 0.92,
    "conditions": {"solvent": "ethanol"},
    "source": "external-model",
    "label": "esterification check",
}


def _headers(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Forward campaign", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_cross_checks_a_supplied_prediction(client):
    with client:
        headers = _headers(client, "fc-check@example.com")
        pid = _project(client, headers)
        res = client.post(
            f"/reaction-projects/{pid}/forward-checks", headers=headers, json=_CHECK
        )
        assert res.status_code == 201, res.text
        body = res.json()
        result = body["result"]
        assert result["safety"]["overall_risk"] in {"low", "medium", "high", "critical", "unknown"}
        assert result["human_review_required"] is True
        assert result["solvent_greenness"] is not None  # ethanol is in the CHEM21 table
        assert result["engine"] == "reaction_forward.v1"
        assert body["reactants_smiles"] == _CHECK["reactants_smiles"]
        assert "disclaimer" in body


def test_energetic_predicted_product_is_flagged(client):
    """A model's confidence is not a safety opinion — the frozen screen catches the azide."""

    with client:
        headers = _headers(client, "fc-azide@example.com")
        pid = _project(client, headers)
        payload = dict(_CHECK, products_smiles=[_AZIDE], confidence=0.99)
        res = client.post(
            f"/reaction-projects/{pid}/forward-checks", headers=headers, json=payload
        )
        assert res.status_code == 201, res.text
        safety = res.json()["result"]["safety"]
        assert safety["overall_risk"] in {"high", "critical"}
        assert safety["requires_expert_review"] is True


def test_empty_products_is_a_422(client):
    with client:
        headers = _headers(client, "fc-empty@example.com")
        pid = _project(client, headers)
        payload = dict(_CHECK, products_smiles=[])
        res = client.post(
            f"/reaction-projects/{pid}/forward-checks", headers=headers, json=payload
        )
        # min_length=1 on the request model refuses it before the store runs.
        assert res.status_code == 422, res.text


def test_persisted_listable_and_gettable(client):
    with client:
        headers = _headers(client, "fc-persist@example.com")
        pid = _project(client, headers)
        created = client.post(
            f"/reaction-projects/{pid}/forward-checks", headers=headers, json=_CHECK
        ).json()
        listed = client.get(f"/reaction-projects/{pid}/forward-checks", headers=headers).json()
        assert [c["id"] for c in listed] == [created["id"]]
        fetched = client.get(
            f"/reaction-projects/{pid}/forward-checks/{created['id']}", headers=headers
        )
        assert fetched.status_code == 200
        assert fetched.json()["result"] == created["result"]


def test_owner_scoped_non_leaking_404(client):
    with client:
        owner = _headers(client, "fc-owner@example.com")
        intruder = _headers(client, "fc-intruder@example.com")
        pid = _project(client, owner)
        cid = client.post(
            f"/reaction-projects/{pid}/forward-checks", headers=owner, json=_CHECK
        ).json()["id"]

        assert (
            client.post(
                f"/reaction-projects/{pid}/forward-checks", headers=intruder, json=_CHECK
            ).status_code
            == 404
        )
        assert (
            client.get(f"/reaction-projects/{pid}/forward-checks", headers=intruder).status_code
            == 404
        )
        assert (
            client.get(
                f"/reaction-projects/{pid}/forward-checks/{cid}", headers=intruder
            ).status_code
            == 404
        )

        # A different project of the SAME owner must not reach this check either — the detail
        # query must confine the row to its own project, not just check path ownership.
        other_pid = _project(client, owner)
        assert (
            client.get(
                f"/reaction-projects/{other_pid}/forward-checks/{cid}", headers=owner
            ).status_code
            == 404
        )
