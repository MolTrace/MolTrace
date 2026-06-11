from fastapi.testclient import TestClient


def _source(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/knowledge/sources",
        headers=headers,
        json={
            "title": "Phase 57 source-supported extraction note",
            "source_type": "journal_article",
            "source_url": "https://example.org/article",
            "doi": "10.1234/moltrace.phase57",
            "publisher": "Example Publisher",
            "status": "active",
            "reliability_label": "medium",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["doi"] == "10.1234/moltrace.phase57"
    assert body["source_url"] == "https://example.org/article"
    assert body["reliability_label"] == "medium"
    assert body["human_review_required"] is True
    return body


def _upload_text(client: TestClient, headers: dict[str, str], source_id: int, text: str) -> dict:
    res = client.post(
        f"/knowledge/sources/{source_id}/files",
        headers=headers,
        files={"file": ("phase57-source.txt", text.encode("utf-8"), "text/plain")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sha256"]
    assert body["parsed_text_hash"]
    assert body["parse_status"] == "parsed"
    assert "_parsed_text_cache" not in body["metadata_json"]
    return body


def test_knowledge_flywheel_extraction_review_dataset_workflow(client, api_headers):
    headers = api_headers
    with client:
        source = _source(client, headers)
        text = (
            "Reaction: Suzuki coupling. Substrate: aryl bromide. Product: biaryl product. "
            "Product SMILES: c1ccccc1-c2ccccc2. Reagent: phenylboronic acid, K2CO3. "
            "Solvent: toluene and water. Catalyst: Pd(PPh3)4. Ligand: PPh3. "
            "Temperature 80 C for 3 h, yield: 82%, conversion: 91%. "
            "Compound: Phase57 analyte. Formula: C12H10. Exact mass 154.0783. "
            "1H NMR (400 MHz, CDCl3) delta 7.45 (m, 10H). "
            "13C NMR (100 MHz, CDCl3) delta 128.1, 127.4. HRMS m/z calcd 154.0783. "
            "The impurity reporting threshold should be 0.05% and qNMR validation requires ATP, "
            "accuracy, precision, uncertainty, and human oversight."
        )
        source_file = _upload_text(client, headers, source["id"], text)

        reaction_run = client.post(
            "/knowledge/extractions/run",
            headers=headers,
            json={"source_id": source["id"], "source_file_id": source_file["id"], "extraction_type": "reaction"},
        )
        assert reaction_run.status_code == 201, reaction_run.text
        reaction_run_body = reaction_run.json()
        assert reaction_run_body["status"] == "requires_review"
        assert reaction_run_body["extracted_count"] == 1

        reactions = client.get(f"/knowledge/extractions/{reaction_run_body['id']}/reactions", headers=headers)
        assert reactions.status_code == 200, reactions.text
        reaction = reactions.json()[0]
        assert reaction["yield_percent"] == 82.0
        assert reaction["temperature_c"] == 80.0
        assert reaction["review_status"] == "unreviewed"
        assert reaction["citation_ids_json"]

        analytical_run = client.post(
            "/knowledge/extractions/run",
            headers=headers,
            json={"source_id": source["id"], "source_file_id": source_file["id"], "extraction_type": "analytical"},
        )
        assert analytical_run.status_code == 201, analytical_run.text
        analytical = client.get(f"/knowledge/extractions/{analytical_run.json()['id']}/analytical", headers=headers)
        assert analytical.status_code == 200, analytical.text
        analytical_record = analytical.json()[0]
        assert analytical_record["formula"] == "C12H10"
        assert analytical_record["frequency_mhz"] == 400.0
        assert analytical_record["solvent"].lower() == "cdcl3"

        regulatory_run = client.post(
            "/knowledge/extractions/run",
            headers=headers,
            json={"source_id": source["id"], "source_file_id": source_file["id"], "extraction_type": "regulatory"},
        )
        assert regulatory_run.status_code == 201, regulatory_run.text
        regulatory = client.get(f"/knowledge/extractions/{regulatory_run.json()['id']}/regulatory", headers=headers)
        assert regulatory.status_code == 200, regulatory.text
        regulatory_record = regulatory.json()[0]
        assert regulatory_record["topic"] in {"impurity_threshold", "qnmr"}
        assert regulatory_record["threshold_summary_json"]["percent_values"]
        assert regulatory_record["review_status"] == "unreviewed"

        missing_source = client.post(
            "/knowledge/sources",
            headers=headers,
            json={"title": "No citation project note", "source_type": "project_note", "reliability_label": "low"},
        )
        assert missing_source.status_code == 201, missing_source.text
        missing_run = client.post(
            "/knowledge/extractions/run",
            headers=headers,
            json={"source_id": missing_source.json()["id"], "extraction_type": "regulatory"},
        )
        assert missing_run.status_code == 201, missing_run.text
        assert "citation missing" in missing_run.json()["warnings_json"]

        tasks = client.get("/knowledge/review-tasks", headers=headers, params={"record_type": "reaction"})
        assert tasks.status_code == 200, tasks.text
        assert any(task["record_id"] == reaction["id"] for task in tasks.json())

        missing_comment = client.post(
            f"/knowledge/records/{reaction['id']}/approve",
            headers=headers,
            json={"record_type": "reaction", "reviewer_name": "Reviewer"},
        )
        assert missing_comment.status_code == 422, missing_comment.text

        approve = client.post(
            f"/knowledge/records/{reaction['id']}/approve",
            headers=headers,
            json={
                "record_type": "reaction",
                "reviewer_name": "Qualified reviewer",
                "reviewer_comment": "Accepted by reviewer for source-supported downstream linking.",
            },
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["review_status"] == "accepted"

        project = client.post(
            "/reaction-projects",
            headers=headers,
            json={"name": "Phase 57 reaction project"},
        )
        assert project.status_code == 201, project.text
        link = client.post(
            f"/knowledge/records/{reaction['id']}/link",
            headers=headers,
            json={
                "record_type": "reaction",
                "target_type": "reaction_project",
                "target_id": project.json()["id"],
                "relation_type": "source_supported_candidate",
                "confidence_label": "requires_review",
            },
        )
        assert link.status_code == 201, link.text
        assert link.json()["target_type"] == "reaction_project"

        training = client.post(
            "/knowledge/training-dataset-candidates",
            headers=headers,
            json={
                "source_id": source["id"],
                "record_type": "reaction",
                "record_id": reaction["id"],
                "dataset_type": "reaction_optimization",
                "quality_flags_json": ["source-supported"],
                "citation_ids_json": reaction["citation_ids_json"],
            },
        )
        assert training.status_code == 201, training.text
        assert training.json()["status"] == "proposed"

        benchmark = client.post(
            "/knowledge/benchmark-dataset-candidates",
            headers=headers,
            json={
                "source_id": source["id"],
                "record_type": "reaction",
                "record_id": reaction["id"],
                "benchmark_type": "reaction_optimization",
                "split_recommendation": "holdout",
                "leakage_risk_label": "low",
            },
        )
        assert benchmark.status_code == 201, benchmark.text
        assert benchmark.json()["leakage_risk_label"] == "low"

        queue = client.post(
            "/knowledge/model-improvement-queue",
            headers=headers,
            json={
                "source_type": "new_reviewed_record",
                "target_module": "reaction_optimization",
                "linked_record_type": "reaction",
                "linked_record_id": reaction["id"],
                "priority": "medium",
                "summary": "New reviewed reaction extracted record for model improvement queue.",
            },
        )
        assert queue.status_code == 201, queue.text
        assert queue.json()["target_module"] == "reaction_optimization"

        feature = client.post(
            "/knowledge/features",
            headers=headers,
            json={
                "record_type": "reaction",
                "record_id": reaction["id"],
                "feature_family": "reaction",
                "features_json": {"yield_percent": 82.0, "temperature_c": 80.0},
                "feature_version": "phase57-v1",
            },
        )
        assert feature.status_code == 201, feature.text
        features = client.get(f"/knowledge/features/reaction/{reaction['id']}", headers=headers)
        assert features.status_code == 200, features.text
        assert features.json()[0]["features_json"]["yield_percent"] == 82.0

        dataset = client.post(
            "/knowledge/dataset-versions",
            headers=headers,
            json={
                "dataset_type": "reaction_optimization",
                "name": "Phase 57 extracted reaction candidates",
                "version": "v0.1",
                "source_record_ids_json": [{"record_type": "reaction", "record_id": reaction["id"]}],
                "split_json": {"holdout": [reaction["id"]]},
                "quality_summary_json": {"candidate_count": 1},
                "leakage_warnings_json": [],
                "status": "ready_for_review",
            },
        )
        assert dataset.status_code == 201, dataset.text
        assert dataset.json()["status"] == "ready_for_review"

        search = client.get("/knowledge/search", headers=headers, params={"query": "Suzuki"})
        assert search.status_code == 200, search.text
        assert search.json()["reaction_records"]


def test_knowledge_flywheel_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/knowledge/sources",
        "/knowledge/sources/{source_id}",
        "/knowledge/sources/{source_id}/files",
        "/knowledge/extractions/run",
        "/knowledge/extractions/runs",
        "/knowledge/extractions/runs/{run_id}",
        "/knowledge/extractions/{run_id}/reactions",
        "/knowledge/extractions/{run_id}/analytical",
        "/knowledge/extractions/{run_id}/regulatory",
        "/knowledge/review-tasks",
        "/knowledge/review-tasks/{task_id}",
        "/knowledge/records/{record_id}/approve",
        "/knowledge/records/{record_id}/reject",
        "/knowledge/records/{record_id}/link",
        "/knowledge/search",
        "/knowledge/training-dataset-candidates",
        "/knowledge/training-dataset-candidates/{candidate_id}",
        "/knowledge/benchmark-dataset-candidates",
        "/knowledge/benchmark-dataset-candidates/{candidate_id}",
        "/knowledge/model-improvement-queue",
        "/knowledge/model-improvement-queue/{item_id}",
        "/knowledge/features",
        "/knowledge/features/{record_type}/{record_id}",
        "/knowledge/dataset-versions",
        "/knowledge/dataset-versions/{dataset_version_id}",
    ]
    for path in required_paths:
        assert path in paths

    schemas = res.json()["components"]["schemas"]
    for schema in [
        "KnowledgeSource",
        "KnowledgeSourceFile",
        "KnowledgeExtractionRun",
        "ExtractedReactionRecord",
        "ExtractedAnalyticalRecord",
        "ExtractedRegulatoryRecord",
        "TrainingDatasetCandidate",
        "BenchmarkDatasetCandidate",
        "DatasetVersion",
    ]:
        assert schema in schemas
