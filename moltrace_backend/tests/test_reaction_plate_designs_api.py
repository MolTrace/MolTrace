"""API tests for Repho R3 wiring: HTE/DoE plate-design endpoints.

Covers create/list/get/export, persistence of the generated plate, project-scoping of the
bare child id, and owner-scoping (a non-owner gets a non-leaking 404 via require_reaction_access).
"""

import csv
import io
import json

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str = "plate@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Plate screen", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


_REQUEST = {
    "plate_format": "96",
    "strategy": "sobol",
    "numeric_json": {"temperature_c": [40, 80]},
    "categorical_json": {"solvent": ["MeCN", "THF", "DMF"]},
    "fixed_json": {"base": "K2CO3"},
}


def test_create_list_get_plate_design(client):
    with client:
        headers = _sign_up(client)
        pid = _project(client, headers)["id"]

        created = client.post(
            f"/reaction-projects/{pid}/plate-designs", headers=headers, json=_REQUEST
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["well_count"] == 96
        assert body["plate_format"] == "96"
        assert body["strategy"] == "sobol"
        wells = body["design_json"]["wells"]
        assert len(wells) == 96
        assert wells[0]["well_id"] == "A1"
        assert all(w["conditions"]["base"] == "K2CO3" for w in wells)  # fixed applied
        design_id = body["id"]

        listed = client.get(f"/reaction-projects/{pid}/plate-designs", headers=headers)
        assert listed.status_code == 200
        assert any(d["id"] == design_id for d in listed.json())

        fetched = client.get(f"/reaction-projects/{pid}/plate-designs/{design_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["well_count"] == 96


def test_export_csv_and_json(client):
    with client:
        headers = _sign_up(client, "plate-export@example.com")
        pid = _project(client, headers)["id"]
        design_id = client.post(
            f"/reaction-projects/{pid}/plate-designs", headers=headers, json=_REQUEST
        ).json()["id"]

        csv_res = client.get(
            f"/reaction-projects/{pid}/plate-designs/{design_id}/export",
            headers=headers,
            params={"target": "csv"},
        )
        assert csv_res.status_code == 200, csv_res.text
        rows = list(csv.reader(io.StringIO(csv_res.json()["content"])))
        assert rows[0][0] == "well_id"
        assert len(rows) - 1 == 96

        json_res = client.get(
            f"/reaction-projects/{pid}/plate-designs/{design_id}/export",
            headers=headers,
            params={"target": "json"},
        )
        assert json_res.status_code == 200
        assert json.loads(json_res.json()["content"])["well_count"] == 96

        bad = client.get(
            f"/reaction-projects/{pid}/plate-designs/{design_id}/export",
            headers=headers,
            params={"target": "xml"},
        )
        assert bad.status_code == 422


def test_factorial_strategy(client):
    with client:
        headers = _sign_up(client, "plate-factorial@example.com")
        pid = _project(client, headers)["id"]
        res = client.post(
            f"/reaction-projects/{pid}/plate-designs",
            headers=headers,
            json={
                "plate_format": "96",
                "strategy": "factorial",
                "numeric_json": {"t": [40, 80]},
                "categorical_json": {"s": ["A", "B"], "c": ["X", "Y"]},
            },
        )
        assert res.status_code == 201, res.text
        assert res.json()["well_count"] == 12  # 2 x 2 x 3 levels


def test_plate_design_is_owner_and_project_scoped(client):
    with client:
        owner = _sign_up(client, "plate-owner@example.com")
        intruder = _sign_up(client, "plate-intruder@example.com")
        pid = _project(client, owner)["id"]
        design_id = client.post(
            f"/reaction-projects/{pid}/plate-designs", headers=owner, json=_REQUEST
        ).json()["id"]

        # non-owner -> non-leaking 404 (require_reaction_access)
        assert client.get(f"/reaction-projects/{pid}/plate-designs", headers=intruder).status_code == 404
        assert (
            client.get(
                f"/reaction-projects/{pid}/plate-designs/{design_id}", headers=intruder
            ).status_code
            == 404
        )

        # a different project of the SAME owner must not reach this design (project-scoping)
        other_pid = _project(client, owner)["id"]
        assert (
            client.get(
                f"/reaction-projects/{other_pid}/plate-designs/{design_id}", headers=owner
            ).status_code
            == 404
        )
