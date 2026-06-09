"""ICH Q3C(R8) residual-solvent classifier + limit check (Prompt 2).

Classifies a residual solvent into ICH Q3C Class 1 (avoid), Class 2 (limit by
PDE), or Class 3 (low toxic potential, PDE >= 50 mg/day) and checks measured
residual levels against the permitted limit for a given daily dose. The Q3C
solvent / PDE table is factual regulatory data, implemented from the official ICH
Q3C(R8) Appendices and cited.

Deterministic-first: pure, auditable lookups + arithmetic over a content-versioned
rule-set — no model in the numeric path. Decision-support: verify each value and
classification against the official ICH Q3C(R8) source and obtain qualified
sign-off before any filing or release decision.

Coverage note: the encoded table is a **curated subset** of ICH Q3C(R8)
Appendices 1-3 — all Class 1 solvents, the common Class 2 solvents, and
representative Class 3 solvents. A solvent not in the table returns ``matched =
False`` (an explicit "unknown", never a guessed limit); extend the table from the
official Appendix as needed.

Concentration limits. ICH gives two options. **Option 1** is a concentration limit
(ppm) computed at a 10 g/day daily dose: ``ppm = PDE (mg/day) * 1000 / 10 g =
PDE * 100``. **Option 2** scales the permitted concentration to the actual daily
dose: ``permitted_ppm = PDE (mg/day) * 1000 / daily_dose (g/day)``.
:func:`classify_solvent` reports the Option-1 concentration limit;
:func:`check_residual_solvent_limits` applies Option 2 at the supplied dose (and the
fixed concentration limit for Class 1).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.validation import ValidationFailure, ValidationReport
from moltrace.regulatory.infra.versioning import content_hash, rule_set_version

__all__ = [
    "ComplianceResult",
    "SolventClassification",
    "check_residual_solvent_limits",
    "classify_solvent",
    "q3c_rule_set",
]

GUIDELINE = "ICH Q3C(R8)"
TITLE = "Impurities: Guideline for Residual Solvents"
TABLE_REFERENCE = "ICH Q3C(R8) Appendices 1-3"
EFFECTIVE_YEAR = "2021"

# ICH Q3C PDEs are predominantly systemic (route-independent); route-specific PDEs
# that the guideline lists separately are not encoded here. The supplied route is
# validated + recorded and the systemic PDE is returned for it.
_Q3C_ROUTES = frozenset({"oral", "parenteral", "inhalation"})

_ANALYTICAL_METHODS = ("Headspace gas chromatography (Ph. Eur. 2.4.24 / USP <467>)",)

_CLASS_DESCRIPTION = {
    1: "Class 1 - solvents to be avoided (known/strongly-suspected human carcinogens "
    "or environmental hazards)",
    2: "Class 2 - solvents to be limited (non-genotoxic animal carcinogens or other "
    "irreversible toxicity); controlled by a permitted daily exposure (PDE)",
    3: "Class 3 - solvents with low toxic potential (PDE >= 50 mg/day; no health-based "
    "exposure limit needed at normal GMP levels)",
}
_CLASS_NOTE = {
    1: "Use should be avoided; if unavoidable, control to the concentration limit and justify.",
    2: "Limit to the permitted daily exposure (PDE); report measured levels.",
    3: "Up to 50 mg/day (0.5%) is acceptable without justification; higher with justification.",
}
_DECISION_SUPPORT_NOTE = (
    "Decision-support only: verify the class, PDE, and limit against the official "
    "ICH Q3C(R8) source and obtain qualified sign-off before any filing or release use."
)

# (name, cas, smiles, class, pde_mg_per_day | None, concentration_limit_ppm, aliases)
# Class 1: concentration_limit_ppm is the ICH limit (ppm); pde is None.
# Class 2/3: pde_mg_per_day is the ICH PDE; concentration limit = PDE * 100 (Option 1).
_TABLE: tuple[tuple[str, str, str, int, float | None, float, tuple[str, ...]], ...] = (
    # --- Class 1 (avoid) -------------------------------------------------- #
    ("Benzene", "71-43-2", "c1ccccc1", 1, None, 2.0, ()),
    ("Carbon tetrachloride", "56-23-5", "ClC(Cl)(Cl)Cl", 1, None, 4.0, ("tetrachloromethane",)),
    ("1,2-Dichloroethane", "107-06-2", "ClCCCl", 1, None, 5.0, ("ethylene dichloride", "edc")),
    ("1,1-Dichloroethene", "75-35-4", "C=C(Cl)Cl", 1, None, 8.0, ("1,1-dichloroethylene",)),
    ("1,1,1-Trichloroethane", "71-55-6", "CC(Cl)(Cl)Cl", 1, None, 1500.0, ("methyl chloroform",)),
    # --- Class 2 (limit by PDE) ------------------------------------------ #
    ("Acetonitrile", "75-05-8", "CC#N", 2, 4.1, 410.0, ("mecn", "acn")),
    ("Chlorobenzene", "108-90-7", "Clc1ccccc1", 2, 3.6, 360.0, ()),
    ("Chloroform", "67-66-3", "ClC(Cl)Cl", 2, 0.6, 60.0, ("trichloromethane",)),
    ("Cyclohexane", "110-82-7", "C1CCCCC1", 2, 38.8, 3880.0, ()),
    ("Dichloromethane", "75-09-2", "ClCCl", 2, 6.0, 600.0, ("dcm", "methylene chloride")),
    ("N,N-Dimethylformamide", "68-12-2", "CN(C)C=O", 2, 8.8, 880.0, ("dmf",)),
    ("1,4-Dioxane", "123-91-1", "C1COCCO1", 2, 3.8, 380.0, ("dioxane",)),
    ("Hexane", "110-54-3", "CCCCCC", 2, 2.9, 290.0, ("n-hexane",)),
    ("Methanol", "67-56-1", "CO", 2, 30.0, 3000.0, ("meoh", "methyl alcohol")),
    ("2-Methoxyethanol", "109-86-4", "COCCO", 2, 0.5, 50.0, ("methyl cellosolve",)),
    ("Methylbutyl ketone", "591-78-6", "CCCCC(C)=O", 2, 0.5, 50.0, ("2-hexanone", "mbk")),
    ("N-Methylpyrrolidone", "872-50-4", "CN1CCCC1=O", 2, 5.3, 530.0, ("nmp",)),
    ("Nitromethane", "75-52-5", "C[N+](=O)[O-]", 2, 0.5, 50.0, ()),
    ("Pyridine", "110-86-1", "c1ccncc1", 2, 2.0, 200.0, ()),
    ("Tetrahydrofuran", "109-99-9", "C1CCOC1", 2, 7.2, 720.0, ("thf",)),
    ("Toluene", "108-88-3", "Cc1ccccc1", 2, 8.9, 890.0, ()),
    ("Trichloroethene", "79-01-6", "ClC=C(Cl)Cl", 2, 0.8, 80.0, ("trichloroethylene", "tce")),
    ("Xylene", "1330-20-7", "Cc1ccccc1C", 2, 21.7, 2170.0, ("xylenes", "dimethylbenzene")),
    # --- Class 3 (low toxic potential; PDE 50 mg/day) -------------------- #
    ("Acetic acid", "64-19-7", "CC(=O)O", 3, 50.0, 5000.0, ()),
    ("Acetone", "67-64-1", "CC(C)=O", 3, 50.0, 5000.0, ("propan-2-one",)),
    ("Anisole", "100-66-3", "COc1ccccc1", 3, 50.0, 5000.0, ("methoxybenzene",)),
    ("1-Butanol", "71-36-3", "CCCCO", 3, 50.0, 5000.0, ("n-butanol",)),
    ("2-Butanol", "78-92-2", "CCC(C)O", 3, 50.0, 5000.0, ("sec-butanol",)),
    ("Butyl acetate", "123-86-4", "CCCCOC(C)=O", 3, 50.0, 5000.0, ("n-butyl acetate",)),
    ("tert-Butylmethyl ether", "1634-04-4", "COC(C)(C)C", 3, 50.0, 5000.0, ("mtbe",)),
    ("Dimethyl sulfoxide", "67-68-5", "CS(C)=O", 3, 50.0, 5000.0, ("dmso",)),
    ("Ethanol", "64-17-5", "CCO", 3, 50.0, 5000.0, ("etoh", "ethyl alcohol")),
    ("Ethyl acetate", "141-78-6", "CCOC(C)=O", 3, 50.0, 5000.0, ("etoac",)),
    ("Ethyl ether", "60-29-7", "CCOCC", 3, 50.0, 5000.0, ("diethyl ether", "ether")),
    ("Heptane", "142-82-5", "CCCCCCC", 3, 50.0, 5000.0, ("n-heptane",)),
    ("Isopropyl acetate", "108-21-4", "CC(C)OC(C)=O", 3, 50.0, 5000.0, ()),
    ("Methyl acetate", "79-20-9", "COC(C)=O", 3, 50.0, 5000.0, ()),
    ("Methylethyl ketone", "78-93-3", "CCC(C)=O", 3, 50.0, 5000.0, ("mek", "2-butanone")),
    ("Methylisobutyl ketone", "108-10-1", "CC(=O)CC(C)C", 3, 50.0, 5000.0, ("mibk",)),
    ("Pentane", "109-66-0", "CCCCC", 3, 50.0, 5000.0, ("n-pentane",)),
    ("1-Propanol", "71-23-8", "CCCO", 3, 50.0, 5000.0, ("n-propanol",)),
    ("2-Propanol", "67-63-0", "CC(C)O", 3, 50.0, 5000.0, ("isopropanol", "ipa")),
    ("Propyl acetate", "109-60-4", "CCCOC(C)=O", 3, 50.0, 5000.0, ()),
    ("Triethylamine", "121-44-8", "CCN(CC)CC", 3, 50.0, 5000.0, ("tea",)),
)


def _normalize(text: str) -> str:
    return " ".join(str(text).strip().lower().replace("-", " ").split())


def _normalize_cas(text: str) -> str:
    return str(text).strip().replace(" ", "")


_BY_NAME: dict[str, int] = {}
_BY_CAS: dict[str, int] = {}
for _i, _row in enumerate(_TABLE):
    _BY_NAME.setdefault(_normalize(_row[0]), _i)
    for _alias in _row[6]:
        _BY_NAME.setdefault(_normalize(_alias), _i)
    _BY_CAS.setdefault(_normalize_cas(_row[1]), _i)

_SMILES_INDEX: dict[str, int] | None = None


def _canonical_smiles(text: str) -> str | None:
    try:
        from rdkit import Chem  # optional; only used to recognise a SMILES string
        from rdkit.rdBase import BlockLogs  # silence parse errors for non-SMILES input
    except ImportError:  # pragma: no cover - rdkit is a core dep but stay defensive
        return None
    with BlockLogs():
        mol = Chem.MolFromSmiles(str(text))
        return Chem.MolToSmiles(mol) if mol is not None else None


def _smiles_index() -> dict[str, int]:
    global _SMILES_INDEX
    if _SMILES_INDEX is None:
        index: dict[str, int] = {}
        for idx, row in enumerate(_TABLE):
            canonical = _canonical_smiles(row[2])
            if canonical is not None:
                index.setdefault(canonical, idx)
        _SMILES_INDEX = index
    return _SMILES_INDEX


def _lookup(identifier: str) -> int | None:
    key = str(identifier).strip()
    cas_hit = _BY_CAS.get(_normalize_cas(key))
    if cas_hit is not None:
        return cas_hit
    name_hit = _BY_NAME.get(_normalize(key))
    if name_hit is not None:
        return name_hit
    canonical = _canonical_smiles(key)
    if canonical is not None:
        return _smiles_index().get(canonical)
    return None


@dataclass(frozen=True)
class SolventClassification:
    """An ICH Q3C classification for one residual solvent."""

    solvent_name: str
    class_number: int | None
    class_description: str
    route: str
    pde_mg_per_day: float | None
    concentration_limit_ppm: float | None
    cas_number: str | None
    analytical_methods: tuple[str, ...]
    regulatory_basis: str
    table_reference: str
    notes: tuple[str, ...]
    matched: bool
    rule_set_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "solvent_name": self.solvent_name,
            "class_number": self.class_number,
            "class_description": self.class_description,
            "route": self.route,
            "pde_mg_per_day": self.pde_mg_per_day,
            "concentration_limit_ppm": self.concentration_limit_ppm,
            "cas_number": self.cas_number,
            "analytical_methods": list(self.analytical_methods),
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "notes": list(self.notes),
            "matched": self.matched,
            "rule_set_version": self.rule_set_version,
        }

    def content_hash(self) -> str:
        return content_hash(self.as_dict())


@dataclass(frozen=True)
class ComplianceResult:
    """The pass/fail verdict for one measured residual solvent at a given dose."""

    solvent_name: str
    class_number: int | None
    measured_ppm: float
    permitted_ppm: float | None
    passed: bool | None  # None when the solvent is not in the encoded table
    margin_ppm: float | None
    regulatory_basis: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "solvent_name": self.solvent_name,
            "class_number": self.class_number,
            "measured_ppm": self.measured_ppm,
            "permitted_ppm": self.permitted_ppm,
            "passed": self.passed,
            "margin_ppm": self.margin_ppm,
            "regulatory_basis": self.regulatory_basis,
            "notes": list(self.notes),
        }


def _validate_route(route: str) -> None:
    if route not in _Q3C_ROUTES:
        ValidationReport(
            success=False,
            failures=(
                ValidationFailure(
                    "route", f"unsupported route {route!r}; expected one of {sorted(_Q3C_ROUTES)}"
                ),
            ),
            n_checks=1,
        ).raise_for_status()


def classify_solvent(solvent_identifier: str, route: str = "oral") -> SolventClassification:
    """Classify a residual solvent by name, CAS number, or SMILES, for a route.

    Returns its ICH Q3C class, the systemic PDE (Class 2/3) and Option-1
    concentration limit, the recommended analytical method, and the regulatory
    basis. An unrecognised solvent returns ``matched = False`` (an explicit
    "unknown" with a note to verify against ICH Q3C(R8)), never a guessed limit.
    """

    _validate_route(route)
    idx = _lookup(solvent_identifier)
    if idx is None:
        return SolventClassification(
            solvent_name=str(solvent_identifier),
            class_number=None,
            class_description="unknown - solvent not in the encoded ICH Q3C(R8) subset",
            route=route,
            pde_mg_per_day=None,
            concentration_limit_ppm=None,
            cas_number=None,
            analytical_methods=_ANALYTICAL_METHODS,
            regulatory_basis=f"{GUIDELINE}: {TITLE}",
            table_reference=TABLE_REFERENCE,
            notes=(
                "Solvent not found in the encoded ICH Q3C(R8) subset; classify against the "
                "official ICH Q3C(R8) Appendices 1-3.",
                _DECISION_SUPPORT_NOTE,
            ),
            matched=False,
            rule_set_version=_RULE_SET_VERSION,
        )

    name, cas, _smiles, class_number, pde, conc_ppm, _aliases = _TABLE[idx]
    return SolventClassification(
        solvent_name=name,
        class_number=class_number,
        class_description=_CLASS_DESCRIPTION[class_number],
        route=route,
        pde_mg_per_day=pde,
        concentration_limit_ppm=conc_ppm,
        cas_number=cas,
        analytical_methods=_ANALYTICAL_METHODS,
        regulatory_basis=f"{GUIDELINE}: {TITLE}",
        table_reference=TABLE_REFERENCE,
        notes=(_CLASS_NOTE[class_number], _DECISION_SUPPORT_NOTE),
        matched=True,
        rule_set_version=_RULE_SET_VERSION,
    )


def check_residual_solvent_limits(
    product_spec: Mapping[str, float],
    daily_dose_g: float,
    route: str = "oral",
) -> list[ComplianceResult]:
    """Check each measured residual solvent against its ICH Q3C limit at the dose.

    ``product_spec`` maps solvent name / CAS to the measured concentration in ppm.
    For Class 2/3 the permitted concentration is the Option-2, dose-scaled limit
    (``PDE * 1000 / daily_dose_g``); for Class 1 it is the fixed concentration
    limit. Returns one :class:`ComplianceResult` per solvent with pass/fail, the
    margin to the limit, and the regulatory basis. An unknown solvent yields
    ``passed = None`` (cannot be judged here).
    """

    if not (isinstance(daily_dose_g, (int, float)) and daily_dose_g > 0):
        raise ValueError("daily_dose_g must be a positive number of grams")
    _validate_route(route)

    results: list[ComplianceResult] = []
    for raw_name, measured in product_spec.items():
        measured_ppm = float(measured)
        classification = classify_solvent(raw_name, route)
        if not classification.matched or classification.class_number is None:
            results.append(
                ComplianceResult(
                    solvent_name=str(raw_name),
                    class_number=None,
                    measured_ppm=measured_ppm,
                    permitted_ppm=None,
                    passed=None,
                    margin_ppm=None,
                    regulatory_basis=f"{GUIDELINE}: {TITLE}",
                    notes=("Unknown solvent; classify against ICH Q3C(R8) before judging.",),
                )
            )
            continue

        if classification.class_number == 1:
            permitted_ppm = float(classification.concentration_limit_ppm or 0.0)
            basis_note = "Class 1 concentration limit (ICH Q3C Option 1)."
        else:
            pde = float(classification.pde_mg_per_day or 0.0)
            permitted_ppm = pde * 1000.0 / daily_dose_g  # Option 2, dose-scaled
            basis_note = "ICH Q3C Option 2 (PDE scaled to the daily dose)."

        results.append(
            ComplianceResult(
                solvent_name=classification.solvent_name,
                class_number=classification.class_number,
                measured_ppm=measured_ppm,
                permitted_ppm=permitted_ppm,
                passed=measured_ppm <= permitted_ppm,
                margin_ppm=permitted_ppm - measured_ppm,
                regulatory_basis=f"{GUIDELINE}: {TITLE}",
                notes=(basis_note, _CLASS_NOTE[classification.class_number]),
            )
        )
    return results


def q3c_rule_set() -> dict[str, Any]:
    """The encoded ICH Q3C(R8) solvent table — the auditable rule-set."""

    return {
        "guideline": GUIDELINE,
        "title": TITLE,
        "table_reference": TABLE_REFERENCE,
        "effective_year": EFFECTIVE_YEAR,
        "solvents": [
            {
                "name": name,
                "cas": cas,
                "class_number": class_number,
                "pde_mg_per_day": pde,
                "concentration_limit_ppm": conc_ppm,
            }
            for (name, cas, _smiles, class_number, pde, conc_ppm, _aliases) in _TABLE
        ],
    }


_RULE_SET_VERSION = rule_set_version(q3c_rule_set())
