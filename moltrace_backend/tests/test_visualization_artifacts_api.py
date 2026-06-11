

def test_spectrum_artifact_normalizes_to_spectrum_1d(client, api_headers):
    headers = api_headers
    with client:
        upload = client.post(
            "/files/upload",
            headers=headers,
            data={"file_kind": "processed_nmr"},
            files={
                "file": (
                    "spectrum.csv",
                    b"ppm,intensity\n4.0,0\n3.8,1\n3.6,5\n3.4,1\n",
                    "text/csv",
                )
            },
        )
        assert upload.status_code == 201, upload.text

        job = client.post(
            "/jobs",
            headers=headers,
            json={
                "job_type": "nmr_processed_preview",
                "input_file_ids_json": [upload.json()["id"]],
                "parameters_json": {"solvent": "CDCl3"},
            },
        )
        assert job.status_code == 201, job.text
        artifact_id = job.json()["artifact_ids"][0]

        res = client.get(f"/visualization/artifacts/{artifact_id}", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["artifact_id"] == artifact_id
        assert body["artifact_type"] == "spectrum_preview"
        assert body["viewer_type"] == "spectrum_1d"
        assert body["data"]["x_label"] == "ppm"
        assert body["data"]["y_label"] == "intensity"
        assert body["data"]["reversed_x_axis"] is True
        assert len(body["data"]["x"]) == len(body["data"]["y"]) == 4


def test_msms_artifact_normalizes_to_msms_mirror(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/visualization/normalize",
            headers=headers,
            json={
                "artifact_id": "msms-demo",
                "artifact_type": "msms_annotation",
                "title": "MS/MS annotation",
                "artifact_json": {
                    "precursor_mz": 47.04914,
                    "adduct": "[M+H]+",
                    "observed_peaks": [
                        {"mz": 47.04914, "intensity": 10, "label": "precursor"},
                        {"mz": 29.03858, "intensity": 100},
                    ],
                    "reference_peaks": [{"mz": 29.03858, "intensity": 80, "label": "reference"}],
                    "fragment_matches": [
                        {"peak_mz": 29.03858, "fragment_type": "candidate_fragment_match"}
                    ],
                    "provenance": {"source": "pytest-artifact"},
                },
                "provenance": {"request_id": "pytest-msms"},
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["viewer_type"] == "msms_mirror"
        assert body["data"]["precursor_mz"] == 47.04914
        assert body["data"]["adduct"] == "[M+H]+"
        assert body["data"]["observed_peaks"][1]["mz"] == 29.03858
        assert body["data"]["reference_peaks"][0]["label"] == "reference"
        assert body["provenance"]["source"] == "pytest-artifact"
        assert body["provenance"]["request_id"] == "pytest-msms"


def test_lcms_feature_artifact_normalizes_to_chromatogram_or_table(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/visualization/normalize",
            headers=headers,
            json={
                "artifact_type": "lcms_feature_table",
                "title": "LC-MS features",
                "artifact_json": {
                    "xic_points": [
                        {
                            "target_mz": 47.04914,
                            "retention_time_min": 1.0,
                            "intensity": 12.0,
                        },
                        {
                            "target_mz": 47.04914,
                            "retention_time_min": 1.1,
                            "intensity": 30.0,
                        },
                    ],
                    "features": [
                        {
                            "feature_id": "F001",
                            "target_mz": 47.04914,
                            "apex_rt_min": 1.1,
                            "area": 42.0,
                        }
                    ],
                },
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["viewer_type"] in {"chromatogram", "table"}
        if body["viewer_type"] == "chromatogram":
            assert body["data"]["traces"][0]["type"] == "xic"
            assert body["data"]["traces"][0]["mz"] == 47.04914
        else:
            assert "feature_id" in body["data"]["columns"]


def test_fragmentation_artifact_normalizes_to_fragmentation_tree(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/visualization/normalize",
            headers=headers,
            json={
                "artifact_type": "fragmentation_tree",
                "title": "Fragmentation tree",
                "artifact_json": {
                    "nodes": [
                        {"node_id": "precursor", "mz": 47.04914, "node_type": "precursor"},
                        {"node_id": "frag-1", "mz": 29.03858, "node_type": "observed_peak"},
                    ],
                    "edges": [
                        {
                            "parent_id": "precursor",
                            "child_id": "frag-1",
                            "relation_type": "neutral_loss",
                        }
                    ],
                    "diagnostic_hits": [{"loss_name": "H2O"}],
                    "contradiction_flags": ["review_required"],
                },
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["viewer_type"] == "fragmentation_tree"
        assert body["data"]["nodes"][0]["node_id"] == "precursor"
        assert body["data"]["edges"][0]["child_id"] == "frag-1"
        assert body["data"]["diagnostic_hits"][0]["loss_name"] == "H2O"
        assert body["data"]["contradictions"] == ["review_required"]


def test_unknown_artifact_returns_json_viewer_with_warning(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/visualization/normalize",
            headers=headers,
            json={
                "artifact_type": "unrecognized_payload",
                "title": "Unknown",
                "artifact_json": {"raw": {"still": "preserved"}},
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["viewer_type"] == "json"
        assert body["data"]["raw"]["still"] == "preserved"
        assert any("could not be normalized" in warning for warning in body["warnings"])


def test_visualization_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    assert "/visualization/artifacts/{artifact_id}" in paths
    assert "/visualization/normalize" in paths
    assert "get" in paths["/visualization/artifacts/{artifact_id}"]
    assert "post" in paths["/visualization/normalize"]
