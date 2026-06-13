"""Prompt 9 — POST /regulatory/spc/analyze endpoint.

The stateless SPC/capability compute endpoint over the moltrace engine: contract presence in the
OpenAPI schema, the happy path (capability + signals + pre-OOS trending lead), auth, and input
validation (missing spec -> 400, short series -> 422).
"""

from __future__ import annotations


def test_spc_analyze_is_in_openapi_contract(app) -> None:
    schema = app.openapi()
    assert "/regulatory/spc/analyze" in schema["paths"]
    components = schema["components"]["schemas"]
    assert "SPCAnalyzeRequest" in components
    assert "SPCAnalyzeResult" in components


def test_spc_analyze_returns_capability_signals_and_pre_oos_lead(client, api_headers) -> None:
    # Slow upward drift that stays in-spec until the final point crosses the USL.
    values = [100.0, 100.3, 100.6, 100.9, 101.2, 101.5, 101.8, 102.1, 102.4, 103.5]
    with client:
        resp = client.post(
            "/regulatory/spc/analyze",
            headers=api_headers,
            json={
                "product": "Examplinib tablets",
                "parameter": "Assay",
                "measurements": [{"value": v, "batch_id": f"B{i}"} for i, v in enumerate(values)],
                "usl": 103.0,
                "lsl": 97.0,
                "target": 100.0,
                "rule_set": "western_electric",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parameter"] == "Assay" and body["n"] == 10
    assert body["capability"]["cpk"] is not None
    assert body["capability"]["rating"] in {"capable", "marginal", "not_capable"}
    # the final point is the OOS; a signal fired strictly before it (the early warning)
    assert body["first_oos_index"] == 9
    assert body["first_signal_index"] is not None and body["first_signal_index"] < 9
    assert body["lead_points"] and body["lead_points"] > 0
    assert any(a["category"] == "oos" for a in body["alerts"])
    assert body["human_review_required"] is True
    assert "disposition" in body["disclaimer"].lower()


def test_spc_analyze_zero_variation_indices_are_null_not_infinity(client, api_headers) -> None:
    with client:
        resp = client.post(
            "/regulatory/spc/analyze",
            headers=api_headers,
            json={
                "measurements": [{"value": 100.0} for _ in range(5)],
                "usl": 105.0,
                "lsl": 95.0,
            },
        )
    assert resp.status_code == 200, resp.text
    cap = resp.json()["capability"]
    assert cap["cp"] is None and cap["cpk"] is None  # inf -> null for valid JSON
    assert cap["rating"] == "capable"
    assert any("zero within-variation" in w for w in cap["warnings"])


def test_spc_analyze_requires_a_specification_limit(client, api_headers) -> None:
    with client:
        resp = client.post(
            "/regulatory/spc/analyze",
            headers=api_headers,
            json={"measurements": [{"value": 1.0}, {"value": 2.0}]},
        )
    assert resp.status_code == 400, resp.text  # engine ValueError -> 400


def test_spc_analyze_rejects_short_series(client, api_headers) -> None:
    with client:
        resp = client.post(
            "/regulatory/spc/analyze",
            headers=api_headers,
            json={"measurements": [{"value": 1.0}], "usl": 3.0, "lsl": 0.0},
        )
    assert resp.status_code == 422  # pydantic min_length=2


def test_spc_analyze_requires_authentication(client) -> None:
    with client:
        resp = client.post(
            "/regulatory/spc/analyze",
            json={"measurements": [{"value": 1.0}, {"value": 2.0}], "usl": 3.0, "lsl": 0.0},
        )
    assert resp.status_code == 401
