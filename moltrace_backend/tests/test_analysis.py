from tempfile import mkdtemp

from fastapi import HTTPException
from fastapi.testclient import TestClient
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


# ──────────────────────────────────────────────────────────────────────────────
# HTTP wire-contract regression for /analyze/validate
#
# The SpectraCheck workspace's session-validate card depends on the EXACT
# response shape of /analyze/validate. These tests lock the four input modes
# the frontend exercises so future refactors of validate_inputs cannot
# silently break the validate-card UI.
# ──────────────────────────────────────────────────────────────────────────────


def _validate_client():
    tmpdir = mkdtemp(prefix="nmrcheck-validate-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/validate.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    return TestClient(app)


_HEADERS = {"x-api-key": "test-key"}


def test_validate_endpoint_both_inputs_match_marks_analysis_ready() -> None:
    """Both SMILES and 1H NMR text supplied and they agree → analysis_ready=true,
    no errors, structure_nmr_match=true. This is the green-path the frontend
    renders as 'Validation passed — analysis ready'."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={
            "sample_id": "ethanol",
            "smiles": "CCO",
            "nmr_text": "3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
            "solvent": "CDCl3",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure_valid"] is True
    assert body["nmr_text_valid"] is True
    assert body["structure_nmr_match"] is True
    assert body["analysis_ready"] is True
    assert body["errors"] == []


def test_validate_endpoint_smiles_only_returns_partial_no_errors() -> None:
    """SMILES alone is a valid input mode — backend returns
    structure_valid=true, nmr_text_valid=false, errors empty, with a warning
    about adding 1H NMR text. The frontend renders this as the 'Partial
    inputs — you can still proceed' state."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={"smiles": "CCO", "nmr_text": None, "solvent": "CDCl3"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure_valid"] is True
    assert body["nmr_text_valid"] is False
    assert body["analysis_ready"] is False
    assert body["errors"] == []
    assert any("1H NMR text" in warning for warning in body["warnings"])


def test_validate_endpoint_nmr_text_only_returns_partial_no_errors() -> None:
    """Symmetric case: 1H NMR text alone is also a valid input mode."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={"smiles": None, "nmr_text": "1.23 (s, 1H)", "solvent": "CDCl3"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure_valid"] is False
    assert body["nmr_text_valid"] is True
    assert body["analysis_ready"] is False
    assert body["errors"] == []
    assert any("SMILES" in warning for warning in body["warnings"])


def test_validate_endpoint_neither_input_returns_warnings_no_errors() -> None:
    """Empty payload — neither SMILES nor 1H NMR text. The endpoint still
    returns 200 with both warnings, no errors. The frontend renders this as
    'No inputs supplied — nothing to validate'."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={"smiles": None, "nmr_text": None, "solvent": None},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure_valid"] is False
    assert body["nmr_text_valid"] is False
    assert body["analysis_ready"] is False
    assert body["errors"] == []
    # Both prompts must be present in the warning list.
    joined = " ".join(body["warnings"])
    assert "SMILES" in joined
    assert "1H NMR text" in joined


def test_validate_endpoint_mismatch_emits_explicit_error() -> None:
    """SMILES + non-matching NMR text → structure_nmr_match=false, errors
    populated with the specific mismatch (the frontend renders this as
    'Validation failed' with the backend error list)."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={
            "sample_id": "mismatch",
            "smiles": "CCO",  # ethanol = 6 H total, 5 visible in CDCl3
            "nmr_text": "7.20 (m, 9H)",  # claims 9 aromatic H
            "solvent": "CDCl3",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["structure_valid"] is True
    assert body["nmr_text_valid"] is True
    assert body["structure_nmr_match"] is False
    assert body["analysis_ready"] is False
    assert len(body["errors"]) >= 1
    assert any(
        "SMILES" in err or "mismatch" in err.lower() or "exceeds" in err.lower()
        for err in body["errors"]
    ), body["errors"]


def test_validate_endpoint_response_shape_matches_frontend_contract() -> None:
    """The frontend declares ValidationReport with a specific set of fields —
    this test asserts every one is present so the wire contract is locked."""
    client = _validate_client()
    response = client.post(
        "/analyze/validate",
        headers=_HEADERS,
        json={"smiles": "CCO", "nmr_text": "3.65 (q, 2H), 1.26 (t, 3H)", "solvent": "CDCl3"},
    )
    assert response.status_code == 200
    body = response.json()
    required_keys = {
        "sample_id",
        "solvent",
        "structure_valid",
        "nmr_text_valid",
        "structure_nmr_match",
        "analysis_ready",
        "parseable_peak_count",
        "expected_visible_h",
        "observed_total_h",
        "adjusted_observed_total_h",
        "delta_visible_h",
        "parsed_peaks",
        "structure",
        "warnings",
        "errors",
    }
    missing = required_keys - body.keys()
    assert not missing, f"validate response missing keys: {missing}"
