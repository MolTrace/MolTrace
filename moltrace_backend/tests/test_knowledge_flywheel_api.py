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


# --- search must honour the review decisions already made ---------------------------------
#
# Search used to filter on text alone. A record a reviewer had explicitly REJECTED came back
# beside an accepted one, indistinguishable — the review ran, a human refused a bad
# extraction, and this surface threw that away. For a corpus whose whole value is that the
# curation is load-bearing, that inverts the feature rather than leaving it incomplete.


def _extracted_reaction(client: TestClient, headers: dict[str, str]) -> dict:
    """Run the pipeline far enough to get one extracted reaction record back."""
    source = _source(client, headers)
    source_file = _upload_text(
        client, headers, source["id"],
        "Suzuki coupling of aryl bromide with boronic acid gave the biaryl in 82% yield.",
    )
    run = client.post(
        "/knowledge/extractions/run",
        headers=headers,
        json={"source_id": source["id"], "source_file_id": source_file["id"],
              "extraction_type": "reaction"},
    )
    assert run.status_code == 201, run.text
    records = client.get(f"/knowledge/extractions/{run.json()['id']}/reactions", headers=headers)
    assert records.status_code == 200, records.text
    assert records.json(), "extraction produced no reaction record to review"
    return records.json()[0]


def test_a_rejected_record_does_not_come_back_from_search(client, api_headers):
    headers = api_headers
    with client:
        record = _extracted_reaction(client, headers)

        before = client.get("/knowledge/search", headers=headers, params={"query": "Suzuki"})
        assert before.status_code == 200, before.text
        assert any(r["id"] == record["id"] for r in before.json()["reaction_records"]), (
            "the record should be findable before anyone reviews it"
        )

        reject = client.post(
            f"/knowledge/records/{record['id']}/reject",
            headers=headers,
            json={"record_type": "reaction", "reviewer_name": "A Reviewer",
                  "reviewer_comment": "misread the yield"},
        )
        assert reject.status_code in (200, 201), reject.text

        after = client.get("/knowledge/search", headers=headers, params={"query": "Suzuki"})
        assert after.status_code == 200, after.text
        assert not any(r["id"] == record["id"] for r in after.json()["reaction_records"]), (
            "a reviewer rejected this record and search returned it anyway"
        )


def test_the_rejected_record_is_still_reachable_when_asked_for_by_name(client, api_headers):
    """The escape hatch exists — a curator auditing rejections needs it — but a caller has
    to ask, rather than receiving rejected material by accident."""
    headers = api_headers
    with client:
        record = _extracted_reaction(client, headers)
        client.post(
            f"/knowledge/records/{record['id']}/reject",
            headers=headers,
            json={"record_type": "reaction", "reviewer_name": "A Reviewer",
                  "reviewer_comment": "misread the yield"},
        )
        shown = client.get(
            "/knowledge/search", headers=headers,
            params={"query": "Suzuki", "include_rejected": True},
        )
        assert shown.status_code == 200, shown.text
        assert any(r["id"] == record["id"] for r in shown.json()["reaction_records"])


def test_an_unreviewed_record_is_returned_but_carries_its_state(client, api_headers):
    """Excluding unreviewed material would make a young corpus look empty. Returning it
    unlabelled would let "nobody has checked this" read as "someone approved it"."""
    headers = api_headers
    with client:
        record = _extracted_reaction(client, headers)
        found = client.get("/knowledge/search", headers=headers, params={"query": "Suzuki"})
        hit = next(r for r in found.json()["reaction_records"] if r["id"] == record["id"])
        assert hit["review_status"] == "unreviewed"


def test_superseding_a_source_appends_a_revision_and_never_edits_the_old_one(client, api_headers):
    headers = api_headers
    source = _source(client, headers)
    original_doi = source["doi"]
    assert source["current_revision_id"], "a new source should already have revision 1"
    first_revision_id = source["current_revision_id"]

    changed = client.patch(
        f"/knowledge/sources/{source['id']}",
        headers=headers,
        json={"doi": "10.9999/corrected", "change_reason": "Publisher issued a correction."},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["doi"] == "10.9999/corrected"
    assert changed.json()["current_revision_id"] != first_revision_id

    revisions = client.get(f"/knowledge/sources/{source['id']}/revisions", headers=headers)
    assert revisions.status_code == 200, revisions.text
    body = revisions.json()
    assert [r["revision_number"] for r in body] == [2, 1], "newest revision first"

    superseded = next(r for r in body if r["revision_number"] == 1)
    current = next(r for r in body if r["revision_number"] == 2)
    # The whole point: the predecessor still says what it said, forever.
    assert superseded["doi"] == original_doi
    assert superseded["is_current"] is False
    assert current["doi"] == "10.9999/corrected"
    assert current["is_current"] is True
    assert current["supersedes_revision_id"] == first_revision_id
    assert current["changed_fields"] == ["doi"]
    assert current["change_reason"] == "Publisher issued a correction."


def test_a_superseded_source_flags_its_records_without_overturning_the_review(client, api_headers):
    headers = api_headers
    record = _extracted_reaction(client, headers)
    source_id = record["source_id"]
    extracted_from = record["source_revision_id"]

    approved = client.post(
        f"/knowledge/records/{record['id']}/approve",
        headers=headers,
        json={"record_type": "reaction", "reviewer_name": "A Reviewer",
              "reviewer_comment": "matches the paper"},
    )
    assert approved.status_code in (200, 201), approved.text

    changed = client.patch(
        f"/knowledge/sources/{source_id}",
        headers=headers,
        json={"reliability_label": "low", "change_reason": "Journal issued an expression of concern."},
    )
    assert changed.status_code == 200, changed.text

    tasks = client.get("/knowledge/review-tasks", headers=headers, params={"status": "open"})
    assert tasks.status_code == 200, tasks.text
    raised = [
        t for t in tasks.json()
        if t["record_type"] == "reaction" and t["record_id"] == record["id"]
    ]
    assert raised, "superseding the source should ask a human to re-check the derived record"
    assert "source changed" in raised[0]["title"]
    assert "reliability label" in raised[0]["title"], "the title should name what moved"

    # Flag, never rewrite: the record keeps the decision a human actually made, and stays
    # bound to the revision it was really extracted from.
    listing = client.get(
        f"/knowledge/extractions/{record['extraction_run_id']}/reactions", headers=headers
    )
    assert listing.status_code == 200, listing.text
    after = next(r for r in listing.json() if r["id"] == record["id"])
    assert after["review_status"] == "accepted", "the human's decision must survive the cascade"
    assert after["source_revision_id"] == extracted_from, (
        "the record must stay bound to the revision it was actually read from; re-pointing "
        "it at the new one would rewrite what it was justified by"
    )


def test_changing_how_far_a_source_is_trusted_is_its_own_audit_event(client, api_headers):
    headers = api_headers
    source = _source(client, headers)
    changed = client.patch(
        f"/knowledge/sources/{source['id']}",
        headers=headers,
        json={"reliability_label": "low"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["reliability_label"] == "low"

    events = client.get(
        "/audit/events", headers=headers, params={"entity_type": "knowledge_source", "limit": 50}
    )
    assert events.status_code == 200, events.text
    payload = events.json()
    entries = payload if isinstance(payload, list) else payload.get("items", payload.get("events", []))
    types = [e.get("event_type") for e in entries]
    assert "knowledge.source.reliability_change" in types, (
        "a reliability change can invalidate every conclusion drawn from the source, so it "
        "should not be findable only by reading a field list inside another entry"
    )


def test_resaving_a_source_unchanged_does_not_manufacture_a_revision(client, api_headers):
    headers = api_headers
    source = _source(client, headers)
    unchanged = client.patch(
        f"/knowledge/sources/{source['id']}",
        headers=headers,
        json={"reliability_label": source["reliability_label"], "doi": source["doi"]},
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["current_revision_id"] == source["current_revision_id"]

    revisions = client.get(f"/knowledge/sources/{source['id']}/revisions", headers=headers)
    assert revisions.status_code == 200, revisions.text
    assert [r["revision_number"] for r in revisions.json()] == [1], (
        "a save that changed nothing should leave no revision behind; an empty entry is "
        "noise in the one chain that is supposed to mean something"
    )


def test_a_record_can_show_which_passage_it_came_from(client, api_headers):
    headers = api_headers
    record = _extracted_reaction(client, headers)
    listing = client.get(
        f"/knowledge/extractions/{record['extraction_run_id']}/reactions", headers=headers
    )
    assert listing.status_code == 200, listing.text
    found = next(r for r in listing.json() if r["id"] == record["id"])

    assert found["locators"], "a record extracted from cited text should say where it came from"
    locator = found["locators"][0]
    assert locator["citation_id"] in found["citation_ids_json"]
    assert locator["source_id"] == found["source_id"]
    assert locator["quote_excerpt"], "the locator should carry the passage, not just an id"
    assert locator["paragraph_number"] is not None
    # Locators are resolved from the citation rather than copied onto the record, so
    # there is no second copy that could drift out of step with it.
    assert locator["source_revision_id"] == found["source_revision_id"], (
        "the passage and the record must agree on which revision of the source they came from"
    )


def _person(client: TestClient, email: str) -> dict[str, str]:
    client.post("/auth/register", json={"email": email, "password": "StrongPassword123!"})
    login = client.post("/auth/login", json={"email": email, "password": "StrongPassword123!"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _dataset_version(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/knowledge/dataset-versions",
        headers=headers,
        json={"dataset_type": "reaction", "name": "Two-person promotion set", "version": "v1"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_promoting_a_dataset_version_takes_two_different_people(client, api_headers):
    first = _person(client, "approver-one@example.com")
    second = _person(client, "approver-two@example.com")
    version = _dataset_version(client, api_headers)

    one = client.post(
        f"/knowledge/dataset-versions/{version['id']}/approvals",
        headers=first, json={"comment": "records look right"},
    )
    assert one.status_code == 201, one.text
    assert one.json()["distinct_approvers"] == 1
    assert one.json()["promoted"] is False, "one person is not two"
    assert one.json()["status"] != "approved"

    # The same human with a second session is still one principal.
    again = client.post(
        f"/knowledge/dataset-versions/{version['id']}/approvals",
        headers=_person(client, "approver-one@example.com"), json={"comment": "still me"},
    )
    assert again.status_code == 400, again.text
    assert "someone else" in again.text
    state = client.get(f"/knowledge/dataset-versions/{version['id']}/approvals", headers=api_headers)
    assert state.json()["distinct_approvers"] == 1, "a repeat approval must not count twice"
    assert state.json()["promoted"] is False

    two = client.post(
        f"/knowledge/dataset-versions/{version['id']}/approvals",
        headers=second, json={"comment": "checked independently"},
    )
    assert two.status_code == 201, two.text
    assert two.json()["distinct_approvers"] == 2
    assert two.json()["promoted"] is True
    assert two.json()["status"] == "approved"


def test_a_dataset_version_cannot_be_promoted_by_editing_its_status(client, api_headers):
    version = _dataset_version(client, api_headers)
    bypass = client.patch(
        f"/knowledge/dataset-versions/{version['id']}",
        headers=api_headers, json={"status": "approved"},
    )
    assert bypass.status_code == 400, bypass.text
    assert "two separate approvals" in bypass.text

    after = client.get(f"/knowledge/dataset-versions/{version['id']}", headers=api_headers)
    assert after.json()["status"] != "approved", (
        "if a single edit can promote, the two-person rule is decoration"
    )
    # A non-promoting status change is still allowed.
    ok = client.patch(
        f"/knowledge/dataset-versions/{version['id']}",
        headers=api_headers, json={"status": "ready_for_review"},
    )
    assert ok.status_code == 200, ok.text


def test_a_machine_credential_cannot_stand_in_for_a_person(client, api_headers):
    version = _dataset_version(client, api_headers)
    res = client.post(
        f"/knowledge/dataset-versions/{version['id']}/approvals",
        headers=api_headers, json={"comment": "automation"},
    )
    assert res.status_code == 400, res.text
    assert "signed-in person" in res.text


def _approved_dataset_version(client: TestClient, api_headers: dict[str, str]) -> dict:
    version = _dataset_version(client, api_headers)
    for email in ("deploy-approver-one@example.com", "deploy-approver-two@example.com"):
        res = client.post(
            f"/knowledge/dataset-versions/{version['id']}/approvals",
            headers=_person(client, email), json={"comment": "ok"},
        )
        assert res.status_code == 201, res.text
    return version


def test_a_deployment_candidate_needs_a_dataset_version_two_people_approved(client, api_headers):
    unapproved = _dataset_version(client, api_headers)
    res = client.post(
        "/knowledge/deployment-candidates",
        headers=api_headers,
        json={"dataset_version_id": unapproved["id"], "model_version": "v1"},
    )
    assert res.status_code == 400, res.text
    assert "approved by two people" in res.text


def test_the_conveyor_refuses_to_skip_the_gate_or_the_canary(client, api_headers):
    version = _approved_dataset_version(client, api_headers)
    made = client.post(
        "/knowledge/deployment-candidates",
        headers=api_headers,
        json={
            "dataset_version_id": version["id"], "model_version": "v2",
            "metrics_json": {"accuracy": 0.91}, "incumbent_metrics_json": {"accuracy": 0.80},
            "metric_directions_json": {"accuracy": "higher"},
            "blocking_metric_name": "citation_support_recall",
            "blocking_metric_value": 0.95, "incumbent_blocking_metric_value": 0.90,
        },
    )
    assert made.status_code == 201, made.text
    candidate = made.json()
    assert candidate["status"] == "draft"

    early_canary = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/canary", headers=api_headers
    )
    assert early_canary.status_code == 400, early_canary.text
    assert "passed the promotion gate" in early_canary.text

    early_promote = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/promote", headers=api_headers
    )
    assert early_promote.status_code == 400, early_promote.text
    assert "run a canary" in early_promote.text

    gated = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/gate", headers=api_headers
    )
    assert gated.status_code == 200, gated.text
    assert gated.json()["status"] == "gate_passed"
    assert gated.json()["gate_verdict_json"]["promotable"] is True
    assert gated.json()["gate_verdict_json"]["requires_human_signoff"] is True
    assert gated.json()["gate_verdict_json"]["blocking_metric_name"] == "citation_support_recall"

    # Promotion still cannot jump the canary just because the gate passed.
    skip = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/promote", headers=api_headers
    )
    assert skip.status_code == 400, skip.text

    canary = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/canary", headers=api_headers
    )
    assert canary.status_code == 200, canary.text
    assert canary.json()["status"] == "canary"
    assert canary.json()["canary_started_at"]

    promoted = client.post(
        f"/knowledge/deployment-candidates/{candidate['id']}/promote", headers=api_headers
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["status"] == "promoted"
    assert promoted.json()["human_review_required"] is True


def test_the_gate_blocks_when_the_blocking_measure_is_missing(client, api_headers):
    version = _approved_dataset_version(client, api_headers)
    made = client.post(
        "/knowledge/deployment-candidates",
        headers=api_headers,
        json={
            "dataset_version_id": version["id"], "model_version": "v3",
            "metrics_json": {"accuracy": 0.99}, "incumbent_metrics_json": {"accuracy": 0.10},
            "metric_directions_json": {"accuracy": "higher"},
        },
    )
    assert made.status_code == 201, made.text
    gated = client.post(
        f"/knowledge/deployment-candidates/{made.json()['id']}/gate", headers=api_headers
    )
    assert gated.status_code == 200, gated.text
    assert gated.json()["status"] == "gate_failed", (
        "a missing blocking measure must block; an absent number is not a passing one, "
        "however good the rest of the vector looks"
    )
    assert gated.json()["gate_verdict_json"]["promotable"] is False


def test_a_dataset_version_cannot_be_born_already_approved(client, api_headers):
    res = client.post(
        "/knowledge/dataset-versions",
        headers=api_headers,
        json={
            "dataset_type": "reaction", "name": "Born approved", "version": "v1",
            "status": "approved",
        },
    )
    # Guarding only the edit path would leave creation as an open door to the same place.
    assert res.status_code == 400, res.text
    assert "two separate approvals" in res.text


def test_re_running_the_gate_cannot_rewind_a_candidate_that_already_shipped(client, api_headers):
    version = _approved_dataset_version(client, api_headers)
    made = client.post(
        "/knowledge/deployment-candidates",
        headers=api_headers,
        json={
            "dataset_version_id": version["id"], "model_version": "v4",
            "metrics_json": {"accuracy": 0.91}, "incumbent_metrics_json": {"accuracy": 0.80},
            "metric_directions_json": {"accuracy": "higher"},
            "blocking_metric_name": "citation_support_recall",
            "blocking_metric_value": 0.95, "incumbent_blocking_metric_value": 0.90,
        },
    )
    cid = made.json()["id"]
    assert client.post(f"/knowledge/deployment-candidates/{cid}/gate", headers=api_headers).status_code == 200
    assert client.post(f"/knowledge/deployment-candidates/{cid}/canary", headers=api_headers).status_code == 200
    assert client.post(f"/knowledge/deployment-candidates/{cid}/promote", headers=api_headers).status_code == 200

    regate = client.post(f"/knowledge/deployment-candidates/{cid}/gate", headers=api_headers)
    assert regate.status_code == 400, regate.text

    after = client.get(f"/knowledge/deployment-candidates/{cid}", headers=api_headers)
    assert after.json()["status"] == "promoted", (
        "a candidate that shipped must not be silently rewound to a pre-gate state while "
        "keeping the timestamps that say it shipped"
    )
    assert after.json()["promoted_at"]
