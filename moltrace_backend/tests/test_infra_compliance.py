"""Unit tests for compliance document generators (infra.compliance)."""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.infra.compliance import (
    GAMP5_APPENDIX,
    build_ich_report_stub,
    render_gamp5_d11_template,
    render_ich_report_stub,
)
from moltrace.spectroscopy.infra.contract import build_spectracheck_contract


def _contract():
    return build_spectracheck_contract(
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=500.0,
        ppm_range=(0.0, 10.0),
        n_points=1024,
        peaks=[
            {"ppm": 1.2, "intensity": 50.0, "category": "compound"},
            {"ppm": 7.26, "intensity": 100.0, "category": "solvent"},
        ],
        integration={"value": 3.0, "method_used": "edited_sum"},
        fingerprint_hash="fp-xyz",
    )


# --------------------------------------------------------------------------- #
# GAMP 5 D11 template
# --------------------------------------------------------------------------- #
def test_gamp5_template_has_required_sections() -> None:
    doc = render_gamp5_d11_template(
        system_name="MolTrace SpectraCheck",
        system_version="0.39.0",
        intended_use="Automated NMR structure verification for GxP release testing.",
    )
    for heading in (
        "Computerised System Validation",
        "Intended Use",
        "GxP Risk Assessment",
        "Requirements Traceability Matrix",
        "Installation Qualification (IQ)",
        "Operational Qualification (OQ)",
        "Performance Qualification (PQ)",
        "21 CFR Part 11",
    ):
        assert heading in doc
    assert GAMP5_APPENDIX in doc


def test_gamp5_template_is_deterministic() -> None:
    kwargs = dict(
        system_name="MolTrace",
        system_version="1.0",
        intended_use="x",
    )
    assert render_gamp5_d11_template(**kwargs) == render_gamp5_d11_template(**kwargs)


def test_gamp5_template_fills_provided_requirements() -> None:
    doc = render_gamp5_d11_template(
        system_name="X",
        system_version="1",
        intended_use="y",
        requirements=[{"id": "URS-1", "urs": "Detect peaks", "status": "Pass"}],
    )
    assert "URS-1" in doc
    assert "Detect peaks" in doc


def test_gamp5_template_rejects_bad_category() -> None:
    with pytest.raises(ValueError):
        render_gamp5_d11_template(
            system_name="X", system_version="1", intended_use="y", gamp_software_category=2
        )


# --------------------------------------------------------------------------- #
# ICH report stub
# --------------------------------------------------------------------------- #
def test_ich_stub_embeds_contract_hash_and_counts() -> None:
    contract = _contract()
    stub = build_ich_report_stub(contract)
    assert stub["ich_guideline"] == "Q2(R2)"
    assert stub["evidence"]["contract_content_hash"] == contract.content_hash()
    assert stub["result_summary"]["peak_count"] == 2
    assert stub["result_summary"]["classification_summary"] == {"compound": 1, "solvent": 1}


def test_ich_stub_is_deterministic() -> None:
    assert build_ich_report_stub(_contract()) == build_ich_report_stub(_contract())


def test_ich_stub_renders_markdown() -> None:
    md = render_ich_report_stub(build_ich_report_stub(_contract()))
    assert "ICH Q2(R2) Report (Stub)" in md
    assert "Contract content hash" in md
    assert "sha256:" in md
