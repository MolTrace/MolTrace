from __future__ import annotations

import csv
import io

ETHANOL_1H = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_1H_SHIFTED = "1H NMR (400 MHz, CDCl3) delta 3.66 (q, J = 7.1 Hz, 2H), 1.25 (t, J = 7.1 Hz, 3H), 2.11 (br s, 1H)"
ETHANOL_13C = "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2."
ETHANOL_13C_SHIFTED = "13C NMR (101 MHz, CDCl3) delta 58.5, 18.0."


def _table_bytes(rows: list[list[object]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["experiment", "f2_ppm", "f1_ppm", "intensity"])
    writer.writerows(rows)
    return out.getvalue().encode()


def test_similarity_score_endpoint_text_layers(client, api_headers) -> None:
    with client:
        response = client.post(
            "/similarity/score",
            headers=api_headers,
            json={
                "sample_id": "ethanol",
                "solvent": "CDCl3",
                "observed_proton_text": ETHANOL_1H,
                "reference_proton_text": ETHANOL_1H_SHIFTED,
                "observed_carbon13_text": ETHANOL_13C,
                "reference_carbon13_text": ETHANOL_13C_SHIFTED,
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["overall_score"] > 0.8
    assert set(data["evidence_layers_used"]) == {"1H", "13C"}
    assert data["layers"][0]["vector_score"] is not None
    assert data["layers"][0]["set_score"] is not None


def test_similarity_score_evidence_endpoint_with_2d_files(client, api_headers) -> None:
    observed_2d = _table_bytes([["HSQC", 3.65, 58.3, 1.0], ["HSQC", 1.26, 18.2, 1.0]])
    reference_2d = _table_bytes([["HSQC", 3.66, 58.5, 1.0], ["HSQC", 1.25, 18.0, 1.0]])
    with client:
        response = client.post(
            "/similarity/score/evidence",
            headers=api_headers,
            data={
                "sample_id": "ethanol",
                "solvent": "CDCl3",
                "observed_proton_text": ETHANOL_1H,
                "reference_proton_text": ETHANOL_1H_SHIFTED,
                "observed_carbon13_text": ETHANOL_13C,
                "reference_carbon13_text": ETHANOL_13C_SHIFTED,
                "nmr2d_experiment_type": "HSQC",
            },
            files={
                "observed_nmr2d_file": ("obs_hsqc.csv", observed_2d, "text/csv"),
                "reference_nmr2d_file": ("ref_hsqc.csv", reference_2d, "text/csv"),
            },
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "HSQC" in data["evidence_layers_used"]
    hsqc = [layer for layer in data["layers"] if layer["layer"] == "HSQC"][0]
    assert hsqc["matched_count"] == 2
    assert hsqc["crosspeak_matches"]
