"""B2b slice 1: an observed impurity keeps an identity a regulatory engine can resolve.

The spectroscopy side identifies contaminants by chemical shift against the Fulmer tables, so it
has a NAME and never a structure. That rules out M7/CPCA, which take SMILES — but ICH Q3C resolves
by name, CAS, or SMILES, so residual solvents are reachable and nothing has to be fabricated.

Two invariants matter more than the mapping itself:

* the resolution never carries an AMOUNT, so it can never become a compliance verdict. Integration
  partitions a window on ``category != "compound"`` and lumps every contaminant together without
  consulting identity, so no measured level is attributable to a named impurity;
* an identity that cannot be resolved refuses and names the cause, rather than guessing a limit.
"""

from nmrcheck.peak_categorization import _impurity_match_for_peak
from nmrcheck.spectral_impurity_q3c import resolve_observed_impurity

# --- the dropped key ---------------------------------------------------------------------------


def test_categorisation_preserves_the_compound_name_not_only_the_label():
    """`match_h1_impurity_shifts` supplies `compound`; the per-peak dict used to drop it.

    The label ("ethyl acetate CH3CO") does not resolve against Q3C; the bare compound name does.
    Dropping the key is what made the whole seam impossible.
    """
    match = _impurity_match_for_peak(nucleus="1H", shift_ppm=2.05, solvent="CDCl3")

    assert match is not None
    assert match["label"] == "ethyl acetate CH3CO"
    assert match["compound"] == "ethyl acetate"


# --- resolution --------------------------------------------------------------------------------


def test_a_named_residual_solvent_resolves_to_its_ich_q3c_class_with_provenance():
    resolution = resolve_observed_impurity(nucleus="1H", shift_ppm=2.05, solvent="CDCl3")

    assert resolution.identity_status == "resolved"
    assert resolution.compound == "ethyl acetate"
    assert resolution.q3c_class_number == 3
    assert resolution.concentration_limit_ppm == 5000.0
    assert resolution.regulatory_basis is not None and "Q3C" in resolution.regulatory_basis
    assert resolution.rule_set_version is not None
    assert resolution.rule_set_version.startswith("sha256:")
    assert resolution.human_review_required is True


def test_a_substance_outside_the_encoded_q3c_subset_refuses_and_names_the_cause():
    """Grease is a real contaminant and not an ICH Q3C solvent. No limit may be invented."""
    resolution = resolve_observed_impurity(nucleus="1H", shift_ppm=0.86, solvent="CDCl3")

    assert resolution.compound == "grease"
    assert resolution.identity_status == "unresolved"
    assert resolution.unresolved_reason == "not_in_q3c_subset"
    assert resolution.concentration_limit_ppm is None
    assert resolution.q3c_class_number is None
    assert resolution.unresolved_detail is not None
    assert "grease" in resolution.unresolved_detail


def test_a_shift_matching_nothing_in_the_library_refuses_with_its_own_reason():
    resolution = resolve_observed_impurity(nucleus="1H", shift_ppm=42.0, solvent="CDCl3")

    assert resolution.identity_status == "unresolved"
    assert resolution.unresolved_reason == "no_library_match"
    assert resolution.compound is None
    assert resolution.concentration_limit_ppm is None


# --- the honesty invariant ---------------------------------------------------------------------


def test_a_resolution_never_carries_a_measured_amount_or_a_verdict():
    """The Q3C limit is a LIMIT, not a measurement, and nothing here may imply compliance.

    Integration attributes no amount to a named contaminant, so a pass/fail against the ppm limit
    cannot be formed. If this ever becomes possible, that is a deliberate change with its own
    evidence — not something a field name should quietly imply.
    """
    resolution = resolve_observed_impurity(nucleus="1H", shift_ppm=2.05, solvent="CDCl3")

    assert resolution.quantitation_available is False
    assert resolution.observed_level_ppm is None
    assert resolution.compliance_note is not None
    assert "not quantitated" in resolution.compliance_note.lower()
    # No pass/fail surface exists at all.
    assert not hasattr(resolution, "compliant")
    assert not hasattr(resolution, "passes")


def test_acetone_resolves_too_so_the_seam_is_not_a_single_lucky_case():
    resolution = resolve_observed_impurity(nucleus="1H", shift_ppm=2.17, solvent="CDCl3")

    assert resolution.compound == "acetone"
    assert resolution.identity_status == "resolved"
    assert resolution.q3c_class_number == 3
