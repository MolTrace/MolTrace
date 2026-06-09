"""Fail-loud validation gates for every structured regulatory input (Prompt 19).

Every structured input — a compound record, a dose specification, an impurity list
handed over from SpectraCheck, and every regulatory-corpus document — must pass a
schema gate **before** it reaches a calculator or the retriever. Bad input fails
loudly with a complete list of violations, never silently.

Reuse-first: the failure model (:class:`ValidationFailure`, :class:`ValidationReport`,
:class:`DataValidationError`) and the optional Great Expectations adapter are the
tested spectroscopy Phase 0 implementations; this module adds the regulatory
schemas on top. The native path needs no extra dependencies; installing the
``infra`` extra upgrades structured-table checks to Great Expectations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from moltrace.spectroscopy.infra.validation import (
    DataValidationError,
    ValidationFailure,
    ValidationReport,
    great_expectations_available,
    validate_with_great_expectations,
)

__all__ = [
    "ALLOWED_IMPURITY_UNITS",
    "ALLOWED_ROUTES",
    "ALLOWED_SUBSTANCE_TYPES",
    "DataValidationError",
    "ValidationFailure",
    "ValidationReport",
    "assert_valid_compound_record",
    "assert_valid_corpus_document",
    "assert_valid_dose",
    "assert_valid_impurity_list",
    "great_expectations_available",
    "validate_compound_record",
    "validate_corpus_document",
    "validate_dose",
    "validate_impurity_list",
    "validate_with_great_expectations",
]

# Administration routes recognised across ICH Q3C/Q3D and the dose calculators.
ALLOWED_ROUTES = frozenset(
    {"oral", "parenteral", "inhalation", "cutaneous", "transcutaneous"}
)
ALLOWED_SUBSTANCE_TYPES = frozenset({"drug_substance", "drug_product"})
# Units an impurity level may be expressed in (the SpectraCheck handoff + filings).
ALLOWED_IMPURITY_UNITS = frozenset({"percent", "ppm", "mg_per_day", "ug_per_day", "ng_per_day"})


def _report(failures: Sequence[ValidationFailure], n_checks: int) -> ValidationReport:
    return ValidationReport(
        success=not failures, failures=tuple(failures), n_checks=n_checks, backend="native"
    )


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _parses_as_date(value: Any) -> bool:
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- #
# Compound record (a structure to assess)
# --------------------------------------------------------------------------- #
def validate_compound_record(data: Mapping[str, Any]) -> ValidationReport:
    """Validate a compound record: a non-empty SMILES, optional name / CAS."""

    failures: list[ValidationFailure] = []
    n = 1
    smiles = data.get("smiles")
    if not isinstance(smiles, str) or not smiles.strip():
        failures.append(ValidationFailure("schema", "missing or empty 'smiles' (str)"))
    for optional in ("name", "cas"):
        if optional in data and data[optional] is not None and not isinstance(data[optional], str):
            n += 1
            failures.append(ValidationFailure("schema", f"'{optional}' must be a string"))
    return _report(failures, n)


# --------------------------------------------------------------------------- #
# Dose specification (drives every threshold calculator)
# --------------------------------------------------------------------------- #
def validate_dose(data: Mapping[str, Any]) -> ValidationReport:
    """Validate a dose spec: positive finite daily dose, known substance type + route."""

    failures: list[ValidationFailure] = []
    n = 0

    n += 1
    dose = data.get("daily_dose_g")
    if dose is None:
        failures.append(ValidationFailure("schema", "missing required field 'daily_dose_g'"))
    elif not _is_finite_number(dose):
        failures.append(ValidationFailure("dose_range", f"daily_dose_g not finite: {dose!r}"))
    elif float(dose) <= 0.0:
        failures.append(ValidationFailure("dose_range", f"daily_dose_g must be > 0, got {dose}"))

    n += 1
    substance_type = data.get("substance_type", "drug_substance")
    if substance_type not in ALLOWED_SUBSTANCE_TYPES:
        failures.append(
            ValidationFailure(
                "substance_type", f"unknown substance_type {substance_type!r}"
            )
        )

    n += 1
    route = data.get("route", "oral")
    if route not in ALLOWED_ROUTES:
        failures.append(ValidationFailure("route", f"unknown route {route!r}"))

    return _report(failures, n)


# --------------------------------------------------------------------------- #
# Impurity list (the SpectraCheck handoff)
# --------------------------------------------------------------------------- #
def validate_impurity_list(data: Mapping[str, Any]) -> ValidationReport:
    """Validate the impurity list handed over from SpectraCheck.

    Expects ``{"impurities": [{"identifier": str, "level": float >= 0,
    "unit": <allowed>}, ...]}``. Each impurity must have a non-empty identifier, a
    finite non-negative level, and a recognised unit.
    """

    failures: list[ValidationFailure] = []
    n = 1
    impurities = data.get("impurities")
    if not isinstance(impurities, Sequence) or isinstance(impurities, (str, bytes)):
        failures.append(ValidationFailure("schema", "'impurities' must be a list"))
        return _report(failures, n)

    for i, imp in enumerate(impurities):
        if not isinstance(imp, Mapping):
            failures.append(ValidationFailure("schema", f"impurity[{i}] must be an object"))
            continue
        n += 1
        identifier = imp.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            failures.append(
                ValidationFailure("schema", f"impurity[{i}] missing non-empty 'identifier'")
            )
        n += 1
        level = imp.get("level")
        if not _is_finite_number(level):
            failures.append(
                ValidationFailure("level", f"impurity[{i}] 'level' not finite: {level!r}")
            )
        elif float(level) < 0.0:
            failures.append(
                ValidationFailure("level", f"impurity[{i}] 'level' must be >= 0, got {level}")
            )
        n += 1
        unit = imp.get("unit")
        if unit not in ALLOWED_IMPURITY_UNITS:
            failures.append(
                ValidationFailure("unit", f"impurity[{i}] unknown unit {unit!r}")
            )

    return _report(failures, n)


# --------------------------------------------------------------------------- #
# Corpus document (the regulatory-RAG corpus, Prompt 20)
# --------------------------------------------------------------------------- #
def validate_corpus_document(data: Mapping[str, Any]) -> ValidationReport:
    """Validate a regulatory-corpus document's required citation metadata.

    Every chunk must be citable + current: ``source``, ``document_id``, a parseable
    ``effective_date``, a ``licence``, a ``content_hash``, and non-empty ``text``.
    """

    failures: list[ValidationFailure] = []
    n = 0
    for field_name in ("source", "document_id", "licence"):
        n += 1
        value = data.get(field_name)
        if not isinstance(value, str) or not value.strip():
            failures.append(
                ValidationFailure("schema", f"missing or empty '{field_name}' (str)")
            )

    n += 1
    if not _parses_as_date(data.get("effective_date")):
        failures.append(
            ValidationFailure(
                "effective_date", f"unparseable effective_date {data.get('effective_date')!r}"
            )
        )

    n += 1
    content_hash_value = data.get("content_hash")
    if not isinstance(content_hash_value, str) or not content_hash_value.startswith("sha256:"):
        failures.append(
            ValidationFailure("content_hash", "missing 'content_hash' (expected 'sha256:...')")
        )

    n += 1
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        failures.append(ValidationFailure("schema", "corpus document has empty 'text'"))

    return _report(failures, n)


# --------------------------------------------------------------------------- #
# Raise-on-failure gates
# --------------------------------------------------------------------------- #
def assert_valid_compound_record(data: Mapping[str, Any]) -> None:
    validate_compound_record(data).raise_for_status()


def assert_valid_dose(data: Mapping[str, Any]) -> None:
    validate_dose(data).raise_for_status()


def assert_valid_impurity_list(data: Mapping[str, Any]) -> None:
    validate_impurity_list(data).raise_for_status()


def assert_valid_corpus_document(data: Mapping[str, Any]) -> None:
    validate_corpus_document(data).raise_for_status()
