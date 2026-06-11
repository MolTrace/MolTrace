import hashlib
import json



def _connector(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/connectors",
        headers=headers,
        json={
            "connector_key": "phase62-instrument",
            "display_name": "Phase 62 Instrument Folder",
            "connector_type": "instrument_watch_folder",
            "target_program": "cross_module",
            "status": "active",
            "config_schema_json": {"folder_path": {"type": "string"}},
            "metadata_json": {"suite": "phase62"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_file(
    client: TestClient,
    headers: dict[str, str],
    *,
    filename: str,
    content: bytes,
    content_type: str = "text/csv",
    file_kind: str = "processed_nmr",
) -> dict:
    response = client.post(
        "/files/upload",
        headers=headers,
        data={"file_kind": file_kind, "metadata_json": json.dumps({"source": "phase62-test"})},
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": "Phase 62 CTD source dossier",
            "product_name": "MolTrace fixture",
            "compound_name": "Fixture compound",
            "intended_use": "Internal export package test fixture.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_connector_health_credentials_and_watch_folder_are_safe(client, api_headers, tmp_path):
    headers = api_headers
    with client:
        connector = _connector(client, headers)

        health = client.post(
            f"/connectors/{connector['id']}/health-check",
            headers=headers,
            json={
                "latency_ms": 12,
                "message": "token=RAW_SECRET should not echo",
                "metadata_json": {"api_key": "RAW_SECRET", "region": "lab-a"},
            },
        )
        assert health.status_code == 201, health.text
        health_body = health.json()
        assert health_body["status"] == "ok"
        assert "RAW_SECRET" not in health.text
        assert health_body["metadata_json"]["api_key"] == "[redacted]"

        credential = client.post(
            f"/connectors/{connector['id']}/credentials",
            headers=headers,
            json={
                "credential_type": "api_key",
                "secret_ref": "vault://moltrace/connectors/phase62",
                "metadata_json": {"token": "RAW_SECRET"},
            },
        )
        assert credential.status_code == 201, credential.text
        credential_body = credential.json()
        assert credential_body["secret_ref"] == "vault://moltrace/connectors/phase62"
        assert "RAW_SECRET" not in credential.text
        assert credential_body["metadata_json"]["token"] == "[redacted]"

        watch_dir = tmp_path / "instrument"
        watch_dir.mkdir()
        watch_folder = client.post(
            "/instrument-watch-folders",
            headers=headers,
            json={
                "connector_id": connector["id"],
                "folder_path": str(watch_dir),
                "file_patterns_json": ["*.csv"],
                "recursive": False,
                "target_program": "spectracheck",
                "target_route": "processed_nmr",
                "status": "active",
            },
        )
        assert watch_folder.status_code == 201, watch_folder.text
        assert watch_folder.json()["connector_id"] == connector["id"]


def test_ingestion_run_hashes_files_and_skips_duplicate_hash(client, api_headers):
    headers = api_headers
    with client:
        connector = _connector(client, headers)
        content = "ppm,intensity\n1.0,10\n2.0,20\n"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        payload = {
            "connector_id": connector["id"],
            "source_system": "instrument",
            "source_path": "instrument/run-001.csv",
            "files_json": [
                {
                    "filename": "run-001.csv",
                    "content_text": content,
                    "content_type": "text/csv",
                    "file_kind": "processed_nmr",
                    "source_path": "instrument/run-001.csv",
                }
            ],
        }

        first = client.post("/ingestion-runs", headers=headers, json=payload)
        assert first.status_code == 201, first.text
        first_body = first.json()
        assert first_body["status"] == "succeeded"
        assert first_body["ingested_count"] == 1
        assert first_body["metadata_json"]["file_hashes_json"] == [expected_hash]

        duplicate = client.post("/ingestion-runs", headers=headers, json=payload)
        assert duplicate.status_code == 201, duplicate.text
        duplicate_body = duplicate.json()
        assert duplicate_body["status"] == "requires_review"
        assert duplicate_body["ingested_count"] == 0
        assert duplicate_body["skipped_count"] == 1
        assert duplicate_body["metadata_json"]["duplicate_files_json"][0]["sha256"] == expected_hash
        assert duplicate_body["warnings_json"]


def test_file_normalization_supports_csv_tsv_and_unsupported_warning(client, api_headers):
    headers = api_headers
    with client:
        csv_file = _upload_file(
            client,
            headers,
            filename="spectrum.csv",
            content=b"ppm,intensity\n1.0,10\n2.0,20\n",
        )
        csv_norm = client.post(f"/files/{csv_file['id']}/normalize", headers=headers, json={})
        assert csv_norm.status_code == 201, csv_norm.text
        csv_body = csv_norm.json()
        assert csv_body["status"] == "succeeded"
        assert csv_body["source_format"] == "csv"
        assert csv_body["target_format"] == "moltrace_spectrum_json"
        assert csv_body["output_artifact_id"]

        tsv_file = _upload_file(
            client,
            headers,
            filename="spectrum.tsv",
            content=b"ppm\tintensity\n1.0\t10\n2.0\t20\n",
            content_type="text/tab-separated-values",
        )
        tsv_norm = client.post(f"/files/{tsv_file['id']}/normalize", headers=headers, json={})
        assert tsv_norm.status_code == 201, tsv_norm.text
        assert tsv_norm.json()["status"] == "succeeded"
        assert tsv_norm.json()["source_format"] == "tsv"

        bin_file = _upload_file(
            client,
            headers,
            filename="raw.bin",
            content=b"\x00\x01unsupported",
            content_type="application/octet-stream",
            file_kind="other",
        )
        unsupported = client.post(f"/files/{bin_file['id']}/normalize", headers=headers, json={})
        assert unsupported.status_code == 201, unsupported.text
        unsupported_body = unsupported.json()
        assert unsupported_body["status"] == "unsupported"
        assert unsupported_body["target_format"] == "unsupported"
        assert unsupported_body["warnings_json"]


def test_external_links_mapping_ctd_package_and_openapi(client, api_headers):
    headers = api_headers
    with client:
        connector = _connector(client, headers)
        external = client.post(
            "/external-records",
            headers=headers,
            json={
                "connector_id": connector["id"],
                "external_system": "LIMS",
                "external_object_type": "sample",
                "external_object_id": "LIMS-SAMPLE-001",
                "title": "LIMS sample",
                "status": "imported",
            },
        )
        assert external.status_code == 201, external.text

        link = client.post(
            "/external-object-links",
            headers=headers,
            json={
                "external_record_id": external.json()["id"],
                "moltrace_resource_type": "file",
                "moltrace_resource_id": 1,
                "relation_type": "source_of",
            },
        )
        assert link.status_code == 201, link.text
        assert link.json()["external_record_id"] == external.json()["id"]

        template = client.post(
            "/mapping-templates",
            headers=headers,
            json={
                "connector_id": connector["id"],
                "name": "LIMS sample to SpectraCheck session",
                "source_type": "lims_sample",
                "target_type": "spectracheck_session",
                "field_map_json": {"sample_id": "sample_id", "batch": "batch_id"},
                "status": "active",
            },
        )
        assert template.status_code == 201, template.text
        assert template.json()["field_map_json"]["sample_id"] == "sample_id"

        dossier = _dossier(client, headers)
        source_file = _upload_file(
            client,
            headers,
            filename="regulatory-source.csv",
            content=b"section,citation\n3.2.S,internal-source\n",
            file_kind="report",
        )
        package = client.post(
            f"/regulatory/dossiers/{dossier['id']}/submission-package",
            headers=headers,
            json={
                "package_type": "ctd_module3",
                "status": "ready_for_review",
                "file_ids_json": [source_file["id"]],
                "source_citations_json": [
                    {"label": "internal-source", "section": "3.2.S", "source_file_id": source_file["id"]}
                ],
            },
        )
        assert package.status_code == 201, package.text
        package_body = package.json()
        assert len(package_body["package_sha256"]) == 64
        manifest = package_body["package_manifest_json"]
        assert manifest["files"][0]["sha256"] == source_file["sha256"]
        assert manifest["source_citations"][0]["label"] == "internal-source"
        assert manifest["review_status"] == "ready_for_review"

        openapi = client.get("/openapi.json", headers=headers)
        assert openapi.status_code == 200, openapi.text
        paths = openapi.json()["paths"]
        assert "/connectors" in paths
        assert "/connectors/{connector_id}/health-check" in paths
        assert "/integrations/spectracheck/import-file" in paths
        assert "/regulatory/dossiers/{dossier_id}/submission-package" in paths
