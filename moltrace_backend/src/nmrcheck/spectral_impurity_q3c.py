"""Spectrum -> ICH Q3C bridge: give an observed contaminant its regulatory identity, or refuse.

This is the first slice of the SpectraCheck -> Regentry provenance seam. It answers exactly one
question — *what does the guidance say about the substance this peak was assigned to?* — and is
deliberately narrow about what it will not answer.

**Why only Q3C.** The spectroscopy side identifies contaminants by chemical shift against the
Fulmer tables, so an assignment carries a NAME and never a structure. ``classify_m7`` and
``classify_cpca`` take a SMILES as their first argument, and no structure field exists anywhere in
the impurity or solvent shift libraries, so mutagenicity and nitrosamine classification are simply
not reachable from a peak — and inventing a structure to reach them would be fabricating the
evidence a regulated determination rests on. ``classify_solvent`` resolves by name, CAS, or SMILES,
so residual solvents are reachable honestly. 22 of the 36 contaminant names in the production
library resolve against the encoded ICH Q3C(R8) subset by name alone.

**Why there is no verdict.** A Q3C concentration limit is in ppm; integration attributes no amount
to a *named* contaminant — ``integrate()`` partitions a window on ``category != "compound"`` and
lumps every contaminant into one excluded set without ever consulting identity. So this module can
report the applicable limit and its citation, and it must not report compliance. That is why
``quantitation_available`` is a field rather than an omission: the absence is stated, not implied.

Pure: no ORM, no HTTP, no clock, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from moltrace.regulatory.impurities import classify_solvent

from .peak_categorization import _impurity_match_for_peak

Nucleus = Literal["1H", "13C"]

# Closed vocabulary. A refusal names which of the three ways identity was lost, so the caller can
# tell "nothing was there" from "we know what it is and the guidance does not cover it".
UnresolvedReason = Literal[
    "no_library_match",  # no contaminant in the shift table matched this shift in this solvent
    "label_only_no_compound",  # the library row carries a display label but no compound name
    "not_in_q3c_subset",  # the compound is named but is not in the encoded ICH Q3C(R8) subset
]

_NOT_QUANTITATED = (
    "Identity only: this signal was assigned to a substance, but no amount is attributable to it. "
    "Integration excludes contaminants as a group without attributing a level to any one of them, "
    "so the limit below is not quantitated and no compliance conclusion may be drawn from it. "
    "Human review is required."
)


@dataclass(frozen=True)
class SpectralImpurityResolution:
    """One observed contaminant, with its ICH Q3C identity resolved or its refusal named."""

    observed_shift_ppm: float
    solvent: str | None
    observed_label: str | None  # "ethyl acetate CH3CO" — display only
    compound: str | None  # "ethyl acetate" — the regulatory-resolvable identity
    expected_ppm: float | None
    delta_ppm: float | None
    match_kind: str | None

    identity_status: Literal["resolved", "unresolved"]
    unresolved_reason: UnresolvedReason | None
    unresolved_detail: str | None

    q3c_class_number: int | None
    q3c_class_description: str | None
    concentration_limit_ppm: float | None
    pde_mg_per_day: float | None
    regulatory_basis: str | None
    table_reference: str | None
    rule_set_version: str | None

    # Stated, never implied: no measured level exists for a named contaminant today.
    quantitation_available: bool = False
    observed_level_ppm: float | None = None
    compliance_note: str = _NOT_QUANTITATED
    human_review_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_shift_ppm": self.observed_shift_ppm,
            "solvent": self.solvent,
            "observed_label": self.observed_label,
            "compound": self.compound,
            "expected_ppm": self.expected_ppm,
            "delta_ppm": self.delta_ppm,
            "match_kind": self.match_kind,
            "identity_status": self.identity_status,
            "unresolved_reason": self.unresolved_reason,
            "unresolved_detail": self.unresolved_detail,
            "q3c_class_number": self.q3c_class_number,
            "q3c_class_description": self.q3c_class_description,
            "concentration_limit_ppm": self.concentration_limit_ppm,
            "pde_mg_per_day": self.pde_mg_per_day,
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "rule_set_version": self.rule_set_version,
            "quantitation_available": self.quantitation_available,
            "observed_level_ppm": self.observed_level_ppm,
            "compliance_note": self.compliance_note,
            "human_review_required": self.human_review_required,
        }


def _unresolved(
    *,
    shift_ppm: float,
    solvent: str | None,
    label: str | None = None,
    compound: str | None = None,
    expected_ppm: float | None = None,
    delta_ppm: float | None = None,
    match_kind: str | None = None,
    reason: UnresolvedReason,
    detail: str,
) -> SpectralImpurityResolution:
    return SpectralImpurityResolution(
        observed_shift_ppm=shift_ppm,
        solvent=solvent,
        observed_label=label,
        compound=compound,
        expected_ppm=expected_ppm,
        delta_ppm=delta_ppm,
        match_kind=match_kind,
        identity_status="unresolved",
        unresolved_reason=reason,
        unresolved_detail=detail,
        q3c_class_number=None,
        q3c_class_description=None,
        concentration_limit_ppm=None,
        pde_mg_per_day=None,
        regulatory_basis=None,
        table_reference=None,
        rule_set_version=None,
    )


def resolve_observed_impurity(
    *, nucleus: Nucleus, shift_ppm: float, solvent: str | None, route: str = "oral"
) -> SpectralImpurityResolution:
    """Resolve the substance a peak was assigned to against ICH Q3C, or refuse and name why.

    Never guesses a limit: an unrecognised substance comes back ``unresolved`` with the reason,
    mirroring ``classify_solvent``'s own ``matched = False`` contract.
    """
    match = _impurity_match_for_peak(nucleus=nucleus, shift_ppm=shift_ppm, solvent=solvent)
    if match is None:
        return _unresolved(
            shift_ppm=shift_ppm,
            solvent=solvent,
            reason="no_library_match",
            detail=(
                f"No contaminant in the reference shift table lies within tolerance of "
                f"{shift_ppm} ppm in {solvent or 'the reported solvent'}."
            ),
        )

    label = match.get("label")
    compound = match.get("compound")
    expected_ppm = match.get("expected_ppm")
    delta_ppm = match.get("delta_ppm")
    match_kind = match.get("kind")

    if not compound:
        return _unresolved(
            shift_ppm=shift_ppm,
            solvent=solvent,
            label=label,
            expected_ppm=expected_ppm,
            delta_ppm=delta_ppm,
            match_kind=match_kind,
            reason="label_only_no_compound",
            detail=(
                f"The matched library row carries the display label {label!r} but no compound "
                "name, so there is no identity to resolve against the guidance."
            ),
        )

    classification = classify_solvent(compound, route)
    if not classification.matched:
        return _unresolved(
            shift_ppm=shift_ppm,
            solvent=solvent,
            label=label,
            compound=compound,
            expected_ppm=expected_ppm,
            delta_ppm=delta_ppm,
            match_kind=match_kind,
            reason="not_in_q3c_subset",
            detail=(
                f"{compound!r} is not in the encoded ICH Q3C(R8) subset — it may be outside Q3C's "
                "scope entirely, or a solvent the encoded table does not carry. Verify against "
                "ICH Q3C(R8) before relying on any limit."
            ),
        )

    return SpectralImpurityResolution(
        observed_shift_ppm=shift_ppm,
        solvent=solvent,
        observed_label=label,
        compound=compound,
        expected_ppm=expected_ppm,
        delta_ppm=delta_ppm,
        match_kind=match_kind,
        identity_status="resolved",
        unresolved_reason=None,
        unresolved_detail=None,
        q3c_class_number=classification.class_number,
        q3c_class_description=classification.class_description,
        concentration_limit_ppm=classification.concentration_limit_ppm,
        pde_mg_per_day=classification.pde_mg_per_day,
        regulatory_basis=classification.regulatory_basis,
        table_reference=classification.table_reference,
        rule_set_version=classification.rule_set_version,
    )
