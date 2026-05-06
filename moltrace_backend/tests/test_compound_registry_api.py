from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'compound_registry.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _spectracheck_session(client: TestClient, headers: dict[str, str]) -> dict:
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "Compound Registry SpectraCheck Project"},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()
    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "CR-SAMPLE-001", "display_name": "Registry aliquot"},
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()
    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "Registry linkage evidence",
        },
    )
    assert session_res.status_code == 201, session_res.text
    return session_res.json()


def _reaction_experiment(client: TestClient, headers: dict[str, str]) -> dict:
    project_res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Compound Registry Reaction", "objective": "maximize_yield", "status": "active"},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()
    experiment_res = client.post(
        f"/reaction-projects/{project['id']}/experiments",
        headers=headers,
        json={
            "experiment_code": "CR-RXN-001",
            "status": "planned",
            "conditions_json": {"solvent": "EtOH", "temperature_c": 25},
        },
    )
    assert experiment_res.status_code == 201, experiment_res.text
    return experiment_res.json()


def _regulatory_dossier(client: TestClient, headers: dict[str, str]) -> dict:
    jurisdiction_res = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={"name": "Compound Registry Jurisdiction", "country_code": "US"},
    )
    assert jurisdiction_res.status_code == 201, jurisdiction_res.text
    jurisdiction = jurisdiction_res.json()
    dossier_res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Compound Registry Dossier",
            "product_name": "Registry Product",
            "compound_name": "Registry Compound",
            "jurisdiction_id": jurisdiction["id"],
            "intended_use": "Research decision support",
        },
    )
    assert dossier_res.status_code == 201, dossier_res.text
    return dossier_res.json()


def _stored_report(client: TestClient, headers: dict[str, str]) -> dict:
    analysis_payload = {
        "sample_id": "CR-REPORT-001",
        "smiles": "CCO",
        "nmr_text": (
            "1H NMR (400 MHz, CDCl3) d 3.65 (q, J = 7.1 Hz, 2H), "
            "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
        ),
        "solvent": "CDCl3",
    }
    analysis_res = client.post("/analyze", headers=headers, json=analysis_payload)
    assert analysis_res.status_code == 200, analysis_res.text
    history_res = client.get("/history", headers=headers)
    assert history_res.status_code == 200, history_res.text
    analysis_id = history_res.json()[0]["id"]
    report_res = client.post(
        f"/reports/from-analysis/{analysis_id}",
        headers=headers,
    )
    assert report_res.status_code == 201, report_res.text
    return report_res.json()


def test_compound_registry_workflow_links_search_and_graph(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        compound_res = client.post(
            "/compound-registry/compounds",
            headers=headers,
            json={
                "preferred_name": "Ethanol candidate",
                "registry_id": "MT-CMP-0001",
                "compound_type": "product",
                "status": "active",
                "original_structure_input": "OCC",
                "original_structure_format": "smiles",
                "stereochemistry_status": "unspecified",
                "salt_solvent_status": "parent",
                "metadata_json": {"program": "phase54"},
            },
        )
        assert compound_res.status_code == 201, compound_res.text
        compound = compound_res.json()
        assert compound["original_structure_input"] == "OCC"
        assert compound["metadata_json"]["program"] == "phase54"
        if compound["canonical_smiles"]:
            assert compound["canonical_smiles"] == "CCO"
            assert compound["molecular_formula"] == "C2H6O"
            assert any("canonical representation derived" in warning for warning in compound["warnings"])
        else:
            assert any("Chemistry toolkit unavailable" in warning for warning in compound["warnings"])

        structures_res = client.get(
            f"/compound-registry/compounds/{compound['id']}/structures",
            headers=headers,
        )
        assert structures_res.status_code == 200, structures_res.text
        structures = structures_res.json()
        assert structures[0]["structure_input"] == "OCC"
        assert structures[0]["validation_status"] in {"valid", "not_checked", "invalid", "ambiguous"}

        alias_res = client.post(
            f"/compound-registry/compounds/{compound['id']}/aliases",
            headers=headers,
            json={"alias": "EtOH-Phase54", "alias_type": "internal_code"},
        )
        assert alias_res.status_code == 201, alias_res.text
        assert alias_res.json()["alias"] == "EtOH-Phase54"

        batch_res = client.post(
            "/compound-registry/batches",
            headers=headers,
            json={
                "compound_id": compound["id"],
                "batch_code": "BATCH-54-001",
                "source_type": "synthesized",
                "amount": 12.5,
                "amount_unit": "mg",
                "purity_percent": 98.2,
                "purity_method": "qNMR",
                "status": "active",
            },
        )
        assert batch_res.status_code == 201, batch_res.text
        batch = batch_res.json()

        aliquot_res = client.post(
            f"/compound-registry/batches/{batch['id']}/aliquots",
            headers=headers,
            json={
                "sample_id": "CR-SAMPLE-001",
                "aliquot_code": "ALQ-54-001",
                "amount": 2.0,
                "amount_unit": "mg",
                "storage_location": "Freezer-A",
                "status": "available",
            },
        )
        assert aliquot_res.status_code == 201, aliquot_res.text
        assert aliquot_res.json()["aliquot_code"] == "ALQ-54-001"

        target_res = client.post(
            "/compound-registry/compounds",
            headers=headers,
            json={
                "preferred_name": "Acetaldehyde candidate",
                "compound_type": "impurity",
                "status": "needs_review",
                "original_structure_input": "CC=O",
                "original_structure_format": "smiles",
            },
        )
        assert target_res.status_code == 201, target_res.text
        relationship_res = client.post(
            f"/compound-registry/compounds/{compound['id']}/relationships",
            headers=headers,
            json={
                "target_compound_id": target_res.json()["id"],
                "relationship_type": "impurity_of",
                "confidence_label": "requires_review",
                "evidence_summary_json": {"basis": "candidate relationship from registry test"},
            },
        )
        assert relationship_res.status_code == 201, relationship_res.text
        assert relationship_res.json()["relationship_type"] == "impurity_of"

        session = _spectracheck_session(client, headers)
        session_link = client.post(
            f"/spectracheck/sessions/{session['id']}/link-compound",
            headers=headers,
            json={"compound_id": compound["id"], "batch_id": batch["id"]},
        )
        assert session_link.status_code == 201, session_link.text
        assert session_link.json()["evidence_link"]["resource_type"] == "spectracheck_session"

        experiment = _reaction_experiment(client, headers)
        reaction_link = client.post(
            f"/reaction-experiments/{experiment['id']}/link-compound",
            headers=headers,
            json={"compound_id": compound["id"], "relation_type": "product_of"},
        )
        assert reaction_link.status_code == 201, reaction_link.text
        assert reaction_link.json()["graph_edge"]["relation_type"] == "product_of"

        dossier = _regulatory_dossier(client, headers)
        dossier_link = client.post(
            f"/regulatory/dossiers/{dossier['id']}/link-compound",
            headers=headers,
            json={"compound_id": compound["id"]},
        )
        assert dossier_link.status_code == 201, dossier_link.text
        assert dossier_link.json()["evidence_link"]["resource_type"] == "regulatory_dossier"

        report = _stored_report(client, headers)
        report_link = client.post(
            f"/reports/{report['id']}/link-compound",
            headers=headers,
            json={"compound_id": compound["id"]},
        )
        assert report_link.status_code == 201, report_link.text
        assert report_link.json()["evidence_link"]["resource_type"] == "report"

        search_res = client.post(
            "/compound-registry/search",
            headers=headers,
            json={"alias": "EtOH-Phase54"},
        )
        assert search_res.status_code == 200, search_res.text
        assert search_res.json()["total"] == 1
        assert search_res.json()["compounds"][0]["id"] == compound["id"]

        compound_links = client.get(
            f"/compound-registry/compounds/{compound['id']}/evidence-links",
            headers=headers,
        )
        assert compound_links.status_code == 200, compound_links.text
        assert {item["resource_type"] for item in compound_links.json()} >= {
            "spectracheck_session",
            "reaction_experiment",
            "regulatory_dossier",
            "report",
        }

        graph_res = client.get("/compound-registry/graph", headers=headers)
        assert graph_res.status_code == 200, graph_res.text
        graph = graph_res.json()
        assert graph["nodes"]
        assert graph["edges"]
        assert any(edge["relation_type"] == "product_of" for edge in graph["edges"])


def test_compound_registry_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/compound-registry/compounds",
        "/compound-registry/compounds/{compound_id}",
        "/compound-registry/compounds/{compound_id}/structures",
        "/compound-registry/compounds/{compound_id}/aliases",
        "/compound-registry/compounds/{compound_id}/relationships",
        "/compound-registry/batches",
        "/compound-registry/batches/{batch_id}",
        "/compound-registry/batches/{batch_id}/aliquots",
        "/compound-registry/evidence-links",
        "/compound-registry/compounds/{compound_id}/evidence-links",
        "/compound-registry/batches/{batch_id}/evidence-links",
        "/compound-registry/graph/edges",
        "/compound-registry/graph",
        "/spectracheck/sessions/{session_id}/link-compound",
        "/reaction-experiments/{experiment_id}/link-compound",
        "/regulatory/dossiers/{dossier_id}/link-compound",
        "/reports/{report_id}/link-compound",
        "/compound-registry/search",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/compound-registry/compounds"]
    assert "get" in paths["/compound-registry/compounds"]
    assert "get" in paths["/compound-registry/compounds/{compound_id}"]
    assert "patch" in paths["/compound-registry/compounds/{compound_id}"]
    assert "post" in paths["/compound-registry/search"]
    schemas = res.json()["components"]["schemas"]
    for schema_name in [
        "CompoundEntity",
        "CompoundStructureRecord",
        "CompoundAlias",
        "CompoundBatch",
        "SampleAliquot",
        "CompoundRelationship",
        "CompoundEvidenceLink",
        "ScientificKnowledgeGraphEdge",
    ]:
        assert schema_name in schemas
