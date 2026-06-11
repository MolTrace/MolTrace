from collections.abc import Callable
from typing import Any

REQUIRED_MS_EVIDENCE_STUDIO_ENDPOINTS = [
    "/ms/hrms/candidates/match/evidence",
    "/ms/hrms/formulas/search",
    "/ms/adducts/infer/evidence",
    "/ms/msms/annotate/evidence",
    "/ms/msms/fragmentation-tree/evidence",
    "/ms/lcms/import/bridge/upload",
    "/ms/lcms/import/bridge/evidence",
    "/ms/lcms/features/detect/upload",
    "/ms/lcms/features/detect/evidence",
    "/ms/lcms/features/group/upload",
    "/ms/lcms/features/group/evidence",
    "/ms/lcms/features/consensus/upload",
    "/ms/lcms/features/consensus/evidence",
    "/ms/lcms/dereplication/upload",
    "/ms/lcms/dereplication/evidence",
    "/confidence/candidates/lcms-consensus-bridge",
    "/confidence/candidates/unified/evidence",
    "/reports/structure-elucidation/compose/evidence",
]

LCMS_SOURCE = (
    "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\n"
    "s1,1,0.0,47.04914,5,\n"
    "s2,1,0.1,47.04914,100,\n"
    "s3,1,0.2,47.04914,7,\n"
    "ms2,2,0.1,29.03858,100,47.04914\n"
)
LCMS_BLANK = (
    "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\n"
    "b1,1,0.0,47.04914,1,\n"
    "b2,1,0.1,47.04914,3,\n"
    "b3,1,0.2,47.04914,1,\n"
)
LCMS_GROUP_TABLE = (
    "group_id,representative_mz,aligned_rt_min,label,sample_area,blank_area,blank_ratio,"
    "blank_subtracted_area,member_count,roles_present\n"
    "G001,47.049141,1.250000,sample_enriched_feature,1000,0,0,1000,1,sample\n"
    "G002,48.052496,1.260000,sample_enriched_feature,35,0,0,35,1,sample\n"
)
LCMS_FAMILY_TABLE = (
    "family_id,anchor_group_id,anchor_mz,anchor_rt_min,label,consensus_score,promoted,"
    "relationship_count,member_count\n"
    "F001,G001,47.049141,1.250000,moderate_confidence_feature_family,0.8300,true,2,3\n"
)
CANDIDATES_TEXT = "methanol | CO | alternate\nethanol | CCO | proposed"
MSMS_PEAKS = "m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25\n"


def test_ms_evidence_studio_required_paths_appear_in_openapi(client, api_headers) -> None:
    with client:
        response = client.get("/openapi.json", headers=api_headers)

    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in REQUIRED_MS_EVIDENCE_STUDIO_ENDPOINTS:
        assert path in paths
        assert "post" in paths[path]


def test_lcms_dereplication_upload_accepts_frontend_file_only_and_stays_cautious(
    client, api_headers
) -> None:
    headers = api_headers
    library = "name,smiles,role\nethanol,CCO,library\nmethanol,CO,library\n"
    with client:
        response = client.post(
            "/ms/lcms/dereplication/upload",
            headers=headers,
            data={"sample_id": "derep-upload"},
            files={"file": ("library.csv", library.encode(), "text/csv")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sample_id"] == "derep-upload"
    assert body["candidate_count"] == 2
    assert body["label"] == "metadata_only_no_identification"
    assert body["human_review_required"] is True
    assert body["warnings"]
    assert len(body["file_sha256"]) == 64


def test_lcms_dereplication_evidence_wraps_consensus_bridge(client, api_headers) -> None:
    headers = api_headers
    with client:
        response = client.post(
            "/ms/lcms/dereplication/evidence",
            headers=headers,
            data={
                "sample_id": "derep-evidence",
                "candidates_text": CANDIDATES_TEXT,
                "lcms_family_table_text": LCMS_FAMILY_TABLE,
                "adduct": "[M+H]+",
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sample_id"] == "derep-evidence"
    assert body["best_match"]["name"] == "ethanol"
    assert body["label"] == "candidate_matches_require_review"
    assert "do not confirm identity" in " ".join(body["notes"])


def test_ms_evidence_studio_frontend_facing_endpoints_smoke(client, api_headers) -> None:
    headers = api_headers
    cases: list[tuple[str, Callable[[], Any], tuple[str, ...]]] = [
        (
            "/ms/hrms/candidates/match/evidence",
            lambda: client.post(
                "/ms/hrms/candidates/match/evidence",
                headers=headers,
                data={
                    "sample_id": "hrms",
                    "candidates_text": CANDIDATES_TEXT,
                    "observed_mz": "47.04914",
                    "adduct": "[M+H]+",
                },
            ),
            ("ranked_candidates", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/hrms/formulas/search",
            lambda: client.post(
                "/ms/hrms/formulas/search",
                headers=headers,
                json={
                    "observed_mz": 47.04914,
                    "adduct": "[M+H]+",
                    "max_c": 3,
                    "max_h": 10,
                    "max_o": 2,
                },
            ),
            ("formulas", "warnings", "metadata"),
        ),
        (
            "/ms/adducts/infer/evidence",
            lambda: client.post(
                "/ms/adducts/infer/evidence",
                headers=headers,
                data={
                    "sample_id": "adduct",
                    "peak_list_text": "m/z,intensity\n47.04914,100\n48.05249,2.3\n",
                },
            ),
            ("adduct_candidates", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/msms/annotate/evidence",
            lambda: client.post(
                "/ms/msms/annotate/evidence",
                headers=headers,
                data={
                    "sample_id": "msms",
                    "peak_list_text": MSMS_PEAKS,
                    "precursor_mz": "47.04914",
                    "adduct": "[M+H]+",
                    "candidates_text": CANDIDATES_TEXT,
                },
            ),
            ("ranked_candidates", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/msms/fragmentation-tree/evidence",
            lambda: client.post(
                "/ms/msms/fragmentation-tree/evidence",
                headers=headers,
                data={
                    "sample_id": "tree",
                    "peak_list_text": MSMS_PEAKS,
                    "precursor_mz": "47.04914",
                    "adduct": "[M+H]+",
                    "candidates_text": CANDIDATES_TEXT,
                },
            ),
            ("ranked_candidates", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/import/bridge/upload",
            lambda: client.post(
                "/ms/lcms/import/bridge/upload",
                headers=headers,
                data={"source_format": "processed_peak_table", "sample_id": "import-upload"},
                files={"file": ("lcms.csv", LCMS_SOURCE.encode(), "text/csv")},
            ),
            ("warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/import/bridge/evidence",
            lambda: client.post(
                "/ms/lcms/import/bridge/evidence",
                headers=headers,
                data={
                    "filename": "lcms.csv",
                    "source_text": LCMS_SOURCE,
                    "source_format": "processed_peak_table",
                    "sample_id": "import-evidence",
                },
            ),
            ("warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/detect/upload",
            lambda: client.post(
                "/ms/lcms/features/detect/upload",
                headers=headers,
                data={
                    "target_mz_text": "47.04914",
                    "min_scans_per_feature": "1",
                    "sample_id": "detect-upload",
                },
                files={"file": ("lcms.csv", LCMS_SOURCE.encode(), "text/csv")},
            ),
            ("features", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/detect/evidence",
            lambda: client.post(
                "/ms/lcms/features/detect/evidence",
                headers=headers,
                data={
                    "filename": "lcms.csv",
                    "source_text": LCMS_SOURCE,
                    "target_mz_text": "47.04914",
                    "min_scans_per_feature": "1",
                    "sample_id": "detect-evidence",
                },
            ),
            ("features", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/group/upload",
            lambda: client.post(
                "/ms/lcms/features/group/upload",
                headers=headers,
                data={
                    "target_mz_text": "47.04914",
                    "min_scans_per_feature": "1",
                    "sample_id": "group-upload",
                },
                files={
                    "sample_file": ("sample.csv", LCMS_SOURCE.encode(), "text/csv"),
                    "blank_file": ("blank.csv", LCMS_BLANK.encode(), "text/csv"),
                },
            ),
            ("groups", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/group/evidence",
            lambda: client.post(
                "/ms/lcms/features/group/evidence",
                headers=headers,
                data={
                    "sample_source_text": LCMS_SOURCE,
                    "blank_source_text": LCMS_BLANK,
                    "target_mz_text": "47.04914",
                    "min_scans_per_feature": "1",
                    "sample_id": "group-evidence",
                },
            ),
            ("groups", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/consensus/upload",
            lambda: client.post(
                "/ms/lcms/features/consensus/upload",
                headers=headers,
                data={
                    "formula": "C2H6O",
                    "min_consensus_score_to_promote": "0.3",
                    "sample_id": "consensus-upload",
                },
                files={"feature_table_file": ("groups.csv", LCMS_GROUP_TABLE.encode(), "text/csv")},
            ),
            ("families", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/features/consensus/evidence",
            lambda: client.post(
                "/ms/lcms/features/consensus/evidence",
                headers=headers,
                data={
                    "feature_table_text": LCMS_GROUP_TABLE,
                    "formula": "C2H6O",
                    "min_consensus_score_to_promote": "0.3",
                    "sample_id": "consensus-evidence",
                },
            ),
            ("families", "warnings", "notes", "metadata"),
        ),
        (
            "/ms/lcms/dereplication/upload",
            lambda: client.post(
                "/ms/lcms/dereplication/upload",
                headers=headers,
                data={
                    "lcms_family_table_text": LCMS_FAMILY_TABLE,
                    "sample_id": "derep-upload-match",
                },
                files={
                    "file": (
                        "library.csv",
                        b"name,smiles\nethanol,CCO\nmethanol,CO\n",
                        "text/csv",
                    )
                },
            ),
            ("matches", "warnings", "notes", "metadata", "evidence_summary"),
        ),
        (
            "/ms/lcms/dereplication/evidence",
            lambda: client.post(
                "/ms/lcms/dereplication/evidence",
                headers=headers,
                data={
                    "candidates_text": CANDIDATES_TEXT,
                    "lcms_family_table_text": LCMS_FAMILY_TABLE,
                    "sample_id": "derep-evidence-match",
                },
            ),
            ("matches", "warnings", "notes", "metadata", "evidence_summary"),
        ),
        (
            "/confidence/candidates/lcms-consensus-bridge",
            lambda: client.post(
                "/confidence/candidates/lcms-consensus-bridge",
                headers=headers,
                json={
                    "sample_id": "bridge",
                    "candidates": [
                        {"name": "ethanol", "smiles": "CCO"},
                        {"name": "methanol", "smiles": "CO"},
                    ],
                    "lcms_family_table_text": LCMS_FAMILY_TABLE,
                    "adduct": "[M+H]+",
                },
            ),
            ("matches", "warnings", "notes", "metadata"),
        ),
        (
            "/confidence/candidates/unified/evidence",
            lambda: client.post(
                "/confidence/candidates/unified/evidence",
                headers=headers,
                data={
                    "sample_id": "unified",
                    "candidates_text": CANDIDATES_TEXT,
                    "hrms_observed_mz": "47.04914",
                    "hrms_adduct": "[M+H]+",
                    "msms_precursor_mz": "47.04914",
                    "msms_peak_list_text": MSMS_PEAKS,
                    "msms_adduct": "[M+H]+",
                },
            ),
            ("warnings", "notes", "component_metadata"),
        ),
        (
            "/reports/structure-elucidation/compose/evidence",
            lambda: client.post(
                "/reports/structure-elucidation/compose/evidence",
                headers=headers,
                data={
                    "sample_id": "report",
                    "report_title": "MS Evidence Studio Report",
                    "candidates_text": CANDIDATES_TEXT,
                    "hrms_observed_mz": "47.04914",
                    "hrms_adduct": "[M+H]+",
                },
            ),
            ("warnings", "notes", "provenance", "human_review_required"),
        ),
    ]

    with client:
        for path, make_request, expected_fields in cases:
            response = make_request()
            assert response.status_code == 200, f"{path}: {response.text}"
            body = response.json()
            for field in expected_fields:
                assert field in body, f"{path} missing {field}"
