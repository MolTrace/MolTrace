from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'phase58_ml_factory.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _dataset_version(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/knowledge/dataset-versions",
        headers=headers,
        json={
            "dataset_type": "reaction_optimization",
            "name": "Phase 58 reviewed reaction surrogate fixture",
            "version": "v0.1",
            "source_record_ids_json": [{"record_type": "reaction", "record_id": 1}],
            "split_json": {"train": [1], "holdout": [1]},
            "quality_summary_json": {
                "examples_json": [
                    {
                        "features": {"temperature_c": 80.0, "catalyst_loading": 0.02},
                        "label": 82.0,
                        "slice": {"reaction_type": "coupling"},
                    }
                ],
                "candidate_count": 1,
            },
            "leakage_warnings_json": [],
            "status": "draft",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_phase58_ml_model_factory_workflow(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        tasks = client.get("/ml/tasks", headers=headers)
        assert tasks.status_code == 200, tasks.text
        task_keys = {task["task_key"] for task in tasks.json()}
        assert {
            "nmr_shift_prediction_baseline",
            "nmr_candidate_ranking_baseline",
            "msms_similarity_scorer",
            "lcms_feature_family_classifier",
            "reaction_surrogate_baseline",
            "regulatory_extraction_classifier",
            "regulatory_citation_support_classifier",
            "knowledge_record_quality_classifier",
        }.issubset(task_keys)

        missing_dataset = client.post(
            "/ml/training-runs",
            headers=headers,
            json={
                "task_key": "reaction_surrogate_baseline",
                "model_family": "baseline",
                "model_name": "reaction-baseline",
                "model_version": "v0.1",
            },
        )
        assert missing_dataset.status_code == 400, missing_dataset.text

        dataset = _dataset_version(client, headers)

        pipeline = client.post(
            "/ml/feature-pipelines",
            headers=headers,
            json={
                "name": "Reaction numeric baseline features",
                "version": "v1",
                "task_key": "reaction_surrogate_baseline",
                "input_schema_json": {"fields": ["temperature_c", "catalyst_loading"]},
                "output_schema_json": {"target": "yield_percent"},
                "feature_steps_json": [{"name": "numeric_only"}],
            },
        )
        assert pipeline.status_code == 201, pipeline.text
        pipeline_id = pipeline.json()["id"]

        training = client.post(
            "/ml/training-runs",
            headers=headers,
            json={
                "task_key": "reaction_surrogate_baseline",
                "dataset_version_id": dataset["id"],
                "feature_pipeline_id": pipeline_id,
                "model_family": "baseline",
                "model_name": "reaction-baseline",
                "model_version": "v0.1",
                "experimental": True,
                "parameters_json": {"baseline_model": "mean"},
            },
        )
        assert training.status_code == 201, training.text
        training_body = training.json()
        assert training_body["status"] == "succeeded"
        assert training_body["model_artifact_id"]
        assert training_body["human_review_required"] is True
        assert any("experimental model" in warning for warning in training_body["warnings"])
        artifact_id = training_body["model_artifact_id"]

        evaluation = client.post(
            "/ml/evaluation-runs",
            headers=headers,
            json={
                "training_run_id": training_body["training_run_id"],
                "model_artifact_id": artifact_id,
                "dataset_version_id": dataset["id"],
                "metrics_json": {"mae": 0.12, "r2": 0.81},
                "slice_metrics_json": {"reaction_type:coupling": {"mae": 0.12}},
                "calibration_summary_json": {"method": "not_assessed"},
                "error_examples_json": [{"case_id": "case-1", "error": "small residual"}],
            },
        )
        assert evaluation.status_code == 201, evaluation.text
        evaluation_body = evaluation.json()
        assert evaluation_body["status"] == "succeeded"
        assert evaluation_body["metrics"]["mae"] == 0.12
        evaluation_id = evaluation_body["evaluation_run_id"]

        artifact = client.get(f"/ml/model-artifacts/{artifact_id}", headers=headers)
        assert artifact.status_code == 200, artifact.text
        assert artifact.json()["status"] == "evaluated"

        missing_card_candidate = client.post(
            "/ml/deployment-candidates",
            headers=headers,
            json={
                "model_artifact_id": artifact_id,
                "target_module": "reaction_optimization",
            },
        )
        assert missing_card_candidate.status_code == 400, missing_card_candidate.text

        card = client.post(
            "/ml/model-cards",
            headers=headers,
            json={
                "model_artifact_id": artifact_id,
                "task_key": "reaction_surrogate_baseline",
                "intended_use": "Review-oriented reaction surrogate baseline model.",
                "limitations": "Fixture-only experimental model; requires review before any use.",
                "training_data_summary_json": {
                    "dataset_version_id": dataset["id"],
                    "status": dataset["status"],
                },
                "evaluation_summary_json": {"evaluation_run_id": evaluation_id, "mae": 0.12},
                "bias_risk_summary_json": {"known_risks": ["small fixture"]},
                "out_of_domain_summary_json": {"status": "not_assessed"},
                "calibration_summary_json": {"status": "not_assessed"},
                "human_review_summary_json": {"required": True},
                "approval_status": "ready_for_review",
            },
        )
        assert card.status_code == 201, card.text
        card_body = card.json()
        assert card_body["approval_status"] == "ready_for_review"

        candidate = client.post(
            "/ml/deployment-candidates",
            headers=headers,
            json={
                "model_artifact_id": artifact_id,
                "model_card_id": card_body["id"],
                "target_module": "reaction_optimization",
                "target_endpoint": "/reaction-optimization/runs",
                "status": "proposed",
            },
        )
        assert candidate.status_code == 201, candidate.text
        candidate_body = candidate.json()
        assert candidate_body["candidate_id"]
        assert candidate_body["status"] == "proposed"
        assert candidate_body["warnings"]

        missing_comment = client.post(
            f"/ml/deployment-candidates/{candidate_body['candidate_id']}/approve",
            headers=headers,
            json={"reviewer_name": "Reviewer"},
        )
        assert missing_comment.status_code == 422, missing_comment.text

        approval = client.post(
            f"/ml/deployment-candidates/{candidate_body['candidate_id']}/approve",
            headers=headers,
            json={
                "reviewer_name": "Qualified reviewer",
                "reviewer_comment": (
                    "Approved for internal use after reviewing evaluation run and model card."
                ),
            },
        )
        assert approval.status_code == 200, approval.text
        assert approval.json()["status"] == "approved_for_internal_use"

        calibration = client.post(
            "/ml/calibration-assessments",
            headers=headers,
            json={
                "model_artifact_id": artifact_id,
                "evaluation_run_id": evaluation_id,
                "calibration_method": "not_assessed",
                "calibration_metrics_json": {"reason": "fixture"},
                "status": "requires_review",
            },
        )
        assert calibration.status_code == 201, calibration.text
        assert calibration.json()["status"] == "requires_review"

        error_analysis = client.post(
            "/ml/error-analysis",
            headers=headers,
            json={
                "evaluation_run_id": evaluation_id,
                "slice_name": "coupling reactions",
                "slice_type": "reaction_type",
                "sample_count": 1,
                "metrics_json": {"mae": 0.12},
                "representative_errors_json": [{"case_id": "case-1", "residual": 0.12}],
                "severity": "warning",
            },
        )
        assert error_analysis.status_code == 201, error_analysis.text
        assert error_analysis.json()["slice_type"] == "reaction_type"

        ood = client.post(
            "/ml/ood-assessments",
            headers=headers,
            json={
                "model_artifact_id": artifact_id,
                "dataset_version_id": dataset["id"],
                "method": "rule_based",
                "ood_summary_json": {"coverage": "fixture only"},
                "high_risk_regions_json": [{"region": "unseen chemistry"}],
                "status": "requires_review",
            },
        )
        assert ood.status_code == 201, ood.text
        assert ood.json()["method"] == "rule_based"

        config = client.post(
            "/ml/prediction-service-configs",
            headers=headers,
            json={
                "target_module": "reaction_optimization",
                "active_model_artifact_id": artifact_id,
                "routing_rules_json": {"mode": "manual"},
                "status": "draft",
            },
        )
        assert config.status_code == 201, config.text
        assert config.json()["status"] == "draft"

        health = client.get("/ml/model-health", headers=headers)
        assert health.status_code == 200, health.text
        health_body = health.json()
        assert health_body["training_run_count"] == 1
        assert health_body["evaluation_run_count"] == 1
        assert health_body["model_artifact_count"] == 1
        assert health_body["experimental_model_count"] == 1
        assert health_body["approved_deployment_candidate_count"] == 1

        audit = client.get(
            "/audit",
            headers=headers,
            params={"event_type": "ml_factory.deployment_candidate.approve"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()


def test_phase58_ml_model_factory_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    for path in [
        "/ml/tasks",
        "/ml/feature-pipelines",
        "/ml/feature-pipelines/{pipeline_id}",
        "/ml/training-runs",
        "/ml/training-runs/{training_run_id}",
        "/ml/training-runs/{training_run_id}/cancel",
        "/ml/evaluation-runs",
        "/ml/evaluation-runs/{evaluation_run_id}",
        "/ml/model-artifacts",
        "/ml/model-artifacts/{model_artifact_id}",
        "/ml/model-cards",
        "/ml/model-cards/{model_card_id}",
        "/ml/calibration-assessments",
        "/ml/calibration-assessments/{assessment_id}",
        "/ml/error-analysis",
        "/ml/error-analysis/{error_analysis_id}",
        "/ml/ood-assessments",
        "/ml/ood-assessments/{ood_assessment_id}",
        "/ml/deployment-candidates",
        "/ml/deployment-candidates/{candidate_id}",
        "/ml/deployment-candidates/{candidate_id}/approve",
        "/ml/deployment-candidates/{candidate_id}/reject",
        "/ml/model-health",
        "/ml/prediction-service-configs",
    ]:
        assert path in paths

    schemas = response.json()["components"]["schemas"]
    for schema in [
        "MLTaskDefinition",
        "FeaturePipeline",
        "MLTrainingRun",
        "MLEvaluationRun",
        "ModelArtifact",
        "ModelCard",
        "ModelMetric",
        "CalibrationAssessment",
        "ErrorAnalysisSlice",
        "OutOfDomainAssessment",
        "DeploymentCandidate",
        "PredictionServiceConfig",
    ]:
        assert schema in schemas
