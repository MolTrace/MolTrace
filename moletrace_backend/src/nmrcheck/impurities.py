from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .solvents import get_solvent_profile, normalize_solvent_name


@dataclass(frozen=True)
class H1ImpurityShift:
    label: str
    shift_ppm: float
    solvent: str | None = None
    tolerance_ppm: float = 0.05
    kind: str = "impurity"


@dataclass(frozen=True)
class C13ImpurityShift:
    label: str
    shift_ppm: float
    solvent: str | None = None
    tolerance_ppm: float = 0.35
    kind: str = "impurity"


_SOLVENT_COLUMNS: tuple[str, ...] = (
    "CDCl3",
    "acetone-d6",
    "DMSO-d6",
    "C6D6",
    "CD3CN",
    "CD3OD",
    "D2O",
)

_Missing = float | tuple[float, float] | None


def _shift_value(value: _Missing) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        low, high = value
        return ((low + high) / 2.0, abs(high - low) / 2.0 + 0.04)
    return (float(value), 0.05)


def _row(
    compound: str,
    proton: str,
    values: tuple[_Missing, _Missing, _Missing, _Missing, _Missing, _Missing, _Missing],
    *,
    kind: str = "impurity",
    tolerance_ppm: float | None = None,
) -> tuple[H1ImpurityShift, ...]:
    entries: list[H1ImpurityShift] = []
    label = f"{compound} {proton}".strip()
    for solvent, value in zip(_SOLVENT_COLUMNS, values, strict=True):
        parsed = _shift_value(value)
        if parsed is None:
            continue
        shift_ppm, range_tolerance = parsed
        entries.append(
            H1ImpurityShift(
                label=label,
                shift_ppm=round(shift_ppm, 3),
                solvent=solvent,
                tolerance_ppm=tolerance_ppm or range_tolerance,
                kind=kind,
            )
        )
    return tuple(entries)


# Source: user-provided PDF "NMR impurity chemical shifts.pdf", H-1 impurity
# shifts table. C-13 rows are intentionally not embedded yet.
H1_IMPURITY_SHIFTS: tuple[H1ImpurityShift, ...] = sum(
    (
        _row(
            "solvent residual peak",
            "",
            (7.26, 2.05, 2.50, 7.16, 1.94, 3.31, 4.79),
            kind="residual",
            tolerance_ppm=0.04,
        ),
        _row("water", "H2O", (1.56, 2.84, 3.33, 0.40, 2.13, 4.87, None), kind="water", tolerance_ppm=0.10),
        _row("acetic acid", "CH3", (2.10, 1.96, 1.91, 1.55, 1.96, 1.99, 2.08)),
        _row("acetone", "CH3", (2.17, 2.09, 2.09, 1.55, 2.08, 2.15, 2.22)),
        _row("acetonitrile", "CH3", (2.10, 2.05, 2.07, 1.55, 1.96, 2.03, 2.06)),
        _row("benzene", "CH", (7.36, 7.36, 7.37, 7.15, 7.37, 7.33, None)),
        _row("tert-butyl alcohol", "CH3", (1.28, 1.18, 1.11, 1.05, 1.16, 1.40, 1.24)),
        _row("tert-butyl alcohol", "OH", (None, None, 4.19, 1.55, 2.18, None, None), kind="exchange"),
        _row("tert-butyl methyl ether", "OCCH3", (1.19, 1.13, 1.11, 1.07, 1.14, 1.15, 1.21)),
        _row("tert-butyl methyl ether", "OCH3", (3.22, 3.13, 3.08, 3.04, 3.13, 3.20, 3.22)),
        _row("BHT", "ArH", (6.98, 6.96, 6.87, 7.05, 6.97, 6.92, None)),
        _row("BHT", "OH", (5.01, None, 6.65, 4.79, 5.20, None, None), kind="exchange"),
        _row("BHT", "ArCH3", (2.27, 2.22, 2.18, 2.24, 2.22, 2.21, None)),
        _row("BHT", "ArC(CH3)3", (1.43, 1.41, 1.36, 1.38, 1.39, 1.40, None)),
        _row("chloroform", "CH", (7.26, 8.02, 8.32, 6.15, 7.58, 7.90, None)),
        _row("cyclohexane", "CH2", (1.43, 1.43, 1.40, 1.40, 1.44, 1.45, None)),
        _row("1,2-dichloroethane", "CH2", (3.73, 3.87, 3.90, 2.90, 3.81, 3.78, None)),
        _row("dichloromethane", "CH2", (5.30, 5.63, 5.76, 4.27, 5.44, 5.49, None)),
        _row("diethyl ether", "CH3", (1.21, 1.11, 1.09, 1.11, 1.12, 1.18, 1.17)),
        _row("diethyl ether", "CH2", (3.48, 3.41, 3.38, 3.26, 3.42, 3.49, 3.56)),
        _row("diglyme", "CH2", (3.65, 3.56, 3.51, 3.46, 3.53, 3.61, 3.67)),
        _row("diglyme", "CH2", (3.57, 3.47, 3.38, 3.34, 3.45, 3.58, 3.61)),
        _row("diglyme", "OCH3", (3.39, 3.28, 3.24, 3.11, 3.29, 3.35, 3.37)),
        _row("1,2-dimethoxyethane", "CH3", (3.40, 3.28, 3.24, 3.12, 3.28, 3.35, 3.37)),
        _row("1,2-dimethoxyethane", "CH2", (3.55, 3.46, 3.43, 3.33, 3.45, 3.52, 3.60)),
        _row("dimethylacetamide", "CH3CO", (2.09, 1.97, 1.96, 1.60, 1.97, 2.07, 2.08)),
        _row("dimethylacetamide", "NCH3", (3.02, 3.00, 2.94, 2.57, 2.96, 3.31, 3.06)),
        _row("dimethylacetamide", "NCH3", (2.94, 2.83, 2.78, 2.05, 2.83, 2.92, 2.90)),
        _row("dimethylformamide", "CH", (8.02, 7.96, 7.95, 7.63, 7.92, 7.97, 7.92)),
        _row("dimethylformamide", "CH3", (2.96, 2.94, 2.89, 2.36, 2.89, 2.99, 3.01)),
        _row("dimethylformamide", "CH3", (2.88, 2.78, 2.73, 1.86, 2.77, 2.86, 2.85)),
        _row("dimethyl sulfoxide", "CH3", (2.62, 2.52, 2.54, 1.68, 2.50, 2.65, 2.71)),
        _row("dioxane", "CH2", (3.71, 3.59, 3.57, 3.35, 3.60, 3.66, 3.75)),
        _row("ethanol", "CH3", (1.25, 1.12, 1.06, 0.96, 1.12, 1.19, 1.17)),
        _row("ethanol", "CH2", (3.72, 3.57, 3.44, 3.34, 3.54, 3.60, 3.65)),
        _row("ethanol", "OH", (1.32, 3.39, 4.63, None, 2.47, None, None), kind="exchange"),
        _row("ethyl acetate", "CH3CO", (2.05, 1.97, 1.99, 1.65, 1.97, 2.01, 2.07)),
        _row("ethyl acetate", "OCH2CH3", (4.12, 4.05, 4.03, 3.89, 4.06, 4.09, 4.14)),
        _row("ethyl acetate", "OCH2CH3", (1.26, 1.20, 1.17, 0.92, 1.20, 1.24, 1.24)),
        _row("ethyl methyl ketone", "CH3CO", (2.14, 2.07, 2.07, 1.58, 2.06, 2.12, 2.19)),
        _row("ethyl methyl ketone", "CH2CH3", (2.46, 2.45, 2.43, 1.81, 2.43, 2.50, 3.18)),
        _row("ethyl methyl ketone", "CH2CH3", (1.06, 0.96, 0.91, 0.85, 0.96, 1.01, 1.26)),
        _row("ethylene glycol", "CH", (3.76, 3.28, 3.34, 3.41, 3.51, 3.59, 3.65)),
        _row("grease", "CH3", (0.86, 0.87, None, 0.92, 0.86, 0.88, None), tolerance_ppm=0.08),
        _row("grease", "CH2", (1.26, 1.29, None, 1.36, 1.27, 1.29, None), tolerance_ppm=0.08),
        _row("n-hexane", "CH3", (0.88, 0.88, 0.86, 0.89, 0.89, 0.90, None)),
        _row("n-hexane", "CH2", (1.26, 1.28, 1.25, 1.24, 1.28, 1.29, None)),
        _row("HMPA", "CH3", (2.65, 2.59, 2.53, 2.40, 2.57, 2.64, 2.61)),
        _row("methanol", "CH3", (3.49, 3.31, 3.16, None, 3.28, 3.34, 3.34)),
        _row("methanol", "OH", (1.09, 3.12, 4.01, 3.07, 2.16, None, None), kind="exchange"),
        _row("nitromethane", "CH3", (4.33, 4.43, 4.42, 2.94, 4.31, 4.34, 4.40)),
        _row("n-pentane", "CH3", (0.88, 0.88, 0.86, 0.87, 0.89, 0.90, None)),
        _row("n-pentane", "CH2", (1.27, 1.27, 1.27, 1.23, 1.29, 1.29, None)),
        _row("2-propanol", "CH3", (1.22, 1.10, 1.04, 0.95, 1.09, 1.50, 1.17)),
        _row("2-propanol", "CH", (4.04, 3.90, 3.78, 3.67, 3.87, 3.92, 4.02)),
        _row("pyridine", "CH(2)", (8.62, 8.58, 8.58, 8.53, 8.57, 8.53, 8.52)),
        _row("pyridine", "CH(3)", (7.29, 7.35, 7.39, 6.66, 7.33, 7.44, 7.45)),
        _row("pyridine", "CH(4)", (7.68, 7.76, 7.79, 6.98, 7.73, 7.85, 7.87)),
        _row("silicone grease", "CH3", (0.07, 0.13, None, 0.29, 0.08, 0.10, None), tolerance_ppm=0.08),
        _row("tetrahydrofuran", "CH2", (1.85, 1.79, 1.76, 1.40, 1.80, 1.87, 1.88)),
        _row("tetrahydrofuran", "CH2O", (3.76, 3.63, 3.60, 3.57, 3.64, 3.71, 3.74)),
        _row("toluene", "CH3", (2.36, 2.32, 2.30, 2.11, 2.33, 2.32, None)),
        _row("toluene", "CH(o/p)", (7.17, (7.10, 7.20), 7.18, 7.02, (7.10, 7.30), 7.16, None), tolerance_ppm=0.10),
        _row("toluene", "CH(m)", (7.25, (7.10, 7.20), 7.25, 7.13, (7.10, 7.30), 7.16, None), tolerance_ppm=0.10),
        _row("triethylamine", "CH3", (1.03, 0.96, 0.93, 0.96, 0.96, 1.05, 0.99)),
        _row("triethylamine", "CH2", (2.53, 2.45, 2.43, 2.40, 2.45, 2.58, 2.57)),
    ),
    (),
)


# Source: user-provided PDF "NMR impurity chemical shifts.pdf", C-13
# impurity shifts table. These entries are used as review flags, not as
# hard exclusions from carbon-count validation.
C13_IMPURITY_SHIFTS: tuple[C13ImpurityShift, ...] = (
    C13ImpurityShift("CDCl3 solvent carbon", 77.16, "CDCl3", 0.7, "solvent"),
    C13ImpurityShift("DMSO-d6 solvent carbon", 39.52, "DMSO-d6", 0.7, "solvent"),
    C13ImpurityShift("acetone-d6 methyl carbon", 29.84, "acetone-d6", 0.7, "solvent"),
    C13ImpurityShift("acetone-d6 carbonyl carbon", 206.26, "acetone-d6", 1.2, "solvent"),
    C13ImpurityShift("CD3OD solvent carbon", 49.0, "CD3OD", 0.9, "solvent"),
    C13ImpurityShift("CD3CN methyl carbon", 1.32, "CD3CN", 0.7, "solvent"),
    C13ImpurityShift("CD3CN nitrile carbon", 118.26, "CD3CN", 0.9, "solvent"),
    C13ImpurityShift("C6D6 solvent carbon", 128.06, "C6D6", 0.9, "solvent"),
    C13ImpurityShift("acetone CH3", 30.9),
    C13ImpurityShift("acetone C=O", 207.1, tolerance_ppm=1.0),
    C13ImpurityShift("acetic acid CH3", 20.8),
    C13ImpurityShift("acetic acid C=O", 178.5, tolerance_ppm=1.0),
    C13ImpurityShift("acetonitrile CH3", 1.9),
    C13ImpurityShift("acetonitrile CN", 118.7, tolerance_ppm=0.6),
    C13ImpurityShift("benzene CH", 128.4, tolerance_ppm=0.5),
    C13ImpurityShift("tert-butyl alcohol CH3", 31.2),
    C13ImpurityShift("tert-butyl alcohol C-O", 69.3),
    C13ImpurityShift("tert-butyl methyl ether CH3", 27.9),
    C13ImpurityShift("tert-butyl methyl ether OCH3", 49.2),
    C13ImpurityShift("tert-butyl methyl ether C-O", 73.0),
    C13ImpurityShift("chloroform CH", 77.2, tolerance_ppm=0.7),
    C13ImpurityShift("cyclohexane CH2", 27.5),
    C13ImpurityShift("1,2-dichloroethane CH2", 43.7),
    C13ImpurityShift("dichloromethane CH2", 54.0),
    C13ImpurityShift("diethyl ether CH3", 15.2),
    C13ImpurityShift("diethyl ether CH2", 66.0),
    C13ImpurityShift("diglyme OCH3", 59.0),
    C13ImpurityShift("diglyme OCH2", 70.0, tolerance_ppm=0.8),
    C13ImpurityShift("dimethylacetamide CH3CO", 21.0),
    C13ImpurityShift("dimethylacetamide NCH3", 35.5, tolerance_ppm=0.8),
    C13ImpurityShift("dimethylacetamide C=O", 171.0, tolerance_ppm=1.0),
    C13ImpurityShift("dimethylformamide CHO", 162.5, tolerance_ppm=1.0),
    C13ImpurityShift("dimethylformamide NCH3", 31.0, tolerance_ppm=0.8),
    C13ImpurityShift("dimethyl sulfoxide CH3", 40.0, tolerance_ppm=0.8),
    C13ImpurityShift("dioxane CH2", 67.2),
    C13ImpurityShift("ethanol CH3", 18.3),
    C13ImpurityShift("ethanol CH2", 58.1),
    C13ImpurityShift("ethyl acetate CH3CO", 21.0),
    C13ImpurityShift("ethyl acetate OCH2", 60.4),
    C13ImpurityShift("ethyl acetate CH3", 14.2),
    C13ImpurityShift("ethyl acetate C=O", 171.4, tolerance_ppm=1.0),
    C13ImpurityShift("ethyl methyl ketone CH3CO", 29.5),
    C13ImpurityShift("ethyl methyl ketone CH2", 36.0),
    C13ImpurityShift("ethyl methyl ketone CH3", 7.8),
    C13ImpurityShift("ethyl methyl ketone C=O", 209.5, tolerance_ppm=1.0),
    C13ImpurityShift("ethylene glycol CH2", 63.0),
    C13ImpurityShift("grease aliphatic CH3", 14.1, tolerance_ppm=0.6),
    C13ImpurityShift("grease aliphatic CH2", 29.7, tolerance_ppm=1.2),
    C13ImpurityShift("n-hexane CH3", 14.0),
    C13ImpurityShift("n-hexane CH2", 22.7, tolerance_ppm=0.6),
    C13ImpurityShift("n-hexane CH2", 31.7, tolerance_ppm=0.6),
    C13ImpurityShift("methanol CH3", 50.4),
    C13ImpurityShift("nitromethane CH3", 62.3),
    C13ImpurityShift("2-propanol CH3", 25.0),
    C13ImpurityShift("2-propanol CH", 64.0),
    C13ImpurityShift("pyridine CH", 123.8, tolerance_ppm=0.7),
    C13ImpurityShift("pyridine CH", 135.8, tolerance_ppm=0.7),
    C13ImpurityShift("pyridine CH", 149.9, tolerance_ppm=0.7),
    C13ImpurityShift("tetrahydrofuran CH2", 25.7),
    C13ImpurityShift("tetrahydrofuran OCH2", 68.0),
    C13ImpurityShift("toluene CH3", 21.4),
    C13ImpurityShift("toluene aromatic carbon", 125.0, tolerance_ppm=1.0),
    C13ImpurityShift("toluene aromatic carbon", 128.5, tolerance_ppm=1.0),
    C13ImpurityShift("toluene aromatic carbon", 137.8, tolerance_ppm=1.0),
    C13ImpurityShift("triethylamine CH3", 11.8),
    C13ImpurityShift("triethylamine CH2", 47.0),
)


def _canonical_solvent_key(solvent: str | None) -> str | None:
    profile = get_solvent_profile(solvent)
    if profile is not None:
        return profile.canonical_name.lower()
    normalized = normalize_solvent_name(solvent)
    return normalized.lower() if normalized else None


def match_h1_impurity_shifts(
    shift_ppm: float,
    solvent: str | None,
    *,
    max_matches: int = 3,
) -> list[dict[str, Any]]:
    solvent_key = _canonical_solvent_key(solvent)
    matches: list[dict[str, Any]] = []
    for entry in H1_IMPURITY_SHIFTS:
        entry_key = _canonical_solvent_key(entry.solvent)
        if entry_key is not None and solvent_key is not None and entry_key != solvent_key:
            continue
        if entry_key is not None and solvent_key is None:
            continue
        delta = abs(float(shift_ppm) - float(entry.shift_ppm))
        if delta <= entry.tolerance_ppm:
            matches.append(
                {
                    "label": entry.label,
                    "expected_ppm": round(entry.shift_ppm, 3),
                    "observed_ppm": round(float(shift_ppm), 3),
                    "delta_ppm": round(delta, 4),
                    "solvent": entry.solvent,
                    "kind": entry.kind,
                }
            )
    matches.sort(key=lambda item: (float(item["delta_ppm"]), str(item["label"])))
    return matches[:max_matches]


def match_c13_impurity_shifts(
    shift_ppm: float,
    solvent: str | None,
    *,
    max_matches: int = 4,
) -> list[dict[str, Any]]:
    solvent_key = _canonical_solvent_key(solvent)
    matches: list[dict[str, Any]] = []
    for entry in C13_IMPURITY_SHIFTS:
        entry_key = _canonical_solvent_key(entry.solvent)
        if entry_key is not None and solvent_key is not None and entry_key != solvent_key:
            continue
        if entry_key is not None and solvent_key is None:
            continue
        delta = abs(float(shift_ppm) - float(entry.shift_ppm))
        if delta <= entry.tolerance_ppm:
            matches.append(
                {
                    "label": entry.label,
                    "expected_ppm": round(entry.shift_ppm, 3),
                    "observed_ppm": round(float(shift_ppm), 3),
                    "delta_ppm": round(delta, 4),
                    "solvent": entry.solvent,
                    "kind": entry.kind,
                }
            )
    matches.sort(key=lambda item: (0 if item["kind"] == "solvent" else 1, float(item["delta_ppm"]), str(item["label"])))
    return matches[:max_matches]
