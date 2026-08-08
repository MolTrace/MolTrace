"""L0 at the HTTP boundary: the AI/ML routes now record what an engine computed.

The defect these tests close: ``POST /ai/predictions`` accepted ``confidence_score``
in the request body and, when the caller omitted it, recorded a hard-coded ``0.82``.
Every downstream consumer -- the calibration record, the drift alert, the review
queue -- treated that number exactly as it would treat a measured one.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

_RANKING_REQUEST: dict[str, Any] = {
    "nucleus": "13C",
    "observed_shifts_ppm": [18.0, 58.0, 128.0, 140.0],
    "candidates": [
        {"candidate_id": "close", "predicted_shifts_ppm": [18.2, 58.3, 127.6, 140.4]},
        {"candidate_id": "far", "predicted_shifts_ppm": [40.0, 90.0, 100.0, 175.0]},
    ],
}


def _post_prediction(
    client: TestClient, headers: dict[str, str], **overrides: Any
) -> Any:
    body: dict[str, Any] = {
        "service_key": "nmr_candidate_ranking",
        "request_json": dict(_RANKING_REQUEST),
        "development_mode": True,
    }
    body.update(overrides)
    return client.post("/ai/predictions", headers=headers, json=body)


def test_an_engine_backed_prediction_is_computed_not_submitted(client, api_headers) -> None:
    with client:
        response = _post_prediction(client, api_headers)
        assert response.status_code == 201, response.text
        body = response.json()

        # The confidence is the top candidate's DP4 posterior, not a stored constant.
        assert body["confidence_score"] is not None
        assert body["confidence_score"] != 0.82
        ranked = body["result"]["engine_output"]["candidates"]
        assert ranked[0]["candidate_id"] == "close"
        assert body["confidence_score"] == ranked[0]["dp4_probability"]

        # The uncertainty is the engine's, and names the scale it is on.
        assert body["uncertainty"]["scale"] == "dp4_posterior"
        assert body["uncertainty"]["n_candidates"] == 2

        # DP4's closed-world assumption is stated, not implied away.
        assert any("closed-world" in warning for warning in body["warnings"])
        assert body["human_review_required"] is True


def test_provenance_travels_with_the_number(client, api_headers) -> None:
    with client:
        created = _post_prediction(client, api_headers)
        assert created.status_code == 201, created.text
        prediction_id = created.json()["prediction_run_id"]

        listed = client.get("/ai/predictions", headers=api_headers)
        assert listed.status_code == 200, listed.text
        run = next(r for r in listed.json() if r["id"] == prediction_id)
        provenance = run["metadata_json"]["provenance"]
        assert provenance["engine"].startswith("moltrace.spectroscopy.ai")
        assert provenance["model_versions"], "a recorded number must name what produced it"


def test_a_caller_cannot_supply_the_confidence_for_an_engine_backed_service(
    client, api_headers
) -> None:
    with client:
        response = _post_prediction(
            client,
            api_headers,
            request_json={**_RANKING_REQUEST, "confidence_score": 0.99},
        )
        assert response.status_code == 400, response.text
        assert "confidence_score" in response.json()["detail"]


def test_a_caller_cannot_supply_the_domain_assessment_either(client, api_headers) -> None:
    with client:
        response = _post_prediction(
            client,
            api_headers,
            request_json={**_RANKING_REQUEST, "ood_status": "in_domain"},
        )
        assert response.status_code == 400, response.text
        assert "ood_status" in response.json()["detail"]


def test_a_bad_engine_input_names_the_field_it_is_missing(client, api_headers) -> None:
    with client:
        response = _post_prediction(client, api_headers, request_json={"nucleus": "13C"})
        assert response.status_code == 400, response.text
        assert "observed_shifts_ppm" in response.json()["detail"]


def test_an_abstaining_engine_result_still_reaches_review(client, api_headers) -> None:
    """No confidence must not read as high confidence just because there is no number."""

    with client:
        response = _post_prediction(
            client,
            api_headers,
            request_json={
                "nucleus": "13C",
                "observed_shifts_ppm": [18.0, 58.0],
                "candidates": [{"candidate_id": "only", "predicted_shifts_ppm": [18.2, 58.3]}],
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["confidence_score"] is None
        assert body["status"] == "requires_review"
        assert any("1.0 by construction" in w for w in body["warnings"])


def test_a_service_with_no_engine_records_no_fabricated_confidence(
    client, api_headers
) -> None:
    """The 0.82 regression guard: no engine and no submitted number means no number."""

    with client:
        response = client.post(
            "/ai/predictions",
            headers=api_headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "request_json": {"temperature_c": 80},
                "development_mode": True,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["confidence_score"] is None
        assert any("not computed by a model" in w for w in body["warnings"])


# --------------------------------------------------------------------------- #
# The promotion gate at the HTTP boundary
# --------------------------------------------------------------------------- #
_TASK_KEY = "nmr_candidate_ranking_baseline"


def _evaluated_artifact(
    client: TestClient, headers: dict[str, str], suffix: str, metrics: dict[str, float]
) -> dict[str, Any]:
    dataset = client.post(
        "/knowledge/dataset-versions",
        headers=headers,
        json={
            "dataset_type": "spectroscopy",
            "name": f"Promotion-gate fixture {suffix}",
            "version": suffix,
            "source_record_ids_json": [{"record_type": "spectrum", "record_id": 1}],
            "split_json": {"train": [1], "holdout": [1]},
            "status": "draft",
        },
    )
    assert dataset.status_code == 201, dataset.text

    training = client.post(
        "/ml/training-runs",
        headers=headers,
        json={
            "task_key": _TASK_KEY,
            "dataset_version_id": dataset.json()["id"],
            "model_family": "baseline",
            "model_name": f"promotion-gate-{suffix}",
            "model_version": suffix,
            "experimental": True,
            "parameters_json": {"baseline_model": "mean"},
        },
    )
    assert training.status_code == 201, training.text
    run = training.json()
    artifact_id = run["model_artifact_id"]

    evaluation = client.post(
        "/ml/evaluation-runs",
        headers=headers,
        json={
            "training_run_id": run["training_run_id"],
            "model_artifact_id": artifact_id,
            "dataset_version_id": dataset.json()["id"],
            "metrics_json": metrics,
        },
    )
    assert evaluation.status_code == 201, evaluation.text

    card = client.post(
        "/ml/model-cards",
        headers=headers,
        json={
            "model_artifact_id": artifact_id,
            "task_key": _TASK_KEY,
            "intended_use": "Fixture for the promotion gate.",
            "limitations": "Fixture-only experimental model; requires review.",
            "human_review_summary_json": {"required": True},
            "approval_status": "ready_for_review",
        },
    )
    assert card.status_code == 201, card.text

    candidate = client.post(
        "/ml/deployment-candidates",
        headers=headers,
        json={
            "model_artifact_id": artifact_id,
            "model_card_id": card.json()["id"],
            "target_module": "spectracheck",
            "target_endpoint": "/ai/predictions",
        },
    )
    assert candidate.status_code == 201, candidate.text
    return {"artifact_id": artifact_id, "candidate_id": candidate.json()["candidate_id"]}


def _approve(client: TestClient, headers: dict[str, str], candidate_id: int) -> Any:
    return client.post(
        f"/ml/deployment-candidates/{candidate_id}/approve",
        headers=headers,
        json={
            "reviewer_name": "Promotion gate reviewer",
            "reviewer_comment": "Reviewed the model card and the evaluation metrics.",
        },
    )


def test_a_calibration_regression_is_refused_however_good_the_accuracy(
    client, api_headers
) -> None:
    """An accuracy gain does not buy a worse ECE: the gate refuses before the reviewer sees it."""

    with client:
        incumbent = _evaluated_artifact(
            client,
            api_headers,
            "incumbent",
            {"top1_accuracy": 0.80, "ece": 0.030, "false_confirmation_rate": 0.020},
        )
        first = _approve(client, api_headers, incumbent["candidate_id"])
        assert first.status_code == 200, first.text
        # No incumbent existed, so the gate had no opinion — and says so to the reviewer
        # rather than letting a skipped check read as an endorsement.
        assert any(
            "Metric comparison skipped" in note and "baseline decision" in note
            for note in first.json()["notes"]
        ), first.json()["notes"]

        challenger = _evaluated_artifact(
            client,
            api_headers,
            "challenger",
            {"top1_accuracy": 0.95, "ece": 0.041, "false_confirmation_rate": 0.020},
        )
        refused = _approve(client, api_headers, challenger["candidate_id"])
        assert refused.status_code == 400, refused.text
        detail = refused.json()["detail"]
        assert "ece" in detail
        assert "may not regress at all" in detail


def test_a_dominating_candidate_is_approved_and_the_gate_records_why(
    client, api_headers
) -> None:
    with client:
        incumbent = _evaluated_artifact(
            client,
            api_headers,
            "base",
            {"top1_accuracy": 0.80, "ece": 0.030, "false_confirmation_rate": 0.020},
        )
        assert _approve(client, api_headers, incumbent["candidate_id"]).status_code == 200

        better = _evaluated_artifact(
            client,
            api_headers,
            "better",
            {"top1_accuracy": 0.86, "ece": 0.028, "false_confirmation_rate": 0.011},
        )
        approved = _approve(client, api_headers, better["candidate_id"])
        assert approved.status_code == 200, approved.text
        note = next(n for n in approved.json()["notes"] if n.startswith("Metric comparison:"))
        assert "top1_accuracy" in note and "ece" in note and "no regression" in note

        listed = client.get("/ml/deployment-candidates", headers=api_headers)
        assert listed.status_code == 200, listed.text
        record = next(
            c for c in listed.json() if c["id"] == better["candidate_id"]
        )
        check = record["metadata_json"]["promotion_check"]
        assert check["applied"] is True
        assert "top1_accuracy" in check["improvements"]
        assert "ece" in check["improvements"]
