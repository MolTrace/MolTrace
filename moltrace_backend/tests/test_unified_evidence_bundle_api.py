from fastapi.testclient import TestClient


def _bundle_item(
    layer: str,
    response: dict,
    *,
    selected: bool = True,
    contradictions: list[str] | None = None,
    warnings: list[str] | None = None,
    score: float | None = None,
    label: str | None = None,
) -> dict:
    return {
        "id": f"{layer}-1",
        "layer": layer,
        "title": layer.replace("_", " ").title(),
        "source_tab": "evidence_queue",
        "status": "ready",
        "score": score,
        "label": label,
        "summary": "Selected evidence for unified review.",
        "evidence_summary": ["Evidence item selected for unified confidence review."],
        "contradictions": contradictions or [],
        "warnings": warnings or [],
        "notes": ["Human review remains required."],
        "endpoint": f"/mock/{layer}",
        "response": response,
        "created_at": "2026-05-02T00:00:00Z",
        "provenance": {"test_fixture": True},
        "selected_for_unified": selected,
    }


def _post_bundle(client: TestClient, headers: dict, evidence_items: list[dict]):
    return client.post(
        "/confidence/candidates/unified/evidence-bundle",
        headers=headers,
        json={
            "sample_id": "sample-bundle-1",
            "solvent": "CDCl3",
            "candidates_text": "ethanol | CCO | proposed\nmethanol | CO | alternate",
            "evidence_items": evidence_items,
            "metadata": {"queue_id": "queue-123"},
        },
    )


def test_unified_evidence_bundle_empty_list_returns_clear_400(client, api_headers):
    with client:
        res = client.post(
            "/confidence/candidates/unified/evidence-bundle",
            headers=api_headers,
            json={"sample_id": "empty", "evidence_items": []},
        )
    assert res.status_code == 400
    assert "at least one evidence item" in res.text


def test_unified_evidence_bundle_with_predicted_nmr_evidence_works(client, api_headers):
    item = _bundle_item(
        "predicted_nmr",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "role": "proposed",
                    "smiles": "CCO",
                    "total_score": 0.84,
                    "label": "best_predicted_match",
                    "evidence_summary": ["Predicted NMR evidence is consistent with ethanol."],
                },
                {
                    "rank": 2,
                    "name": "methanol",
                    "role": "alternate",
                    "smiles": "CO",
                    "total_score": 0.31,
                    "label": "weak_match",
                    "evidence_summary": ["Predicted NMR evidence is weaker for methanol."],
                },
            ],
        },
    )
    with client:
        res = _post_bundle(client, api_headers, [item])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["sample_id"] == "sample-bundle-1"
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["human_review_required"] is True
    assert "Candidate-specific predicted NMR" in data["evidence_layers_used"]
    assert data["metadata"]["raw_response_policy"].startswith("Full endpoint responses")
    assert "response_sha256" in data["metadata"]["evidence_references"][0]
    assert "response" not in data["metadata"]["evidence_references"][0]


def test_unified_evidence_bundle_ignores_unselected_items(client, api_headers):
    unselected = _bundle_item(
        "predicted_nmr",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "methanol",
                    "smiles": "CO",
                    "total_score": 0.99,
                }
            ],
        },
        selected=False,
    )
    selected = _bundle_item(
        "hrms_exact_mass",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "smiles": "CCO",
                    "ppm_score": 0.74,
                }
            ],
        },
    )
    with client:
        res = _post_bundle(client, api_headers, [unselected, selected])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["metadata"]["selected_item_count"] == 1
    assert data["metadata"]["ignored_item_count"] == 1
    assert "Candidate-specific predicted NMR" not in data["evidence_layers_used"]


def test_unified_evidence_bundle_with_hrms_evidence_works(client, api_headers):
    item = _bundle_item(
        "hrms_exact_mass",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "smiles": "CCO",
                    "ppm_score": 0.98,
                    "label": "exact_mass_match",
                    "evidence_summary": ["HRMS exact mass is within tolerance for ethanol."],
                },
                {
                    "rank": 2,
                    "name": "methanol",
                    "smiles": "CO",
                    "ppm_score": 0.12,
                    "label": "outside_tolerance",
                    "evidence_summary": ["Methanol is not favored by exact mass."],
                },
            ],
        },
    )
    with client:
        res = _post_bundle(client, api_headers, [item])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["agreement_count"] >= 1
    assert "HRMS exact mass" in data["evidence_layers_used"]


def test_unified_evidence_bundle_with_msms_evidence_works(client, api_headers):
    item = _bundle_item(
        "msms_annotation",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "smiles": "CCO",
                    "candidate_score": 0.72,
                    "label": "consistent_with_msms",
                    "evidence_summary": ["MS/MS fragments are consistent with ethanol for review."],
                }
            ],
        },
    )
    with client:
        res = _post_bundle(client, api_headers, [item])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert "Processed MS/MS annotation" in data["evidence_layers_used"]


def test_unified_evidence_bundle_contradictions_increment_count(client, api_headers):
    item = _bundle_item(
        "hrms_exact_mass",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "smiles": "CCO",
                    "ppm_score": 0.44,
                    "label": "outside_tolerance",
                    "evidence_summary": ["Exact mass evidence requires review."],
                }
            ],
        },
        contradictions=["HRMS conflicts with the selected candidate."],
        label="conflicting_evidence",
    )
    with client:
        res = _post_bundle(client, api_headers, [item])
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["contradiction_count"] >= 1
    assert data["label"] == "conflicting_evidence"
    assert "HRMS conflicts with the selected candidate." in data["global_contradictions"]


def test_unified_evidence_bundle_preserves_warnings(client, api_headers):
    item = _bundle_item(
        "msms_annotation",
        {
            "ranked_candidates": [
                {
                    "rank": 1,
                    "name": "ethanol",
                    "smiles": "CCO",
                    "candidate_score": 0.68,
                    "warnings": ["Candidate fragment assignment is tentative."],
                }
            ],
            "warnings": ["MS/MS source peak list had low signal-to-noise."],
        },
        warnings=["Evidence Queue item had source warnings."],
    )
    with client:
        res = _post_bundle(client, api_headers, [item])
    assert res.status_code == 200, res.text
    data = res.json()
    assert "Evidence Queue item had source warnings." in data["warnings"]
    assert "MS/MS source peak list had low signal-to-noise." in data["warnings"]
    assert "Candidate fragment assignment is tentative." in data["best_candidate"]["warnings"]


def test_unified_evidence_bundle_endpoint_appears_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200
    openapi = res.json()
    path = openapi["paths"]["/confidence/candidates/unified/evidence-bundle"]
    assert "post" in path
    assert "UnifiedEvidenceBundleRequest" in openapi["components"]["schemas"]
    assert "UnifiedEvidenceBundleConfidenceResult" in openapi["components"]["schemas"]
