"""Prompt 6 — ICH Q6A specification builder.

Per-decision-tree tests + two representative end-to-end products (an immediate-release drug product
and a drug-substance API). Impurity limits are cross-checked against the validated P1-5 engines
(Q3A/B thresholds, ICH M7 TTC, FDA CPCA AI limit) so the spec rows are not hand-invented. These are
representative profiles exercising the Q6A decision logic, not transcriptions of specific ANDA files.
"""

from __future__ import annotations

from moltrace.regulatory.impurities import calculate_q3ab_thresholds, classify_cpca, classify_m7
from moltrace.regulatory.specifications import (
    BatchResult,
    ImpurityObservation,
    MethodValidation,
    SubstanceProfile,
    build_specification,
    process_capability_cpk,
)

_MV = MethodValidation(
    validated_methods=frozenset({"assay_hplc", "dissolution", "water_kf", "IR spectroscopy"})
)


def _spec(profile, batches=()):
    return build_specification(profile, list(batches), _MV)


# --------------------------------------------------------------------------- #
# Individual decision trees
# --------------------------------------------------------------------------- #
def test_appearance_and_identification_are_always_present() -> None:
    spec = _spec(
        SubstanceProfile(name="X", physical_form="white crystalline powder", colour="white")
    )
    appearance = spec.parameter("Appearance / Description")
    assert appearance is not None
    assert appearance.proposed_limit == "white crystalline powder, white"
    assert "Decision Tree #1" in appearance.justification
    ident = spec.parameter("Identification")
    assert ident is not None and "Decision Tree #2" in ident.justification


def test_assay_band_depends_on_substance_type() -> None:
    ds = _spec(SubstanceProfile(name="API", substance_type="drug_substance"))
    dp = _spec(SubstanceProfile(name="Tab", substance_type="drug_product"))
    assert ds.parameter("Assay").proposed_limit == "98.0% to 102.0%"
    assert dp.parameter("Assay").proposed_limit == "95.0% to 105.0%"


def test_ordinary_impurity_uses_q3ab_qualification_threshold() -> None:
    profile = SubstanceProfile(
        name="API",
        substance_type="drug_substance",
        max_daily_dose_g=1.0,
        impurities=(ImpurityObservation("Impurity A"),),  # no batch levels -> no Cpk tightening
    )
    qual = calculate_q3ab_thresholds(
        1.0, "drug_substance", "oral"
    ).qualification_threshold.effective_percent
    row = _spec(profile).parameter("Impurity: Impurity A")
    assert row is not None
    assert row.proposed_limit == f"NMT {qual:g}%"  # the validated engine value, not invented
    assert "qualification threshold" in row.justification


def test_genotoxic_impurity_uses_m7_ttc_safety_limit() -> None:
    profile = SubstanceProfile(
        name="API",
        max_daily_dose_g=1.0,
        impurities=(ImpurityObservation("EMS", structural_assignment="CCOS(=O)(=O)C"),),
    )
    m7 = classify_m7("CCOS(=O)(=O)C")
    expected_ppm = m7.ttc_ug_per_day / 1.0
    row = _spec(profile).parameter("Impurity: EMS (mutagenic)")
    assert row is not None
    assert row.proposed_limit == f"NMT {expected_ppm:.3g} ppm"
    assert f"Class {m7.m7_class}" in row.justification and "TTC" in row.justification


def test_cohort_of_concern_impurity_uses_cpca_ai_limit() -> None:
    profile = SubstanceProfile(
        name="API",
        max_daily_dose_g=1.0,
        impurities=(ImpurityObservation("NDMA", structural_assignment="CN(C)N=O"),),
    )
    cpca = classify_cpca("CN(C)N=O")
    expected_ppm = cpca.ai_limit_ng_per_day / 1.0 / 1000.0
    row = _spec(profile).parameter("Impurity: NDMA (Cohort of Concern)")
    assert row is not None
    assert row.proposed_limit == f"NMT {expected_ppm:.3g} ppm"
    assert "Cohort of Concern" in row.justification and "CPCA" in row.justification


def test_process_capability_tightens_the_limit() -> None:
    # Tight, well-centred batch data (Cpk > 1.33) -> limit tightened below the Q3A/B ceiling.
    profile = SubstanceProfile(
        name="API",
        max_daily_dose_g=1.0,
        impurities=(
            ImpurityObservation("Impurity B", batch_levels_percent=(0.04, 0.05, 0.045, 0.048)),
        ),
    )
    row = _spec(profile).parameter("Impurity: Impurity B")
    assert row is not None
    assert row.proposed_limit == "NMT 0.075%"  # observed max 0.05 x 1.5
    assert "Cpk" in row.justification


def test_dissolution_vs_disintegration_selection() -> None:
    ir = SubstanceProfile(name="Tab", substance_type="drug_product", is_solid_oral=True)
    spec_ir = _spec(ir)
    assert spec_ir.parameter("Dissolution") is not None
    assert spec_ir.parameter("Disintegration") is None

    rapid = SubstanceProfile(
        name="Tab",
        substance_type="drug_product",
        is_solid_oral=True,
        high_solubility=True,
        rapidly_dissolving=True,
    )
    spec_rapid = _spec(rapid)
    assert spec_rapid.parameter("Dissolution") is None
    assert spec_rapid.parameter("Disintegration") is not None


def test_water_content_only_for_hygroscopic_or_hydrate() -> None:
    dry = _spec(SubstanceProfile(name="API"))
    assert dry.parameter("Water content") is None
    hydrate = _spec(
        SubstanceProfile(name="API", is_hydrate=True),
        batches=[
            BatchResult("B1", water_content_percent=3.0),
            BatchResult("B2", water_content_percent=3.2),
        ],
    )
    water = hydrate.parameter("Water content")
    assert water is not None and water.proposed_limit.startswith("NMT")
    assert "Decision Tree #7" in water.justification


def test_process_capability_cpk_helper() -> None:
    assert process_capability_cpk([0.04, 0.05, 0.045], usl=0.2) is not None
    assert process_capability_cpk([0.05], usl=0.2) is None  # < 2 batches
    assert process_capability_cpk([0.05, 0.05, 0.05], usl=0.2) == float("inf")  # zero variance


# --------------------------------------------------------------------------- #
# Representative end-to-end products
# --------------------------------------------------------------------------- #
def test_immediate_release_drug_product_specification() -> None:
    profile = SubstanceProfile(
        name="Examplinib 250 mg tablets",
        substance_type="drug_product",
        dosage_form="immediate-release tablet",
        route="oral",
        max_daily_dose_g=0.5,
        is_solid_oral=True,
        physical_form="film-coated tablet",
        colour="white",
        impurities=(
            ImpurityObservation("Des-methyl examplinib", batch_levels_percent=(0.05, 0.06, 0.055)),
            ImpurityObservation("Ethyl methanesulfonate", structural_assignment="CCOS(=O)(=O)C"),
        ),
    )
    batches = [
        BatchResult(
            f"B{i}", assay_percent=a, dissolution_percent_30min=94.0, total_impurities_percent=0.4
        )
        for i, a in enumerate((99.4, 100.1, 98.9))
    ]
    spec = build_specification(profile, batches, _MV)
    names = {p.parameter for p in spec.parameters}
    assert {
        "Appearance / Description",
        "Identification",
        "Assay",
        "Dissolution",
        "Total impurities",
    } <= names
    assert spec.parameter("Assay").proposed_limit == "95.0% to 105.0%"
    assert (
        spec.parameter("Impurity: Ethyl methanesulfonate (mutagenic)") is not None
    )  # M7 safety limit
    assert spec.parameter("Disintegration") is None
    assert spec.metadata["guideline"] == "ICH Q6A"
    assert all(
        p.method_reference and p.justification for p in spec.parameters
    )  # every row complete


def test_drug_substance_api_specification() -> None:
    profile = SubstanceProfile(
        name="Examplinib hydrochloride monohydrate",
        substance_type="drug_substance",
        dosage_form="active pharmaceutical ingredient",
        route="oral",
        max_daily_dose_g=1.0,
        is_solid_oral=False,
        is_hydrate=True,
        physical_form="white crystalline solid",
        impurities=(
            ImpurityObservation("Impurity RC-A"),
            ImpurityObservation("N-nitrosamine impurity", structural_assignment="CN(C)N=O"),
        ),
    )
    batches = [
        BatchResult(f"B{i}", assay_percent=a, water_content_percent=3.1)
        for i, a in enumerate((99.8, 100.0, 99.6))
    ]
    spec = build_specification(profile, batches, _MV)
    assert spec.parameter("Assay").proposed_limit == "98.0% to 102.0%"
    assert spec.parameter("Water content") is not None
    assert spec.parameter("Dissolution") is None  # not a solid oral dosage form
    # the nitrosamine row uses the CPCA acceptable intake (Cohort of Concern)
    coc = spec.parameter("Impurity: N-nitrosamine impurity (Cohort of Concern)")
    assert coc is not None and "ppm" in coc.proposed_limit
    assert spec.parameter("Any unspecified impurity") is not None
