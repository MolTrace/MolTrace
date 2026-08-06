"""Wire-level contract for the spectrum series + kinetics endpoints.

Two properties matter more than the shape. A refusal is a 200 carrying its reason, not an error —
"this series cannot support a rate, and here is why" is the answer. And the response cannot
express a rate constant without its standard error, because the wire model requires it.
"""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

HEADERS = {"x-api-key": "test-key"}


def _series(client: TestClient, name: str = "hydrolysis") -> int:
    response = client.post(
        "/spectrum/series",
        headers=HEADERS,
        json={"name": name, "tracked_quantity": "product integral (H)"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _fill(client: TestClient, series_id: int, *, k: float = 0.10, n: int = 11) -> None:
    for i in range(n):
        response = client.post(
            f"/spectrum/series/{series_id}/points",
            headers=HEADERS,
            json={"elapsed_seconds": float(i), "observed_value": 100.0 * math.exp(-k * i)},
        )
        assert response.status_code == 200, response.text


def test_a_clean_series_returns_its_rate_constant_with_uncertainty(client: TestClient):
    series_id = _series(client)
    _fill(client, series_id, k=0.10)

    response = client.get(f"/spectrum/series/{series_id}/kinetics", headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "fit"
    assert body["refusal"] is None
    fit = body["fit"]
    assert fit["order"] == "first"
    assert abs(fit["rate_constant"] - 0.10) < 1e-6
    # The uncertainty is always present — the wire model cannot express a fit without it.
    assert fit["standard_error"] is not None
    assert fit["point_count"] == 11
    assert body["human_review_required"] is True


def test_a_series_that_cannot_support_a_rate_returns_200_with_its_reason(client: TestClient):
    """A refusal is an answer, not a failure — surfacing it as an error would hide the cause."""
    series_id = _series(client, "too-short")
    _fill(client, series_id, n=3)

    response = client.get(f"/spectrum/series/{series_id}/kinetics", headers=HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "refusal"
    assert body["fit"] is None
    assert body["refusal"]["reason"] == "too_few_points"
    assert "5" in body["refusal"]["detail"]


def test_a_refusal_never_carries_a_rate_constant(client: TestClient):
    series_id = _series(client, "flat")
    for i in range(6):
        client.post(
            f"/spectrum/series/{series_id}/points",
            headers=HEADERS,
            json={"elapsed_seconds": float(i), "observed_value": 50.0},
        )

    body = client.get(f"/spectrum/series/{series_id}/kinetics", headers=HEADERS).json()
    assert body["outcome"] == "refusal"
    assert body["fit"] is None
    assert body["refusal"]["reason"] == "no_change_over_time"
    assert "rate_constant" not in body["refusal"]


def test_an_unknown_series_is_a_non_leaking_404(client: TestClient):
    response = client.get("/spectrum/series/987654/kinetics", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["detail"] == "Spectrum series not found."

    added = client.post(
        "/spectrum/series/987654/points",
        headers=HEADERS,
        json={"elapsed_seconds": 1.0, "observed_value": 1.0},
    )
    assert added.status_code == 404


def test_a_negative_elapsed_time_is_rejected(client: TestClient):
    series_id = _series(client)
    response = client.post(
        f"/spectrum/series/{series_id}/points",
        headers=HEADERS,
        json={"elapsed_seconds": -1.0, "observed_value": 10.0},
    )
    assert response.status_code == 422


def test_an_unknown_field_is_rejected(client: TestClient):
    response = client.post(
        "/spectrum/series",
        headers=HEADERS,
        json={"name": "s", "tracked_quantity": "q", "rate_constant": 0.5},
    )
    assert response.status_code == 422


def test_requires_authentication(client: TestClient):
    assert client.post("/spectrum/series", json={"name": "s"}).status_code == 401


def test_routes_are_registered_in_the_openapi_schema(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert "post" in schema["paths"]["/spectrum/series"]
    assert "get" in schema["paths"]["/spectrum/series/{series_id}/kinetics"]
    assert "SpectrumKineticsResult" in schema["components"]["schemas"]
    # The FE contract must show that standard_error is required, not optional.
    fit_schema = schema["components"]["schemas"]["KineticFitOut"]
    assert "standard_error" in fit_schema["required"]
