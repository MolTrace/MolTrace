from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str = "regulatory@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _jurisdiction(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={
            "name": "US FDA",
            "region": "North America",
            "country_code": "US",
            "authority_name": "Food and Drug Administration",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _source(client: TestClient, headers: dict[str, str], jurisdiction_id: int) -> dict:
    text = (
        "Identity documentation requires analytical evidence for compound identity, including "
        "source-supported spectral data, impurity discussion, and traceable method summaries. "
        "Submission support should include cited source documents and evidence gap review before use."
    )
    res = client.post(
        "/regulatory/sources/upload",
        headers=headers,
        data={
            "title": "Identity Evidence Guidance",
            "source_type": "guidance",
            "jurisdiction_id": str(jurisdiction_id),
            "version": "2026-draft",
            "status": "active",
        },
        files={"file": ("identity-guidance.txt", text.encode("utf-8"), "text/plain")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _dossier(client: TestClient, headers: dict[str, str], jurisdiction_id: int) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Target compound jurisdiction-specific dossier",
            "product_name": "Target compound",
            "compound_name": "Example analyte",
            "jurisdiction_id": jurisdiction_id,
            "intended_use": "Research decision support package",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _requirement(
    client: TestClient,
    headers: dict[str, str],
    dossier_id: int,
    *,
    citation_id: int | None = None,
    priority: str = "high",
    status: str = "evidence_needed",
    title: str = "Identity evidence package",
) -> dict:
    body = {
        "title": title,
        "category": "identity",
        "requirement_text": "Provide source-supported identity and analytical evidence.",
        "priority": priority,
        "status": status,
    }
    if citation_id is not None:
        body["citation_ids_json"] = [citation_id]
    res = client.post(
        f"/regulatory/dossiers/{dossier_id}/requirements",
        headers=headers,
        json=body,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_regulatory_jurisdiction_source_search_and_dossier_workflow(client, api_headers):
    with client:
        headers = _sign_up(client, "reg-intel-workflow@example.com")

        # Jurisdictions and source documents are GLOBAL, unowned reference data: every caller's
        # citations and assessment verdicts resolve against them. Publishing them is therefore an
        # operator action (standalone-modules Layer 0.A) — the regulatory user below consumes them.
        jurisdiction = _jurisdiction(client, api_headers)
        listed_jurisdictions = client.get("/regulatory/jurisdictions", headers=headers)
        assert listed_jurisdictions.status_code == 200, listed_jurisdictions.text
        assert listed_jurisdictions.json()[0]["name"] == "US FDA"

        dossier = _dossier(client, headers, jurisdiction["id"])
        no_source_query = client.post(
            f"/regulatory/dossiers/{dossier['id']}/query",
            headers=headers,
            json={"question": "What identity documentation is required?"},
        )
        assert no_source_query.status_code == 201, no_source_query.text
        assert no_source_query.json()["status"] == "insufficient_sources"
        assert no_source_query.json()["answer"]["confidence_label"] == "insufficient_sources"
        assert no_source_query.json()["answer"]["human_review_required"] is True

        source = _source(client, api_headers, jurisdiction["id"])
        assert source["sha256"]
        assert source["citations"]
        citation_id = source["citations"][0]["id"]

        search = client.post(
            "/regulatory/sources/search",
            headers=headers,
            json={"query": "identity documentation analytical evidence", "jurisdiction_id": jurisdiction["id"]},
        )
        assert search.status_code == 200, search.text
        assert search.json()["sources"]
        assert search.json()["citations"]

        fetched = client.get(f"/regulatory/sources/{source['id']}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["id"] == source["id"]

        citations = client.get(f"/regulatory/sources/{source['id']}/citations", headers=headers)
        assert citations.status_code == 200, citations.text
        assert citations.json()[0]["id"] == citation_id

        requirement = _requirement(client, headers, dossier["id"], citation_id=citation_id)
        assert requirement["citation_ids_json"] == [citation_id]

        evidence = client.post(
            f"/regulatory/dossiers/{dossier['id']}/evidence-links",
            headers=headers,
            json={
                "requirement_id": requirement["id"],
                "evidence_type": "spectracheck_report",
                "resource_id": 42,
                "title": "SpectraCheck identity report",
                "summary": "Analytical evidence linked for human review.",
                "status": "linked",
            },
        )
        assert evidence.status_code == 201, evidence.text
        assert evidence.json()["requirement_id"] == requirement["id"]

        links = client.get(f"/regulatory/dossiers/{dossier['id']}/evidence-links", headers=headers)
        assert links.status_code == 200, links.text
        assert links.json()[0]["evidence_type"] == "spectracheck_report"

        cited_query = client.post(
            f"/regulatory/dossiers/{dossier['id']}/query",
            headers=headers,
            json={"question": "What identity documentation and analytical evidence are required?"},
        )
        assert cited_query.status_code == 201, cited_query.text
        answer = cited_query.json()["answer"]
        assert cited_query.json()["status"] == "answered"
        assert answer["citation_ids_json"]
        assert answer["citations"]
        assert "Source-supported draft interpretation requires review" in answer["answer_text"]
        assert answer["human_review_required"] is True

        fetched_query = client.get(f"/regulatory/queries/{cited_query.json()['id']}", headers=headers)
        assert fetched_query.status_code == 200, fetched_query.text
        assert fetched_query.json()["answer"]["citation_ids_json"] == answer["citation_ids_json"]


def test_regulatory_risk_review_and_readiness_report(client, api_headers):
    with client:
        headers = _sign_up(client, "reg-intel-risk@example.com")
        # Global reference data is published by an operator; the dossier work below is the user's.
        jurisdiction = _jurisdiction(client, api_headers)
        source = _source(client, api_headers, jurisdiction["id"])
        dossier = _dossier(client, headers, jurisdiction["id"])
        citation_id = source["citations"][0]["id"]
        satisfied = _requirement(
            client,
            headers,
            dossier["id"],
            citation_id=citation_id,
            priority="medium",
            status="satisfied",
            title="Identity source support",
        )
        evidence = client.post(
            f"/regulatory/dossiers/{dossier['id']}/evidence-links",
            headers=headers,
            json={
                "requirement_id": satisfied["id"],
                "evidence_type": "unified_evidence",
                "resource_id": 7,
                "title": "Unified evidence bundle",
                "summary": "Accepted source-supported identity evidence for review.",
                "status": "accepted",
            },
        )
        assert evidence.status_code == 201, evidence.text
        missing = _requirement(
            client,
            headers,
            dossier["id"],
            priority="critical",
            status="evidence_needed",
            title="Impurity evidence gap",
        )

        risk = client.post(
            f"/regulatory/dossiers/{dossier['id']}/risk-assessment",
            headers=headers,
            json={},
        )
        assert risk.status_code == 201, risk.text
        body = risk.json()
        assert body["overall_risk"] == "critical"
        assert any(item["requirement_id"] == missing["id"] for item in body["missing_evidence_json"])
        assert body["human_review_required"] is True

        fetched_risk = client.get(
            f"/regulatory/dossiers/{dossier['id']}/risk-assessment",
            headers=headers,
        )
        assert fetched_risk.status_code == 200, fetched_risk.text
        assert fetched_risk.json()["id"] == body["id"]

        missing_rationale = client.post(
            f"/regulatory/dossiers/{dossier['id']}/review",
            headers=headers,
            json={"decision": "needs_changes", "reviewer_name": "Reviewer"},
        )
        assert missing_rationale.status_code == 422, missing_rationale.text

        review = client.post(
            f"/regulatory/dossiers/{dossier['id']}/review",
            headers=headers,
            json={
                "decision": "needs_changes",
                "reviewer_name": "Reviewer",
                "rationale": "Evidence gap requires review before the dossier can progress.",
            },
        )
        assert review.status_code == 201, review.text
        assert review.json()["decision"] == "needs_changes"

        reviews = client.get(f"/regulatory/dossiers/{dossier['id']}/review", headers=headers)
        assert reviews.status_code == 200, reviews.text
        assert reviews.json()[0]["rationale"]

        report = client.post(
            f"/regulatory/dossiers/{dossier['id']}/readiness-report",
            headers=headers,
            json={},
        )
        assert report.status_code == 201, report.text
        readiness = report.json()
        assert readiness["citation_ids_json"] == [citation_id]
        assert readiness["gaps_json"]
        assert readiness["risks_json"]["overall_risk"] == "critical"
        assert readiness["human_review_required"] is True
        # Provenance: a persisted readiness report carries a stable sha256 content
        # hash in metadata_json.report_hash (what the dossier UI surfaces).
        report_hash = readiness["metadata_json"]["report_hash"]
        assert isinstance(report_hash, str) and len(report_hash) == 64
        assert all(c in "0123456789abcdef" for c in report_hash)

        fetched_report = client.get(
            f"/regulatory/readiness-reports/{readiness['id']}",
            headers=headers,
        )
        assert fetched_report.status_code == 200, fetched_report.text
        assert fetched_report.json()["id"] == readiness["id"]

        # Rehydration: the dossier-scoped list returns persisted reports newest-first,
        # so the UI can reload a readiness report without an in-session POST.
        listed = client.get(
            f"/regulatory/dossiers/{dossier['id']}/readiness-report",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        listed_reports = listed.json()
        assert isinstance(listed_reports, list)
        assert listed_reports[0]["id"] == readiness["id"]


def _upload(client, headers, jurisdiction_id: int, *, title: str, body: str) -> dict:
    res = client.post(
        "/regulatory/sources/upload",
        headers=headers,
        data={
            "title": title,
            "source_type": "guidance",
            "jurisdiction_id": str(jurisdiction_id),
            "version": "2026-draft",
            "status": "active",
        },
        files={"file": (f"{title.lower().replace(' ', '-')}.txt", body.encode("utf-8"), "text/plain")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_source_search_does_not_match_a_word_inside_another_word(client, api_headers):
    """Retrieval scored by substring containment, so a short query term matched inside longer words.

    "led" scored a hit on every occurrence of "controlled", "compelled" and "scheduled", tying a
    document that never uses the word with one that does. On a regulatory Q&A path the ranking is
    what selects the quoted citations, so a false match does not merely add noise -- it can put an
    unrelated excerpt into a drafted answer.
    """

    headers = api_headers
    with client:
        jurisdiction = _jurisdiction(client, headers)
        _upload(
            client, headers, jurisdiction["id"],
            title="Controlled Storage Guidance",
            body=(
                "Every batch is controlled and scheduled under the quality system. Storage areas "
                "remain controlled throughout, and controlled documents are retained on file."
            ),
        )
        _upload(
            client, headers, jurisdiction["id"],
            title="Acceptable Intake Guidance",
            body=(
                "Nitrosamine limits are led by the acceptable intake for the compound. The "
                "assessment is led by a qualified reviewer before any release decision."
            ),
        )

        search = client.post(
            "/regulatory/sources/search",
            headers=headers,
            json={"query": "led", "jurisdiction_id": jurisdiction["id"]},
        )
        assert search.status_code == 200, search.text
        titles = [s["title"] for s in search.json()["sources"]]

    assert "Acceptable Intake Guidance" in titles, titles
    assert "Controlled Storage Guidance" not in titles, titles


def test_source_search_ranks_the_rarer_term_higher(client, api_headers):
    """A term common to every document carries no discriminating power; a rare one does.

    Constructed so a raw count of matched terms cannot separate the two: both candidates match
    exactly two of the three query terms, so the old scorer tied them and fell through to its
    id-descending tie-break -- which here favours the document uploaded last, i.e. the wrong one.
    Weighting each term by how rare it is across the candidates is what breaks the tie on meaning
    rather than on insertion order.
    """

    headers = api_headers
    with client:
        jurisdiction = _jurisdiction(client, headers)
        # Uploaded FIRST, so the id tie-break works against it.
        _upload(
            client, headers, jurisdiction["id"],
            title="Sulfolane Guidance",
            body="Residual sulfolane is assessed against its own storage limit.",
        )
        for i in range(4):
            _upload(
                client, headers, jurisdiction["id"],
                title=f"Common Guidance {i}",
                body="Storage conditions apply to the batch and the conditions are documented.",
            )

        search = client.post(
            "/regulatory/sources/search",
            headers=headers,
            json={"query": "storage conditions sulfolane", "jurisdiction_id": jurisdiction["id"]},
        )
        assert search.status_code == 200, search.text
        titles = [s["title"] for s in search.json()["sources"]]

    # Both match two of three terms. "sulfolane" appears once across the corpus; "storage" and
    # "conditions" appear in all five, so they say nothing about which document to read.
    assert titles[0] == "Sulfolane Guidance", titles


def test_phase53_openapi_includes_regulatory_intelligence_endpoints(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/regulatory/jurisdictions",
        "/regulatory/sources/upload",
        "/regulatory/sources",
        "/regulatory/sources/{source_id}",
        "/regulatory/sources/{source_id}/citations",
        "/regulatory/sources/search",
        "/regulatory/dossiers",
        "/regulatory/dossiers/{dossier_id}",
        "/regulatory/dossiers/{dossier_id}/requirements",
        "/regulatory/requirements/{requirement_id}",
        "/regulatory/dossiers/{dossier_id}/evidence-links",
        "/regulatory/dossiers/{dossier_id}/query",
        "/regulatory/queries/{query_id}",
        "/regulatory/dossiers/{dossier_id}/risk-assessment",
        "/regulatory/dossiers/{dossier_id}/review",
        "/regulatory/dossiers/{dossier_id}/readiness-report",
        "/regulatory/readiness-reports/{report_id}",
    ]:
        assert path in paths
    assert "post" in paths["/regulatory/sources/upload"]
    assert "patch" in paths["/regulatory/dossiers/{dossier_id}"]
    assert "get" in paths["/regulatory/dossiers/{dossier_id}/readiness-report"]
