"""QM9-NMR loader + shielding→shift conversion for the NMRNet accuracy gate.

QM9-NMR (https://moldis-group.github.io/qm9nmr/) ships **isotropic magnetic
shielding** σ (mPW1PW91/6-311+G(2d,p)), not chemical shifts δ. NMR shifts are
referenced against a standard (TMS), so a conversion is required before the
``test_nmrnet_qm9_mae_within_30pct_of_paper`` gate can compare against the
paper's reported MAE:

    δ = intercept − slope · σ

* With **slope = 1** and **intercept = σ(TMS)** this is plain TMS referencing.
* In practice a *linear regression* of σ against experimental δ (per nucleus, at
  the QM9-NMR DFT level) gives a better (intercept, slope); use those constants
  for a like-for-like comparison with the paper.

``QM9NMR_EXAMPLE_REFERENCE`` below carries *example* TMS-shielding constants at
roughly the QM9-NMR level — **flagged for verification**. Do not treat them as
authoritative; substitute the calibration your benchmark run actually uses.

The loader accepts a normalised JSON intermediate (the prep step from the raw
``SI_DFT_NMR.txt`` + ``SI_DFT_geo.xyz`` lives with the GPU benchmark tooling,
not here)::

    [{"smiles": "...",
      # EITHER already-referenced shifts:
      "shifts":    [{"atom_index": int, "nucleus": "1H"|"13C", "shift_ppm": float}],
      # OR raw shielding to be converted with a supplied reference:
      "shielding": [{"atom_index": int, "nucleus": "1H"|"13C", "sigma": float}]}, ...]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "LinearReference",
    "QM9NMR_EXAMPLE_REFERENCE",
    "QM9Record",
    "shielding_to_shift",
    "load_qm9nmr_json",
]


@dataclass(frozen=True)
class LinearReference:
    """``δ = intercept − slope · σ`` for one nucleus."""

    intercept: float
    slope: float = 1.0


# TMS isotropic-shielding references for σ→δ (δ = σ_TMS − σ) at the QM9-NMR level
# (mPW1PW91/6-311+G(2d,p) @ B3LYP/6-31G(2df,p)).
#   * ¹³C, Gas phase: σ(TMS) = 186.9704 ppm — published on the QM9-NMR site. Use
#     the matching-solvent TMS σ from the dataset's SI.pdf for the CCl4 / THF /
#     Acetone / Methanol / DMSO columns instead of Gas when you convert those.
#   * ¹H: the QM9-NMR page does not publish a TMS ¹H σ; take it from SI.pdf (the
#     ~31.5–31.8 ppm value at this level). The ¹H entry below is a PLACEHOLDER.
# For the most faithful gate, prefer a per-nucleus *linear fit* (intercept, slope)
# of σ vs experimental δ over plain referencing.
QM9NMR_EXAMPLE_REFERENCE: dict[str, LinearReference] = {
    "1H": LinearReference(intercept=31.6, slope=1.0),  # PLACEHOLDER — see SI.pdf
    "13C": LinearReference(intercept=186.9704, slope=1.0),  # Gas-phase TMS (published)
}


def shielding_to_shift(sigma: float, reference: LinearReference) -> float:
    """Convert one isotropic shielding σ to a chemical shift δ (ppm)."""

    return reference.intercept - reference.slope * float(sigma)


@dataclass
class QM9Record:
    """One QM9-NMR molecule and its reference shifts (post-conversion)."""

    smiles: str
    shifts: list[dict] = field(default_factory=list)  # {atom_index, nucleus, shift_ppm}


def load_qm9nmr_json(
    path: str | Path,
    *,
    reference: dict[str, LinearReference] | None = None,
) -> list[QM9Record]:
    """Load the normalised QM9-NMR JSON, converting σ→δ where needed.

    Parameters
    ----------
    path:
        Path to the normalised JSON intermediate.
    reference:
        Per-nucleus ``LinearReference`` used to convert any ``"shielding"``
        entries. Required only if the file carries raw shielding; ignored for
        records that already provide ``"shifts"``. Pass
        :data:`QM9NMR_EXAMPLE_REFERENCE` only as a placeholder.
    """

    raw = json.loads(Path(path).read_text())
    records: list[QM9Record] = []
    for entry in raw:
        smiles = entry["smiles"]
        shifts: list[dict] = []

        for shift in entry.get("shifts", []):
            shifts.append(
                {
                    "atom_index": int(shift["atom_index"]),
                    "nucleus": shift["nucleus"],
                    "shift_ppm": float(shift["shift_ppm"]),
                }
            )

        for shielding in entry.get("shielding", []):
            nucleus = shielding["nucleus"]
            if reference is None or nucleus not in reference:
                raise ValueError(
                    f"record {smiles!r} carries raw shielding for {nucleus} but no "
                    f"LinearReference was supplied to convert it"
                )
            shifts.append(
                {
                    "atom_index": int(shielding["atom_index"]),
                    "nucleus": nucleus,
                    "shift_ppm": shielding_to_shift(
                        float(shielding["sigma"]), reference[nucleus]
                    ),
                }
            )

        records.append(QM9Record(smiles=smiles, shifts=shifts))
    return records
