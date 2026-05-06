from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.candidate import compare_candidates, parse_candidate_text
from nmrcheck.models import CandidateComparisonRequest, CandidateInput
from nmrcheck.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "current_state"

ETHANOL_1H = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_13C = "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2."


def _client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'week26_candidates.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            enable_2d_nmr=True,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _load_state_json(name: str) -> dict[str, object]:
    return json.loads((STATE_FIXTURES / name).read_text())


def test_parse_candidate_text_name_smiles_role() -> None:
    candidates = parse_candidate_text("Ethanol | CCO | proposed\nMethanol | CO | side product")

    assert len(candidates) == 2
    assert candidates[0].name == "Ethanol"
    assert candidates[0].smiles == "CCO"
    assert candidates[0].role == "proposed"


def test_parse_candidate_text_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="No candidate structures"):
        parse_candidate_text("\n# only a comment\n")


def test_candidate_comparison_ranks_ethanol_highest() -> None:
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id="EtOH-001",
            solvent="CDCl3",
            proton_nmr_text=ETHANOL_1H,
            carbon13_text=ETHANOL_13C,
            candidates=[
                CandidateInput(name="Ethanol", smiles="CCO", role="proposed"),
                CandidateInput(name="Methanol", smiles="CO", role="starting material"),
                CandidateInput(name="Propanol", smiles="CCCO", role="side product"),
            ],
        )
    )

    assert result.candidate_count == 3
    assert result.best_candidate is not None
    assert result.best_candidate.name == "Ethanol"
    assert result.best_candidate.total_score >= result.ranked_candidates[1].total_score
    assert "1H" in result.evidence_layers_used
    assert "13C" in result.evidence_layers_used
    assert any("not final structure confirmation" in note for note in result.notes)


def test_candidate_comparison_flags_invalid_structure() -> None:
    result = compare_candidates(
        CandidateComparisonRequest(
            proton_nmr_text=ETHANOL_1H,
            candidates=[
                CandidateInput(name="Bad", smiles="not_a_smiles"),
                CandidateInput(name="Ethanol", smiles="CCO"),
            ],
        )
    )

    bad = [item for item in result.ranked_candidates if item.name == "Bad"][0]
    assert bad.label == "invalid_structure"
    assert bad.total_score == 0.0


def test_candidate_comparison_warns_when_top_scores_are_close() -> None:
    result = compare_candidates(
        CandidateComparisonRequest(
            proton_nmr_text=ETHANOL_1H,
            carbon13_text=ETHANOL_13C,
            candidates=[
                CandidateInput(name="EtOH A", smiles="CCO"),
                CandidateInput(name="EtOH B", smiles="CCO"),
            ],
        )
    )

    assert result.ranked_candidates[0].total_score == result.ranked_candidates[1].total_score
    assert any("Top two candidates are close" in alert for alert in result.ambiguity_alerts)


def test_structure_only_candidate_comparison_is_capped_as_weak_support() -> None:
    result = compare_candidates(
        CandidateComparisonRequest(
            candidates=[
                CandidateInput(name="Ethanol", smiles="CCO"),
                CandidateInput(name="Methanol", smiles="CO"),
            ],
        )
    )

    assert result.best_candidate is not None
    assert result.best_candidate.total_score <= 0.35
    assert result.best_candidate.label == "weak_support"
    assert any("No 1H or 13C text" in warning for warning in result.warnings)


def test_candidate_compare_endpoint_works_with_json(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/candidates/compare",
            headers=headers,
            json={
                "sample_id": "EtOH-JSON",
                "solvent": "CDCl3",
                "proton_nmr_text": ETHANOL_1H,
                "carbon13_text": ETHANOL_13C,
                "candidates": [
                    {"name": "Ethanol", "smiles": "CCO", "role": "proposed"},
                    {"name": "Methanol", "smiles": "CO", "role": "starting material"},
                ],
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["best_candidate"]["name"] == "Ethanol"
    assert data["ranked_candidates"][0]["score_breakdown"]["proton_score"] is not None


def test_candidate_compare_evidence_endpoint_works_with_multipart_layers(tmp_path) -> None:
    client, headers = _client(tmp_path)
    dept_bytes = (FIXTURES / "dept" / "ethanol_dept135.csv").read_bytes()
    hsqc_bytes = (FIXTURES / "nmr2d" / "ethanol_hsqc.csv").read_bytes()
    with client:
        response = client.post(
            "/candidates/compare/evidence",
            headers=headers,
            data={
                "sample_id": "EtOH-MULTI",
                "solvent": "CDCl3",
                "proton_nmr_text": ETHANOL_1H,
                "carbon13_text": ETHANOL_13C,
                "candidates_text": "Ethanol | CCO | proposed\nMethanol | CO | starting material",
                "dept_apt_experiment_type": "DEPT135",
                "nmr2d_experiment_type": "HSQC",
                "apt_positive": "CH_CH3",
            },
            files={
                "dept_apt_file": ("ethanol_dept135.csv", dept_bytes, "text/csv"),
                "nmr2d_file": ("ethanol_hsqc.csv", hsqc_bytes, "text/csv"),
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["best_candidate"]["name"] == "Ethanol"
    assert "DEPT/APT" in data["evidence_layers_used"]
    assert "2D NMR" in data["evidence_layers_used"]
    assert data["ranked_candidates"][0]["score_breakdown"]["dept_apt_score"] is not None
    assert data["ranked_candidates"][0]["score_breakdown"]["nmr2d_score"] is not None


def test_candidate_compare_evidence_rejects_invalid_dept_file(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/candidates/compare/evidence",
            headers=headers,
            data={"candidates_text": "Ethanol | CCO | proposed"},
            files={"dept_apt_file": ("invalid_dept.csv", b"not_a_shift\nnope\n", "text/csv")},
        )

    assert response.status_code == 400
    assert "No valid DEPT/APT peaks" in response.json()["detail"]


def test_candidate_comparison_does_not_change_stable_endpoint_outputs(tmp_path) -> None:
    client, headers = _client(tmp_path)
    spectrum_content = (STATE_FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    proton_payload = _load_state_json("ethanol_inputs.json")
    carbon_payload = _load_state_json("ethanol_carbon13_inputs.json")
    with client:
        spectrum_before = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", spectrum_content, "text/csv")},
        )
        proton_before = client.post("/proton/evidence", headers=headers, json=proton_payload)
        carbon_before = client.post("/carbon13/analyze", headers=headers, json=carbon_payload)
        candidate_response = client.post(
            "/candidates/compare",
            headers=headers,
            json={
                "sample_id": "stable-guard",
                "solvent": "CDCl3",
                "proton_nmr_text": proton_payload["nmr_text"],
                "carbon13_text": carbon_payload["carbon13_text"],
                "candidates": [
                    {"name": "Ethanol", "smiles": "CCO", "role": "proposed"},
                    {"name": "Methanol", "smiles": "CO", "role": "starting material"},
                ],
            },
        )
        spectrum_after = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", spectrum_content, "text/csv")},
        )
        proton_after = client.post("/proton/evidence", headers=headers, json=proton_payload)
        carbon_after = client.post("/carbon13/analyze", headers=headers, json=carbon_payload)

    assert candidate_response.status_code == 200, candidate_response.text
    assert spectrum_before.status_code == 200
    assert spectrum_after.status_code == 200
    assert proton_before.status_code == 200
    assert proton_after.status_code == 200
    assert carbon_before.status_code == 200
    assert carbon_after.status_code == 200
    assert spectrum_before.json() == spectrum_after.json()
    assert proton_before.json() == proton_after.json()
    assert carbon_before.json() == carbon_after.json()
