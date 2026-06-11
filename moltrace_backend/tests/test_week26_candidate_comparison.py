from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmrcheck.candidate import compare_candidates, parse_candidate_text
from nmrcheck.models import CandidateComparisonRequest, CandidateInput

FIXTURES = Path(__file__).parent / "fixtures"
STATE_FIXTURES = FIXTURES / "current_state"

ETHANOL_1H = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_13C = "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2."


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


def test_candidate_compare_endpoint_works_with_json(client, api_headers) -> None:
    with client:
        response = client.post(
            "/candidates/compare",
            headers=api_headers,
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


def test_candidate_compare_evidence_endpoint_works_with_multipart_layers(client, api_headers) -> None:
    dept_bytes = (FIXTURES / "dept" / "ethanol_dept135.csv").read_bytes()
    hsqc_bytes = (FIXTURES / "nmr2d" / "ethanol_hsqc.csv").read_bytes()
    with client:
        response = client.post(
            "/candidates/compare/evidence",
            headers=api_headers,
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


def test_candidate_compare_evidence_rejects_invalid_dept_file(client, api_headers) -> None:
    with client:
        response = client.post(
            "/candidates/compare/evidence",
            headers=api_headers,
            data={"candidates_text": "Ethanol | CCO | proposed"},
            files={"dept_apt_file": ("invalid_dept.csv", b"not_a_shift\nnope\n", "text/csv")},
        )

    assert response.status_code == 400
    assert "No valid DEPT/APT peaks" in response.json()["detail"]


def test_candidate_comparison_does_not_change_stable_endpoint_outputs(client, api_headers) -> None:
    spectrum_content = (STATE_FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    proton_payload = _load_state_json("ethanol_inputs.json")
    carbon_payload = _load_state_json("ethanol_carbon13_inputs.json")
    with client:
        spectrum_before = client.post(
            "/spectrum/preview",
            headers=api_headers,
            files={"file": ("processed_spectrum_trace.csv", spectrum_content, "text/csv")},
        )
        proton_before = client.post("/proton/evidence", headers=api_headers, json=proton_payload)
        carbon_before = client.post("/carbon13/analyze", headers=api_headers, json=carbon_payload)
        candidate_response = client.post(
            "/candidates/compare",
            headers=api_headers,
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
            headers=api_headers,
            files={"file": ("processed_spectrum_trace.csv", spectrum_content, "text/csv")},
        )
        proton_after = client.post("/proton/evidence", headers=api_headers, json=proton_payload)
        carbon_after = client.post("/carbon13/analyze", headers=api_headers, json=carbon_payload)

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


# ──────────────────────────────────────────────────────────────────────────────
# Per-class priors (compound_class) tests
# ──────────────────────────────────────────────────────────────────────────────


def test_unspecified_compound_class_does_not_apply_prior() -> None:
    """Default behaviour: no class → no audit metadata, default weights."""
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id="no-class",
            solvent="CDCl3",
            proton_nmr_text=ETHANOL_1H,
            carbon13_text=ETHANOL_13C,
            candidates=[CandidateInput(name="Ethanol", smiles="CCO")],
        )
    )

    assert result.compound_class is None
    assert result.compound_class_prior_applied is None


def test_compound_class_prior_renormalises_weights_and_emits_audit() -> None:
    """When a recognised class is given the audit payload reports original +
    renormalised weights that sum to 1.0."""
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id="carbo",
            solvent="D2O",
            compound_class="carbohydrates",
            proton_nmr_text="1H NMR (D2O) delta 5.20 (d, 1H), 3.40 (m, 6H)",
            carbon13_text="13C NMR delta 102.5, 76.8, 73.4, 71.2, 70.1, 61.5",
            candidates=[CandidateInput(name="Glucose", smiles="OCC1OC(O)C(O)C(O)C1O")],
        )
    )

    audit = result.compound_class_prior_applied
    assert audit is not None
    assert audit["compound_class"] == "carbohydrates"
    assert set(audit["original_weights"].keys()) == {
        "structure",
        "proton",
        "carbon13",
        "dept_apt",
        "nmr2d",
    }
    renorm = audit["renormalised_weights"]
    assert abs(sum(renorm.values()) - 1.0) < 1e-5, renorm
    # Carbohydrates explicitly up-weight nmr2d (1.5x) and carbon13 (1.3x);
    # the renormalised values must be strictly greater than the originals.
    assert renorm["nmr2d"] > audit["original_weights"]["nmr2d"]
    assert renorm["carbon13"] > audit["original_weights"]["carbon13"]
    # And the human-readable notes should mention what was moved.
    notes_text = " ".join(audit["notes"])
    assert "carbohydrates" in notes_text.lower()
    assert "Up-weighted" in notes_text or "carbon13" in notes_text


def test_protein_class_downweights_proton_and_boosts_2d() -> None:
    """Proteins: 1H overlap is severe so proton weight must drop, 2D must rise."""
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id="protein-stub",
            solvent="DMSO-d6",
            compound_class="proteins",
            proton_nmr_text=ETHANOL_1H,
            candidates=[CandidateInput(name="Stub", smiles="CCO")],
        )
    )

    audit = result.compound_class_prior_applied
    assert audit is not None
    assert audit["renormalised_weights"]["proton"] < audit["original_weights"]["proton"]
    assert audit["renormalised_weights"]["nmr2d"] > audit["original_weights"]["nmr2d"]


def test_unknown_compound_class_falls_through_without_audit() -> None:
    """A class string with no entry in the multiplier table must NOT crash and
    must NOT add an audit payload; a fall-through note is emitted instead."""
    # We bypass normalize_compound_class here on purpose — the candidate
    # comparator must be defensive even if a future caller forgets to normalise.
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id="weird-class",
            solvent="CDCl3",
            compound_class="not_a_real_class_x",
            proton_nmr_text=ETHANOL_1H,
            candidates=[CandidateInput(name="Ethanol", smiles="CCO")],
        )
    )

    assert result.compound_class == "not_a_real_class_x"
    assert result.compound_class_prior_applied is None
    assert any("no class-specific weighting" in note for note in result.notes)


# NB: E2E tests for the /nmr/processed/analyze endpoint plumbing live in
# test_nmr_frontend_upload_api.py, which uses a client factory that
# initialises the audit_events table. The four tests above are unit-level
# (calling compare_candidates directly) and avoid that dependency.
