"""Data validation gates: every ingested dataset and inference input must pass
before it is allowed into the pipeline.  Violations fail loudly.

Checks enforced for a spectrum / inference input:

* **schema** -- required fields present and the right shape;
* **nucleus** -- a recognised NMR-active nucleus;
* **field range** -- spectrometer frequency physically plausible;
* **no NaNs / Infs** -- in the ppm axis or intensity vector;
* **value ranges** -- ppm values inside the nucleus's expected window, axis and
  intensity the same length, both non-empty.

The :func:`validate_spectrum_input` / :func:`assert_valid_spectrum_input`
native gate works with zero extra dependencies and is what the pipeline calls.
When the optional ``infra`` extra is installed, :func:`validate_with_great_expectations`
runs the *same* logical suite through Great Expectations over a pandas
DataFrame, so customers who standardise on GE get a GE validation result too.
Both paths raise :class:`DataValidationError` on failure.
"""

from __future__ import annotations

import importlib.util
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "ALLOWED_NUCLEI",
    "DataValidationError",
    "FIELD_MHZ_RANGE",
    "ValidationFailure",
    "ValidationReport",
    "assert_valid_spectrum_input",
    "great_expectations_available",
    "spectrum_expectation_suite",
    "validate_spectrum_input",
    "validate_with_great_expectations",
]

# Spin-1/2 and common quadrupolar NMR-active nuclei MolTrace ingests.
ALLOWED_NUCLEI = frozenset(
    {"1H", "2H", "13C", "15N", "19F", "31P", "11B", "29Si", "17O", "77Se", "119Sn", "195Pt"}
)

# 1H Larmor frequency bound: lowest benchtop instruments ~20-40 MHz, highest
# commercial magnets reach ~1.2 GHz. Anything outside is corrupt metadata.
FIELD_MHZ_RANGE = (1.0, 1300.0)

# Generous per-nucleus ppm windows -- wide enough to never reject real spectra
# (including over-wide sweep widths) but tight enough to catch garbage/units bugs.
_PPM_RANGE: dict[str, tuple[float, float]] = {
    "1H": (-20.0, 40.0),
    "2H": (-20.0, 40.0),
    "13C": (-50.0, 300.0),
    "15N": (-100.0, 1100.0),
    "19F": (-400.0, 200.0),
    "31P": (-400.0, 400.0),
    "11B": (-150.0, 150.0),
    "29Si": (-400.0, 150.0),
}
_DEFAULT_PPM_RANGE = (-2000.0, 2000.0)


@dataclass(frozen=True)
class ValidationFailure:
    check: str
    detail: str


class DataValidationError(ValueError):
    """Raised when data fails validation; carries every individual failure."""

    def __init__(self, failures: Sequence[ValidationFailure]) -> None:
        self.failures = list(failures)
        summary = "; ".join(f"{f.check}: {f.detail}" for f in self.failures)
        super().__init__(f"data validation failed ({len(self.failures)} issue(s)): {summary}")


@dataclass(frozen=True)
class ValidationReport:
    success: bool
    failures: tuple[ValidationFailure, ...] = field(default_factory=tuple)
    n_checks: int = 0
    backend: str = "native"

    def raise_for_status(self) -> None:
        if not self.success:
            raise DataValidationError(self.failures)


# --------------------------------------------------------------------------- #
# Native spectrum gate
# --------------------------------------------------------------------------- #
def _as_float_array(value: Any) -> np.ndarray | None:
    try:
        arr = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    return arr if arr.ndim == 1 else None


def validate_spectrum_input(
    data: Mapping[str, Any],
    *,
    ppm_field: str = "ppm_axis",
    intensity_field: str = "intensity",
) -> ValidationReport:
    """Validate a spectrum / inference input and return a full report.

    Collects *every* violation (rather than failing on the first) so a caller
    sees the complete picture.  Use :func:`assert_valid_spectrum_input` for the
    raise-on-failure gate.
    """

    failures: list[ValidationFailure] = []
    n_checks = 0

    # -- nucleus ----------------------------------------------------------- #
    n_checks += 1
    nucleus = data.get("nucleus")
    if nucleus is None:
        failures.append(ValidationFailure("schema", "missing required field 'nucleus'"))
    elif nucleus not in ALLOWED_NUCLEI:
        failures.append(
            ValidationFailure("nucleus", f"unrecognised nucleus {nucleus!r}")
        )

    # -- field_mhz --------------------------------------------------------- #
    n_checks += 1
    field_mhz = data.get("field_mhz")
    lo_f, hi_f = FIELD_MHZ_RANGE
    if field_mhz is None:
        failures.append(ValidationFailure("schema", "missing required field 'field_mhz'"))
    else:
        try:
            field_val = float(field_mhz)
        except (TypeError, ValueError):
            failures.append(
                ValidationFailure("field_range", f"field_mhz not numeric: {field_mhz!r}")
            )
        else:
            if not math.isfinite(field_val):
                failures.append(ValidationFailure("field_range", "field_mhz is not finite"))
            elif not (lo_f <= field_val <= hi_f):
                failures.append(
                    ValidationFailure(
                        "field_range", f"field_mhz {field_val} outside [{lo_f}, {hi_f}] MHz"
                    )
                )

    # -- arrays ------------------------------------------------------------ #
    n_checks += 1
    ppm = _as_float_array(data.get(ppm_field))
    intensity = _as_float_array(data.get(intensity_field))
    if ppm is None:
        failures.append(
            ValidationFailure("schema", f"'{ppm_field}' missing or not a 1-D numeric array")
        )
    if intensity is None:
        failures.append(
            ValidationFailure("schema", f"'{intensity_field}' missing or not a 1-D numeric array")
        )

    if ppm is not None and intensity is not None:
        n_checks += 1
        if ppm.size == 0 or intensity.size == 0:
            failures.append(ValidationFailure("schema", "ppm/intensity arrays are empty"))
        elif ppm.size != intensity.size:
            failures.append(
                ValidationFailure(
                    "length", f"ppm length {ppm.size} != intensity length {intensity.size}"
                )
            )
        else:
            n_checks += 1
            if not np.all(np.isfinite(ppm)):
                failures.append(ValidationFailure("nan", "ppm axis contains NaN/Inf"))
            if not np.all(np.isfinite(intensity)):
                failures.append(ValidationFailure("nan", "intensity contains NaN/Inf"))

            n_checks += 1
            lo_p, hi_p = _PPM_RANGE.get(str(nucleus), _DEFAULT_PPM_RANGE)
            if np.all(np.isfinite(ppm)) and (ppm.min() < lo_p or ppm.max() > hi_p):
                failures.append(
                    ValidationFailure(
                        "ppm_range",
                        f"ppm span [{ppm.min():.3f}, {ppm.max():.3f}] outside expected "
                        f"[{lo_p}, {hi_p}] for {nucleus}",
                    )
                )

    return ValidationReport(
        success=not failures,
        failures=tuple(failures),
        n_checks=n_checks,
        backend="native",
    )


def assert_valid_spectrum_input(data: Mapping[str, Any], **kwargs: Any) -> None:
    """Raise :class:`DataValidationError` if ``data`` is not a valid spectrum input."""

    validate_spectrum_input(data, **kwargs).raise_for_status()


# --------------------------------------------------------------------------- #
# Great Expectations adapter (optional)
# --------------------------------------------------------------------------- #
def great_expectations_available() -> bool:
    return (
        importlib.util.find_spec("great_expectations") is not None
        and importlib.util.find_spec("pandas") is not None
    )


def spectrum_expectation_suite(nucleus: str = "1H") -> list[dict[str, Any]]:
    """The declarative expectation suite mirroring the native spectrum gate.

    Returned as Great-Expectations-style ``{expectation_type, kwargs}`` dicts so
    it can be fed to :func:`validate_with_great_expectations` *or* inspected /
    versioned as documentation of the data contract.
    """

    lo_p, hi_p = _PPM_RANGE.get(nucleus, _DEFAULT_PPM_RANGE)
    lo_f, hi_f = FIELD_MHZ_RANGE
    return [
        {"expectation_type": "expect_column_to_exist", "kwargs": {"column": "ppm"}},
        {"expectation_type": "expect_column_to_exist", "kwargs": {"column": "intensity"}},
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "ppm"},
        },
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": "intensity"},
        },
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "ppm", "min_value": lo_p, "max_value": hi_p},
        },
        {
            "expectation_type": "expect_column_values_to_be_between",
            "kwargs": {"column": "field_mhz", "min_value": lo_f, "max_value": hi_f},
        },
        {
            "expectation_type": "expect_column_values_to_be_in_set",
            "kwargs": {"column": "nucleus", "value_set": sorted(ALLOWED_NUCLEI)},
        },
    ]


def validate_with_great_expectations(
    rows: Sequence[Mapping[str, Any]],
    suite: Sequence[Mapping[str, Any]] | None = None,
    *,
    nucleus: str = "1H",
) -> ValidationReport:
    """Validate tabular rows through Great Expectations; raises if GE is absent.

    ``rows`` is a list of per-peak records (each with ``ppm``, ``intensity``,
    ``nucleus``, ``field_mhz``).  Returns a :class:`ValidationReport` with
    ``backend="great_expectations"``.  Call :meth:`ValidationReport.raise_for_status`
    (or check ``.success``) to gate ingestion.
    """

    if not great_expectations_available():
        raise RuntimeError(
            "Great Expectations (and pandas) are not installed; install the "
            "optional infra extra (`pip install nmrcheck[infra]`) or use the "
            "native validate_spectrum_input gate."
        )

    import great_expectations as gx
    import pandas as pd

    if not hasattr(gx, "from_pandas"):  # pragma: no cover - GE >= 1.0 not pinned
        raise RuntimeError(
            "installed Great Expectations lacks the legacy from_pandas API; pin "
            "great-expectations<1.0 (the infra extra does this)."
        )

    suite = list(suite) if suite is not None else spectrum_expectation_suite(nucleus)
    frame = pd.DataFrame(list(rows))
    dataset = gx.from_pandas(frame)

    for spec in suite:
        method = getattr(dataset, spec["expectation_type"])
        method(**dict(spec.get("kwargs", {})))

    result = dataset.validate(result_format="BASIC")
    failures: list[ValidationFailure] = []
    for entry in result["results"]:
        if not entry["success"]:
            cfg = entry["expectation_config"]
            failures.append(ValidationFailure(cfg["expectation_type"], str(cfg.get("kwargs", {}))))

    return ValidationReport(
        success=bool(result["success"]),
        failures=tuple(failures),
        n_checks=len(suite),
        backend="great_expectations",
    )
