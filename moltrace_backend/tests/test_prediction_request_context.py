"""Regression coverage for the AI prediction request context contract.

The frontend "Run prediction" action attaches four context references
(evidence_item_id, compound_id, session_id, notes) to a prediction. These have
no dedicated columns; they are accepted as first-class optional fields and
persisted into the run summary and metadata so requester intent is retained.
Before this contract change PredictionRequest rejected them as extra_forbidden,
so every run returned 422.
"""

from tests.test_phase59_controlled_ai_inference_api import _approved_artifact


def test_prediction_context_fields_persist(client, api_headers):
    headers = api_headers
    with client:
        approved = _approved_artifact(client, headers)
        artifact_id = approved["artifact_id"]

        # Corrected FE body: mechanical renames applied + the 4 context fields kept.
        resp = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": artifact_id,
                "request_json": {"temperature_c": 80, "confidence_score": 0.86},
                "experimental": False,
                "evidence_item_id": 12,
                "compound_id": 34,
                "session_id": 7,
                "notes": "ran for lot A",
            },
        )
        assert resp.status_code == 201, resp.text

        run = client.get("/ai/predictions", headers=headers).json()[0]
        expected = {
            "evidence_item_id": 12,
            "compound_id": 34,
            "session_id": 7,
            "notes": "ran for lot A",
        }
        assert run["request_summary_json"]["context"] == expected, run["request_summary_json"]
        assert run["metadata_json"]["context"] == expected, run["metadata_json"]

        # An empty-context request adds no "context" key at all (no noise).
        resp2 = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "model_artifact_id": artifact_id,
                "request_json": {"temperature_c": 80, "confidence_score": 0.86},
            },
        )
        assert resp2.status_code == 201, resp2.text
        run2 = client.get("/ai/predictions", headers=headers).json()[0]
        assert "context" not in run2["request_summary_json"], run2["request_summary_json"]
        assert "context" not in run2["metadata_json"], run2["metadata_json"]


def test_prediction_rejects_stale_frontend_keys(client, api_headers):
    """The pre-fix FE body must still 422: its extra keys are not the contract."""
    headers = api_headers
    with client:
        resp = client.post(
            "/ai/predictions",
            headers=headers,
            json={
                "service_key": "reaction_outcome_predictor",
                "target_module": "nmr",
                "task_key": "quant",
                "input_summary_json": {},
                "artifact_id": None,
                "experimental_mode": False,
            },
        )
        assert resp.status_code == 422, resp.text
        rejected = {err["loc"][-1] for err in resp.json()["detail"]}
        assert {
            "target_module",
            "task_key",
            "input_summary_json",
            "artifact_id",
            "experimental_mode",
        } <= rejected, rejected
