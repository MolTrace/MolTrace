"""Completeness pass over the tenant-operations and rule-set hardening in ``590c001``.

That change made the *create* routes operator-only, and
``test_tenant_ops_and_reference_data_hardening.py`` pins them closed. It left two gaps of
the same family, both still reachable:

1. The seven tenant-operations ``PATCH`` routes are keyed by a child id rather than a
   tenant id, so their ``_require_tenant_ops_access`` call had to wait for the record
   lookup — and it was placed after the *store call*, which commits. A non-admin therefore
   got a 403 back while the write landed. The same ordering also made the response an
   existence oracle: 404 for an id that does not exist, 403 for one that does.

2. When a configured rule set answers a regulated question it shadows the version-pinned
   ICH engine, and the stored result carried no attribution — no rule set id, no
   ``rule_set_version``. A customer-authored 1 ppm toluene limit and ICH Q3C's 890 ppm were
   indistinguishable in the record. Regulated numbers must name the rule set that produced
   them, which is exactly what makes an override auditable rather than silent.
"""

import ast
from pathlib import Path

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _tenant(client: TestClient, headers: dict[str, str], key: str) -> dict:
    res = client.post(
        "/tenants",
        headers=headers,
        json={
            "tenant_key": key,
            "display_name": key.replace("-", " ").title(),
            "tenant_type": "pilot",
            "status": "onboarding",
            "primary_contact_email": "ops@example.com",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# 1. The tenant-operations PATCH routes must authorize before they write
# --------------------------------------------------------------------------- #
def test_non_operator_patch_of_an_entitlement_does_not_land(client, api_headers):
    """The headline case: a 403 that arrives *after* the commit is not a denial.

    Entitlements are commercial state, so a customer flipping ``enabled`` on their own
    licence row is the whole point of gating this surface.
    """
    with client:
        tenant = _tenant(client, api_headers, "patch-order-alpha")
        created = client.post(
            f"/tenants/{tenant['id']}/entitlements",
            headers=api_headers,
            json={"program": "spectracheck", "feature_key": "spectracheck", "enabled": True},
        )
        assert created.status_code == 201, created.text
        entitlement_id = created.json()["id"]

        customer = _sign_up(client, "patch-order-customer@example.com")
        res = client.patch(
            f"/tenant-entitlements/{entitlement_id}",
            headers=customer,
            json={"enabled": False, "feature_key": "minted"},
        )
        assert res.status_code == 403, res.text

        after = client.get(f"/tenants/{tenant['id']}/entitlements", headers=api_headers)
        assert after.status_code == 200, after.text
        row = after.json()[0]
        assert row["enabled"] is True, "the rejected write was committed anyway"
        assert row["feature_key"] == "spectracheck"


def test_non_operator_patch_does_not_disclose_whether_the_record_exists(client, api_headers):
    """A real id answered 403 and a fake id answered 404, which enumerates the table."""
    with client:
        tenant = _tenant(client, api_headers, "patch-oracle-alpha")
        created = client.post(
            f"/tenants/{tenant['id']}/entitlements",
            headers=api_headers,
            json={"program": "regulatory_hub", "feature_key": "regulatory_hub", "enabled": True},
        )
        assert created.status_code == 201, created.text
        real_id = created.json()["id"]

        customer = _sign_up(client, "patch-oracle-customer@example.com")
        existing = client.patch(
            f"/tenant-entitlements/{real_id}", headers=customer, json={"enabled": False}
        )
        missing = client.patch(
            f"/tenant-entitlements/{real_id + 10_000}", headers=customer, json={"enabled": False}
        )
        assert existing.status_code == missing.status_code, (
            f"existing id -> {existing.status_code}, absent id -> {missing.status_code}"
        )


def test_non_operator_patch_of_a_tenant_environment_does_not_land(client, api_headers):
    """One sibling proved end-to-end; the static check below covers the rest."""
    with client:
        tenant = _tenant(client, api_headers, "patch-order-beta")
        created = client.post(
            f"/tenants/{tenant['id']}/environments",
            headers=api_headers,
            json={"environment_type": "sandbox", "status": "active"},
        )
        assert created.status_code == 201, created.text
        environment_id = created.json()["id"]

        customer = _sign_up(client, "patch-order-env@example.com")
        # A valid body, so the 403 is an authorization decision and not a validation
        # rejection that happens to arrive first.
        res = client.patch(
            f"/tenant-environments/{environment_id}",
            headers=customer,
            json={"status": "disabled"},
        )
        assert res.status_code == 403, res.text

        after = client.get(f"/tenants/{tenant['id']}/environments", headers=api_headers)
        assert after.status_code == 200, after.text
        assert after.json()[0]["status"] == "active", "the rejected write was committed anyway"


def test_no_tenant_ops_route_touches_the_store_before_it_checks_the_role(client):
    """The invariant behind the cases above, across every call site at once.

    Fourteen routes shared the bug because they share a shape: resolve the record, *then*
    gate. Enumerating them by hand is how the next one gets missed, so this walks the
    module instead. The rule is the strong one — no store call of any kind before the role
    check — because a read-then-gate route still answers 404 for an id that does not exist
    and 403 for one that does, which enumerates the table for a caller with no access to it.
    """
    api_path = Path(__file__).resolve().parents[1] / "src" / "nmrcheck" / "api.py"
    tree = ast.parse(api_path.read_text())

    def _dotted(call: ast.Call) -> str:
        node: ast.expr = call.func
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))

    offenders: list[str] = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls = [node for node in ast.walk(func) if isinstance(node, ast.Call)]
        role_lines = [
            node.lineno
            for node in calls
            if _dotted(node) in {"_require_tenant_ops_role", "_require_tenant_ops_access"}
        ]
        if not role_lines:
            continue
        first_role = min(role_lines)
        for node in calls:
            name = _dotted(node)
            if not name.startswith("tenant_store."):
                continue
            if node.lineno < first_role:
                offenders.append(f"{func.name} calls {name} at line {node.lineno} before its role check")

    assert not offenders, "tenant-operations routes that reach the store before authorizing:\n" + "\n".join(offenders)


# --------------------------------------------------------------------------- #
# 2. A configured rule set that answers a regulated question must name itself
# --------------------------------------------------------------------------- #
def _jurisdiction(client: TestClient, headers: dict[str, str], name: str, code: str) -> dict:
    res = client.post(
        "/regulatory/jurisdictions",
        headers=headers,
        json={"name": name, "country_code": code, "authority_name": name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _dossier(client: TestClient, headers: dict[str, str], jurisdiction_id: int, title: str) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": title,
            "product_name": f"{title} product",
            "compound_name": f"{title} compound",
            "jurisdiction_id": jurisdiction_id,
            "intended_use": "Research decision support",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _toluene_rule_set(client: TestClient, headers: dict[str, str], jurisdiction_id: int) -> dict:
    """A rule set that contradicts ICH Q3C: toluene as class 1 at 1 ppm, not class 2 at 890."""
    res = client.post(
        "/regulatory/rule-sets",
        headers=headers,
        json={
            "name": "House residual-solvent limits",
            "jurisdiction_id": jurisdiction_id,
            "version": "house-2026.1",
            "source_type": "internal_sop",
            "source_ids_json": [],
            "status": "active",
            "residual_solvent_rules_json": [
                {
                    "solvent_name": "toluene",
                    "solvent_class": "class_1",
                    "concentration_limit": 1.0,
                    "permitted_daily_exposure": 0.01,
                    "citation_ids_json": [],
                }
            ],
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _toluene_match(client: TestClient, headers: dict[str, str], dossier_id: int) -> dict:
    res = client.post(
        f"/regulatory/dossiers/{dossier_id}/residual-solvent-assessment",
        headers=headers,
        json={"solvents_json": [{"solvent_name": "toluene", "observed_ppm": 400}]},
    )
    assert res.status_code == 201, res.text
    return res.json()["residual_solvent_summary_json"]["matched_solvents"][0]


def test_configured_solvent_rule_records_the_rule_set_that_overrode_ich(client, api_headers):
    """An override is legitimate; an *unattributed* override is not.

    Without this the record shows ``concentration_limit: 1.0`` with nothing to say the
    number is a house limit rather than ICH Q3C's 890 ppm.
    """
    with client:
        juris = _jurisdiction(client, api_headers, "Attribution US", "US")
        rule_set = _toluene_rule_set(client, api_headers, juris["id"])
        dossier = _dossier(client, api_headers, juris["id"], "Attribution dossier")

        match = _toluene_match(client, api_headers, dossier["id"])

        assert match["rule_found"] is True
        assert match["concentration_limit"] == 1.0
        assert match["source"] == "configured_rule_set"
        assert match["rule_set_id"] == rule_set["id"]
        assert match["rule_set_version"] == "house-2026.1"
        assert match["threshold_triggered"] is True  # 400 ppm >= the house 1 ppm limit


def test_ich_q3c_still_answers_toluene_for_a_dossier_the_rule_set_does_not_cover(client, api_headers):
    """The scoping that does exist must hold: a jurisdiction-scoped rule set stays there.

    Toluene is ICH Q3C class 2 at 890 ppm, so 400 ppm is under the limit. A house rule set
    published for another jurisdiction must not pull this dossier to 1 ppm.
    """
    with client:
        covered = _jurisdiction(client, api_headers, "Covered US", "US")
        _toluene_rule_set(client, api_headers, covered["id"])
        other = _jurisdiction(client, api_headers, "Uncovered EU", "EU")
        dossier = _dossier(client, api_headers, other["id"], "Uncovered dossier")

        match = _toluene_match(client, api_headers, dossier["id"])

        assert match["rule_found"] is False
        assert match["source"] == "ich_q3c_engine"
        assert match["solvent_class"] == "class_2"
        assert match["concentration_limit"] == 890.0
        assert match["threshold_triggered"] is False
        assert match["rule_set_version"]  # the engine's own pinned version


def test_configured_impurity_threshold_records_the_rule_set_that_triggered(client, api_headers):
    """Same requirement on the impurity register: which rule set set the band."""
    with client:
        juris = _jurisdiction(client, api_headers, "Impurity attribution US", "US")
        rule_set = client.post(
            "/regulatory/rule-sets",
            headers=api_headers,
            json={
                "name": "House impurity bands",
                "jurisdiction_id": juris["id"],
                "version": "house-impurity-2026.1",
                "source_type": "internal_sop",
                "source_ids_json": [],
                "status": "active",
                "impurity_threshold_rules_json": [
                    {
                        "rule_type": "identification",
                        "threshold_percent": 0.02,
                        "applies_to": "drug_substance",
                        "citation_ids_json": [],
                    }
                ],
            },
        )
        assert rule_set.status_code == 201, rule_set.text
        dossier = _dossier(client, api_headers, juris["id"], "Impurity attribution dossier")

        res = client.post(
            f"/regulatory/dossiers/{dossier['id']}/impurity-risk-register",
            headers=api_headers,
            json={
                "impurity_name": "Unknown LC-MS feature",
                "impurity_type": "process_impurity",
                "source": "lcms_feature",
                "observed_level_percent": 0.05,
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["threshold_triggered"] == "identification"
        provenance = body["metadata_json"]["threshold_provenance"]
        assert provenance["source"] == "configured_rule_set"
        assert provenance["rule_set_id"] == rule_set.json()["id"]
        assert provenance["rule_set_version"] == "house-impurity-2026.1"


def test_nitrosamine_watch_records_the_rule_set_behind_each_matched_rule(client, api_headers):
    with client:
        juris = _jurisdiction(client, api_headers, "Nitrosamine attribution US", "US")
        rule_set = client.post(
            "/regulatory/rule-sets",
            headers=api_headers,
            json={
                "name": "House nitrosamine motifs",
                "jurisdiction_id": juris["id"],
                "version": "house-nitro-2026.1",
                "source_type": "internal_sop",
                "source_ids_json": [],
                "status": "active",
                "nitrosamine_risk_rules_json": [
                    {
                        "risk_category": "n_nitroso_motif",
                        "structural_pattern": "N(N=O)",
                        "citation_ids_json": [],
                    }
                ],
            },
        )
        assert rule_set.status_code == 201, rule_set.text
        dossier = _dossier(client, api_headers, juris["id"], "Nitrosamine attribution dossier")

        res = client.post(
            f"/regulatory/dossiers/{dossier['id']}/nitrosamine-watch",
            headers=api_headers,
            json={"structure_text": "candidate motif CN(N=O)C"},
        )
        assert res.status_code == 201, res.text
        matched = res.json()["nitrosamine_summary_json"]["matched_rules"]
        assert matched, "the configured motif rule should have matched"
        assert matched[0]["rule_set_id"] == rule_set.json()["id"]
        assert matched[0]["rule_set_version"] == "house-nitro-2026.1"
