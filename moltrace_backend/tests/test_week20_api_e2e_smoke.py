def test_register_login_validate_analyze_workspace_report_smoke(client, api_headers) -> None:
    with client:
        email = "week20@example.com"
        password = "StrongPassword123!"
        reg = client.post("/auth/register", json={"email": email, "password": password})
        assert reg.status_code in {201, 409}

        login = client.post("/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "sample_id": "EtOH-001",
            "smiles": "CCO",
            "nmr_text": (
                "1H NMR (400 MHz, CDCl3) d 3.65 (q, J = 7.1 Hz, 2H), "
                "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
            ),
            "solvent": "CDCl3",
        }

        validate = client.post("/analyze/validate", json=payload, headers=headers)
        assert validate.status_code == 200
        assert validate.json()["structure_valid"] is True

        analyze = client.post("/analyze", json=payload, headers=headers)
        assert analyze.status_code == 200

        project = client.post(
            "/workspaces/projects",
            json={"name": "Week20 Smoke", "description": "E2E smoke test"},
            headers=headers,
        )
        assert project.status_code == 201
        project_id = project.json()["id"]

        sample = client.post(
            f"/workspaces/projects/{project_id}/samples",
            json={
                "sample_id": "EtOH-001",
                "smiles": "CCO",
                "solvent": "CDCl3",
                "nmr_text": payload["nmr_text"],
            },
            headers=headers,
        )
        assert sample.status_code == 201

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        deployment = client.get("/admin/deployment", headers={"x-api-key": "test-key"})
        assert deployment.status_code == 200
        assert "Varian/Agilent" in deployment.json()["raw_fid_vendors_beta"]
