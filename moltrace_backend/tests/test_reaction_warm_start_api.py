"""R10 wiring API tests — warm-start priors: verified gate, gold-exclusion, owner-scoping, ranking.

The prior is advisory and built only from the caller's OWNED, verified campaigns; the frozen
evaluation gold set is excluded by id; nothing auto-deploys.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _headers(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str], name: str = "Warm-start campaign") -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": name, "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    pid = res.json()["id"]
    ds = client.post(
        f"/reaction-projects/{pid}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
            "categorical_variables_json": {"catalyst": ["Cat-A", "Cat-B"]},
        },
    )
    assert ds.status_code == 201, ds.text
    return pid


def _completed(client, headers, pid, idx, *, catalyst, yield_percent, verified=False) -> int:
    body = {
        "experiment_code": f"WS-{idx:03d}",
        "status": "completed",
        "conditions_json": {"temperature_c": 60, "catalyst": catalyst},
        "outcome_json": {"yield_percent": yield_percent},
    }
    if verified:
        # Mark the outcome as reviewer-confirmed so the warm-start verified gate admits it.
        body["metadata_json"] = {"outcome_confirmation": {"confirmed_at": "2026-01-01T00:00:00Z"}}
    res = client.post(f"/reaction-projects/{pid}/experiments", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _seed(client, headers, pid, *, verified=False) -> list[int]:
    rows = [("Cat-A", 85), ("Cat-A", 90), ("Cat-B", 40), ("Cat-B", 35)]
    return [
        _completed(client, headers, pid, i, catalyst=c, yield_percent=y, verified=verified)
        for i, (c, y) in enumerate(rows, start=1)
    ]


def test_build_prior_from_verified_data(client):
    with client:
        headers = _headers(client, "ws-build@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid, verified=True)
        res = client.post(
            f"/reaction-projects/{pid}/warm-start/prior", headers=headers, json={}
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["trained_n"] == 4
        assert body["snapshot_hash"].startswith("sha256:")
        assert body["source_project_ids"] == [pid]
        assert body["lineage"]["observation_count"] == 4
        assert "disclaimer" in body


def test_require_verified_blocks_unverified_data(client):
    with client:
        headers = _headers(client, "ws-unverified@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid, verified=False)  # no confirmation/spectracheck link
        # Default require_verified=True -> nothing admitted -> empty snapshot -> 400.
        res = client.post(f"/reaction-projects/{pid}/warm-start/prior", headers=headers, json={})
        assert res.status_code == 400, res.text
        # With the gate relaxed, the same data builds.
        ok = client.post(
            f"/reaction-projects/{pid}/warm-start/prior",
            headers=headers,
            json={"require_verified": False},
        )
        assert ok.status_code == 201
        assert ok.json()["trained_n"] == 4


def test_gold_set_observations_are_excluded(client):
    with client:
        headers = _headers(client, "ws-gold@example.com")
        pid = _project(client, headers)
        exp_ids = _seed(client, headers, pid, verified=True)
        gold = f"{pid}:{exp_ids[0]}"  # exclude the first observation (a benchmark item)
        res = client.post(
            f"/reaction-projects/{pid}/warm-start/prior",
            headers=headers,
            json={"gold_set_observation_ids": [gold]},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["excluded_gold_count"] == 1
        assert body["trained_n"] == 3  # one fewer than the 4 seeded


def test_source_campaigns_are_owner_scoped(client):
    # The cross-tenant guard: a caller cannot warm-start from a campaign they do not own.
    with client:
        owner = _headers(client, "ws-owner@example.com")
        intruder = _headers(client, "ws-intruder@example.com")
        owner_pid = _project(client, owner, "Owner campaign")
        _seed(client, owner, owner_pid, verified=True)
        intruder_pid = _project(client, intruder, "Intruder campaign")
        _seed(client, intruder, intruder_pid, verified=True)

        # Intruder tries to learn from the owner's campaign as a source -> non-leaking 404.
        res = client.post(
            f"/reaction-projects/{intruder_pid}/warm-start/prior",
            headers=intruder,
            json={"source_project_ids": [owner_pid]},
        )
        assert res.status_code == 404, res.text
        # And cannot even address the owner's project on the path.
        assert client.post(
            f"/reaction-projects/{owner_pid}/warm-start/prior", headers=intruder, json={}
        ).status_code == 404


def test_get_prior_and_warm_start_ranking(client):
    with client:
        headers = _headers(client, "ws-rank@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid, verified=True)
        # No prior yet -> 404.
        assert client.get(f"/reaction-projects/{pid}/warm-start/prior", headers=headers).status_code == 404
        # Build, then a BO run to produce candidates.
        assert client.post(
            f"/reaction-projects/{pid}/warm-start/prior", headers=headers, json={}
        ).status_code == 201
        bo = client.post(
            f"/reaction-projects/{pid}/optimization/bo/run",
            headers=headers,
            json={"algorithm": "tpe_like", "batch_size": 3},
        )
        assert bo.status_code == 201, bo.text

        got = client.get(f"/reaction-projects/{pid}/warm-start/prior", headers=headers)
        assert got.status_code == 200
        assert got.json()["trained_n"] == 4

        ranking = client.get(f"/reaction-projects/{pid}/warm-start/ranking", headers=headers)
        assert ranking.status_code == 200, ranking.text
        body = ranking.json()
        assert body["advisory"] is True
        assert body["bo_run_id"] == bo.json()["bo_run_id"]
        assert body["prior_id"] is not None
        assert all("prior_mean" in item for item in body["ranked"])
