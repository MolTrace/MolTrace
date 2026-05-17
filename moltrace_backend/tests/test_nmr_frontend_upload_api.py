import hashlib
import io
import zipfile

import numpy as np
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

HEADERS = {"x-api-key": "test-key"}
PEAK_CSV = b"""shift_ppm,integration_h,multiplicity
3.65,2,q
1.26,3,t
2.10,1,br s
"""
TRACE_TSV = b"""ppm\tintensity
4.20\t0
4.10\t3
4.00\t0
1.30\t0
1.20\t5
1.10\t0
"""
CARBON13_CSV = b"""ppm,signal
77.0,12
58.2,200
18.1,140
"""


def _client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'nmr_frontend.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app)


def _build_bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.1, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(-time_axis * 10.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= synthetic frontend raw FID test
##$TD= {points * 2}
##$SW_h= {sw_hz}
##$SW= 10.0
##$SFO1= {sfo1}
##$BF1= {sfo1}
##$O1= {center_ppm * sfo1}
##$O1P= {center_ppm}
##$NUC1= <1H>
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ethanol_raw/fid", interleaved.tobytes())
        archive.writestr("ethanol_raw/acqus", acqus)
        archive.writestr("ethanol_raw/pulseprogram", "zg30\n")
    return buffer.getvalue()


def test_nmr_processed_csv_preview_returns_flat_arrays(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"sample_id": "csv-preview", "nucleus": "1H", "solvent": "CDCl3"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sample_id"] == "csv-preview"
    assert payload["nucleus"] == "1H"
    assert payload["filename"] == "peaks.csv"
    assert payload["point_count"] == 3
    assert payload["x"] == [3.65, 1.26, 2.1]
    assert len(payload["x"]) == len(payload["y"])
    assert payload["x_label"] == "ppm"
    assert payload["y_label"] == "intensity"


def test_nmr_processed_tsv_preview_returns_flat_arrays(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"sample_id": "tsv-preview", "nucleus": "1H"},
            files={"file": ("trace.tsv", TRACE_TSV, "text/tab-separated-values")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "trace.tsv"
    assert payload["point_count"] == 6
    assert payload["x"]
    assert payload["y"]
    assert payload["metadata"]["peak_inference"] == "skipped_for_display_preview"
    assert not any("inferred heuristically" in warning for warning in payload["warnings"])


def test_nmr_processed_analyze_returns_peaks(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "analyze-peaks",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), "
                    "1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["peak_count"] == 3
    assert payload["x"] == [3.65, 1.26, 2.1]
    assert len(payload["x"]) == len(payload["y"])
    assert payload["x_label"] == "ppm"
    assert payload["peaks"][0]["shift_ppm"] == 3.65
    assert payload["analysis_score"] is not None
    assert payload["metadata"]["peak_inference"] == "enabled"
    assert any("Human review" in item for item in payload["evidence_summary"])


def test_nmr_processed_analyze_returns_peak_enrichment(tmp_path) -> None:
    """Per-peak categorization, impurity matches, labile-H summary, and
    peak-category counts must be present in the analyze response."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "enrichment",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), "
                    "1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    # Each peak has the new enrichment keys.
    for peak in payload["peaks"]:
        assert "category" in peak, f"missing category on peak {peak}"
        assert "chemical_region" in peak
        assert "labile_hint" in peak
        assert "category_reason" in peak

    # Top-level summary fields are present and the right shape.
    assert isinstance(payload["peak_category_summary"], dict)
    assert sum(payload["peak_category_summary"].values()) == len(payload["peaks"])

    assert isinstance(payload["labile_hydrogen_summary"], dict)
    summary = payload["labile_hydrogen_summary"]
    assert "expected_labile_h" in summary
    assert "observed_labile_candidates" in summary
    # Ethanol has 1 labile H (OH), and the 2.10 br s peak should be detected.
    assert summary["expected_labile_h"] == 1
    assert len(summary["observed_labile_candidates"]) >= 1

    assert isinstance(payload["impurity_candidates"], list)
    assert isinstance(payload["predicted_vs_observed"], list)
    # With "ethanol | CCO" candidate, predicted vs observed should produce rows.
    assert len(payload["predicted_vs_observed"]) > 0
    # Each matched row carries the new literature-grounded confidence fields.
    matched_rows = [r for r in payload["predicted_vs_observed"] if r["status"] == "matched"]
    if matched_rows:
        sample = matched_rows[0]
        assert "z_dp4" in sample
        assert "tail_probability" in sample
        assert sample["confidence"] in {"high", "medium", "low"}

    # references block always cites Smith & Goodman 2010 even for single-candidate analyses.
    references = payload["references"]
    assert isinstance(references, list) and len(references) > 0
    ref_keys = {ref["key"] for ref in references}
    assert "smith_goodman_2010_dp4" in ref_keys
    assert "silverstein_2014_8e" in ref_keys


def test_nmr_processed_analyze_runs_dp4_ranking_for_multiple_candidates(tmp_path) -> None:
    """When the user supplies ≥2 candidate SMILES, the response must include
    a DP4 ranking sorted by descending probability that sums to ~1.0."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "dp4-ranking",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), "
                    "1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "Methanol | CO\nEthanol | CCO\nPropanol | CCCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    ranking = payload["dp4_ranking"]
    assert isinstance(ranking, list) and len(ranking) >= 2
    total_p = sum(row["dp4_probability"] for row in ranking)
    assert 0.99 <= total_p <= 1.01
    probabilities = [row["dp4_probability"] for row in ranking]
    assert probabilities == sorted(probabilities, reverse=True)
    # DP4-AI citation surfaces when a multi-candidate ranking is computed.
    ref_keys = {r["key"] for r in payload["references"]}
    assert "howarth_goodman_2020_dp4ai" in ref_keys


def test_nmr_processed_invalid_file_returns_clear_400(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "1H"},
            files={"file": ("bad.csv", b"not,numeric\nabc,def\n", "text/csv")},
        )

    assert response.status_code == 400
    assert "Could not parse numeric spectrum data" in response.json()["detail"]


def test_nmr_raw_fid_preview_computes_sha256(tmp_path) -> None:
    content = _build_bruker_zip()
    expected = hashlib.sha256(content).hexdigest()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/preview",
            headers=HEADERS,
            data={"sample_id": "raw-preview", "nucleus": "1H", "vendor": "auto"},
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_sha256"] == expected
    assert payload["vendor_detected"] == "Bruker"
    assert payload["file_inventory"]["required_files_present"] is True
    assert any("No Fourier transform" in note for note in payload["notes"])


def test_nmr_raw_fid_unsupported_archive_returns_clear_error(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/preview",
            headers=HEADERS,
            data={"nucleus": "1H", "vendor": "auto"},
            files={"file": ("not-raw.txt", b"not an archive", "text/plain")},
        )

    assert response.status_code == 400
    assert "Raw FID vault rejected the upload" in response.json()["detail"]


def test_nmr_raw_fid_process_preserves_raw_hash(tmp_path) -> None:
    content = _build_bruker_zip()
    expected = hashlib.sha256(content).hexdigest()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/process",
            headers=HEADERS,
            data={
                "sample_id": "raw-process",
                "nucleus": "1H",
                "vendor": "auto",
                "processing_preset": "balanced",
                "preserve_raw": "true",
            },
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_sha256"] == expected
    assert payload["metadata"]["preserve_raw"] is True
    assert payload["point_count"] > 0
    assert len(payload["x"]) == len(payload["y"])
    recipe = payload["processing_parameters"]["processing_recipe"]
    assert recipe["baseline_correction"] == "bernstein"


def test_nmr_processed_accepts_1h_and_13c_nucleus_values(tmp_path) -> None:
    with _client(tmp_path) as client:
        proton = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "1H"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )
        carbon = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "13C", "solvent": "CDCl3"},
            files={"file": ("carbon.csv", CARBON13_CSV, "text/csv")},
        )

    assert proton.status_code == 200, proton.text
    assert carbon.status_code == 200, carbon.text
    assert proton.json()["nucleus"] == "1H"
    assert carbon.json()["nucleus"] == "13C"
    assert proton.json()["metadata"]["peak_inference"] == "skipped_for_display_preview"
    assert carbon.json()["metadata"]["peak_inference"] == "skipped_for_display_preview"


def test_nmr_processed_invalid_nucleus_is_rejected(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "15N"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 422


def test_nmr_frontend_upload_routes_are_in_openapi(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/nmr/processed/preview" in paths
    assert "/nmr/processed/analyze" in paths
    assert "/nmr/raw-fid/preview" in paths
    assert "/nmr/raw-fid/process" in paths


def test_nmr_processed_analyze_echoes_compound_class_in_metadata(tmp_path) -> None:
    """The compound_class form param round-trips into response metadata and
    is forwarded to candidate comparison."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "compound-class-test",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H)",
                "candidates_text": "ethanol | CCO",
                "compound_class": "small_molecules",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["metadata"]["compound_class"] == "small_molecules"
    candidate_comparison = payload["metadata"].get("candidate_comparison")
    assert candidate_comparison is not None
    assert candidate_comparison.get("compound_class") == "small_molecules"


def test_nmr_processed_analyze_rejects_unknown_compound_class_with_warning(
    tmp_path,
) -> None:
    """Unknown compound_class values are dropped (metadata is None) and a
    warning is surfaced rather than 4xx-ing the request."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "bad-class",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H)",
                "candidates_text": "ethanol | CCO",
                "compound_class": "not_a_real_class",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["metadata"]["compound_class"] is None
    assert any(
        "Ignored unrecognised compound_class" in warning
        for warning in payload["warnings"]
    )


def test_nmr_raw_fid_process_returns_enriched_peaks_and_summaries(tmp_path) -> None:
    """Parity check: /nmr/raw-fid/process must return the same enriched
    peak/summary fields as /nmr/processed/analyze so the Raw FID tab can
    mount the same evidence panels as the Processed tab."""
    content = _build_bruker_zip()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/process",
            headers=HEADERS,
            data={
                "sample_id": "raw-fid-enriched",
                "nucleus": "1H",
                "vendor": "auto",
                "processing_preset": "balanced",
                # Shared session inputs that drive enrichment.
                "candidates_text": "Ethanol | CCO",
                "proton_nmr_text": "3.65 (q, 2H), 1.26 (t, 3H)",
            },
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    # Wire-contract: every field the frontend panels consume must be present.
    required_keys = {
        "peaks",
        "peak_count",
        "peak_category_summary",
        "labile_hydrogen_summary",
        "proton_inventory",
        "impurity_candidates",
        "processing_parameters",
    }
    missing = required_keys - payload.keys()
    assert not missing, f"raw-fid/process response missing keys: {missing}"

    # Peaks must be enriched (category attached) when a SMILES is supplied.
    assert isinstance(payload["peaks"], list)
    if payload["peaks"]:
        first_peak = payload["peaks"][0]
        assert "category" in first_peak, (
            "Enriched peaks must carry a category field; got peak shape "
            f"{sorted(first_peak.keys())}"
        )

    # Audit metadata records that the shared NMR text + candidates reached the
    # endpoint (parity with /nmr/processed/analyze).
    metadata = payload["metadata"]
    assert metadata.get("candidate_text_supplied") is True
    assert metadata.get("proton_nmr_text_supplied") is True
    assert metadata.get("carbon13_text_supplied") is False


def test_nmr_raw_fid_preview_echoes_compound_class(tmp_path) -> None:
    content = _build_bruker_zip()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/preview",
            headers=HEADERS,
            data={
                "sample_id": "raw-class",
                "nucleus": "1H",
                "vendor": "auto",
                "compound_class": "natural_products",
            },
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["metadata"]["compound_class"] == "natural_products"


def test_nmr_processed_analyze_applies_per_class_prior(tmp_path) -> None:
    """End-to-end: a recognised compound_class triggers the per-class weight
    multiplier table; the audit payload reports renormalised weights summing
    to 1.0 and is reachable via metadata.candidate_comparison."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "carbo-e2e",
                "nucleus": "1H",
                "solvent": "D2O",
                "nmr_text": "1H NMR (D2O) delta 3.65 (q, 2H), 1.26 (t, 3H)",
                "candidates_text": "Ethanol | CCO",
                "compound_class": "carbohydrates",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    cc = payload["metadata"].get("candidate_comparison")
    assert cc is not None
    audit = cc.get("compound_class_prior_applied")
    assert audit is not None
    assert audit["compound_class"] == "carbohydrates"
    assert abs(sum(audit["renormalised_weights"].values()) - 1.0) < 1e-5
    # Carbohydrates explicitly boost nmr2d & carbon13 — verify the renormalised
    # values move in the expected direction relative to defaults.
    assert audit["renormalised_weights"]["nmr2d"] > audit["original_weights"]["nmr2d"]
    assert audit["renormalised_weights"]["carbon13"] > audit["original_weights"]["carbon13"]


def test_nmr_processed_analyze_emits_proton_inventory_and_subset(tmp_path) -> None:
    """End-to-end: /nmr/processed/analyze response carries:
    - labile_hydrogen_summary.labile_subset declaring the EXACT element subset
    - proton_inventory with observed + expected + deltas blocks
    - references include shift-window literature citations."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "ethanol",
                "nucleus": "1H",
                "solvent": "CDCl3",
                # Ethanol: 1 OH, 0 NH, 0 SH → subset must be "OH" (not generic)
                "nmr_text": "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
                "candidates_text": "Ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    # 1. Labile-H summary declares the exact subset.
    labile = payload["labile_hydrogen_summary"]
    assert labile["labile_subset"] == "OH"
    assert labile["expected_oh_h"] == 1
    assert labile["expected_nh_h"] == 0
    assert labile["expected_sh_h"] == 0
    assert any("(OH)" in note for note in labile["notes"])
    assert not any("(OH/NH/SH)" in note for note in labile["notes"])

    # 2. proton_inventory has observed + expected + deltas + warnings keys.
    inventory = payload["proton_inventory"]
    assert inventory["nucleus"] == "1H"
    assert set(inventory["observed"].keys()) >= {
        "aromatic",
        "aliphatic",
        "labile",
        "non_labile",
        "total",
    }
    assert inventory["expected"]["aliphatic"] == 5  # CH3 (3) + CH2 (2)
    assert inventory["expected"]["labile"] == 1  # OH
    assert inventory["expected"]["labile_subset"] == "OH"

    # 3. The references block must include the shift-window citations.
    ref_authors = {ref.get("authors", "") for ref in payload["references"]}
    citation_text = " ".join(ref_authors)
    assert "Pretsch" in citation_text or "Friebolin" in citation_text
    assert "Gottlieb" in citation_text or "Fulmer" in citation_text


def test_nmr_processed_analyze_tobramycin_peaks_are_anomeric_not_olefinic(
    tmp_path,
) -> None:
    """Regression for user-reported bug: the bundled Tobramycin SMILES is fully
    saturated (three aminosugar rings, no C=C bonds), so peaks in the 4.4–6
    ppm window must be labelled 'anomeric' and NOT 'olefinic'.

    Tobramycin SMILES (the one the user pasted):
        O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])
        [C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)
        [C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N
    """
    tobramycin_smiles = (
        "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])"
        "[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)"
        "[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N"
    )
    # Peaks in the anomeric region above the D2O HOD residual (4.55–5.05 ppm).
    # All three test peaks are at 5.10+ so the solvent short-circuit doesn't
    # mask the anomeric classification we're checking.
    peak_csv = (
        b"shift_ppm,integration_h,multiplicity\n"
        b"5.55,1,d\n"
        b"5.30,1,d\n"
        b"5.10,1,d\n"
        b"3.65,1,m\n"
        b"2.85,2,m\n"
    )
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "tobramycin",
                "nucleus": "1H",
                "solvent": "D2O",
                "candidates_text": f"Tobramycin | {tobramycin_smiles} | starting material",
            },
            files={"file": ("peaks.csv", peak_csv, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    # Find the picked peaks in the 4.4–6 ppm range and assert they are NOT
    # categorised as "olefinic". They MUST be anomeric since the SMILES has
    # anomeric protons and zero olefinic protons.
    anomeric_window_peaks = [
        p for p in payload["peaks"] if 4.4 <= float(p["shift_ppm"]) < 6.0
    ]
    assert len(anomeric_window_peaks) >= 1
    for peak in anomeric_window_peaks:
        assert peak["category"] == "anomeric", (
            f"Tobramycin peak at {peak['shift_ppm']} ppm was categorised as "
            f"'{peak['category']}' — should be 'anomeric' since SMILES is saturated."
        )
        assert "no olefinic" in peak["category_reason"].lower() or "anomeric assignment" in peak["category_reason"].lower(), (
            f"Reason must justify the anomeric call: {peak['category_reason']}"
        )

    # The peak_category_summary must reflect the new category — not "olefinic".
    summary = payload["peak_category_summary"]
    assert "anomeric" in summary
    assert "olefinic" not in summary, (
        f"olefinic must not appear in peak_category_summary for tobramycin: {summary}"
    )


def test_nmr_processed_analyze_uses_shared_proton_carbon_layers(tmp_path) -> None:
    """Integration-audit fix: the shared session card's 1H + 13C texts (sent
    as proton_nmr_text + carbon13_text) feed candidate scoring as parallel
    evidence layers, not just the active nucleus."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "shared-layers",
                "nucleus": "1H",
                "solvent": "CDCl3",
                # Local override targeting the active 1H nucleus
                "nmr_text": "1H NMR (CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
                # Shared session card values: BOTH must feed candidate scoring
                "proton_nmr_text": "1H NMR (CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
                "carbon13_text": "13C NMR (CDCl3) delta 58.3, 18.2",
                "candidates_text": "Ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    cc = payload["metadata"].get("candidate_comparison")
    assert cc is not None
    layers = cc.get("evidence_layers_used") or []
    # The key assertion: BOTH 1H and 13C must be present, not just the active nucleus.
    assert "1H" in layers, f"Expected 1H in evidence_layers_used, got {layers}"
    assert "13C" in layers, f"Expected 13C in evidence_layers_used, got {layers}"
