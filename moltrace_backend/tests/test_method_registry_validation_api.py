def test_method_registry_validation_dashboard_workflow(client, api_headers):
    headers = api_headers
    with client:
        builtins_res = client.get("/method-registry", headers=headers)
        assert builtins_res.status_code == 200, builtins_res.text
        builtin_slugs = {record["slug"] for record in builtins_res.json()}
        assert "candidate_specific_predicted_nmr_matching" in builtin_slugs
        assert "workflow_orchestration" in builtin_slugs

        method_res = client.post(
            "/method-registry",
            headers=headers,
            json={
                "name": "Fixture NMR Method",
                "slug": "fixture_nmr_method",
                "category": "nmr",
                "version": "2026.05",
                "description": "Fixture method for validation dashboard tests.",
                "endpoint_paths_json": ["/fixture/nmr"],
            },
        )
        assert method_res.status_code == 201, method_res.text
        method = method_res.json()

        patch_method = client.patch(
            f"/method-registry/{method['id']}",
            headers=headers,
            json={"status": "experimental"},
        )
        assert patch_method.status_code == 200, patch_method.text
        assert patch_method.json()["status"] == "experimental"

        model_res = client.post(
            "/model-versions",
            headers=headers,
            json={
                "method_id": method["id"],
                "model_name": "fixture-heuristic",
                "model_family": "heuristic",
                "version": "1.0.0",
                "validation_summary": "Validated only against fixture data.",
            },
        )
        assert model_res.status_code == 201, model_res.text
        model = model_res.json()

        scoring_res = client.post(
            "/scoring-profiles",
            headers=headers,
            json={
                "method_id": method["id"],
                "name": "Fixture scoring",
                "slug": "fixture_scoring",
                "version": "1.0.0",
                "weights_json": {"shape": 0.6, "shift": 0.4},
                "scoring_rules_json": {"combine": "weighted_mean"},
                "label_thresholds_json": {"plausible": 0.7},
            },
        )
        assert scoring_res.status_code == 201, scoring_res.text
        scoring = scoring_res.json()

        threshold_res = client.post(
            "/threshold-profiles",
            headers=headers,
            json={
                "name": "Fixture thresholds",
                "slug": "fixture_thresholds",
                "version": "1.0.0",
                "category": "nmr",
                "thresholds_json": {"min_score": 0.7},
            },
        )
        assert threshold_res.status_code == 201, threshold_res.text
        threshold = threshold_res.json()

        benchmark_res = client.post(
            "/benchmark-datasets",
            headers=headers,
            json={
                "name": "Fixture benchmark",
                "slug": "fixture_benchmark",
                "version": "1.0.0",
                "category": "nmr",
                "description": "Small synthetic benchmark for API tests.",
                "sample_count": 2,
                "ground_truth_summary": "Fixture labels only.",
            },
        )
        assert benchmark_res.status_code == 201, benchmark_res.text
        benchmark = benchmark_res.json()

        validation_res = client.post(
            "/validation-runs",
            headers=headers,
            json={
                "method_id": method["id"],
                "model_version_id": model["id"],
                "scoring_profile_id": scoring["id"],
                "threshold_profile_id": threshold["id"],
                "benchmark_dataset_id": benchmark["id"],
                "status": "requires_review",
                "metrics_json": {"fixture_accuracy": 0.91},
                "warnings_json": ["Fixture validation is not a scientific claim."],
                "notes_json": ["Human review remains required."],
                "metrics": [
                    {
                        "metric_name": "fixture_accuracy",
                        "metric_value": 0.91,
                        "target_value": 0.9,
                        "passed": True,
                    },
                    {
                        "metric_name": "fixture_drift",
                        "metric_value": 0.42,
                        "target_value": 0.2,
                        "passed": False,
                    },
                ],
                "drift_alerts": [
                    {
                        "severity": "warning",
                        "title": "Fixture drift review",
                        "message": "Fixture drift requires review before release.",
                        "metric_name": "fixture_drift",
                        "baseline_value": 0.2,
                        "current_value": 0.42,
                    }
                ],
            },
        )
        assert validation_res.status_code == 201, validation_res.text
        validation_run = validation_res.json()
        assert validation_run["metrics_json"]["fixture_accuracy"] == 0.91
        assert {metric["metric_name"] for metric in validation_run["metrics"]} == {
            "fixture_accuracy",
            "fixture_drift",
        }

        fetched_validation = client.get(
            f"/validation-runs/{validation_run['id']}",
            headers=headers,
        )
        assert fetched_validation.status_code == 200, fetched_validation.text
        assert len(fetched_validation.json()["metrics"]) == 2

        alerts_res = client.get("/model-health/drift-alerts", headers=headers)
        assert alerts_res.status_code == 200, alerts_res.text
        open_alerts = [alert for alert in alerts_res.json() if alert["status"] == "open"]
        assert open_alerts
        alert_id = open_alerts[0]["id"]

        ack_res = client.post(
            f"/model-health/drift-alerts/{alert_id}/acknowledge",
            headers=headers,
        )
        assert ack_res.status_code == 200, ack_res.text
        assert ack_res.json()["status"] == "acknowledged"

        resolve_res = client.post(
            f"/model-health/drift-alerts/{alert_id}/resolve",
            headers=headers,
        )
        assert resolve_res.status_code == 200, resolve_res.text
        assert resolve_res.json()["status"] == "resolved"

        health_res = client.get("/model-health", headers=headers)
        assert health_res.status_code == 200, health_res.text
        health = health_res.json()
        assert health["method_count"] >= len(builtin_slugs)
        assert health["validation_run_count"] == 1

        comparison_res = client.post(
            "/method-comparisons",
            headers=headers,
            json={
                "baseline_method_id": method["id"],
                "candidate_method_id": method["id"],
                "benchmark_dataset_id": benchmark["id"],
                "status": "succeeded",
                "metrics_json": {"delta_accuracy": 0.0},
                "winner": "tie",
            },
        )
        assert comparison_res.status_code == 201, comparison_res.text

        audit_res = client.get(
            "/audit",
            headers=headers,
            params={"event_type": "method_registry.validation_run.create"},
        )
        assert audit_res.status_code == 200, audit_res.text
        assert audit_res.json()


def test_method_registry_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/method-registry",
        "/method-registry/{method_id}",
        "/model-versions",
        "/model-versions/{model_version_id}",
        "/scoring-profiles",
        "/scoring-profiles/{profile_id}",
        "/threshold-profiles",
        "/threshold-profiles/{profile_id}",
        "/benchmark-datasets",
        "/benchmark-datasets/{benchmark_id}",
        "/validation-runs",
        "/validation-runs/{validation_run_id}",
        "/method-comparisons",
        "/method-comparisons/{comparison_id}",
        "/model-health",
        "/model-health/drift-alerts",
        "/model-health/drift-alerts/{alert_id}/acknowledge",
        "/model-health/drift-alerts/{alert_id}/resolve",
    ]:
        assert path in paths
    assert "post" in paths["/method-registry"]
    assert "patch" in paths["/model-versions/{model_version_id}"]
