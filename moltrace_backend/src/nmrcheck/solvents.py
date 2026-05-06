from __future__ import annotations

from dataclasses import dataclass

from .models import Peak, SolventHeuristicHit


@dataclass(frozen=True)
class SolventSignal:
    label: str
    ppm: float
    kind: str  # residual, water, exchange, impurity


@dataclass(frozen=True)
class SolventProfile:
    canonical_name: str
    aliases: tuple[str, ...]
    residual_signals: tuple[SolventSignal, ...]
    default_tolerance_ppm: float
    notes: tuple[str, ...]


SOLVENT_PROFILES: tuple[SolventProfile, ...] = (
    SolventProfile(
        canonical_name="CDCl3",
        aliases=("cdcl3", "chloroform-d", "chloroform-d1"),
        residual_signals=(
            SolventSignal("residual CHCl3", 7.26, "residual"),
            SolventSignal("water in CDCl3", 1.56, "water"),
        ),
        default_tolerance_ppm=0.08,
        notes=(
            "In CDCl3, labile OH/NH signals may be broadened, shifted, or absent from the integration summary.",
            "Residual CHCl3 and trace water are common small signals in CDCl3 spectra.",
        ),
    ),
    SolventProfile(
        canonical_name="DMSO-d6",
        aliases=("dmso-d6", "(cd3)2so", "dmso"),
        residual_signals=(
            SolventSignal("residual DMSO-d5", 2.50, "residual"),
            SolventSignal("water in DMSO-d6", 3.33, "water"),
        ),
        default_tolerance_ppm=0.08,
        notes=(
            "In DMSO-d6, exchangeable OH/NH signals are often observed but can still broaden.",
            "Residual DMSO and water are common extra signals in DMSO-d6 spectra.",
        ),
    ),
    SolventProfile(
        canonical_name="CD3OD",
        aliases=("cd3od", "methanol-d4", "meod", "methanol-d"),
        residual_signals=(
            SolventSignal("residual CHD2OD", 3.31, "residual"),
            SolventSignal("water in CD3OD", 4.87, "water"),
        ),
        default_tolerance_ppm=0.10,
        notes=(
            "In CD3OD, exchangeable OH/NH signals can be especially unreliable because proton exchange is common.",
            "Residual solvent and water can contribute extra signals if the peak list is not solvent-filtered.",
        ),
    ),
    SolventProfile(
        canonical_name="D2O",
        aliases=("d2o", "deuterium oxide", "heavy water"),
        residual_signals=(
            SolventSignal("HDO in D2O", 4.79, "water"),
        ),
        default_tolerance_ppm=0.12,
        notes=(
            "In D2O, exchangeable OH/NH/SH protons often exchange away and may disappear from 1H NMR integration.",
            "The residual HDO peak is commonly observed near 4.79 ppm.",
        ),
    ),
    SolventProfile(
        canonical_name="acetone-d6",
        aliases=("acetone-d6", "(cd3)2co"),
        residual_signals=(
            SolventSignal("residual acetone-d5", 2.05, "residual"),
            SolventSignal("water in acetone-d6", 2.84, "water"),
        ),
        default_tolerance_ppm=0.08,
        notes=(
            "Acetone-d6 commonly shows residual solvent and water peaks around 2.05 and 2.84 ppm.",
        ),
    ),
    SolventProfile(
        canonical_name="CD3CN",
        aliases=("cd3cn", "acetonitrile-d3", "mecn-d3"),
        residual_signals=(
            SolventSignal("residual CD2HCN", 1.94, "residual"),
            SolventSignal("water in CD3CN", 2.13, "water"),
        ),
        default_tolerance_ppm=0.08,
        notes=(
            "CD3CN often shows small residual acetonitrile and water signals near 1.94 and 2.13 ppm.",
        ),
    ),
    SolventProfile(
        canonical_name="C6D6",
        aliases=("c6d6", "benzene-d6"),
        residual_signals=(
            SolventSignal("residual C6D5H", 7.16, "residual"),
            SolventSignal("water in C6D6", 0.40, "water"),
        ),
        default_tolerance_ppm=0.10,
        notes=(
            "In C6D6, both analyte and impurity peaks can shift substantially relative to CDCl3.",
            "Trace water in C6D6 can appear unusually far upfield.",
        ),
    ),
    SolventProfile(
        canonical_name="pyridine-d5",
        aliases=("pyridine-d5", "c5d5n"),
        residual_signals=(
            SolventSignal("residual pyridine-d4 (ortho)", 8.74, "residual"),
            SolventSignal("residual pyridine-d4 (para)", 7.58, "residual"),
            SolventSignal("residual pyridine-d4 (meta)", 7.22, "residual"),
            SolventSignal("water in pyridine-d5", 3.11, "water"),
        ),
        default_tolerance_ppm=0.12,
        notes=(
            "Pyridine-d5 has multiple residual aromatic solvent resonances.",
            "Water and exchangeable protons can shift noticeably in pyridine-d5.",
        ),
    ),
    SolventProfile(
        canonical_name="THF-d8",
        aliases=("thf-d8", "tetrahydrofuran-d8"),
        residual_signals=(
            SolventSignal("residual THF-d7 (O-CH2)", 3.58, "residual"),
            SolventSignal("residual THF-d7 (CH2)", 1.73, "residual"),
            SolventSignal("water in THF-d8", 2.14, "water"),
        ),
        default_tolerance_ppm=0.10,
        notes=(
            "THF-d8 has two common residual solvent resonances, so extra signals near 3.58 and 1.73 ppm deserve a solvent check.",
        ),
    ),
    SolventProfile(
        canonical_name="toluene-d8",
        aliases=("toluene-d8", "c7d8"),
        residual_signals=(
            SolventSignal("residual toluene-d7 (methyl)", 2.09, "residual"),
            SolventSignal("residual toluene-d7 (aromatic)", 6.97, "residual"),
            SolventSignal("water in toluene-d8", 0.68, "water"),
        ),
        default_tolerance_ppm=0.10,
        notes=(
            "Toluene-d8 often gives both aromatic and methyl residual solvent signals.",
        ),
    ),
)


def normalize_solvent_name(solvent: str | None) -> str | None:
    if solvent is None:
        return None
    value = solvent.strip().lower()
    return value or None


def get_solvent_profile(solvent: str | None) -> SolventProfile | None:
    key = normalize_solvent_name(solvent)
    if key is None:
        return None
    for profile in SOLVENT_PROFILES:
        if key == profile.canonical_name.lower() or key in profile.aliases:
            return profile
    return None


def find_solvent_peak_hits(peaks: list[Peak], solvent: str | None) -> list[SolventHeuristicHit]:
    profile = get_solvent_profile(solvent)
    if profile is None:
        return []

    hits: list[SolventHeuristicHit] = []
    for peak in peaks:
        for signal in profile.residual_signals:
            delta = abs(peak.shift_ppm - signal.ppm)
            if delta <= profile.default_tolerance_ppm:
                hits.append(
                    SolventHeuristicHit(
                        solvent=profile.canonical_name,
                        signal_label=signal.label,
                        expected_ppm=signal.ppm,
                        observed_ppm=peak.shift_ppm,
                        delta_ppm=round(delta, 4),
                        kind=signal.kind,
                    )
                )
    return hits


def find_solvent_peak_hit_indices(peaks: list[Peak], solvent: str | None) -> set[int]:
    profile = get_solvent_profile(solvent)
    if profile is None:
        return set()

    indices: set[int] = set()
    for index, peak in enumerate(peaks):
        for signal in profile.residual_signals:
            delta = abs(peak.shift_ppm - signal.ppm)
            if delta <= profile.default_tolerance_ppm:
                indices.add(index)
                break
    return indices
