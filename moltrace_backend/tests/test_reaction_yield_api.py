"""API tests for R12 yield-prediction runs (lightweight surrogate; owner-scoped; honest backend)."""

from __future__ import annotations

from fastapi.testclient import TestClient

_FALLBACK_BACKENDS = {"knn_surrogate", "sklearn_gp_surrogate"}


def _headers(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str], name: str = "Yield campaign") -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": name, "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _completed(client, headers, pid, idx, *, catalyst, temperature, yield_percent) -> int:
    res = client.post(
        f"/reaction-projects/{pid}/experiments",
        headers=headers,
        json={
            "experiment_code": f"YP-{idx:03d}",
            "status": "completed",
            "conditions_json": {"temperature_c": temperature, "catalyst": catalyst},
            "outcome_json": {"yield_percent": yield_percent},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _seed(client, headers, pid) -> None:
    rows = [("Cat-A", 40, 78), ("Cat-A", 60, 85), ("Cat-A", 80, 90), ("Cat-B", 60, 35)]
    for i, (c, t, y) in enumerate(rows, start=1):
        _completed(client, headers, pid, i, catalyst=c, temperature=t, yield_percent=y)


def test_predicts_with_the_honest_fallback_backend(client):
    with client:
        headers = _headers(client, "yp-predict@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)
        res = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60, "catalyst": "Cat-A"}]},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        # Never pin ONE backend: sklearn's presence differs between local and CI.
        assert body["backend"] in _FALLBACK_BACKENDS
        assert body["trained_n"] == 4
        assert len(body["predictions"]) == 1
        prediction = body["predictions"][0]
        assert isinstance(prediction["mean"], float)
        assert prediction["std"] >= 0.0
        # The honesty contract: the client always sees WHICH backend ran and why.
        assert body["capability_provenance"]["backend"] == "fallback"
        assert body["capability_provenance"]["capability"] == "yield_gnn"
        assert "disclaimer" in body


def test_underspecified_conditions_are_disclosed_not_silently_imputed(client):
    with client:
        headers = _headers(client, "yp-disclose@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)
        res = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"catalyst": "Cat-A"}]},  # temperature_c missing
        )
        assert res.status_code == 201, res.text
        warnings = res.json()["predictions"][0]["warnings"]
        assert any("temperature_c" in w for w in warnings), warnings


def test_no_training_data_is_a_400_not_a_500(client):
    with client:
        headers = _headers(client, "yp-empty@example.com")
        pid = _project(client, headers)  # no experiments at all
        res = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60}]},
        )
        assert res.status_code == 400, res.text
        assert "zero examples" in res.json()["detail"]


def test_require_verified_filters_the_training_set(client):
    with client:
        headers = _headers(client, "yp-verified@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)  # none verified
        res = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60}], "require_verified": True},
        )
        # All four experiments are unverified -> zero training examples -> honest 400.
        assert res.status_code == 400, res.text


def test_require_verified_admits_only_the_verified_subset_of_a_mix(client):
    """With a MIX of verified and unverified rows, trained_n must equal the verified count."""

    with client:
        headers = _headers(client, "yp-mix@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)  # 4 unverified
        for i, y in enumerate([88, 92], start=10):
            res = client.post(
                f"/reaction-projects/{pid}/experiments",
                headers=headers,
                json={
                    "experiment_code": f"YP-{i:03d}",
                    "status": "completed",
                    "conditions_json": {"temperature_c": 70, "catalyst": "Cat-A"},
                    "outcome_json": {"yield_percent": y},
                    "metadata_json": {
                        "outcome_confirmation": {"confirmed_at": "2026-01-01T00:00:00Z"}
                    },
                },
            )
            assert res.status_code == 201, res.text
        body = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 70, "catalyst": "Cat-A"}],
                  "require_verified": True},
        ).json()
        assert body["trained_n"] == 2
        assert body["require_verified"] is True


def test_string_yield_trains_like_the_platform_reads_it(client):
    """Ingest stores outcome_json raw, so "85" (a string) is a legitimate stored value.

    The surrogate must coerce it exactly like the platform's canonical outcome read
    (``_float_or_none``) — training on the same value BO scoring sees, instead of silently
    dropping the row.
    """

    with client:
        headers = _headers(client, "yp-strnum@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)  # 4 numeric rows
        res = client.post(
            f"/reaction-projects/{pid}/experiments",
            headers=headers,
            json={
                "experiment_code": "YP-020",
                "status": "completed",
                "conditions_json": {"temperature_c": 60, "catalyst": "Cat-A"},
                "outcome_json": {"yield_percent": "85"},
            },
        )
        assert res.status_code == 201, res.text
        assert res.json()["outcome"]["yield_percent"] == 85.0  # the canonical read coerces
        body = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60, "catalyst": "Cat-A"}]},
        ).json()
        assert body["trained_n"] == 5  # the string row trains too


def test_create_emits_an_audit_event(client, app):
    from sqlalchemy import select as sa_select

    from nmrcheck.orm import AuditEventORM

    with client:
        headers = _headers(client, "yp-audit@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)
        run_id = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60}]},
        ).json()["id"]
        with app.state.session_factory() as session:
            rows = session.scalars(
                sa_select(AuditEventORM).where(
                    AuditEventORM.event_type == "reaction.yield_prediction.create",
                    AuditEventORM.entity_id == run_id,
                )
            ).all()
        assert rows, "yield-prediction create must land in the audit ledger"
        assert rows[0].entity_type == "reaction_yield_prediction_run"
        assert rows[0].actor_email == "yp-audit@example.com"


def test_heavy_backend_is_never_fit_inline(client, monkeypatch):
    """Flag on changes nothing here: no promotion evidence is passed, and training is off-request."""

    monkeypatch.setenv("MOLTRACE_REACTION_YIELD_GNN", "1")
    with client:
        headers = _headers(client, "yp-heavy@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)
        res = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 60, "catalyst": "Cat-A"}]},
        )
        assert res.status_code == 201, res.text
        assert res.json()["backend"] != "torch_mpnn_mc_dropout"


def test_persisted_listable_and_gettable(client):
    with client:
        headers = _headers(client, "yp-persist@example.com")
        pid = _project(client, headers)
        _seed(client, headers, pid)
        created = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=headers,
            json={"conditions": [{"temperature_c": 80, "catalyst": "Cat-A"}]},
        ).json()
        listed = client.get(
            f"/reaction-projects/{pid}/yield-predictions", headers=headers
        ).json()
        assert [run["id"] for run in listed] == [created["id"]]
        fetched = client.get(
            f"/reaction-projects/{pid}/yield-predictions/{created['id']}", headers=headers
        )
        assert fetched.status_code == 200
        assert fetched.json()["predictions"] == created["predictions"]


def test_owner_scoped_non_leaking_404(client):
    with client:
        owner = _headers(client, "yp-owner@example.com")
        intruder = _headers(client, "yp-intruder@example.com")
        pid = _project(client, owner)
        _seed(client, owner, pid)
        run_id = client.post(
            f"/reaction-projects/{pid}/yield-predictions",
            headers=owner,
            json={"conditions": [{"temperature_c": 60}]},
        ).json()["id"]

        assert (
            client.post(
                f"/reaction-projects/{pid}/yield-predictions",
                headers=intruder,
                json={"conditions": [{"temperature_c": 60}]},
            ).status_code
            == 404
        )
        assert (
            client.get(f"/reaction-projects/{pid}/yield-predictions", headers=intruder).status_code
            == 404
        )
        assert (
            client.get(
                f"/reaction-projects/{pid}/yield-predictions/{run_id}", headers=intruder
            ).status_code
            == 404
        )

        # A different project of the SAME owner must not reach this run either.
        other_pid = _project(client, owner, "Other campaign")
        assert (
            client.get(
                f"/reaction-projects/{other_pid}/yield-predictions/{run_id}", headers=owner
            ).status_code
            == 404
        )
