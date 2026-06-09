"""ICH Q3A(R2) / Q3B(R2) impurity threshold calculator (Prompt 1).

Computes the reporting, identification, and qualification thresholds for an
impurity from the maximum daily dose, per **ICH Q3A(R2)** (new drug *substances*)
and **ICH Q3B(R2)** (new drug *products*). The threshold values are factual
regulatory criteria implemented from the official guideline tables and cited; no
copyrighted guideline text is reproduced.

Deterministic-first: this is pure, auditable arithmetic over a content-versioned
rule-set — there is no model in the numeric path. Every threshold carries its
regulatory basis + table reference. Output is **decision-support**: a qualified
regulatory-affairs reviewer must verify each value against the official ICH source
and sign off before any use in a filing or release decision.

ICH Q3A(R2) — drug substances (Attachment 1, Thresholds):

* <= 2 g/day: reporting 0.05 %; identification 0.10 % or 1.0 mg/day (lower);
  qualification 0.15 % or 1.0 mg/day (lower).
* > 2 g/day: reporting 0.03 %; identification 0.05 %; qualification 0.05 %.

ICH Q3B(R2) — drug products (Attachment 1):

* Reporting: <= 1 g -> 0.1 % ; > 1 g -> 0.05 %.
* Identification: < 1 mg -> 1.0 % or 5 ug TDI ; 1-10 mg -> 0.5 % or 20 ug TDI ;
  > 10 mg-2 g -> 0.2 % or 2 mg TDI ; > 2 g -> 0.10 % (whichever is lower where a
  cap applies).
* Qualification: < 10 mg -> 1.0 % or 50 ug TDI ; 10-100 mg -> 0.5 % or 200 ug TDI ;
  > 100 mg-2 g -> 0.2 % or 3 mg TDI ; > 2 g -> 0.15 % (whichever is lower where a
  cap applies).

"Whichever is lower" is resolved to a single **effective %** given the daily dose:
an absolute cap (mg/day or ug/day total daily intake) is converted to a percentage
of the dose and the smaller of the percentage rule and the cap governs. The ICH
Q3A/Q3B thresholds are independent of the route of administration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.validation import assert_valid_dose
from moltrace.regulatory.infra.versioning import content_hash, rule_set_version

__all__ = [
    "GUIDANCE_Q3A",
    "GUIDANCE_Q3B",
    "ImpurityThresholds",
    "ThresholdValue",
    "calculate_q3ab_thresholds",
    "q3ab_rule_set",
]

GUIDANCE_Q3A = {
    "guideline": "ICH Q3A(R2)",
    "title": "Impurities in New Drug Substances",
    "table_reference": "ICH Q3A(R2) Attachment 1 (Thresholds)",
    "effective_year": "2006",
}
GUIDANCE_Q3B = {
    "guideline": "ICH Q3B(R2)",
    "title": "Impurities in New Drug Products",
    "table_reference": "ICH Q3B(R2) Attachment 1",
    "effective_year": "2006",
}

# Rule tuples are (percent_rule, absolute_cap, absolute_unit | None).
# absolute_unit: "mg_per_day" (mg total daily intake) | "ug_per_day" (ug TDI).
_Q3A_BANDS = {
    "<=2g": {
        "band": "maximum daily dose <= 2 g/day",
        "reporting": (0.05, None, None),
        "identification": (0.10, 1.0, "mg_per_day"),
        "qualification": (0.15, 1.0, "mg_per_day"),
    },
    ">2g": {
        "band": "maximum daily dose > 2 g/day",
        "reporting": (0.03, None, None),
        "identification": (0.05, None, None),
        "qualification": (0.05, None, None),
    },
}

# Q3B identification bands (indexed by _q3b_id_band); each: (band_label, rule).
_Q3B_ID_BANDS = [
    ("maximum daily dose < 1 mg", (1.0, 5.0, "ug_per_day")),
    ("maximum daily dose 1 mg to 10 mg", (0.5, 20.0, "ug_per_day")),
    ("maximum daily dose > 10 mg to 2 g", (0.2, 2.0, "mg_per_day")),
    ("maximum daily dose > 2 g", (0.10, None, None)),
]
_Q3B_QUAL_BANDS = [
    ("maximum daily dose < 10 mg", (1.0, 50.0, "ug_per_day")),
    ("maximum daily dose 10 mg to 100 mg", (0.5, 200.0, "ug_per_day")),
    ("maximum daily dose > 100 mg to 2 g", (0.2, 3.0, "mg_per_day")),
    ("maximum daily dose > 2 g", (0.15, None, None)),
]


@dataclass(frozen=True)
class ThresholdValue:
    """One ICH threshold resolved to an effective percentage for the given dose.

    The ICH rule is "``percent_rule`` % **or** an absolute cap, whichever is lower".
    ``effective_percent`` applies that rule for the supplied daily dose; when a cap
    is the binding (lower) limit, ``absolute_is_binding`` is True and
    ``absolute_cap`` / ``absolute_unit`` record it.
    """

    kind: str  # "reporting" | "identification" | "qualification"
    effective_percent: float
    percent_rule: float
    absolute_cap: float | None
    absolute_unit: str | None  # "mg_per_day" | "ug_per_day"
    absolute_is_binding: bool
    dose_band: str
    basis: str
    table_reference: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "effective_percent": self.effective_percent,
            "percent_rule": self.percent_rule,
            "absolute_cap": self.absolute_cap,
            "absolute_unit": self.absolute_unit,
            "absolute_is_binding": self.absolute_is_binding,
            "dose_band": self.dose_band,
            "basis": self.basis,
            "table_reference": self.table_reference,
        }


@dataclass(frozen=True)
class ImpurityThresholds:
    """The reporting / identification / qualification thresholds for one dose."""

    daily_dose_g: float
    substance_type: str  # "drug_substance" | "drug_product"
    route: str
    reporting_threshold: ThresholdValue
    identification_threshold: ThresholdValue
    qualification_threshold: ThresholdValue
    regulatory_basis: str
    table_reference: str
    guidance_effective_year: str
    rule_set_version: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "daily_dose_g": self.daily_dose_g,
            "substance_type": self.substance_type,
            "route": self.route,
            "reporting_threshold": self.reporting_threshold.as_dict(),
            "identification_threshold": self.identification_threshold.as_dict(),
            "qualification_threshold": self.qualification_threshold.as_dict(),
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "guidance_effective_year": self.guidance_effective_year,
            "rule_set_version": self.rule_set_version,
            "notes": list(self.notes),
        }

    def content_hash(self) -> str:
        """Deterministic ``sha256:<hex>`` content address of the full result."""

        return content_hash(self.as_dict())


def _cap_as_percent(cap_value: float, cap_unit: str, daily_dose_g: float) -> float:
    """Express an absolute daily-intake cap as a percentage of the daily dose."""

    if cap_unit == "mg_per_day":
        # cap_value mg / (daily_dose_g * 1000 mg) * 100
        return cap_value / (daily_dose_g * 10.0)
    if cap_unit == "ug_per_day":
        # cap_value ug = cap_value * 1e-6 g; as % of daily_dose_g
        return cap_value * 1e-4 / daily_dose_g
    raise ValueError(f"unknown absolute unit {cap_unit!r}")


def _resolve(
    kind: str,
    rule: tuple[float, float | None, str | None],
    *,
    daily_dose_g: float,
    dose_band: str,
    basis: str,
    table_reference: str,
) -> ThresholdValue:
    percent_rule, cap_value, cap_unit = rule
    if cap_value is None or cap_unit is None:
        return ThresholdValue(
            kind=kind,
            effective_percent=percent_rule,
            percent_rule=percent_rule,
            absolute_cap=None,
            absolute_unit=None,
            absolute_is_binding=False,
            dose_band=dose_band,
            basis=basis,
            table_reference=table_reference,
        )
    cap_pct = _cap_as_percent(cap_value, cap_unit, daily_dose_g)
    binding = cap_pct < percent_rule
    return ThresholdValue(
        kind=kind,
        effective_percent=min(percent_rule, cap_pct),
        percent_rule=percent_rule,
        absolute_cap=cap_value,
        absolute_unit=cap_unit,
        absolute_is_binding=binding,
        dose_band=dose_band,
        basis=basis,
        table_reference=table_reference,
    )


def _q3b_id_band(dose_mg: float) -> int:
    if dose_mg < 1.0:
        return 0
    if dose_mg <= 10.0:
        return 1
    if dose_mg <= 2000.0:
        return 2
    return 3


def _q3b_qual_band(dose_mg: float) -> int:
    if dose_mg < 10.0:
        return 0
    if dose_mg <= 100.0:
        return 1
    if dose_mg <= 2000.0:
        return 2
    return 3


def q3ab_rule_set() -> dict[str, Any]:
    """The encoded ICH Q3A(R2)/Q3B(R2) threshold tables — the auditable rule-set."""

    return {
        "q3a": {"guidance": GUIDANCE_Q3A, "bands": _Q3A_BANDS},
        "q3b": {
            "guidance": GUIDANCE_Q3B,
            "reporting": {"<=1g": 0.1, ">1g": 0.05},
            "identification_bands": _Q3B_ID_BANDS,
            "qualification_bands": _Q3B_QUAL_BANDS,
        },
    }


# Content address of the encoded rule-set; ties every result to this exact table set.
_RULE_SET_VERSION = rule_set_version(q3ab_rule_set())

_DECISION_SUPPORT_NOTE = (
    "Decision-support only: verify each threshold against the official ICH source "
    "and obtain qualified regulatory-affairs sign-off before any filing or release use."
)
_ROUTE_NOTE = "ICH Q3A/Q3B thresholds are independent of the route of administration."


def calculate_q3ab_thresholds(
    daily_dose_g: float,
    substance_type: str = "drug_substance",
    route: str = "oral",
) -> ImpurityThresholds:
    """Calculate ICH Q3A(R2)/Q3B(R2) reporting, identification, and qualification thresholds.

    ``substance_type`` selects the guideline: ``"drug_substance"`` -> ICH Q3A(R2),
    ``"drug_product"`` -> ICH Q3B(R2). ``route`` is validated and recorded but does
    not change the Q3A/Q3B thresholds (they are route-independent). The maximum
    daily dose is in grams; when the maximum daily dose is not established, the
    conservative convention is to pass ``2.0`` (the <= 2 g/day Q3A band).

    Returns an :class:`ImpurityThresholds` whose three thresholds are each resolved
    to an effective percentage (applying "whichever is lower" where the guideline
    pairs a percentage with an absolute cap), every value tagged with its regulatory
    basis + table reference and tied to the content-versioned rule-set.
    """

    assert_valid_dose(
        {"daily_dose_g": daily_dose_g, "substance_type": substance_type, "route": route}
    )
    dose = float(daily_dose_g)
    if not math.isfinite(dose) or dose <= 0.0:  # pragma: no cover - guarded by assert_valid_dose
        raise ValueError("daily_dose_g must be a positive, finite number of grams")

    if substance_type == "drug_substance":
        return _q3a(dose, route)
    return _q3b(dose, route)


def _q3a(daily_dose_g: float, route: str) -> ImpurityThresholds:
    band_key = "<=2g" if daily_dose_g <= 2.0 else ">2g"
    band = _Q3A_BANDS[band_key]
    basis = f"{GUIDANCE_Q3A['guideline']} ({band['band']})"
    table_ref = GUIDANCE_Q3A["table_reference"]
    return ImpurityThresholds(
        daily_dose_g=daily_dose_g,
        substance_type="drug_substance",
        route=route,
        reporting_threshold=_resolve(
            "reporting", band["reporting"], daily_dose_g=daily_dose_g,
            dose_band=band["band"], basis=basis, table_reference=table_ref,
        ),
        identification_threshold=_resolve(
            "identification", band["identification"], daily_dose_g=daily_dose_g,
            dose_band=band["band"], basis=basis, table_reference=table_ref,
        ),
        qualification_threshold=_resolve(
            "qualification", band["qualification"], daily_dose_g=daily_dose_g,
            dose_band=band["band"], basis=basis, table_reference=table_ref,
        ),
        regulatory_basis=f"{GUIDANCE_Q3A['guideline']}: {GUIDANCE_Q3A['title']}",
        table_reference=table_ref,
        guidance_effective_year=GUIDANCE_Q3A["effective_year"],
        rule_set_version=_RULE_SET_VERSION,
        notes=(_DECISION_SUPPORT_NOTE, _ROUTE_NOTE),
    )


def _q3b(daily_dose_g: float, route: str) -> ImpurityThresholds:
    dose_mg = daily_dose_g * 1000.0
    table_ref = GUIDANCE_Q3B["table_reference"]

    reporting_pct = 0.1 if daily_dose_g <= 1.0 else 0.05
    reporting_band = (
        "maximum daily dose <= 1 g" if daily_dose_g <= 1.0 else "maximum daily dose > 1 g"
    )
    reporting = ThresholdValue(
        kind="reporting",
        effective_percent=reporting_pct,
        percent_rule=reporting_pct,
        absolute_cap=None,
        absolute_unit=None,
        absolute_is_binding=False,
        dose_band=reporting_band,
        basis=f"{GUIDANCE_Q3B['guideline']} ({reporting_band})",
        table_reference=table_ref,
    )

    id_label, id_rule = _Q3B_ID_BANDS[_q3b_id_band(dose_mg)]
    qual_label, qual_rule = _Q3B_QUAL_BANDS[_q3b_qual_band(dose_mg)]
    return ImpurityThresholds(
        daily_dose_g=daily_dose_g,
        substance_type="drug_product",
        route=route,
        reporting_threshold=reporting,
        identification_threshold=_resolve(
            "identification", id_rule, daily_dose_g=daily_dose_g, dose_band=id_label,
            basis=f"{GUIDANCE_Q3B['guideline']} ({id_label})", table_reference=table_ref,
        ),
        qualification_threshold=_resolve(
            "qualification", qual_rule, daily_dose_g=daily_dose_g, dose_band=qual_label,
            basis=f"{GUIDANCE_Q3B['guideline']} ({qual_label})", table_reference=table_ref,
        ),
        regulatory_basis=f"{GUIDANCE_Q3B['guideline']}: {GUIDANCE_Q3B['title']}",
        table_reference=table_ref,
        guidance_effective_year=GUIDANCE_Q3B["effective_year"],
        rule_set_version=_RULE_SET_VERSION,
        notes=(_DECISION_SUPPORT_NOTE, _ROUTE_NOTE),
    )
