"""L0/C2 — approving a model in the product now changes what the router serves.

The hole this closes: `InferenceRouter` resolves what to serve from
`moltrace.spectroscopy.ai.registry`, keyed by (role, nucleus) among entries whose
current status is `production`. Nothing in the product ever wrote those tables. So
`POST /ml/deployment-candidates/{id}/approve` flipped a row's status and changed
**nothing** about which artifact actually answered a prediction — the governance
surface and the serving path were two systems that both called their subject
"the deployed model".
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi.testclient import TestClient

_TASK_KEY = "nmr_shift_prediction_baseline"
_METRICS = {"top1_accuracy": 0.80, "ece": 0.030, "false_confirmation_rate": 0.020}


def _sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _promotion(suffix: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "role": "nmrnet_checkpoint",
        "semantic_version": f"1.0.{suffix}",
        "dataset_snapshot_hash": f"sha256:{_sha256('dataset-' + suffix)}",
        "dataset_row_count": 4950,
        "nucleus": "13C",
        "dataset_source": "nmrshiftdb2",
        # `create_training_run` records `artifact_sha256=None`, so the promoter supplies
        # the hash of the artifact that was actually reviewed. See
        # `test_an_artifact_with_no_content_hash_cannot_be_promoted`.
        "artifact_sha256": _sha256("artifact-" + suffix),
    }
    body.update(overrides)
    return body


def _artifact(
    client: TestClient,
    headers: dict[str, str],
    suffix: str,
    *,
    metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    dataset = client.post(
        "/knowledge/dataset-versions",
        headers=headers,
        json={
            "dataset_type": "spectroscopy",
            "name": f"Registry-promotion fixture {suffix}",
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
            "model_name": f"registry-promotion-{suffix}",
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
            "metrics_json": dict(metrics or _METRICS),
        },
    )
    assert evaluation.status_code == 201, evaluation.text

    card = client.post(
        "/ml/model-cards",
        headers=headers,
        json={
            "model_artifact_id": artifact_id,
            "task_key": _TASK_KEY,
            "intended_use": "Fixture for registry promotion.",
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


def _approve(
    client: TestClient,
    headers: dict[str, str],
    candidate_id: int,
    promotion: dict[str, Any] | None = None,
) -> Any:
    body: dict[str, Any] = {
        "reviewer_name": "Registry reviewer",
        "reviewer_comment": "Reviewed the model card, the metrics, and the data lineage.",
    }
    if promotion is not None:
        body["registry_promotion"] = promotion
    return client.post(
        f"/ml/deployment-candidates/{candidate_id}/approve", headers=headers, json=body
    )


def _artifact_record(client: TestClient, headers: dict[str, str], artifact_id: int) -> Any:
    response = client.get(f"/ml/model-artifacts/{artifact_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# The hole, closed
# --------------------------------------------------------------------------- #
def test_promotion_makes_the_router_resolve_the_approved_artifact(client, api_headers) -> None:
    """The load-bearing assertion: after approval, InferenceRouter serves this artifact."""

    with client:
        fixture = _artifact(client, api_headers, "serving")
        approved = _approve(client, api_headers, fixture["candidate_id"], _promotion("serving"))
        assert approved.status_code == 200, approved.text

        record = _artifact_record(client, api_headers, fixture["artifact_id"])
        model_id = record["registry_model_id"]
        assert model_id == "nmrnet_checkpoint:13C:1.0.serving"
        assert record["registry_status"] == "production"
        assert record["registry_role"] == "nmrnet_checkpoint"
        assert record["registry_nucleus"] == "13C"

        # Resolve through the science layer itself, not through the record we just read.
        from nmrcheck import ai_engine_adapter as adapter
        from moltrace.spectroscopy.ai.registry import ModelRegistry, ModelRole

        factory = client.app.state.session_factory
        registry = ModelRegistry(adapter._registry_store(factory))
        resolved = registry.resolve(ModelRole.NMRNET_CHECKPOINT, "13C")
        assert resolved is not None, "the router would find no production artifact"
        assert resolved.model_id == model_id
        assert resolved.training_data_lineage.row_count == 4950
        assert resolved.training_data_lineage.source == "nmrshiftdb2"


def test_approval_without_a_promotion_block_does_not_change_serving(client, api_headers) -> None:
    """Approving for the product is a different decision from serving traffic."""

    with client:
        fixture = _artifact(client, api_headers, "unpromoted")
        approved = _approve(client, api_headers, fixture["candidate_id"])
        assert approved.status_code == 200, approved.text

        record = _artifact_record(client, api_headers, fixture["artifact_id"])
        assert record["status"] == "approved"
        assert record["registry_model_id"] is None
        assert record["registry_status"] is None


def test_a_promotion_supersedes_the_incumbent_for_the_same_role_and_nucleus(
    client, api_headers
) -> None:
    with client:
        first = _artifact(client, api_headers, "old")
        assert (
            _approve(client, api_headers, first["candidate_id"], _promotion("old")).status_code
            == 200
        )

        second = _artifact(
            client,
            api_headers,
            "new",
            metrics={"top1_accuracy": 0.86, "ece": 0.028, "false_confirmation_rate": 0.011},
        )
        approved = _approve(client, api_headers, second["candidate_id"], _promotion("new"))
        assert approved.status_code == 200, approved.text

        # The record shows the supersession, and the old entry is retired rather than
        # edited -- the append-only property the link exists to preserve.
        listed = client.get("/ml/deployment-candidates", headers=api_headers)
        promotion = next(
            c for c in listed.json() if c["id"] == second["candidate_id"]
        )["metadata_json"]["registry_promotion"]
        assert promotion["promoted"] is True
        assert promotion["superseded_model_id"] == "nmrnet_checkpoint:13C:1.0.old"

        old_record = _artifact_record(client, api_headers, first["artifact_id"])
        assert old_record["registry_status"] == "retired"
        new_record = _artifact_record(client, api_headers, second["artifact_id"])
        assert new_record["registry_status"] == "production"


# --------------------------------------------------------------------------- #
# Refusals — each names its cause, and none unwinds the approval
# --------------------------------------------------------------------------- #
def test_an_artifact_with_no_content_hash_cannot_be_promoted(client, api_headers) -> None:
    """A promotion that cannot be verified later is refused, and the approval stands."""

    with client:
        fixture = _artifact(client, api_headers, "nohash")
        promotion = _promotion("nohash")
        del promotion["artifact_sha256"]  # and the artifact row carries none either
        response = _approve(client, api_headers, fixture["candidate_id"], promotion)
        assert response.status_code == 200, response.text

        listed = client.get("/ml/deployment-candidates", headers=api_headers)
        outcome = next(
            c for c in listed.json() if c["id"] == fixture["candidate_id"]
        )["metadata_json"]["registry_promotion"]
        assert outcome["promoted"] is False
        assert "no content hash" in outcome["reason"]

        record = _artifact_record(client, api_headers, fixture["artifact_id"])
        assert record["status"] == "approved"
        assert record["registry_model_id"] is None


def test_a_failed_promotion_leaves_the_approval_standing(client, api_headers) -> None:
    """Approved and not serving is a state a reviewer can act on; a false success is not."""

    with client:
        fixture = _artifact(client, api_headers, "dup")
        # The same semantic version is claimed twice against different content, which
        # the append-only registry must refuse rather than reconcile.
        assert (
            _approve(client, api_headers, fixture["candidate_id"], _promotion("dup")).status_code
            == 200
        )
        clash = _artifact(
            client,
            api_headers,
            "clash",
            metrics={"top1_accuracy": 0.86, "ece": 0.028, "false_confirmation_rate": 0.011},
        )
        response = _approve(
            client,
            api_headers,
            clash["candidate_id"],
            _promotion("dup", artifact_sha256=_sha256("different-bytes")),
        )
        assert response.status_code == 200, response.text

        listed = client.get("/ml/deployment-candidates", headers=api_headers)
        promotion = next(
            c for c in listed.json() if c["id"] == clash["candidate_id"]
        )["metadata_json"]["registry_promotion"]
        assert promotion["promoted"] is False
        assert "different artifact hash" in promotion["reason"]

        # The approval itself stands, and the router keeps serving the incumbent.
        record = _artifact_record(client, api_headers, clash["artifact_id"])
        assert record["status"] == "approved"
        assert record["registry_model_id"] is None


def test_an_unknown_role_is_refused_by_name(client, api_headers) -> None:
    with client:
        fixture = _artifact(client, api_headers, "badrole")
        response = _approve(
            client,
            api_headers,
            fixture["candidate_id"],
            _promotion("badrole", role="not_a_role"),
        )
        # Rejected by the contract before it reaches the registry.
        assert response.status_code == 422, response.text


def test_promotion_requires_data_lineage(client, api_headers) -> None:
    """A promotion with no data lineage is not reproducible, so the contract refuses it."""

    with client:
        fixture = _artifact(client, api_headers, "nolineage")
        promotion = _promotion("nolineage")
        del promotion["dataset_snapshot_hash"]
        response = _approve(client, api_headers, fixture["candidate_id"], promotion)
        assert response.status_code == 422, response.text
        assert "dataset_snapshot_hash" in response.text
