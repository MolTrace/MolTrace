from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Nucleus = Literal["1H", "13C"]


@dataclass(frozen=True)
class ShiftWindow:
    low: float
    high: float
    label: str
    kind: str = "reference"
    confidence_penalty: float = 0.0

    def contains(self, ppm: float) -> bool:
        return min(self.low, self.high) <= ppm <= max(self.low, self.high)


# Practical, conservative solvent/impurity windows. Values are deliberately windows,
# not single exact numbers, because referencing, temperature, concentration, pH, and
# processing choices can move peaks.
SOLVENT_IMPURITY_WINDOWS: dict[str, dict[Nucleus, list[ShiftWindow]]] = {
    "CDCl3": {
        "1H": [
            ShiftWindow(7.20, 7.32, "residual CHCl3", "solvent"),
            ShiftWindow(1.45, 1.70, "water in CDCl3", "water"),
            ShiftWindow(0.00, 0.08, "TMS/reference", "reference"),
        ],
        "13C": [ShiftWindow(76.3, 77.7, "CDCl3 solvent carbon", "solvent")],
    },
    "DMSO-d6": {
        "1H": [
            ShiftWindow(2.45, 2.56, "residual DMSO-d5", "solvent"),
            ShiftWindow(3.20, 3.45, "water in DMSO-d6", "water"),
        ],
        "13C": [ShiftWindow(38.8, 40.2, "DMSO-d6 solvent carbon", "solvent")],
    },
    "CD3OD": {
        "1H": [
            ShiftWindow(3.25, 3.38, "residual CD3OD", "solvent"),
            ShiftWindow(4.70, 5.05, "water/HOD in methanol-d4", "water"),
        ],
        "13C": [ShiftWindow(48.2, 50.2, "CD3OD solvent carbon", "solvent")],
    },
    "D2O": {
        "1H": [ShiftWindow(4.55, 5.05, "HOD/water in D2O", "water")],
        "13C": [],
    },
    "acetone-d6": {
        "1H": [
            ShiftWindow(2.00, 2.12, "residual acetone-d5", "solvent"),
            ShiftWindow(2.70, 2.95, "water in acetone-d6", "water"),
        ],
        "13C": [
            ShiftWindow(28.5, 30.8, "acetone-d6 methyl carbon", "solvent"),
            ShiftWindow(204.5, 207.5, "acetone-d6 carbonyl carbon", "solvent"),
        ],
    },
    "CD3CN": {
        "1H": [
            ShiftWindow(1.90, 2.05, "residual acetonitrile-d2", "solvent"),
            ShiftWindow(2.05, 2.25, "water in acetonitrile-d3", "water"),
        ],
        "13C": [
            ShiftWindow(0.5, 2.5, "CD3CN methyl carbon", "solvent"),
            ShiftWindow(117.0, 119.5, "CD3CN nitrile carbon", "solvent"),
        ],
    },
    "C6D6": {
        "1H": [
            ShiftWindow(7.05, 7.25, "residual benzene-d5", "solvent"),
            ShiftWindow(0.35, 0.60, "water in benzene-d6", "water"),
        ],
        "13C": [ShiftWindow(127.0, 129.5, "C6D6 solvent carbon", "solvent")],
    },
    "pyridine-d5": {
        "1H": [
            ShiftWindow(7.10, 7.30, "residual pyridine-d4 beta H", "solvent"),
            ShiftWindow(7.45, 7.70, "residual pyridine-d4 gamma H", "solvent"),
            ShiftWindow(8.45, 8.80, "residual pyridine-d4 alpha H", "solvent"),
        ],
        "13C": [ShiftWindow(123.0, 151.0, "pyridine-d5 solvent carbons", "solvent")],
    },
}

PROTON_REGION_RULES: list[ShiftWindow] = [
    ShiftWindow(10.0, 13.5, "carboxylic acid / strongly H-bonded proton", "chemical_region"),
    ShiftWindow(9.0, 10.5, "aldehydic proton", "chemical_region"),
    ShiftWindow(6.0, 8.8, "aromatic / alkene proton", "chemical_region"),
    ShiftWindow(4.4, 5.8, "anomeric / acetal / vinylic proton", "chemical_region"),
    ShiftWindow(3.0, 4.5, "O/N-bearing or heteroatom-adjacent proton", "chemical_region"),
    ShiftWindow(2.0, 3.2, "allylic / benzylic / heteroatom-adjacent proton", "chemical_region"),
    ShiftWindow(0.5, 2.1, "aliphatic proton", "chemical_region"),
    ShiftWindow(-1.0, 0.5, "upfield / reference / unusual proton", "chemical_region"),
]

CARBON13_REGION_RULES: list[ShiftWindow] = [
    ShiftWindow(190.0, 220.0, "ketone / aldehyde carbonyl carbon", "chemical_region"),
    ShiftWindow(160.0, 190.0, "carboxyl / ester / amide / carbonate carbon", "chemical_region"),
    ShiftWindow(110.0, 160.0, "aromatic / alkene carbon", "chemical_region"),
    ShiftWindow(90.0, 110.0, "anomeric / acetal carbon", "chemical_region"),
    ShiftWindow(55.0, 90.0, "oxygenated carbon", "chemical_region"),
    ShiftWindow(40.0, 70.0, "nitrogen-bearing carbon", "chemical_region"),
    ShiftWindow(0.0, 55.0, "aliphatic carbon", "chemical_region"),
    ShiftWindow(-10.0, 0.0, "unusual upfield carbon", "chemical_region"),
]


def canonical_solvent(solvent: str | None) -> str | None:
    if not solvent:
        return None
    value = solvent.strip()
    for key in SOLVENT_IMPURITY_WINDOWS:
        if key.lower() == value.lower():
            return key
    return value or None


def solvent_windows(solvent: str | None, nucleus: Nucleus) -> list[ShiftWindow]:
    key = canonical_solvent(solvent)
    if not key:
        return []
    return SOLVENT_IMPURITY_WINDOWS.get(key, {}).get(nucleus, [])


def find_solvent_or_impurity_hits(ppm: float, *, solvent: str | None, nucleus: Nucleus) -> list[ShiftWindow]:
    return [window for window in solvent_windows(solvent, nucleus) if window.contains(ppm)]


def classify_proton_region(ppm: float) -> str:
    for window in PROTON_REGION_RULES:
        if window.contains(ppm):
            return window.label
    return "out-of-range / unusual proton"


def classify_carbon13_region(ppm: float) -> str:
    # Return the most specific overlapping 13C label. Nitrogen-bearing and oxygenated overlap intentionally;
    # downstream code can retain both if needed, but the primary label is determined in table order.
    for window in CARBON13_REGION_RULES:
        if window.contains(ppm):
            return window.label
    return "out-of-range / unusual carbon"
