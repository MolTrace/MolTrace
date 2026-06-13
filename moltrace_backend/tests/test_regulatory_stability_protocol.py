"""Prompt 11 — ICH Q1A(R2) stability protocol generator.

Validates climate-zone determination, the per-zone storage conditions and ICH timepoints, the
dosage-form attribute panels for the five required forms (oral tablet, oral capsule, injectable
solution, nasal spray, transdermal patch), the ICH Q1E statistical plan, and the Markdown / .docx
renderers. The authoritative WHO/ICH constants are asserted explicitly — including the corrections
to the prompt's simplified values (Zone III is 30 °C/35 % RH, not 30/65; intermediate timepoints are
0/6/9/12, not 0/6/12).
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.stability import (
    ClimateZone,
    ConditionType,
    StabilityProtocol,
    generate_stability_protocol,
)


def _conditions(protocol, ctype):
    return [c for c in protocol.storage_conditions if c.condition_type is ctype]


def _attr_names(protocol):
    return {a.name for a in protocol.attributes}


# --------------------------------------------------------------------------- #
# Climate-zone determination
# --------------------------------------------------------------------------- #
def test_ich_markets_are_zone_ii() -> None:
    for market in ("US", "EU", "Japan"):
        p = generate_stability_protocol("oral tablet", "oral", "HDPE bottle", "carton", [market])
        assert p.climate_zones == (ClimateZone.ZONE_II,)


def test_asean_is_zone_ivb_and_multi_market_unions_zones() -> None:
    p = generate_stability_protocol(
        "oral tablet", "oral", "HDPE bottle", "carton", ["US", "EU", "Japan", "ASEAN"]
    )
    # distinct zones, ordered by stringency: II then IVb
    assert p.climate_zones == (ClimateZone.ZONE_II, ClimateZone.ZONE_IVB)


def test_unknown_market_defaults_to_zone_ivb_with_warning() -> None:
    p = generate_stability_protocol("oral tablet", "oral", "blister", "carton", ["Atlantis"])
    assert p.climate_zones == (ClimateZone.ZONE_IVB,)
    assert any("Atlantis" in w and "IVb" in w for w in p.warnings)


def test_empty_markets_raises() -> None:
    with pytest.raises(ValueError):
        generate_stability_protocol("oral tablet", "oral", "blister", "carton", [])


# --------------------------------------------------------------------------- #
# Storage conditions — authoritative WHO/ICH values (with the prompt corrections)
# --------------------------------------------------------------------------- #
def test_long_term_conditions_per_zone_are_authoritative() -> None:
    expected = {
        "US": (ClimateZone.ZONE_II, 25.0, 60.0),
        "Gulf": (ClimateZone.ZONE_IVA, 30.0, 65.0),  # GCC = Zone IVa (WHO/SFDA), NOT hot-dry III
        "Iraq": (ClimateZone.ZONE_III, 30.0, 35.0),  # the documented hot-DRY exception: 30/35
        "ASEAN": (ClimateZone.ZONE_IVB, 30.0, 75.0),
    }
    for market, (zone, temp, rh) in expected.items():
        p = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", [market])
        lt = _conditions(p, ConditionType.LONG_TERM)
        assert len(lt) == 1
        assert lt[0].zone is zone
        assert (lt[0].temperature_c, lt[0].relative_humidity_percent) == (temp, rh)


def test_accelerated_is_40_75_for_all_zones() -> None:
    for market in ("US", "ASEAN", "Gulf"):
        p = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", [market])
        acc = _conditions(p, ConditionType.ACCELERATED)
        assert len(acc) == 1
        assert (acc[0].temperature_c, acc[0].relative_humidity_percent) == (40.0, 75.0)


def test_intermediate_present_only_for_zone_i_or_ii() -> None:
    zone_ii = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", ["US"])
    assert _conditions(zone_ii, ConditionType.INTERMEDIATE)  # Zone II -> intermediate present
    assert _conditions(zone_ii, ConditionType.INTERMEDIATE)[0].temperature_c == 30.0
    assert _conditions(zone_ii, ConditionType.INTERMEDIATE)[0].relative_humidity_percent == 65.0

    ivb_only = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", ["ASEAN"])
    assert _conditions(ivb_only, ConditionType.INTERMEDIATE) == []  # no Zone I/II -> none


def test_ich_timepoints() -> None:
    p = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", ["US", "ASEAN"])
    lt = _conditions(p, ConditionType.LONG_TERM)[0]
    inter = _conditions(p, ConditionType.INTERMEDIATE)[0]
    acc = _conditions(p, ConditionType.ACCELERATED)[0]
    assert lt.timepoints_months == (0, 3, 6, 9, 12, 18, 24, 36)
    assert inter.timepoints_months == (0, 6, 9, 12)  # ICH minimum of 4, NOT 0/6/12
    assert acc.timepoints_months == (0, 3, 6)


# --------------------------------------------------------------------------- #
# Attribute panels — the five required dosage forms (validation requirement)
# --------------------------------------------------------------------------- #
_UNIVERSAL = {
    "Appearance / description",
    "Assay (content of active)",
    "Degradation products (related substances)",
    "Water content",
}
_FIVE_FORMS = {
    ("oral tablet", "oral"): {"Dissolution", "Hardness", "Friability", "Disintegration"},
    ("oral capsule", "oral"): {
        "Dissolution",
        "Water activity",
        "Capsule shell integrity / brittleness",
    },
    ("injectable solution", "parenteral"): {
        "Sterility",
        "Bacterial endotoxins",
        "pH",
        "Particulate matter (sub-visible)",
        "Osmolality",
    },
    ("nasal spray", "nasal"): {
        "Spray pattern",
        "Droplet / particle size distribution",
        "Delivered-dose (shot-weight) uniformity",
        "Plume geometry",
    },
    ("transdermal patch", "transdermal"): {
        "In-vitro drug-release rate",
        "Adhesion / peel / tack",
        "Cold flow",
    },
}


@pytest.mark.parametrize(("form_route", "signature"), list(_FIVE_FORMS.items()))
def test_attribute_panels_for_five_dosage_forms(form_route, signature) -> None:
    dosage_form, route = form_route
    p = generate_stability_protocol(dosage_form, route, "primary", "secondary", ["US"])
    names = _attr_names(p)
    assert _UNIVERSAL <= names, f"{dosage_form}: missing universal attributes"
    assert signature <= names, f"{dosage_form}: missing {signature - names}"


def test_only_sterile_routes_carry_sterility() -> None:
    tablet = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", ["US"])
    assert "Sterility" not in _attr_names(tablet)
    nasal = generate_stability_protocol("nasal spray", "nasal", "bottle", "carton", ["US"])
    assert "Sterility" not in _attr_names(nasal)  # nasal is not a sterile route
    injectable = generate_stability_protocol("injectable solution", "iv", "vial", "carton", ["US"])
    assert "Sterility" in _attr_names(injectable)


def test_sterile_route_adds_sterility_even_for_a_plain_solution() -> None:
    # A "solution" (not the injectable keyword) given a parenteral route still gets sterility.
    p = generate_stability_protocol("solution", "parenteral", "vial", "carton", ["US"])
    assert {"Sterility", "Bacterial endotoxins"} <= _attr_names(p)


def test_unknown_dosage_form_warns_but_keeps_universal_attributes() -> None:
    p = generate_stability_protocol("medicated chewing gum", "oral", "blister", "carton", ["US"])
    assert _UNIVERSAL <= _attr_names(p)
    assert any("medicated chewing gum" in w for w in p.warnings)


# --------------------------------------------------------------------------- #
# Statistical plan + structure
# --------------------------------------------------------------------------- #
def test_statistical_plan_is_q1e_regression() -> None:
    p = generate_stability_protocol("oral tablet", "oral", "bottle", "carton", ["US"])
    assert "ICH Q1E" in p.statistical_plan.references
    assert "regression" in p.statistical_plan.method.lower()
    assert "confidence" in p.statistical_plan.shelf_life_rule.lower()
    assert p.n_primary_batches == 3
    assert p.guideline == "ICH Q1A(R2)"
    assert p.human_review_required is True


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def test_markdown_and_dict_render() -> None:
    p = generate_stability_protocol(
        "injectable solution", "iv", "Type I glass vial", "carton", ["US", "EU", "ASEAN"]
    )
    md = p.as_markdown()
    for heading in (
        "Stability Protocol — ICH Q1A(R2)",
        "Storage conditions & testing timepoints",
        "Attributes to test",
        "Statistical analysis plan (ICH Q1E)",
        "QA review & approval",
    ):
        assert heading in md, heading
    assert "25 °C / 60 % RH" in md and "30 °C / 75 % RH" in md and "40 °C / 75 % RH" in md
    payload = p.as_dict()
    assert payload["guideline"] == "ICH Q1A(R2)"
    assert payload["climate_zones"] == ["II", "IVb"]
    assert any(c["type"] == "accelerated" for c in payload["storage_conditions"])
    assert payload["n_primary_batches"] == 3


def test_to_docx_renders_a_readable_document(tmp_path) -> None:
    docx = pytest.importorskip("docx")  # optional extra; skipped if not installed
    p = generate_stability_protocol("oral tablet", "oral", "HDPE bottle", "carton", ["US", "ASEAN"])
    out = p.to_docx(tmp_path / "stability_protocol.docx")
    assert out.exists() and out.stat().st_size > 0
    reopened = docx.Document(str(out))
    text = "\n".join(para.text for para in reopened.paragraphs)
    assert "Stability Protocol" in text
    assert "Statistical analysis plan (ICH Q1E)" in text
    assert isinstance(p, StabilityProtocol)
