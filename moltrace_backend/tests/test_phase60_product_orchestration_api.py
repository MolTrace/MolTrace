from fastapi.testclient import TestClient

DEFAULT_PROGRAM_ORDER = ["spectracheck", "regulatory_hub", "reaction_optimization"]


def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Phase 60 regulatory-first dossier",
            "product_name": "Phase 60 fixture product",
            "compound_name": "Phase 60 fixture compound",
            "intended_use": "Internal compliance planning fixture.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reaction_project(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/reaction-projects",
        headers=headers,
        json={
            "name": "Phase 60 compliance-constrained reaction",
            "description": "Fixture reaction project for compliance-driven constraints.",
            "objective": "multi_objective",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _spectracheck_evidence(client: TestClient, headers: dict[str, str]) -> dict:
    project = client.post(
        "/projects",
        headers=headers,
        json={"name": "Phase 60 SpectraCheck project"},
    )
    assert project.status_code == 201, project.text
    sample = client.post(
        f"/projects/{project.json()['id']}/samples",
        headers=headers,
        json={
            "sample_id": "phase60-sample",
            "display_name": "Phase 60 Sample",
            "molecule_name": "Fixture molecule",
            "status": "approved",
        },
    )
    assert sample.status_code == 201, sample.text
    session = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project.json()["id"],
            "sample_pk": sample.json()["id"],
            "title": "Phase 60 evidence session",
            "status": "evidence_ready",
        },
    )
    assert session.status_code == 201, session.text
    evidence = client.post(
        f"/spectracheck/sessions/{session.json()['id']}/evidence",
        headers=headers,
        json={
            "layer": "nmr",
            "title": "Impurity signal evidence",
            "source_tab": "SpectraCheck",
            "status": "review_required",
            "summary": "Impurity signal at 0.12 percent; requires review.",
            "evidence_summary_json": ["Impurity level percent was observed."],
            "response_json": {"impurity_level_percent": 0.12},
            "selected_for_unified": True,
            "provenance_json": {"source": "phase60-test"},
        },
    )
    assert evidence.status_code == 201, evidence.text
    return {
        "project": project.json(),
        "sample": sample.json(),
        "session": session.json(),
        "evidence": evidence.json(),
    }


def _active_impurity_rule_set(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/regulatory/rule-sets",
        headers=headers,
        json={
            "name": "Phase 60 impurity thresholds",
            "version": "v1",
            "source_type": "custom",
            "status": "active",
            "impurity_threshold_rules_json": [
                {
                    "rule_type": "reporting",
                    "threshold_percent": 0.05,
                    "applies_to": "unspecified",
                },
                {
                    "rule_type": "identification",
                    "threshold_percent": 0.1,
                    "applies_to": "unspecified",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_phase60_product_program_order_and_module_priority(client, api_headers):
    headers = api_headers
    with client:
        programs = client.get("/product/programs", headers=headers)
        assert programs.status_code == 200, programs.text
        assert [program["program_key"] for program in programs.json()] == DEFAULT_PROGRAM_ORDER
        assert [program["display_order"] for program in programs.json()] == [1, 2, 3]

        priority = client.get("/product/module-priority", headers=headers)
        assert priority.status_code == 200, priority.text
        by_context = {row["context"]: row["program_order_json"] for row in priority.json()}
        assert by_context["global"] == DEFAULT_PROGRAM_ORDER
        assert by_context["project"] == DEFAULT_PROGRAM_ORDER


def test_phase60_cross_module_orchestration_workflow(client, api_headers):
    headers = api_headers
    with client:
        dossier = _dossier(client, headers)
        reaction_project = _reaction_project(client, headers)
        spectracheck = _spectracheck_evidence(client, headers)

        missing_rules = client.post(
            "/bridges/spectroscopy-to-regulatory",
            headers=headers,
            json={
                "spectracheck_session_id": spectracheck["session"]["id"],
                "evidence_item_id": spectracheck["evidence"]["id"],
                "dossier_id": dossier["id"],
            },
        )
        assert missing_rules.status_code == 201, missing_rules.text
        assert missing_rules.json()["created_action_item_ids_json"] == []
        assert any(
            "missing_rule_set" in warning for warning in missing_rules.json()["warnings_json"]
        )

        _active_impurity_rule_set(client, headers)
        impurity_bridge = client.post(
            "/bridges/spectroscopy-to-regulatory",
            headers=headers,
            json={
                "spectracheck_session_id": spectracheck["session"]["id"],
                "evidence_item_id": spectracheck["evidence"]["id"],
                "dossier_id": dossier["id"],
            },
        )
        assert impurity_bridge.status_code == 201, impurity_bridge.text
        impurity_body = impurity_bridge.json()
        assert impurity_body["bridge_status"] == "action_items_created"
        assert impurity_body["human_review_required"] is True
        assert impurity_body["created_action_item_ids_json"]
        assert (
            impurity_body["extracted_regulatory_signals_json"]["impurity_signals"][0][
                "observed_level_percent"
            ]
            == 0.12
        )

        flag_bridge = client.post(
            "/bridges/spectroscopy-to-regulatory",
            headers=headers,
            json={
                "dossier_id": dossier["id"],
                "metadata_json": {
                    "signals_json": {
                        "residual_solvent_flag": True,
                        "nitrosamine_like_flag": True,
                    }
                },
            },
        )
        assert flag_bridge.status_code == 201, flag_bridge.text
        flag_body = flag_bridge.json()
        assert len(flag_body["created_action_item_ids_json"]) >= 2
        assert flag_body["human_review_required"] is True

        action_items = client.get("/cross-module/action-items", headers=headers)
        assert action_items.status_code == 200, action_items.text
        assert any(
            item["action_type"] == "run_regulatory_assessment" for item in action_items.json()
        )

        regulatory_bridge = client.post(
            "/bridges/regulatory-to-reaction",
            headers=headers,
            json={
                "dossier_id": dossier["id"],
                "regulatory_action_item_id": impurity_body["created_action_item_ids_json"][0],
                "reaction_project_id": reaction_project["id"],
            },
        )
        assert regulatory_bridge.status_code == 201, regulatory_bridge.text
        regulatory_body = regulatory_bridge.json()
        assert regulatory_body["bridge_status"] == "constraints_created"
        assert regulatory_body["human_review_required"] is True
        assert regulatory_body["created_constraint_ids_json"]
        assert (
            regulatory_body["regulatory_constraints_json"][0]["constraint_type"] == "impurity_limit"
        )

        objective = client.post(
            f"/reaction-projects/{reaction_project['id']}/compliance-objective",
            headers=headers,
            json={
                "regulatory_constraint_set_id": regulatory_body["created_constraint_ids_json"][0],
                "objective_json": {"yield_selectivity_goal": "balance yield and compliance risk"},
                "status": "draft",
            },
        )
        assert objective.status_code == 201, objective.text
        objective_body = objective.json()
        assert objective_body["hard_constraints_json"]["requires_review"] is True
        assert objective_body["objective_json"]["compliance_driven_optimization_constraint"] is True

        bundle = client.post(
            f"/regulatory/dossiers/{dossier['id']}/ctd-module3-bundle",
            headers=headers,
            json={
                "report_json": {"source_citations": ["phase60-regulatory-fixture"]},
                "status": "draft",
            },
        )
        assert bundle.status_code == 201, bundle.text
        bundle_body = bundle.json()
        assert bundle_body["human_review_required"] is True
        assert bundle_body["report_sha256"]
        assert bundle_body["report_json"]["bundle_type"] == "draft CTD Module 3 bundle"
        assert bundle_body["report_json"]["human_review_status"]["requires_review"] is True
        assert bundle_body["report_json"]["provenance_hashes"]

        command_center = client.get("/cross-module/command-center", headers=headers)
        assert command_center.status_code == 200, command_center.text
        center_body = command_center.json()
        assert center_body["metadata_json"]["program_order_json"] == DEFAULT_PROGRAM_ORDER
        assert center_body["spectracheck_summary_json"]["display_order"] == 1
        assert center_body["regulatory_summary_json"]["display_order"] == 2
        assert center_body["reaction_summary_json"]["display_order"] == 3


def test_phase60_product_orchestration_openapi(client):
    with client:
        response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    for path in [
        "/product/programs",
        "/product/programs/order",
        "/product/module-priority",
        "/product/cross-module/workflow-templates",
        "/bridges/spectroscopy-to-regulatory",
        "/bridges/spectroscopy-to-regulatory/{bridge_id}",
        "/bridges/spectroscopy-to-regulatory/{bridge_id}/review",
        "/bridges/regulatory-to-reaction",
        "/bridges/regulatory-to-reaction/{bridge_id}",
        "/bridges/regulatory-to-reaction/{bridge_id}/review",
        "/reaction-projects/{reaction_project_id}/regulatory-constraints",
        "/reaction-regulatory-constraints/{constraint_id}",
        "/reaction-projects/{reaction_project_id}/compliance-objective",
        "/regulatory/dossiers/{dossier_id}/ctd-module3-bundle",
        "/ctd-module3-bundles/{bundle_id}",
        "/cross-module/action-items",
        "/cross-module/action-items/{action_item_id}",
        "/cross-module/command-center",
        "/cross-module/command-center/project/{project_id}",
        "/cross-module/command-center/compound/{compound_id}",
        "/cross-module/command-center/batch/{batch_id}",
    ]:
        assert path in paths

    schemas = response.json()["components"]["schemas"]
    for schema in [
        "ProductProgramRegistry",
        "ModulePriorityMap",
        "CrossModuleWorkflowTemplate",
        "SpectroscopyToRegulatoryBridge",
        "RegulatoryToReactionBridge",
        "RegulatoryConstraintSet",
        "ComplianceDrivenOptimizationObjective",
        "CTDModule3ReportBundle",
        "CrossModuleActionItem",
        "CrossModuleCommandCenterSummary",
    ]:
        assert schema in schemas
