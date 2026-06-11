from fastapi.testclient import TestClient


def _dataset_version(client: TestClient, headers: dict[str, str], suffix: str) -> dict:
    response = client.post(
        "/knowledge/dataset-versions",
        headers=headers,
        json={
            "dataset_type": "reaction_optimization",
            "name": f"Phase 59 reviewed reaction fixture {suffix}",
            "version": suffix,
            "source_record_ids_json": [{"record_type": "reaction", "record_id": 1}],
            "split_json": {"train": [1], "holdout": [1]},
            "quality_summary_json": {
                "examples_json": [
                    {
                        "features": {"temperature_c": 80.0, "catalyst_loading": 0.02},
                        "label": 82.0,
                        "slice": {"reaction_type": "coupling"},
                    }
                ]
            },
            "status": "draft",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trained_artifact(client: TestClient, headers: dict[str, str], suffix: str) -> dict:
    dataset = _dataset_version(client, headers, suffix)
    training = client.post(
        "/ml/training-runs",
        headers=headers,
        json={
            "task_key": "reaction_surrogate_baseline",
            "dataset_version_id": dataset["id"],
            "model_family": "baseline",
            "model_name": f"phase59-reaction-baseline-{suffix}",
            "model_version": suffix,
            "experimental": True,
            "parameters_json": {"baseline_model": "mean"},
        },
    )
    assert training.status_code == 201, training.text
    return {"dataset": dataset, "training": training.json()}


def _approved_artifact(client: TestClient, headers: dict[str, str]) -> dict:
    fixture = _trained_artifact(client, headers, "approved")
    dataset = fixture["dataset"]
    training = fixture["training"]
    artifact_id = training["model_artifact_id"]

    evaluation = client.post(
        "/ml/evaluation-runs",
        headers=headers,
        json={
            "training_run_id": training["training_run_id"],
            "model_artifact_id": artifact_id,
            "dataset_version_id": dataset["id"],
            "metrics_json": {"mae": 0.11, "r2": 0.82},
            "slice_metrics_json": {"reaction_type:coupling": {"mae": 0.11}},
            "error_examples_json": [{"case_id": "case-1", "error": "fixture residual"}],
        },
    )
    assert evaluation.status_code == 201, evaluation.text

    card = client.post(
        "/ml/model-cards",
        headers=headers,
        json={
            "model_artifact_id": artifact_id,
            "task_key": "reaction_surrogate_baseline",
            "intended_use": "Internal review of reaction baseline model-supported suggestions.",
            "limitations": "Fixture-only experimental model; requires review for all predictions.",
            "training_data_summary_json": {"dataset_version_id": dataset["id"]},
            "evaluation_summary_json": {
                "evaluation_run_id": evaluation.json()["evaluation_run_id"]
            },
            "bias_risk_summary_json": {"known_risks": ["small fixture"]},
            "out_of_domain_summary_json": {"status": "not_assessed"},
            "calibration_summary_json": {"status": "not_assessed"},
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
            "target_module": "reaction_optimization",
            "target_endpoint": "/ai/predictions",
        },
    )
    assert candidate.status_code == 201, candidate.text

    approval = client.post(
        f"/ml/deployment-candidates/{candidate.json()['candidate_id']}/approve",
        headers=headers,
        json={
            "reviewer_name": "Phase 59 reviewer",
            "reviewer_comment": "Approved for internal use after reviewing model card and metrics.",
        },
    )
    assert approval.status_code == 200, approval.text
    return {
        "dataset": dataset,
        "training": training,
        "evaluation": evaluation.json(),
        "card": card.json(),
        "candidate": approval.json(),
        "artifact_id": artifact_id,
    }


def test_phase59_controlled_ai_inference_workflow(client, api_headers):
    headers = api_headers
    with client:
        services = client.get("/ai/services", headers=headers)
        assert services.status_code == 200, services.text
        service_keys = {service["service_key"] for service in services.json()}
        assert {
            "nmr_shift_prediction",
            "nmr_candidate_ranking",
            "msms_annotation_scorer",
            "lcms_feature_classifier",
            "reaction_outcome_predictor",
            "reaction_recommendation_scorer",
            "regulatory_extraction_classifier",
            "citation_support_classifier",
            "knowledge_quality_scorer",
        }.issubset(service_keys)

        approved = _approved_artifact(client, headers)
        unapproved = _trained_artifact(client, headers, "experimental")["training"]
        approved_artifact_id = approved["artifact_id"]
        unapproved_artifact_id = unapproved["model_artifact_id"]

        blocked = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": unapproved_artifact_id,
                "request_json": {"temperature_c": 80, "confidence_score": 0.9},
            },
        )
        assert blocked.status_code == 400, blocked.text
        assert "Unapproved model artifact" in blocked.text

        experimental = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": unapproved_artifact_id,
                "experimental": True,
                "request_json": {"temperature_c": 80, "confidence_score": 0.91},
            },
        )
        assert experimental.status_code == 201, experimental.text
        assert experimental.json()["status"] == "succeeded"
        assert experimental.json()["human_review_required"] is True
        assert any("Experimental model" in warning for warning in experimental.json()["warnings"])

        prediction = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": approved_artifact_id,
                "dataset_version_id": approved["dataset"]["id"],
                "request_json": {
                    "temperature_c": 80,
                    "confidence_score": 0.86,
                    "raw_spectrum": "private raw points must not be stored",
                    "full_smiles": "C" * 100,
                },
                "candidate_summaries_json": [
                    {
                        "candidate_id": "rxn-1",
                        "summary": "coupling fixture",
                        "score": 0.86,
                        "full_smiles": "private",
                    }
                ],
            },
        )
        assert prediction.status_code == 201, prediction.text
        prediction_body = prediction.json()
        assert prediction_body["model_artifact_id"] == approved_artifact_id
        assert prediction_body["deployment_candidate_id"]
        assert prediction_body["result"]["model_supported_suggestion"] is True
        assert prediction_body["confidence_score"] == 0.86
        prediction_id = prediction_body["prediction_run_id"]

        stored_predictions = client.get("/ai/predictions", headers=headers)
        assert stored_predictions.status_code == 200, stored_predictions.text
        stored_summary = stored_predictions.json()[0]["request_summary_json"]
        assert "raw_spectrum" not in stored_summary["request_json"]
        assert "full_smiles" not in stored_summary["request_json"]
        assert "full_smiles" not in stored_summary["candidate_summaries_json"][0]

        low_confidence = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": approved_artifact_id,
                "request_json": {"temperature_c": 80, "confidence_score": 0.25},
            },
        )
        assert low_confidence.status_code == 201, low_confidence.text
        assert low_confidence.json()["status"] == "requires_review"

        candidates = client.get("/ai/active-learning/candidates", headers=headers)
        assert candidates.status_code == 200, candidates.text
        assert any(candidate["reason"] == "low_confidence" for candidate in candidates.json())

        feedback = client.post(
            f"/ai/predictions/{prediction_id}/feedback",
            headers=headers,
            json={
                "feedback_type": "rejected",
                "reason_code": "wrong_structure",
                "reviewer_name": "Reviewer",
                "reviewer_comment": "Fixture output should be revised.",
            },
        )
        assert feedback.status_code == 200, feedback.text
        assert feedback.json()["reason_code"] == "wrong_structure"
        assert feedback.json()["active_learning_candidate_id"]
        assert feedback.json()["model_improvement_item_id"]

        queue = client.get("/knowledge/model-improvement-queue", headers=headers)
        assert queue.status_code == 200, queue.text
        assert any(
            item["id"] == feedback.json()["model_improvement_item_id"] for item in queue.json()
        )

        review = client.post(
            f"/ai/predictions/{prediction_id}/review",
            headers=headers,
            json={
                "reviewer_name": "Reviewer",
                "reviewer_comment": "Accepted as a reviewable model-supported suggestion.",
                "decision": "accepted",
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["feedback_type"] == "accepted"

        ood_prediction = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": approved_artifact_id,
                "request_json": {"confidence_score": 0.82, "ood_status": "possible_ood"},
            },
        )
        assert ood_prediction.status_code == 201, ood_prediction.text
        assert ood_prediction.json()["ood_status"] == "possible_ood"

        events = client.get("/ai/model-monitoring/events", headers=headers)
        assert events.status_code == 200, events.text
        assert any(event["event_type"] == "out_of_domain" for event in events.json())

        shadow = client.post(
            "/ai/shadow-evaluations",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "production_model_artifact_id": approved_artifact_id,
                "candidate_model_artifact_id": unapproved_artifact_id,
                "dataset_version_id": approved["dataset"]["id"],
                "status": "requires_review",
                "comparison_metrics_json": {"mae_delta": 0.03},
                "disagreement_examples_json": [{"case_id": "rxn-1", "delta": 0.03}],
            },
        )
        assert shadow.status_code == 201, shadow.text
        assert shadow.json()["status"] == "requires_review"

        canary = client.post(
            "/ai/canary-deployments",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "candidate_model_artifact_id": approved_artifact_id,
                "target_module": "reaction_optimization",
                "traffic_percent": 5,
            },
        )
        assert canary.status_code == 201, canary.text
        canary_id = canary.json()["id"]

        missing_comment = client.post(
            f"/ai/canary-deployments/{canary_id}/approve",
            headers=headers,
            json={"reviewer_name": "Reviewer"},
        )
        assert missing_comment.status_code == 422, missing_comment.text

        canary_approval = client.post(
            f"/ai/canary-deployments/{canary_id}/approve",
            headers=headers,
            json={
                "reviewer_name": "Reviewer",
                "reviewer_comment": (
                    "Approved canary record only; active service remains unchanged."
                ),
            },
        )
        assert canary_approval.status_code == 200, canary_approval.text
        assert canary_approval.json()["status"] == "approved"

        monitoring = client.get("/ai/model-monitoring", headers=headers)
        assert monitoring.status_code == 200, monitoring.text
        assert monitoring.json()["prediction_count"] >= 4
        assert monitoring.json()["active_learning_candidate_count"] >= 2

        audit = client.get("/ai/prediction-audit", headers=headers)
        assert audit.status_code == 200, audit.text
        assert audit.json()
        # The structured reason taxonomy round-trips through the read model.
        assert any(
            fb["reason_code"] == "wrong_structure"
            for entry in audit.json()
            for fb in entry["feedback"]
        )


def test_phase59_controlled_ai_inference_openapi(client):
    with client:
        response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    for path in [
        "/ai/services",
        "/ai/services/{service_id}",
        "/ai/predictions",
        "/ai/predictions/{prediction_id}",
        "/ai/predictions/{prediction_id}/feedback",
        "/ai/predictions/{prediction_id}/review",
        "/ai/routing/decide",
        "/ai/routing/decisions",
        "/ai/routing/decisions/{decision_id}",
        "/ai/explanations",
        "/ai/explanations/{explanation_id}",
        "/ai/active-learning/candidates",
        "/ai/active-learning/candidates/{candidate_id}",
        "/ai/shadow-evaluations",
        "/ai/shadow-evaluations/{shadow_run_id}",
        "/ai/canary-deployments",
        "/ai/canary-deployments/{canary_id}",
        "/ai/canary-deployments/{canary_id}/approve",
        "/ai/canary-deployments/{canary_id}/reject",
        "/ai/model-monitoring",
        "/ai/model-monitoring/events",
        "/ai/prediction-audit",
    ]:
        assert path in paths

    schemas = response.json()["components"]["schemas"]
    for schema in [
        "AIServiceRegistry",
        "PredictionRun",
        "PredictionResult",
        "PredictionResponse",
        "PredictionFeedbackResponse",
        "ModelRoutingDecision",
        "InferenceExplanation",
        "ActiveLearningCandidate",
        "ShadowEvaluationRun",
        "CanaryDeploymentRecord",
        "ModelMonitoringEvent",
        "AIModelMonitoringSummary",
        "PredictionAuditEntry",
    ]:
        assert schema in schemas

    # The structured reason taxonomy is part of the typed contract the FE binds
    # to (request, read model, and response all carry the optional reason_code).
    for schema_name in [
        "PredictionFeedbackCreate",
        "PredictionFeedback",
        "PredictionFeedbackResponse",
        "PredictionReviewRequest",
    ]:
        assert "reason_code" in schemas[schema_name]["properties"], schema_name


def test_phase59_feedback_reason_taxonomy(client, api_headers):
    """The structured reason taxonomy is optional, closed, and persisted."""
    headers = api_headers
    with client:
        approved = _approved_artifact(client, headers)
        prediction = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": approved["artifact_id"],
                "request_json": {"temperature_c": 80, "confidence_score": 0.88},
            },
        )
        assert prediction.status_code == 201, prediction.text
        prediction_id = prediction.json()["prediction_run_id"]

        # reason_code is optional: a bare thumbs-down has no structured reason.
        bare = client.post(
            f"/ai/predictions/{prediction_id}/feedback",
            headers=headers,
            json={"feedback_type": "rejected", "reviewer_name": "Reviewer"},
        )
        assert bare.status_code == 200, bare.text
        assert bare.json()["reason_code"] is None

        # Every taxonomy value is accepted and echoed back verbatim.
        for reason in [
            "wrong_shift",
            "wrong_multiplicity",
            "wrong_structure",
            "missed_impurity",
            "wrong_integration",
            "calibration_off",
            "other",
        ]:
            ok = client.post(
                f"/ai/predictions/{prediction_id}/feedback",
                headers=headers,
                json={"feedback_type": "corrected", "reason_code": reason},
            )
            assert ok.status_code == 200, ok.text
            assert ok.json()["reason_code"] == reason

        # The taxonomy is closed: an out-of-vocabulary reason is rejected (422).
        bad = client.post(
            f"/ai/predictions/{prediction_id}/feedback",
            headers=headers,
            json={"feedback_type": "rejected", "reason_code": "made_up_reason"},
        )
        assert bad.status_code == 422, bad.text

        # The reason flows into the active-learning fan-out metadata.
        audit = client.get("/ai/prediction-audit", headers=headers)
        assert audit.status_code == 200, audit.text
        reasons = {
            fb["reason_code"]
            for entry in audit.json()
            for fb in entry["feedback"]
            if fb["reason_code"] is not None
        }
        assert {"wrong_structure", "calibration_off", "other"}.issubset(reasons)
