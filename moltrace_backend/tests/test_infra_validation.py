"""Unit tests for data validation gates (infra.validation)."""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.infra.validation import (
    DataValidationError,
    assert_valid_spectrum_input,
    great_expectations_available,
    spectrum_expectation_suite,
    validate_spectrum_input,
    validate_with_great_expectations,
)


def _good_spectrum() -> dict:
    return {
        "nucleus": "1H",
        "field_mhz": 500.0,
        "ppm_axis": np.linspace(0.0, 10.0, 256).tolist(),
        "intensity": np.ones(256).tolist(),
    }


# --------------------------------------------------------------------------- #
# native gate -- happy path
# --------------------------------------------------------------------------- #
def test_valid_spectrum_passes() -> None:
    report = validate_spectrum_input(_good_spectrum())
    assert report.success
    assert report.failures == ()
    # raise-on-failure gate does not raise.
    assert_valid_spectrum_input(_good_spectrum())


# --------------------------------------------------------------------------- #
# native gate -- each violation fails loudly
# --------------------------------------------------------------------------- #
def test_missing_nucleus_fails() -> None:
    data = _good_spectrum()
    del data["nucleus"]
    report = validate_spectrum_input(data)
    assert not report.success
    assert any(f.check == "schema" for f in report.failures)


def test_unknown_nucleus_fails() -> None:
    data = _good_spectrum()
    data["nucleus"] = "42Z"
    report = validate_spectrum_input(data)
    assert any(f.check == "nucleus" for f in report.failures)


def test_field_out_of_range_fails() -> None:
    data = _good_spectrum()
    data["field_mhz"] = 9_999.0
    report = validate_spectrum_input(data)
    assert any(f.check == "field_range" for f in report.failures)


def test_field_non_numeric_fails() -> None:
    data = _good_spectrum()
    data["field_mhz"] = "fast"
    report = validate_spectrum_input(data)
    assert any(f.check == "field_range" for f in report.failures)


def test_length_mismatch_fails() -> None:
    data = _good_spectrum()
    data["intensity"] = data["intensity"][:-1]
    report = validate_spectrum_input(data)
    assert any(f.check == "length" for f in report.failures)


def test_nan_in_intensity_fails() -> None:
    data = _good_spectrum()
    intensity = list(data["intensity"])
    intensity[5] = float("nan")
    data["intensity"] = intensity
    report = validate_spectrum_input(data)
    assert any(f.check == "nan" for f in report.failures)


def test_ppm_out_of_range_fails() -> None:
    data = _good_spectrum()
    # 1H expected window is generous (-20..40); 500 ppm is clearly wrong units.
    data["ppm_axis"] = np.linspace(0.0, 500.0, 256).tolist()
    report = validate_spectrum_input(data)
    assert any(f.check == "ppm_range" for f in report.failures)


def test_empty_arrays_fail() -> None:
    data = _good_spectrum()
    data["ppm_axis"] = []
    data["intensity"] = []
    report = validate_spectrum_input(data)
    assert not report.success


def test_assert_raises_collects_all_failures() -> None:
    data = {"nucleus": "ZZ", "field_mhz": -1.0, "ppm_axis": [1.0], "intensity": [1.0, 2.0]}
    with pytest.raises(DataValidationError) as exc:
        assert_valid_spectrum_input(data)
    # nucleus + field_range + length all reported.
    checks = {f.check for f in exc.value.failures}
    assert {"nucleus", "field_range", "length"} <= checks


def test_13c_uses_wider_ppm_window() -> None:
    data = {
        "nucleus": "13C",
        "field_mhz": 125.0,
        "ppm_axis": np.linspace(0.0, 220.0, 128).tolist(),
        "intensity": np.ones(128).tolist(),
    }
    assert validate_spectrum_input(data).success


# --------------------------------------------------------------------------- #
# Great Expectations adapter
# --------------------------------------------------------------------------- #
def test_ge_suite_is_declarative_and_versionable() -> None:
    suite = spectrum_expectation_suite("1H")
    types = {s["expectation_type"] for s in suite}
    assert "expect_column_values_to_be_in_set" in types
    assert "expect_column_values_to_be_between" in types


def test_ge_adapter_raises_without_install() -> None:
    if great_expectations_available():
        pytest.skip("GE installed; cannot test the missing-dependency guard")
    with pytest.raises(RuntimeError):
        validate_with_great_expectations([{"ppm": 1.0}])


def test_ge_adapter_runs_when_present() -> None:
    gx = pytest.importorskip("great_expectations")
    pytest.importorskip("pandas")
    if not hasattr(gx, "from_pandas"):
        pytest.skip("legacy GE from_pandas API unavailable (GE >= 1.0)")
    rows = [
        {"ppm": 1.0, "intensity": 5.0, "nucleus": "1H", "field_mhz": 500.0},
        {"ppm": 7.2, "intensity": 9.0, "nucleus": "1H", "field_mhz": 500.0},
    ]
    report = validate_with_great_expectations(rows, nucleus="1H")
    assert report.backend == "great_expectations"
    assert report.success
