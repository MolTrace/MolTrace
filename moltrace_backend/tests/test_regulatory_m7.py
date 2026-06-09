"""Tests for the ICH M7(R2) mutagenic-impurity classifier (Prompt 4).

Exercises every branch of the M7 decision tree (the dual-(Q)SAR rule, experimental
override, Cohort of Concern, staged TTC), the two internal-consistency invariants
required by the spec (a (Q)SAR-driven Class 5 is negative from both in-silico
systems; a Class 1 has experimental carcinogenicity data), the structural-alert
screen, and fail-loud input validation. The M7 decision logic is deterministic, so
these assertions pin the regulated behaviour exactly.

The structural-alert set is a curated subset and the worked classes below are the
unambiguous textbook cases; the official ICH M7(R2) Q&A worked examples should be
added as pinned cases and verified by a qualified toxicologist before filing use.
"""

from __future__ import annotations

import itertools

import pytest

from moltrace.regulatory.impurities import classify_m7, m7_rule_set
from moltrace.regulatory.infra.validation import DataValidationError

# Representative structures.
ETHANOL = "CCO"
HEXANE = "CCCCCC"
ANILINE = "Nc1ccccc1"  # aromatic amine alert
NITROBENZENE = "O=[N+]([O-])c1ccccc1"  # aromatic nitro alert
EMS = "CCOS(=O)(=O)C"  # ethyl methanesulfonate - sulfonate ester alert
ETHYLENE_OXIDE = "C1CO1"  # epoxide alert
NDMA = "CN(C)N=O"  # N-nitrosodimethylamine - Cohort of Concern
AZOXYMETHANE = "C/N=[N+](\\[O-])C"  # alkyl-azoxy - Cohort of Concern
COUMARIN = "O=c1ccc2ccccc2o1"  # must NOT be a false CoC


# --------------------------------------------------------------------------- #
# Dual (Q)SAR rule
# --------------------------------------------------------------------------- #
def test_both_negative_qsar_is_class5():
    c = classify_m7(ANILINE, in_silico_result_expert="negative", in_silico_result_statistical="negative")
    assert c.m7_class == 5
    assert c.in_silico_concordance == "concordant_negative"
    assert c.ttc_ug_per_day is None


@pytest.mark.parametrize(
    "expert, statistical", [("positive", "negative"), ("negative", "positive"), ("positive", "positive")]
)
def test_either_positive_qsar_is_class3(expert, statistical):
    c = classify_m7(ANILINE, in_silico_result_expert=expert, in_silico_result_statistical=statistical)
    assert c.m7_class == 3
    assert c.ttc_ug_per_day == 10.0  # default duration 120 months -> >1-10 yr band


def test_discordant_requires_expert_review():
    c = classify_m7(ANILINE, in_silico_result_expert="positive", in_silico_result_statistical="negative")
    assert c.in_silico_concordance == "discordant"
    assert c.expert_review_required is True
    assert c.m7_class == 3


def test_concordant_results_do_not_force_expert_review():
    c = classify_m7(ANILINE, in_silico_result_expert="positive", in_silico_result_statistical="positive")
    assert c.expert_review_required is False


# --------------------------------------------------------------------------- #
# Experimental data overrides in silico
# --------------------------------------------------------------------------- #
def test_experimental_ames_positive_is_class2():
    c = classify_m7(ANILINE, experimental_ames="positive")
    assert c.m7_class == 2
    assert c.data_basis == "experimental_ames"
    assert c.ttc_ug_per_day == 10.0


def test_experimental_carcinogen_positive_is_class1():
    c = classify_m7(EMS, experimental_carcinogen="positive")
    assert c.m7_class == 1
    assert c.ttc_ug_per_day is None  # compound-specific AI, not TTC
    assert "acceptable intake" in c.regulatory_action_required.lower()


def test_negative_carcinogenicity_overrides_alerts_to_class5():
    c = classify_m7(
        ANILINE,
        experimental_carcinogen="negative",
        in_silico_result_expert="positive",
        in_silico_result_statistical="positive",
    )
    assert c.m7_class == 5


def test_negative_ames_overrides_alert_to_class5():
    c = classify_m7(ANILINE, experimental_ames="negative")
    assert c.m7_class == 5
    assert c.data_basis == "experimental_ames"


def test_experimental_overrides_qsar_negative():
    # in-silico both negative, but a positive Ames makes it Class 2.
    c = classify_m7(
        ANILINE,
        in_silico_result_expert="negative",
        in_silico_result_statistical="negative",
        experimental_ames="positive",
    )
    assert c.m7_class == 2


# --------------------------------------------------------------------------- #
# Cohort of Concern
# --------------------------------------------------------------------------- #
def test_coc_nitrosamine_no_data_is_class2_compound_specific():
    c = classify_m7(NDMA)
    assert c.coc_flag is True
    assert "N-nitroso" in c.coc_categories
    assert c.m7_class == 2
    assert c.ttc_ug_per_day is None  # TTC not applicable to a CoC compound
    assert c.expert_review_required is True
    assert "acceptable intake" in c.regulatory_action_required.lower()


def test_coc_nitrosamine_with_carcinogenicity_is_class1():
    c = classify_m7(NDMA, experimental_carcinogen="positive")
    assert c.coc_flag is True
    assert c.m7_class == 1
    assert c.ttc_ug_per_day is None


def test_coc_not_cleared_by_negative_ames():
    # A negative bacterial assay does not clear a Cohort-of-Concern compound.
    c = classify_m7(NDMA, experimental_ames="negative")
    assert c.coc_flag is True
    assert c.m7_class == 2


def test_coc_cleared_only_by_negative_carcinogenicity():
    c = classify_m7(NDMA, experimental_carcinogen="negative")
    assert c.m7_class == 5  # definitive negative carcinogenicity study overrides


def test_coc_azoxy_detected():
    c = classify_m7(AZOXYMETHANE)
    assert c.coc_flag is True
    assert "alkyl-azoxy" in c.coc_categories
    assert "alkyl-azoxy" in c.structural_alerts


def test_coumarin_is_not_a_false_cohort_of_concern():
    c = classify_m7(COUMARIN)
    assert c.coc_flag is False


# --------------------------------------------------------------------------- #
# Staged (less-than-lifetime) TTC
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "duration_months, expected_ttc",
    [
        (0.5, 120.0),
        (1, 120.0),
        (1.5, 20.0),
        (6, 20.0),
        (12, 20.0),
        (24, 10.0),
        (120, 10.0),
        (121, 1.5),
        (240, 1.5),
    ],
)
def test_staged_ttc_bands(duration_months, expected_ttc):
    c = classify_m7(
        ANILINE,
        in_silico_result_expert="positive",
        in_silico_result_statistical="positive",
        duration_months=duration_months,
    )
    assert c.ttc_ug_per_day == expected_ttc


def test_default_duration_is_ten_year_band():
    c = classify_m7(ANILINE, in_silico_result_expert="positive", in_silico_result_statistical="positive")
    assert c.duration_months == 120.0
    assert c.ttc_ug_per_day == 10.0


# --------------------------------------------------------------------------- #
# Structural-alert screen + no-data fallbacks
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("smiles", [ETHANOL, HEXANE])
def test_nonalerting_no_data_is_class5(smiles):
    c = classify_m7(smiles)
    assert c.m7_class == 5
    assert c.structural_alerts == ()
    assert c.in_silico_concordance == "concordant_negative"


@pytest.mark.parametrize(
    "smiles, expected_alert",
    [
        (ANILINE, "aromatic amine"),
        (NITROBENZENE, "aromatic nitro"),
        (EMS, "alkyl/aryl sulfonate ester"),
        (ETHYLENE_OXIDE, "epoxide"),
        (NDMA, "nitrosamine (N-nitroso)"),
    ],
)
def test_structural_alert_screen(smiles, expected_alert):
    c = classify_m7(smiles)
    assert expected_alert in c.structural_alerts


@pytest.mark.parametrize("smiles", [ANILINE, NITROBENZENE, EMS, ETHYLENE_OXIDE])
def test_alerting_no_data_is_class3(smiles):
    # An alerting structure with no mutagenicity data -> Class 3 (TTC).
    c = classify_m7(smiles)
    assert c.m7_class == 3
    assert c.ttc_ug_per_day == 10.0


# --------------------------------------------------------------------------- #
# Internal-consistency invariants (required by the spec)
# --------------------------------------------------------------------------- #
def _input_matrix():
    calls = (None, "positive", "negative")
    smiles = (ETHANOL, ANILINE, EMS, NDMA)
    yield from itertools.product(smiles, calls, calls, calls, calls)


def test_class5_qsar_invariant_negative_from_both_in_silico():
    # Every (Q)SAR-driven Class 5 must be negative from both in-silico systems.
    for smi, ex, st, am, ca in _input_matrix():
        c = classify_m7(
            smi,
            in_silico_result_expert=ex,
            in_silico_result_statistical=st,
            experimental_ames=am,
            experimental_carcinogen=ca,
        )
        if c.m7_class == 5 and c.data_basis == "qsar":
            assert c.in_silico_concordance == "concordant_negative", (smi, ex, st, am, ca)


def test_class1_invariant_requires_experimental_carcinogenicity():
    # A Class 1 assignment must be backed by positive experimental carcinogenicity.
    for smi, ex, st, am, ca in _input_matrix():
        c = classify_m7(
            smi,
            in_silico_result_expert=ex,
            in_silico_result_statistical=st,
            experimental_ames=am,
            experimental_carcinogen=ca,
        )
        if c.m7_class == 1:
            assert ca == "positive", (smi, ex, st, am, ca)


def test_coc_never_uses_ttc():
    # No Cohort-of-Concern result may carry a TTC (always compound-specific AI).
    for smi in (NDMA, AZOXYMETHANE):
        for am, ca in itertools.product((None, "positive", "negative"), repeat=2):
            c = classify_m7(smi, experimental_ames=am, experimental_carcinogen=ca)
            if c.coc_flag and c.m7_class != 5:
                assert c.ttc_ug_per_day is None, (smi, am, ca)


# --------------------------------------------------------------------------- #
# Fail-loud input validation
# --------------------------------------------------------------------------- #
def test_invalid_smiles_fails_loud():
    with pytest.raises(DataValidationError):
        classify_m7("not_a_valid_smiles_string")
    with pytest.raises(DataValidationError):
        classify_m7("")


def test_invalid_call_value_fails_loud():
    with pytest.raises(DataValidationError):
        classify_m7(ETHANOL, experimental_ames="maybe")
    with pytest.raises(DataValidationError):
        classify_m7(ETHANOL, in_silico_result_expert="equivocal")


def test_invalid_duration_fails_loud():
    with pytest.raises(DataValidationError):
        classify_m7(ETHANOL, duration_months=0)
    with pytest.raises(DataValidationError):
        classify_m7(ETHANOL, duration_months=-5)


# --------------------------------------------------------------------------- #
# Traceability + determinism
# --------------------------------------------------------------------------- #
def test_classification_is_citation_tagged():
    c = classify_m7(NDMA)
    assert c.regulatory_basis.startswith("ICH M7(R2)")
    assert "Mueller" in c.class_scheme_reference
    assert c.rule_set_version.startswith("sha256:")
    assert "3.2.S.3.2" in c.reasoning
    assert c.class_definition.startswith("Class 2")


def test_reasoning_is_nonempty_narrative():
    c = classify_m7(ANILINE, in_silico_result_expert="positive", in_silico_result_statistical="negative")
    assert len(c.reasoning) > 80
    assert "discordant" in c.reasoning.lower()


def test_result_is_deterministic():
    assert classify_m7(NDMA).content_hash() == classify_m7(NDMA).content_hash()
    assert classify_m7(EMS, experimental_carcinogen="positive").content_hash() == (
        classify_m7(EMS, experimental_carcinogen="positive").content_hash()
    )
    assert m7_rule_set() == m7_rule_set()
