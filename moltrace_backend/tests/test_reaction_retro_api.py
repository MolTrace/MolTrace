"""API tests for R13 route scoring (pure frozen-engine overlay; owner-scoped; generation unwired)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_AZIDE = "CCN=[N+]=[N-]"

# Ester target from acid + alcohol, with a reagent — two-step tree.
_ROUTE = {
    "smiles": "CCOC(C)=O",
    "reagents": ["OS(O)(=O)=O"],
    "solvent": "ethanol",
    "children": [
        {"smiles": "CC(O)=O", "children": []},
        {"smiles": "CCO", "children": []},
    ],
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
        json={"name": "Retro campaign", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_scores_a_supplied_route_with_the_frozen_engines(client):
    with client:
        headers = _headers(client, "rs-score@example.com")
        pid = _project(client, headers)
        res = client.post(
            f"/reaction-projects/{pid}/route-scores",
            headers=headers,
            json={"route": _ROUTE, "label": "esterification"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        score = body["score"]
        assert isinstance(score["route_score"], float)
        assert "safety" in score["score_components"]
        assert "brevity" in score["score_components"]
        # Reagents are screened too — the H2SO4 reagent appears in the safety screens.
        screened = {(s["smiles"], s["role"]) for s in score["safety"]["screens"]}
        assert ("OS(O)(=O)=O", "reagent") in screened
        assert score["safety"]["requires_expert_review"] is True
        assert score["human_review_required"] is True
        assert body["mermaid"].startswith("graph TD")
        assert body["human_review_required"] is True
        assert "disclaimer" in body
        assert score["engine"] == "reaction_retro.v1"


def test_energetic_molecule_on_the_route_is_flagged(client):
    with client:
        headers = _headers(client, "rs-azide@example.com")
        pid = _project(client, headers)
        route = {"smiles": _AZIDE, "children": [{"smiles": "CCO", "children": []}]}
        res = client.post(
            f"/reaction-projects/{pid}/route-scores", headers=headers, json={"route": route}
        )
        assert res.status_code == 201, res.text
        safety = res.json()["score"]["safety"]
        assert safety["worst_risk"] in {"high", "critical"}


def test_malformed_route_is_a_400_not_a_500(client):
    with client:
        headers = _headers(client, "rs-malformed@example.com")
        pid = _project(client, headers)
        res = client.post(
            f"/reaction-projects/{pid}/route-scores",
            headers=headers,
            json={"route": {"children": []}},  # no SMILES
        )
        assert res.status_code == 400, res.text
        assert "SMILES" in res.json()["detail"]


def test_aizynth_route_format_is_accepted(client):
    with client:
        headers = _headers(client, "rs-aizynth@example.com")
        pid = _project(client, headers)
        aizynth = {
            "type": "mol",
            "smiles": "CCOC(C)=O",
            "children": [
                {
                    "type": "reaction",
                    "children": [
                        {"type": "mol", "smiles": "CC(O)=O", "children": []},
                        {"type": "mol", "smiles": "CCO", "children": []},
                    ],
                }
            ],
        }
        res = client.post(
            f"/reaction-projects/{pid}/route-scores",
            headers=headers,
            json={"route": aizynth, "route_format": "aizynth"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["score"]["starting_materials"] == 2


def test_persisted_listable_and_gettable(client):
    with client:
        headers = _headers(client, "rs-persist@example.com")
        pid = _project(client, headers)
        created = client.post(
            f"/reaction-projects/{pid}/route-scores", headers=headers, json={"route": _ROUTE}
        ).json()
        listed = client.get(f"/reaction-projects/{pid}/route-scores", headers=headers).json()
        assert [r["id"] for r in listed] == [created["id"]]
        fetched = client.get(
            f"/reaction-projects/{pid}/route-scores/{created['id']}", headers=headers
        )
        assert fetched.status_code == 200
        assert fetched.json()["score"] == created["score"]


def test_owner_scoped_non_leaking_404(client):
    with client:
        owner = _headers(client, "rs-owner@example.com")
        intruder = _headers(client, "rs-intruder@example.com")
        pid = _project(client, owner)
        sid = client.post(
            f"/reaction-projects/{pid}/route-scores", headers=owner, json={"route": _ROUTE}
        ).json()["id"]

        assert (
            client.post(
                f"/reaction-projects/{pid}/route-scores", headers=intruder, json={"route": _ROUTE}
            ).status_code
            == 404
        )
        assert (
            client.get(f"/reaction-projects/{pid}/route-scores", headers=intruder).status_code
            == 404
        )
        assert (
            client.get(
                f"/reaction-projects/{pid}/route-scores/{sid}", headers=intruder
            ).status_code
            == 404
        )

        # A different project of the SAME owner must not reach this score either — the detail
        # query must confine the row to its own project, not just check path ownership.
        other_pid = _project(client, owner)
        assert (
            client.get(
                f"/reaction-projects/{other_pid}/route-scores/{sid}", headers=owner
            ).status_code
            == 404
        )


def test_no_route_generation_surface_is_registered(routed_app):
    """The AiZynth generative path is deliberately unwired — encode that as a regression guard."""

    for route in routed_app.routes:
        path = getattr(route, "path", "")
        assert "propose" not in path or "route" not in path.split("/")[-1], path
        assert not path.endswith("/retro-routes"), path
