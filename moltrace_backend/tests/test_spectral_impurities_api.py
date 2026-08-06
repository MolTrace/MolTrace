"""Wire-level contract for the spectral impurity observation endpoints.

Pins the shape, the non-leaking 404 (the store returns the same ``None`` for absent and
not-yours), the 422 on a route the Q3C engine would otherwise raise on, and the two honesty
properties this feature exists to hold: a stored limit is never a compliance verdict, and the
internal owner column never reaches the wire.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.orm import AnalysisORM

HEADERS = {"x-api-key": "test-key"}


def _analysis(app, *, user_id: int | None) -> int:
    factory = app.state.session_factory
    with factory() as session:
        row = AnalysisORM(
            user_id=user_id,
            smiles="CCO",
            nmr_text="1H NMR (CDCl3): 2.05 (s, 3H)",
            label="pass",
            expected_total_h=6.0,
            observed_total_h=6.0,
            confidence=0.9,
            notes_json="[]",
            full_report_json="{}",
        )
        session.add(row)
        session.commit()
        return int(row.id)


def test_recording_a_known_residual_solvent_returns_its_limit_and_provenance(
    client: TestClient, app
):
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 2.05, "solvent": "CDCl3"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    observation = body["observation"]
    assert observation["compound"] == "ethyl acetate"
    assert observation["identity_status"] == "resolved"
    assert observation["q3c_class_number"] == 3
    assert observation["concentration_limit_ppm"] == 5000.0
    assert body["rule_set_versions"]["q3c_solvents"].startswith("sha256:")
    assert body["human_review_required"] is True
    assert "not a compliance determination" in body["disclaimer"].lower()


def test_a_limit_is_never_returned_as_a_verdict(client: TestClient, app):
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 2.05, "solvent": "CDCl3"},
    )
    observation = response.json()["observation"]

    assert observation["quantitation_available"] is False
    assert observation["observed_level_ppm"] is None
    assert "not quantitated" in observation["compliance_note"].lower()
    # No pass/fail key exists anywhere on the wire.
    assert not {"compliant", "passes", "verdict"} & set(observation)


def test_the_internal_owner_column_never_reaches_the_wire(client: TestClient, app):
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 2.05, "solvent": "CDCl3"},
    )
    assert "user_id" not in response.json()["observation"]


def test_an_unresolved_substance_carries_its_reason_and_no_rule_set_version(
    client: TestClient, app
):
    """Grease is a real contaminant and not a Q3C solvent: reason named, no limit invented."""
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 0.86, "solvent": "CDCl3"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    observation = body["observation"]
    assert observation["identity_status"] == "unresolved"
    assert observation["unresolved_reason"] == "not_in_q3c_subset"
    assert observation["concentration_limit_ppm"] is None
    # Empty rather than fabricated: no rule set produced a number.
    assert body["rule_set_versions"] == {}


def test_an_unknown_analysis_is_a_non_leaking_404(client: TestClient):
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": 987_654, "shift_ppm": 2.05, "solvent": "CDCl3"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Analysis record not found."


def test_an_unsupported_route_is_rejected_at_the_edge_not_inside_the_engine(
    client: TestClient, app
):
    """classify_solvent raises on an unsupported route; the wire model must catch it first."""
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={
            "analysis_id": analysis_id,
            "shift_ppm": 2.05,
            "solvent": "CDCl3",
            "route": "topical",
        },
    )
    assert response.status_code == 422


def test_an_unknown_field_is_rejected(client: TestClient, app):
    analysis_id = _analysis(app, user_id=None)
    response = client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 2.05, "compound": "ethyl acetate"},
    )
    # extra="forbid": a caller must not be able to assert the regulatory identity.
    assert response.status_code == 422


def test_listing_returns_recorded_observations(client: TestClient, app):
    analysis_id = _analysis(app, user_id=None)
    client.post(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        json={"analysis_id": analysis_id, "shift_ppm": 2.05, "solvent": "CDCl3"},
    )

    response = client.get(
        "/regulatory/spectral-impurities",
        headers=HEADERS,
        params={"analysis_id": analysis_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["observations"]) == 1
    assert body["observations"][0]["compound"] == "ethyl acetate"
    assert body["human_review_required"] is True


def test_requires_authentication(client: TestClient):
    response = client.post(
        "/regulatory/spectral-impurities",
        json={"analysis_id": 1, "shift_ppm": 2.05},
    )
    assert response.status_code == 401


def test_both_routes_are_registered_in_the_openapi_schema(client: TestClient):
    """The FE contract is generated from this — an unregistered route is an invisible feature."""
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/regulatory/spectral-impurities"]
    assert "post" in path and "get" in path
    assert "SpectralImpurityObservationResult" in schema["components"]["schemas"]
