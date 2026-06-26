"""R8 wiring: the advisor surface invokes the math-frozen Claude agent when opted in.

Hermetic: the feature flag is enabled but no API key is present, so the agent degrades to the
deterministic rule-based path — the real frozen executors run, full provenance is persisted, and
no network call is made.
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


def _seed_project(client: TestClient, headers: dict[str, str]) -> dict:
    project = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Agent advisor screen", "objective": "maximize_yield", "status": "active"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    ds = client.post(
        f"/reaction-projects/{project_id}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
            "categorical_variables_json": {"solvent": ["MeCN", "THF"], "catalyst": ["Cat-A", "Cat-B"]},
        },
    )
    assert ds.status_code == 201, ds.text
    rows = [
        (40, "MeCN", "Cat-A", 42),
        (60, "MeCN", "Cat-A", 58),
        (80, "THF", "Cat-A", 64),
        (60, "THF", "Cat-B", 71),
        (80, "MeCN", "Cat-B", 67),
    ]
    for index, (temperature, solvent, catalyst, yield_percent) in enumerate(rows, start=1):
        exp = client.post(
            f"/reaction-projects/{project_id}/experiments",
            headers=headers,
            json={
                "experiment_code": f"AGT-{index:03d}",
                "status": "completed",
                "conditions_json": {
                    "temperature_c": temperature,
                    "solvent": solvent,
                    "catalyst": catalyst,
                },
                "outcome_json": {"yield_percent": yield_percent},
            },
        )
        assert exp.status_code == 201, exp.text
    bo = client.post(
        f"/reaction-projects/{project_id}/optimization/bo/run",
        headers=headers,
        json={"algorithm": "tpe_like", "batch_size": 2},
    )
    assert bo.status_code == 201, bo.text
    return {"project_id": project_id, "bo_run_id": bo.json()["bo_run_id"]}


def test_advisor_invokes_agent_layer_when_enabled(client, monkeypatch):
    # Enable the opt-in agent layer but guarantee no key -> deterministic fallback, no network.
    monkeypatch.setenv("MOLTRACE_REACTION_AGENT", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with client:
        headers = _headers(client, "agent-advisor@example.com")
        seed = _seed_project(client, headers)

        res = client.post(
            f"/reaction-projects/{seed['project_id']}/advisor/run",
            headers=headers,
            json={"bo_run_id": seed["bo_run_id"], "advisor_mode": "llm_guided_placeholder"},
        )
        assert res.status_code == 201, res.text
        body = res.json()

        # The structured math stays rule-based; the agent rides in metadata (no schema change).
        assert body["advisor_mode"] == "rule_based_mechanistic"
        agent = body["metadata_json"]["agent"]
        assert agent["engine"] == "reaction_agent.v1"
        assert agent["mode"] == "rule_based_fallback"  # no API key -> degraded
        assert agent["llm_used"] is False
        assert agent["model_version"] is None
        assert agent["human_review_required"] is True

        # The mandatory safety pre-check ran via the real frozen gate (no screenings -> clear).
        names = [call["name"] for call in agent["tool_calls"]]
        assert "assess_safety" in names
        safety = next(c for c in agent["tool_calls"] if c["name"] == "assess_safety")
        assert safety["output"]["status"] == "clear"
        assert agent["execution_blocked"] is False

        # The fallback plan ran the real BO-backed recommend tool end-to-end through the advisor.
        assert "recommend_next_batch" in names
        rec = next(c for c in agent["tool_calls"] if c["name"] == "recommend_next_batch")
        assert "candidates" in rec["output"]

        # The degraded-path note is recorded for the audit trail.
        assert any("degraded to the deterministic rule-based path" in note for note in body["notes"])


def test_advisor_without_flag_does_not_invoke_agent(client, monkeypatch):
    monkeypatch.delenv("MOLTRACE_REACTION_AGENT", raising=False)
    with client:
        headers = _headers(client, "no-agent@example.com")
        seed = _seed_project(client, headers)
        res = client.post(
            f"/reaction-projects/{seed['project_id']}/advisor/run",
            headers=headers,
            json={"bo_run_id": seed["bo_run_id"], "advisor_mode": "llm_guided_placeholder"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        # Flag off: behaviour is unchanged — no agent layer, the legacy not-configured note stands.
        assert "agent" not in body["metadata_json"]
        assert any("LLM guidance is not configured" in note for note in body["notes"])
