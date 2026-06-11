def test_lcms_import_bridge_endpoint(client, api_headers):
    headers = api_headers
    payload = {
        "filename": "ethanol.csv",
        "source_text": "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\nms1,1,0.1,47.04914,100,\nms2,2,0.2,29.03858,100,47.04914\n",
    }
    with client:
        res = client.post("/ms/lcms/import/bridge", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["source_format"] == "processed_peak_table"
    assert data["ms1_scan_count"] == 1
    assert data["ms2_scan_count"] == 1
    assert data["selected_msms_precursor_mz"] == 47.04914


def test_lcms_import_bridge_evidence_endpoint(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/ms/lcms/import/bridge/evidence",
            headers=headers,
            data={
                "filename": "ethanol.csv",
                "source_text": "mz,intensity\n47.04914,100\n48.05249,2.3\n",
                "source_format": "processed_peak_table",
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["source_format"] == "processed_peak_table"
    assert data["extracted_ms1_peak_count"] == 2


def test_lcms_import_bridge_upload_endpoint_preserves_hash(client, api_headers):
    headers = api_headers
    source = b"scan_id,ms_level,rt_min,mz,intensity,precursor_mz\nms1,1,0.1,47.04914,100,\n"
    with client:
        res = client.post(
            "/ms/lcms/import/bridge/upload",
            headers=headers,
            data={"source_format": "processed_peak_table"},
            files={"file": ("ethanol.csv", source, "text/csv")},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["source_format"] == "processed_peak_table"
    assert data["immutable_raw_data"] is True
    assert len(data["file_sha256"]) == 64


def test_lcms_import_bridge_malformed_input_returns_400(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/ms/lcms/import/bridge",
            headers=headers,
            json={"filename": "bad.csv", "source_text": "not a peak table"},
        )
    assert res.status_code == 400
