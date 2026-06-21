"""Owner-scoping for cross-module reaction routes whose owner-relevant id is in the request BODY
(the path-based require_reaction_access gate cannot reach those). Proves a non-owner gets a
non-leaking 404 — closing the cross-tenant import/export/bridge holes — while the owner is not
over-restricted. System/admin remain unrestricted (covered by the system-key phase60 suite).
"""

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client, headers) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Owned", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _experiment(client, headers, pid) -> int:
    res = client.post(
        f"/reaction-projects/{pid}/experiments",
        headers=headers,
        json={
            "experiment_code": "OWN-1",
            "status": "completed",
            "conditions_json": {"temperature_c": 60},
            "outcome_json": {"impurity_percent": 0.2},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _connector(client, headers) -> int:
    res = client.post(
        "/connectors",
        headers=headers,
        json={
            "connector_key": "own-conn",
            "display_name": "Owner connector",
            "connector_type": "instrument_watch_folder",
            "target_program": "cross_module",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _dossier(client, headers, title="D") -> int:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": title,
            "product_name": "p",
            "compound_name": "c",
            "intended_use": "fixture",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _impurity_action(client, headers, dossier_id) -> int:
    res = client.post(
        "/regulatory/action-items",
        headers=headers,
        json={
            "dossier_id": dossier_id,
            "action_type": "impurity_identification",
            "severity": "high",
            "status": "open",
            "title": "Impurity above identification threshold",
            "description": "fixture",
            "metadata_json": {"threshold_percent": 0.15, "observed_level_percent": 0.4},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_integration_routes_are_owner_scoped(client):
    with client:
        owner = _sign_up(client, "xm-owner@example.com")
        intruder = _sign_up(client, "xm-intruder@example.com")
        pid = _project(client, owner)
        eid = _experiment(client, owner, pid)
        conn = _connector(client, owner)

        # DENY: a non-owner cannot import into the owner's project (body reaction_project_id)
        imp = client.post(
            "/integrations/reactions/import-experiment-table",
            headers=intruder,
            json={"file_id": 1, "reaction_project_id": pid},
        )
        assert imp.status_code == 404, imp.text

        # DENY: a non-owner cannot export the owner's experiment (body experiment_ids_json)
        exp = client.post(
            "/integrations/reactions/export-approved-experiments",
            headers=intruder,
            json={"connector_id": conn, "target_system": "ext", "experiment_ids_json": [eid]},
        )
        assert exp.status_code == 404, exp.text

        # ALLOW: the owner can export their own experiment (proves no over-restriction)
        ok = client.post(
            "/integrations/reactions/export-approved-experiments",
            headers=owner,
            json={"connector_id": conn, "target_system": "ext", "experiment_ids_json": [eid]},
        )
        assert ok.status_code == 201, ok.text


def _create_bridge(client, headers, dossier_id, action_id, pid):
    return client.post(
        "/bridges/regulatory-to-reaction",
        headers=headers,
        json={
            "dossier_id": dossier_id,
            "regulatory_action_item_id": action_id,
            "reaction_project_id": pid,
        },
    )


def test_bridge_routes_are_owner_scoped(client):
    with client:
        owner = _sign_up(client, "br-owner@example.com")
        intruder = _sign_up(client, "br-intruder@example.com")
        pid = _project(client, owner)
        did = _dossier(client, owner)
        aid = _impurity_action(client, owner, did)

        created = _create_bridge(client, owner, did, aid, pid)
        assert created.status_code == 201, created.text
        bridge_id = created.json()["id"]

        # DENY create: the intruder owns their OWN dossier+action but NOT the owner's project,
        # so bridging onto it is refused (this is the previously-missing project check).
        i_did = _dossier(client, intruder, "D2")
        i_aid = _impurity_action(client, intruder, i_did)
        denied = _create_bridge(client, intruder, i_did, i_aid, pid)
        assert denied.status_code == 404, denied.text

        # DENY get / review: the intruder cannot read or modify the owner's bridge
        assert client.get(
            f"/bridges/regulatory-to-reaction/{bridge_id}", headers=intruder
        ).status_code == 404
        assert client.post(
            f"/bridges/regulatory-to-reaction/{bridge_id}/review",
            headers=intruder,
            json={"reviewer_name": "x", "reviewer_comment": "x"},
        ).status_code == 404

        # DENY list: the owner's bridge does not appear in the intruder's listing
        i_list = client.get("/bridges/regulatory-to-reaction", headers=intruder).json()
        assert all(b["id"] != bridge_id for b in i_list)

        # ALLOW: the owner can read, review, and list their own bridge
        assert client.get(
            f"/bridges/regulatory-to-reaction/{bridge_id}", headers=owner
        ).status_code == 200
        assert client.post(
            f"/bridges/regulatory-to-reaction/{bridge_id}/review",
            headers=owner,
            json={"reviewer_name": "owner", "reviewer_comment": "ok"},
        ).status_code == 200
        o_list = client.get("/bridges/regulatory-to-reaction", headers=owner).json()
        assert any(b["id"] == bridge_id for b in o_list)


def test_bridge_list_pagination_does_not_drop_owned(client):
    # Owner-scoping must filter BEFORE the SQL limit, else a user's own bridges interleaved with
    # others' in the sort order get silently dropped under a small limit.
    with client:
        owner = _sign_up(client, "pg-owner@example.com")
        intruder = _sign_up(client, "pg-intruder@example.com")
        pid = _project(client, owner)
        did = _dossier(client, owner)
        b1 = _create_bridge(client, owner, did, _impurity_action(client, owner, did), pid).json()[
            "id"
        ]
        # an intruder bridge created between the owner's two -> interleaved id (desc) order
        i_pid = _project(client, intruder)
        i_did = _dossier(client, intruder, "Di")
        _create_bridge(client, intruder, i_did, _impurity_action(client, intruder, i_did), i_pid)
        b2 = _create_bridge(client, owner, did, _impurity_action(client, owner, did), pid).json()[
            "id"
        ]

        ids = {b["id"] for b in client.get(
            "/bridges/regulatory-to-reaction?limit=2", headers=owner
        ).json()}
        assert {b1, b2} <= ids, f"owned bridges dropped by pagination: {ids}"
