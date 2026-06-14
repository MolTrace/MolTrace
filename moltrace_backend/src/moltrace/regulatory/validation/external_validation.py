"""External validation sets (Prompt 21, Phase 7).

Reproduce published external reference limits exactly:
- FDA Nitrosamine (NDSRI) database — compounds with a known CPCA category + AI limit;
- EMA Nitrosamines Q&A worked examples (current revision);
- CTD Module 3 structural/content checks against the Prompt 17 gold-set reports.

The FULL datasets (200+ NDSRI compounds, the EMA Q&A current revision, 50 historical anonymised CTD
reports) are loaded from external manifests the regulated user supplies — this module is the
MECHANISM plus a built-in **validated subset** (compounds the engine unit tests already pin to
guideline ground truth). Regulatory ground truth is never fabricated here: an unverified compound is
omitted, not guessed. Every reproduced AI limit is a zero-tolerance
:class:`~moltrace.regulatory.infra.eval.CalculationCheck`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moltrace.regulatory.impurities import classify_cpca
from moltrace.regulatory.infra.eval import CalculationCheck

__all__ = [
    "EMA_QA_SUBSET",
    "NDSRI_FDA_SUBSET",
    "CTDValidationResult",
    "ExternalCompound",
    "ExternalValidationResult",
    "bundle_from_ctd_sections",
    "ctd_module3_content_issues",
    "ctd_module3_missing_sections",
    "load_external_manifest",
    "validate_compounds",
    "validate_ctd_module3",
    "validate_ema_qa",
    "validate_ndsri",
]

_TOLERANCE = 1e-9

# ICH/CTD M3 impurities + nitrosamine sections a submission-ready Module 3 bundle must carry.
CTD_MODULE3_REQUIRED_SECTIONS = (
    "3.2.S.3.2",  # impurities
    "3.2.P.5.5",  # characterisation of impurities (product)
)


@dataclass(frozen=True)
class ExternalCompound:
    """A reference compound with its published category + AI limit for a named authority."""

    name: str
    smiles: str
    expected_category: int
    expected_ai_limit_ng_per_day: float
    authority: str = "FDA"


@dataclass(frozen=True)
class ExternalValidationResult:
    """The outcome of reproducing an external reference set."""

    source: str
    n_compounds: int
    ai_limit_checks: tuple[CalculationCheck, ...]
    category_failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.category_failures and not any(c.is_error() for c in self.ai_limit_checks)


# Built-in validated subset (guideline-traceable, asserted by tests/test_regulatory_cpca.py):
# FDA CPCA Category 1 AI limit = 26.5 ng/day; Category 5 = 1500 ng/day.
# EMA overrides Category 1 to 18.0 ng/day.
NDSRI_FDA_SUBSET: tuple[ExternalCompound, ...] = (
    ExternalCompound("NDMA", "CN(C)N=O", 1, 26.5, "FDA"),
    ExternalCompound("NDEA", "CCN(CC)N=O", 1, 26.5, "FDA"),
    ExternalCompound("NMBzA", "O=NN(C)Cc1ccccc1", 1, 26.5, "FDA"),
    ExternalCompound("di-tert-butyl nitrosamine", "O=NN(C(C)(C)C)C(C)(C)C", 5, 1500.0, "FDA"),
)
EMA_QA_SUBSET: tuple[ExternalCompound, ...] = (
    ExternalCompound("NDMA", "CN(C)N=O", 1, 18.0, "EMA"),
    ExternalCompound("NDEA", "CCN(CC)N=O", 1, 18.0, "EMA"),
    ExternalCompound("NMBzA", "O=NN(C)Cc1ccccc1", 1, 18.0, "EMA"),
    ExternalCompound("di-tert-butyl nitrosamine", "O=NN(C(C)(C)C)C(C)(C)C", 5, 1500.0, "EMA"),
)


def validate_compounds(
    compounds: Sequence[ExternalCompound], source: str
) -> ExternalValidationResult:
    """Assert MolTrace reproduces each compound's category + AI limit exactly."""

    ai_checks: list[CalculationCheck] = []
    category_failures: list[str] = []
    for c in compounds:
        result = classify_cpca(c.smiles, authority=c.authority)
        if result.category != c.expected_category:
            category_failures.append(
                f"{source}:{c.name}: category {result.category} != expected {c.expected_category}"
            )
        ai_checks.append(
            CalculationCheck(
                f"{source}:{c.name}:ai_limit",
                result.ai_limit_ng_per_day,
                c.expected_ai_limit_ng_per_day,
                _TOLERANCE,
            )
        )
    return ExternalValidationResult(
        source=source,
        n_compounds=len(compounds),
        ai_limit_checks=tuple(ai_checks),
        category_failures=tuple(category_failures),
    )


def validate_ndsri(extra: Sequence[ExternalCompound] = ()) -> ExternalValidationResult:
    """Reproduce the FDA NDSRI set (built-in validated subset + any supplied compounds)."""

    return validate_compounds((*NDSRI_FDA_SUBSET, *extra), "FDA NDSRI")


def validate_ema_qa(extra: Sequence[ExternalCompound] = ()) -> ExternalValidationResult:
    """Reproduce the EMA Q&A set (built-in validated subset + any supplied compounds)."""

    return validate_compounds((*EMA_QA_SUBSET, *extra), "EMA Q&A")


def load_external_manifest(path: str | Path, *, authority: str) -> list[ExternalCompound]:
    """Load a full external reference set (e.g. the 200+ NDSRI database) from a JSON manifest.

    Manifest: a JSON list of {name, smiles, expected_category, expected_ai_limit_ng_per_day}. The
    regulated user supplies the real dataset; this never invents one.
    """

    with Path(path).open() as fh:
        records = json.load(fh)
    return [
        ExternalCompound(
            name=str(r["name"]),
            smiles=str(r["smiles"]),
            expected_category=int(r["expected_category"]),
            expected_ai_limit_ng_per_day=float(r["expected_ai_limit_ng_per_day"]),
            authority=str(r.get("authority", authority)),
        )
        for r in records
    ]


def ctd_module3_missing_sections(
    bundle: Mapping[str, Any], *, required: Sequence[str] = CTD_MODULE3_REQUIRED_SECTIONS
) -> list[str]:
    """Structural check: which required CTD Module 3 sections are absent from a bundle.

    Run over each of the 50 anonymised CTD reports (the Prompt 17 gold set) to assert the generated
    Module 3 structure matches. A required id is satisfied when it is contained in any present
    section key (so a compound section number like ``"3.2.P.5.5 / 3.2.P.5.6"`` satisfies
    ``"3.2.P.5.5"``). Returns missing section ids (empty = valid).
    """

    present = list(bundle.get("sections", {}) or {})
    return sorted(req for req in required if not any(req in key for key in present))


def ctd_module3_content_issues(
    bundle: Mapping[str, Any], *, required: Sequence[str] = CTD_MODULE3_REQUIRED_SECTIONS
) -> list[str]:
    """Content check: each present required section must carry impurity rows AND traceable sources.

    A submission-ready Module 3 impurities section is not just a heading — it must contain at least
    one impurity table row and at least one cited SourceRef (so every number is traceable). Returns
    a list of content issues (empty = valid).
    """

    sections = bundle.get("sections", {}) or {}
    issues: list[str] = []
    for req in required:
        for key, meta in sections.items():
            if req not in key:
                continue
            meta = meta or {}
            if int(meta.get("n_table_rows", 0)) <= 0:
                issues.append(f"{key}: no impurity table rows")
            if int(meta.get("n_sources", 0)) <= 0:
                issues.append(f"{key}: no traceable sources")
    return issues


def bundle_from_ctd_sections(sections: Sequence[Any]) -> dict[str, Any]:
    """Build the ``{"sections": {...}}`` bundle (section id -> content metadata) from CTDSections.

    Each section contributes its impurity-table row count and cited-source count, so the structural
    AND content checks can run over the real Prompt 8 generator output (or a historical report).
    """

    out: dict[str, Any] = {}
    for section in sections:
        d = section.as_dict()
        rows = sum(len((sub.get("table") or {}).get("rows", ())) for sub in d["subsections"])
        out[d["section_number"]] = {
            "title": d["title"],
            "n_table_rows": rows,
            "n_sources": len(d.get("sources", ())),
        }
    return {"sections": out}


def _reference_module3_bundle() -> dict[str, Any]:
    """A real CTD 3.2.S.3.2 bundle generated by the Prompt 8 engine — the built-in CTD self-check.

    Drives the deterministic impurity engines through the actual generator so the launch gate proves
    the Module 3 structure + content contract end to end (the 50 historical reports are supplied by
    the regulated user via :func:`validate_ctd_module3`).
    """

    from moltrace.regulatory.ctd import (
        ImpurityEntry,
        ImpurityOrigin,
        ImpurityProfile,
        generate_3s3_impurities_drug_substance,
    )
    from moltrace.regulatory.impurities import calculate_q3ab_thresholds
    from moltrace.regulatory.specifications.q6a_builder import SubstanceProfile

    q3ab = calculate_q3ab_thresholds(1.0, "drug_substance", "oral")
    substance = SubstanceProfile(
        name="Reference Substance", substance_type="drug_substance", max_daily_dose_g=1.0
    )
    profile = ImpurityProfile(
        "Reference Substance",
        impurities=(
            ImpurityEntry(
                "Process impurity A",
                origin=ImpurityOrigin.PROCESS_RELATED,
                observed_levels_percent=(0.04,),
            ),
            ImpurityEntry(
                "Mutagenic alert impurity",
                structure_smiles="CCOS(=O)(=O)C",  # ethyl methanesulfonate (ICH M7)
                origin=ImpurityOrigin.PROCESS_RELATED,
                observed_levels_percent=(0.0005,),
            ),
        ),
    )
    section = generate_3s3_impurities_drug_substance(substance, profile, q3ab)
    return bundle_from_ctd_sections([section])


@dataclass(frozen=True)
class CTDValidationResult:
    """The outcome of the CTD Module 3 structural + content validation over a set of reports."""

    source: str
    n_reports: int
    structural_failures: tuple[str, ...]
    content_failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.structural_failures and not self.content_failures

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "n_reports": self.n_reports,
            "structural_failures": list(self.structural_failures),
            "content_failures": list(self.content_failures),
            "ok": self.ok,
        }


def validate_ctd_module3(
    bundles: Sequence[Mapping[str, Any]] | None = None,
    *,
    required: Sequence[str] = ("3.2.S.3.2",),
    source: str = "CTD Module 3",
) -> CTDValidationResult:
    """Structural + content checks over CTD Module 3 reports.

    With ``bundles=None`` this runs the built-in self-check: a real 3.2.S.3.2 section from the
    Prompt 8 engine must carry the required section, impurity rows, and traceable sources. Supply
    the 50 historical anonymised reports (the Prompt 17 gold set) as ``bundles`` to validate each
    against the required sections — the generated / historical Module 3 structure never drifts.
    """

    report_bundles = list(bundles) if bundles is not None else [_reference_module3_bundle()]
    structural: list[str] = []
    content: list[str] = []
    for i, bundle in enumerate(report_bundles):
        for missing in ctd_module3_missing_sections(bundle, required=required):
            structural.append(f"report[{i}]: missing section {missing}")
        for issue in ctd_module3_content_issues(bundle, required=required):
            content.append(f"report[{i}]: {issue}")
    return CTDValidationResult(
        source=source,
        n_reports=len(report_bundles),
        structural_failures=tuple(structural),
        content_failures=tuple(content),
    )
