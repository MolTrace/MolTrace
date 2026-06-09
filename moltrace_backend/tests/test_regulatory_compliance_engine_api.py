from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'regulatory_compliance.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _jurisdiction(client: TestClient, headers: dict[str, str], name: str, country_code: str) -> dict:
    res = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={"name": name, "country_code": country_code, "authority_name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _dossier(client: TestClient, headers: dict[str, str], jurisdiction_id: int) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Phase 55 compliance dossier",
            "product_name": "Phase 55 product",
            "compound_name": "Phase 55 compound",
            "jurisdiction_id": jurisdiction_id,
            "intended_use": "Research decision support",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _rule_set(
    client: TestClient,
    headers: dict[str, str],
    jurisdiction_id: int,
    *,
    reporting: float,
    identification: float,
    qualification: float,
    solvent_limit: float = 3000.0,
) -> dict:
    res = client.post(
        "/regulatory/rule-sets",
        headers=headers,
        json={
            "name": f"Phase 55 ICH-like rules {jurisdiction_id}",
            "jurisdiction_id": jurisdiction_id,
            "version": "draft-2026",
            "source_type": "ich",
            "source_ids_json": [],
            "status": "active",
            "impurity_threshold_rules_json": [
                {
                    "rule_type": "reporting",
                    "threshold_percent": reporting,
                    "applies_to": "drug_substance",
                    "citation_ids_json": [],
                },
                {
                    "rule_type": "identification",
                    "threshold_percent": identification,
                    "applies_to": "drug_substance",
                    "citation_ids_json": [],
                },
                {
                    "rule_type": "qualification",
                    "threshold_percent": qualification,
                    "applies_to": "drug_substance",
                    "citation_ids_json": [],
                },
            ],
            "residual_solvent_rules_json": [
                {
                    "solvent_name": "methanol",
                    "solvent_class": "class_2",
                    "concentration_limit": solvent_limit,
                    "permitted_daily_exposure": 30.0,
                    "citation_ids_json": [],
                }
            ],
            "nitrosamine_risk_rules_json": [
                {
                    "risk_category": "n_nitroso_motif",
                    "structural_pattern": "N(N=O)",
                    "citation_ids_json": [],
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_regulatory_compliance_engine_workflow(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        us = _jurisdiction(client, headers, "Phase 55 US", "US")
        eu = _jurisdiction(client, headers, "Phase 55 EU", "EU")
        dossier = _dossier(client, headers, us["id"])
        us_rules = _rule_set(
            client,
            headers,
            us["id"],
            reporting=0.05,
            identification=0.10,
            qualification=0.15,
        )
        eu_rules = _rule_set(
            client,
            headers,
            eu["id"],
            reporting=0.03,
            identification=0.08,
            qualification=0.12,
        )

        listed_rules = client.get("/regulatory/rule-sets", headers=headers)
        assert listed_rules.status_code == 200, listed_rules.text
        assert {item["id"] for item in listed_rules.json()} >= {us_rules["id"], eu_rules["id"]}
        assert any("source_needed" in warning for warning in us_rules["warnings"])

        impurity = client.post(
            f"/regulatory/dossiers/{dossier['id']}/impurity-risk-register",
            headers=headers,
            json={
                "impurity_name": "Unknown LC-MS feature",
                "impurity_type": "process_impurity",
                "source": "lcms_feature",
                "observed_level_percent": 0.12,
                "structural_assignment": "candidate relationship only",
            },
        )
        assert impurity.status_code == 201, impurity.text
        impurity_body = impurity.json()
        assert impurity_body["threshold_triggered"] == "identification"
        assert impurity_body["action_item_id"]
        assert impurity_body["human_review_required"] is True

        solvent = client.post(
            f"/regulatory/dossiers/{dossier['id']}/residual-solvent-assessment",
            headers=headers,
            json={"solvents_json": [{"solvent_name": "MeOH", "observed_ppm": 1200}]},
        )
        assert solvent.status_code == 201, solvent.text
        solvent_match = solvent.json()["residual_solvent_summary_json"]["matched_solvents"][0]
        assert solvent_match["normalized_solvent_name"] == "methanol"
        assert solvent_match["rule_found"] is True
        assert solvent.json()["human_review_required"] is True

        nitrosamine = client.post(
            f"/regulatory/dossiers/{dossier['id']}/nitrosamine-watch",
            headers=headers,
            json={"structure_text": "candidate motif CN(N=O)C"},
        )
        assert nitrosamine.status_code == 201, nitrosamine.text
        nitro_body = nitrosamine.json()
        assert nitro_body["nitrosamine_summary_json"]["review_required"] is True
        assert nitro_body["nitrosamine_summary_json"]["nitrosamine_confirmed"] is False
        assert nitro_body["overall_status"] == "action_required"

        qnmr = client.post(
            f"/regulatory/dossiers/{dossier['id']}/qnmr-compliance",
            headers=headers,
            json={"validation_parameters_json": {"precision": {"rsd": 1.2}}},
        )
        assert qnmr.status_code == 201, qnmr.text
        qnmr_body = qnmr.json()
        assert qnmr_body["q2_q14_readiness_status"] == "gaps_identified"
        assert any("ATP" in warning for warning in qnmr_body["warnings_json"])
        assert qnmr_body["human_review_required"] is True

        method_profile = client.post(
            f"/regulatory/dossiers/{dossier['id']}/method-validation-profile",
            headers=headers,
            json={"method_type": "qnmr", "precision_json": {"repeatability": "draft"}},
        )
        assert method_profile.status_code == 201, method_profile.text
        assert method_profile.json()["validation_status"] == "gaps_identified"

        ai_record = client.post(
            f"/regulatory/dossiers/{dossier['id']}/ai-governance-record",
            headers=headers,
            json={"ai_system_name": "MolTrace reviewer assistant"},
        )
        assert ai_record.status_code == 201, ai_record.text
        ai_body = ai_record.json()
        assert ai_body["governance_status"] == "gaps_identified"
        assert any("model_version_id" in warning for warning in ai_body["warnings_json"])
        assert any("human_override_available" in warning for warning in ai_body["warnings_json"])

        jurisdictional_map = client.post(
            f"/regulatory/dossiers/{dossier['id']}/jurisdictional-map",
            headers=headers,
            json={
                "jurisdiction_id": eu["id"],
                "rule_set_id": eu_rules["id"],
                "compare_jurisdiction_ids_json": [us["id"]],
            },
        )
        assert jurisdictional_map.status_code == 201, jurisdictional_map.text
        assert jurisdictional_map.json()["differences_json"]["threshold_differences"]

        batch_assessment = client.post(
            f"/regulatory/dossiers/{dossier['id']}/batch-assessment",
            headers=headers,
            json={},
        )
        assert batch_assessment.status_code == 201, batch_assessment.text
        batch_body = batch_assessment.json()
        assert batch_body["overall_status"] == "action_required"
        assert impurity_body["action_item_id"] in batch_body["action_item_ids_json"]
        assert batch_body["qnmr_summary_json"]["q2_q14_readiness_status"] == "gaps_identified"

        action_items = client.get(
            "/regulatory/action-items",
            headers=headers,
            params={"dossier_id": dossier["id"], "status": "open"},
        )
        assert action_items.status_code == 200, action_items.text
        assert action_items.json()
        update = client.patch(
            f"/regulatory/action-items/{impurity_body['action_item_id']}",
            headers=headers,
            json={"status": "in_progress", "assigned_to": "QA reviewer"},
        )
        assert update.status_code == 200, update.text
        assert update.json()["status"] == "in_progress"
        assert update.json()["assigned_to"] == "QA reviewer"


def test_residual_solvent_uses_q3c_engine_when_no_tenant_rule(tmp_path):
    # A dossier with no configured rule-set: the residual-solvent assessment is now
    # populated from the deterministic ICH Q3C engine instead of warning source_needed.
    client, headers = _client(tmp_path)
    with client:
        juris = _jurisdiction(client, headers, "Q3C engine US", "US")
        dossier = _dossier(client, headers, juris["id"])
        res = client.post(
            f"/regulatory/dossiers/{dossier['id']}/residual-solvent-assessment",
            headers=headers,
            json={"solvents_json": [{"solvent_name": "acetonitrile", "observed_ppm": 5000}]},
        )
        assert res.status_code == 201, res.text
        match = res.json()["residual_solvent_summary_json"]["matched_solvents"][0]
        assert match["rule_found"] is False
        assert match["solvent_class"] == "class_2"  # ICH Q3C engine
        assert match["concentration_limit"] == 410.0
        assert match["source"] == "ich_q3c_engine"
        assert match["threshold_triggered"] is True  # 5000 ppm > 410 ppm limit


def test_residual_solvent_unknown_still_source_needed(tmp_path):
    # A solvent outside the encoded Q3C subset keeps the source-needed fallback.
    client, headers = _client(tmp_path)
    with client:
        juris = _jurisdiction(client, headers, "Q3C unknown US", "US")
        dossier = _dossier(client, headers, juris["id"])
        res = client.post(
            f"/regulatory/dossiers/{dossier['id']}/residual-solvent-assessment",
            headers=headers,
            json={"solvents_json": [{"solvent_name": "water", "observed_ppm": 100}]},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert any("source_needed" in w for w in body["warnings"])
        assert body["residual_solvent_summary_json"]["matched_solvents"][0].get("solvent_class") is None


def test_nitrosamine_watch_uses_cpca_for_smiles(tmp_path):
    # A clean nitrosamine SMILES now yields the real FDA CPCA category + AI limit,
    # not just a regex motif flag. nitrosamine_confirmed stays False (decision-support).
    client, headers = _client(tmp_path)
    with client:
        juris = _jurisdiction(client, headers, "CPCA US", "US")
        dossier = _dossier(client, headers, juris["id"])
        res = client.post(
            f"/regulatory/dossiers/{dossier['id']}/nitrosamine-watch",
            headers=headers,
            json={"structure_text": "CN(C)N=O"},  # NDMA
        )
        assert res.status_code == 201, res.text
        summary = res.json()["nitrosamine_summary_json"]
        assert summary["review_required"] is True
        assert summary["nitrosamine_confirmed"] is False
        assert summary["cpca"]["cpca_category"] == 1
        assert summary["cpca"]["ai_limit_ng_per_day"] == 26.5
        assert summary["cpca"]["coc_flag"] is True


def test_regulatory_compliance_engine_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/regulatory/rule-sets",
        "/regulatory/rule-sets/{rule_set_id}",
        "/regulatory/dossiers/{dossier_id}/batch-assessment",
        "/regulatory/dossiers/{dossier_id}/impurity-risk-register",
        "/regulatory/dossiers/{dossier_id}/residual-solvent-assessment",
        "/regulatory/dossiers/{dossier_id}/nitrosamine-watch",
        "/regulatory/dossiers/{dossier_id}/qnmr-compliance",
        "/regulatory/dossiers/{dossier_id}/method-validation-profile",
        "/regulatory/dossiers/{dossier_id}/ai-governance-record",
        "/regulatory/dossiers/{dossier_id}/jurisdictional-map",
        "/regulatory/action-items",
        "/regulatory/action-items/{action_item_id}",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/regulatory/rule-sets"]
    assert "get" in paths["/regulatory/rule-sets"]
    assert "patch" in paths["/regulatory/action-items/{action_item_id}"]
    schemas = res.json()["components"]["schemas"]
    for schema in [
        "RegulatoryRuleSet",
        "ImpurityThresholdRule",
        "ResidualSolventRule",
        "NitrosamineRiskRule",
        "QNMRComplianceProfile",
        "AnalyticalMethodValidationProfile",
        "RegulatoryActionItem",
        "BatchRegulatoryAssessment",
        "ImpurityRiskRegister",
        "AIGovernanceRecord",
        "JurisdictionalRequirementMap",
    ]:
        assert schema in schemas
