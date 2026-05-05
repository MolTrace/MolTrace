from tempfile import mkdtemp

from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from nmrcheck.analysis import validate_inputs
from nmrcheck.api import AccessContext, analyze, create_app
from nmrcheck.database import init_db
from nmrcheck.models import AnalysisInputs, AnalysisValidationInputs
from nmrcheck.settings import Settings


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-analysis-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/analysis.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/analyze",
        "query_string": b"",
    }
    return Request(scope)


def test_analysis_inputs_reject_empty_smiles() -> None:
    try:
        AnalysisInputs(
            sample_id="empty-smiles",
            smiles="   ",
            nmr_text="1.23 (s, 1H)",
            solvent="CDCl3",
        )
    except ValidationError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected empty SMILES to fail validation.")


def test_analysis_inputs_reject_empty_nmr_text() -> None:
    try:
        AnalysisInputs(
            sample_id="empty-nmr",
            smiles="CCO",
            nmr_text="   ",
            solvent="CDCl3",
        )
    except ValidationError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected empty 1H NMR text to fail validation.")


def test_validate_inputs_rejects_invalid_smiles() -> None:
    payload = AnalysisInputs(
        sample_id="bad-smiles",
        smiles="not a smiles",
        nmr_text="1.23 (s, 1H)",
        solvent="CDCl3",
    )

    report = validate_inputs(payload)

    assert report.structure_valid is False
    assert report.nmr_text_valid is True
    assert report.analysis_ready is False
    assert any("Invalid SMILES" in error or "SMILES" in error for error in report.errors)


def test_validate_inputs_rejects_malformed_nmr_text() -> None:
    payload = AnalysisInputs(
        sample_id="bad-nmr",
        smiles="CCO",
        nmr_text="this is not parseable nmr text",
        solvent="CDCl3",
    )

    report = validate_inputs(payload)

    assert report.nmr_text_valid is False
    assert report.structure_valid is True
    assert report.analysis_ready is False
    assert any(
        "Could not parse any peaks" in error or "parse" in error.lower()
        for error in report.errors
    )


def test_validate_inputs_checks_smiles_without_nmr_text() -> None:
    payload = AnalysisValidationInputs(
        sample_id="structure-only",
        smiles="CCO",
        nmr_text=None,
        solvent="CDCl3",
    )

    report = validate_inputs(payload)

    assert report.structure_valid is True
    assert report.nmr_text_valid is False
    assert report.structure_nmr_match is False
    assert report.analysis_ready is False
    assert report.errors == []
    assert any("1H NMR text" in warning for warning in report.warnings)


def test_validate_inputs_checks_nmr_text_without_smiles() -> None:
    payload = AnalysisValidationInputs(
        sample_id="nmr-only",
        smiles=None,
        nmr_text="1.23 (s, 1H)",
        solvent="CDCl3",
    )

    report = validate_inputs(payload)

    assert report.structure_valid is False
    assert report.nmr_text_valid is True
    assert report.structure_nmr_match is False
    assert report.analysis_ready is False
    assert report.errors == []
    assert any("SMILES" in warning for warning in report.warnings)


def test_validate_inputs_rejects_structure_nmr_mismatch() -> None:
    payload = AnalysisInputs(
        sample_id="mismatch-1",
        smiles="CCO",
        nmr_text="7.20 (m, 5H)",
        solvent="CDCl3",
    )

    report = validate_inputs(payload)

    assert report.structure_valid is True
    assert report.nmr_text_valid is True
    assert report.structure_nmr_match is False
    assert report.analysis_ready is False
    assert report.expected_visible_h == 6.0
    assert any("SMILES / 1H NMR mismatch" in error for error in report.errors)


def test_validate_inputs_accepts_d2o_non_labile_match() -> None:
    payload = AnalysisInputs(
        sample_id="d2o-1",
        smiles="CCO",
        nmr_text="3.65 (q, 2H), 1.26 (t, 3H)",
        solvent="D2O",
    )

    report = validate_inputs(payload)

    assert report.structure_valid is True
    assert report.nmr_text_valid is True
    assert report.structure_nmr_match is True
    assert report.analysis_ready is True
    assert report.expected_visible_h == 5.0
    assert report.observed_total_h == 5.0
    assert report.errors == []


def test_analyze_endpoint_rejects_mismatched_smiles_and_nmr_text() -> None:
    payload = AnalysisInputs(
        sample_id="mismatch-2",
        smiles="CCO",
        nmr_text="7.20 (m, 5H)",
        solvent="CDCl3",
    )

    try:
        analyze(payload, _build_request(), AccessContext(system_api_key=True))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "SMILES / 1H NMR mismatch" in str(exc.detail)
    else:
        raise AssertionError("Expected analyze() to reject mismatched SMILES and 1H NMR text.")
