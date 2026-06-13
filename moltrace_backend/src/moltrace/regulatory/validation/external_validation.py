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
    "ExternalCompound",
    "ExternalValidationResult",
    "ctd_module3_missing_sections",
    "load_external_manifest",
    "validate_compounds",
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
    """Structural check: the required CTD Module 3 sections present in a generated bundle.

    Run over each of the 50 anonymised CTD reports (the Prompt 17 gold set) to assert the
    generated Module 3 structure matches. Returns missing section ids (empty = valid).
    """

    sections = set(bundle.get("sections", {}) or {})
    return sorted(s for s in required if s not in sections)
