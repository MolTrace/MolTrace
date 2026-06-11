"""Dossier-level nitrosamine cumulative-risk rollup (FDA Rev 2).

GET /regulatory/dossiers/{id}/nitrosamine-cumulative-risk sums measured / AI-limit
across the dossier's nitrosamine watches that carry both a CPCA AI limit and a measured
ng/day; total must be < 1. Watches missing either input are reported under ``excluded``.
The < 1 decision rule is the CPCA engine's (aggregate_cumulative_risk).
"""

import pytest
from fastapi.testclient import TestClient

from moltrace.regulatory.impurities import (
    aggregate_cumulative_risk,
    calculate_cumulative_risk,
)
from moltrace.regulatory.infra.validation import DataValidationError

# NDMA: FDA CPCA Category 1 -> AI limit 26.5 ng/day.
NDMA = "CN(C)N=O"
NDMA_AI = 26.5


def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    juris = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={"name": "Cumulative US", "country_code": "US", "authority_name": "FDA"},
    )
    assert juris.status_code == 201, juris.text
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Cumulative-risk dossier",
            "product_name": "Cumulative product",
            "compound_name": "Cumulative compound",
            "jurisdiction_id": juris.json()["id"],
            "intended_use": "Research decision support",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _watch(client, headers, dossier_id, *, structure_text, measured=None) -> dict:
    body: dict = {"structure_text": structure_text}
    if measured is not None:
        body["measured_ng_per_day"] = measured
    res = client.post(
        f"/regulatory/dossiers/{dossier_id}/nitrosamine-watch",
        headers=headers,
        json=body,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _rollup(client, headers, dossier_id):
    return client.get(
        f"/regulatory/dossiers/{dossier_id}/nitrosamine-cumulative-risk",
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# API: the rollup verdict
# --------------------------------------------------------------------------- #
def test_cumulative_risk_passes_below_one(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        _watch(client, headers, dossier["id"], structure_text=NDMA, measured=10.0)
        _watch(client, headers, dossier["id"], structure_text=NDMA, measured=10.0)
        res = _rollup(client, headers, dossier["id"])
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["dossier_id"] == dossier["id"]
        assert body["n_components"] == 2
        assert body["n_excluded"] == 0
        assert body["total_risk_ratio"] == pytest.approx(10.0 / NDMA_AI + 10.0 / NDMA_AI)
        assert body["passes"] is True
        assert body["human_review_required"] is True
        # Each component carries the AI limit, measured value and its ratio.
        comp = body["components"][0]
        assert comp["ai_limit_ng_per_day"] == NDMA_AI
        assert comp["measured_ng_per_day"] == 10.0
        assert comp["category"] == 1
        assert comp["risk_ratio"] == pytest.approx(10.0 / NDMA_AI)
        assert comp["structure_text"] == NDMA
        assert comp["assessment_id"] > 0


def test_cumulative_risk_fails_at_or_above_one(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        # Two NDMA at 20 ng/day each -> 40 / 26.5 > 1.
        _watch(client, headers, dossier["id"], structure_text=NDMA, measured=20.0)
        _watch(client, headers, dossier["id"], structure_text=NDMA, measured=20.0)
        body = _rollup(client, headers, dossier["id"]).json()
        assert body["total_risk_ratio"] > 1.0
        assert body["passes"] is False
        assert body["n_components"] == 2


def test_watch_without_measured_is_excluded(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        _watch(client, headers, dossier["id"], structure_text=NDMA, measured=12.0)
        _watch(client, headers, dossier["id"], structure_text=NDMA)  # no measured
        body = _rollup(client, headers, dossier["id"]).json()
        assert body["n_components"] == 1
        assert body["n_excluded"] == 1
        assert "no measured ng/day" in body["excluded"][0]["reason"]
        assert body["total_risk_ratio"] == pytest.approx(12.0 / NDMA_AI)
        assert body["passes"] is True


def test_non_nitrosamine_watch_is_excluded(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        # Free-text flag (no parseable structure) -> no CPCA AI limit, even with a measured value.
        _watch(
            client,
            headers,
            dossier["id"],
            structure_text="possible nitrosamine impurity (structure TBD)",
            measured=15.0,
        )
        body = _rollup(client, headers, dossier["id"]).json()
        assert body["n_components"] == 0
        assert body["n_excluded"] == 1
        assert "not a parseable nitrosamine" in body["excluded"][0]["reason"]
        assert body["total_risk_ratio"] == 0.0
        assert body["passes"] is True


def test_empty_dossier_is_zero_and_passes(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        body = _rollup(client, headers, dossier["id"]).json()
        assert body["n_components"] == 0
        assert body["n_excluded"] == 0
        assert body["total_risk_ratio"] == 0.0
        assert body["passes"] is True
        assert any("cumulative risk is 0 by default" in note for note in body["notes"])


def test_rollup_missing_dossier_is_404(client, api_headers):
    headers = api_headers
    with client:
        res = _rollup(client, headers, 999_999)
        assert res.status_code == 404, res.text


def test_rollup_route_in_openapi(client):
    with client:
        spec = client.get("/openapi.json").json()
        assert (
            "/regulatory/dossiers/{dossier_id}/nitrosamine-cumulative-risk" in spec["paths"]
        )


# --------------------------------------------------------------------------- #
# Engine: aggregate_cumulative_risk owns the < 1 rule; calculate_cumulative_risk delegates
# --------------------------------------------------------------------------- #
def test_aggregate_from_known_limits_passes_and_passes_through_keys():
    r = aggregate_cumulative_risk(
        [
            {"assessment_id": 7, "ai_limit_ng_per_day": 26.5, "measured_ng_per_day": 10.0},
            {"assessment_id": 8, "ai_limit_ng_per_day": 1500.0, "measured_ng_per_day": 100.0},
        ]
    )
    assert r.total_risk_ratio == pytest.approx(10.0 / 26.5 + 100.0 / 1500.0)
    assert r.passes is True
    assert r.components[0]["assessment_id"] == 7  # extra keys pass through untouched
    assert r.components[0]["risk_ratio"] == pytest.approx(10.0 / 26.5)


def test_aggregate_empty_is_zero_and_passes():
    r = aggregate_cumulative_risk([])
    assert r.total_risk_ratio == 0.0
    assert r.passes is True
    assert r.components == ()


def test_aggregate_rejects_bad_inputs():
    with pytest.raises(DataValidationError):
        aggregate_cumulative_risk([{"ai_limit_ng_per_day": 26.5, "measured_ng_per_day": -1.0}])
    with pytest.raises(DataValidationError):
        aggregate_cumulative_risk([{"ai_limit_ng_per_day": 0.0, "measured_ng_per_day": 1.0}])


def test_calculate_cumulative_risk_still_delegates():
    # The SMILES-driven front door yields the same verdict as the aggregate it delegates to.
    r = calculate_cumulative_risk([(NDMA, 10.0), (NDMA, 10.0)])
    assert r.total_risk_ratio == pytest.approx(10.0 / 26.5 + 10.0 / 26.5)
    assert r.passes is True
    assert len(r.components) == 2
