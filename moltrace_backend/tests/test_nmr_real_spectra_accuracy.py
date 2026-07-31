"""Accuracy on REAL instrument data, scored against known structures.

Every other NMR test uses synthetic traces, hand-written peak lists, or
structure-free fixtures. This one runs the actual raw-FID pipeline over the only
real, structure-paired 1H corpus in the repo — ``tests/fixtures/nmrshiftdb2``,
whose SMILES are recoverable from the bundled NMReDATA source index — and asks
the question a chemist would: does the reported proton total resemble the number
of protons in the molecule?

Marked ``slow``: processing seven raw FIDs takes a few minutes, so it is
excluded from the default run (``addopts = -m 'not slow'``). Opt in with::

    .venv/bin/python -m pytest tests/test_nmr_real_spectra_accuracy.py -m slow

Measured baseline before the fix (2026-07-30) — the reported integral totals
were 3-8x the true proton count:

    C6H10O2  true 10 H  ->  76.0 H reported  (34 peaks)
    C4H8O    true  8 H  ->  29.5 H reported  (21 peaks)
    C8H7N    true  7 H  ->  ~38 H reported   (25 peaks)

Two independent mechanisms produced that, both since fixed:
  * ``_round_half_integrations(minimum=0.5)`` promoted every noise-level peak to
    half a proton — 25 phantom peaks contributed 12.5 H of pure fabrication;
  * ``_provisional_integrations`` used ``reference = max(min(areas), max*0.08)``,
    which pins the LARGEST peak at ~1/0.08 = 12.5 H regardless of the molecule,
    so a 10-proton compound reported a single 12 H resonance.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).parent / "fixtures" / "nmrshiftdb2"
BUNDLE = FIXTURES / "expected" / "nmrshiftdb2_bruker_20.json"
NMREDATA = FIXTURES / "source" / "nmrshiftdb2rawdata.nmredata.sd"

# The reported integral total must land within this factor of the true proton
# count. Generous on purpose: these are archival spectra, none of which was
# acquired quantitatively, so exact proton counts are not achievable. What is
# NOT acceptable is reporting several times more protons than the molecule has.
MAX_TOTAL_H_RATIO = 2.5


def _structure_index() -> tuple[dict[str, str], dict[str, str]]:
    """spectrum_id -> (SMILES, solvent) from the bundled NMReDATA index."""
    if not NMREDATA.exists():
        return {}, {}
    text = NMREDATA.read_text(errors="ignore")
    smiles: dict[str, str] = {}
    solvent: dict[str, str] = {}
    for record in text.split("$$$$"):
        match = re.search(r"<NMREDATA_SMILES>\s*\n(.+?)\n", record)
        if not match:
            continue
        value = match.group(1).strip().rstrip("\\")
        sol = re.search(r"<NMREDATA_SOLVENT>\s*\n(.+?)\n", record)
        sol_value = (sol.group(1).strip().rstrip("\\") if sol else "").split(",")[0]
        for spectrum_id in re.findall(r"spectrumid=(\d+)", record):
            smiles[spectrum_id] = value
            solvent[spectrum_id] = sol_value.strip()
    return smiles, solvent


def _cases() -> list[dict[str, object]]:
    if not BUNDLE.exists():
        return []
    smiles, solvent = _structure_index()
    bundle = json.loads(BUNDLE.read_text())
    cases: list[dict[str, object]] = []
    for fixture in bundle.get("fixtures", []):
        if fixture.get("nucleus") != "1H":
            continue
        spectrum_id = str(fixture.get("spectrum_id"))
        archive = FIXTURES / str(fixture.get("archive"))
        if spectrum_id not in smiles or not archive.exists():
            continue
        cases.append(
            {
                "id": f"nmrshiftdb2_{spectrum_id}",
                "smiles": smiles[spectrum_id],
                "solvent": solvent.get(spectrum_id) or None,
                "archive": archive,
            }
        )
    return cases


CASES = _cases()


def _analyse(case: dict[str, object]) -> dict[str, object]:
    os.environ["MOLTRACE_STRUCTURE_ASSIGNMENT"] = "1"
    from nmrcheck.chemistry import structure_summary_from_smiles
    from nmrcheck.fid import process_bruker_1d_zip

    structure = structure_summary_from_smiles(str(case["smiles"]))
    archive = case["archive"]
    assert isinstance(archive, Path)
    report = process_bruker_1d_zip(
        filename=archive.name,
        content=archive.read_bytes(),
        solvent=case["solvent"],  # type: ignore[arg-type]
        nucleus="1H",
        expected_total_h=structure.total_hydrogens,
        expected_non_labile_h=structure.non_labile_hydrogens,
    )
    peaks = list(report.inferred_peaks)
    return {
        "structure": structure,
        "reported_total_h": sum(float(p.integration_h) for p in peaks),
        "peaks": peaks,
        "metadata": report.metadata,
    }


@pytest.mark.skipif(not CASES, reason="nmrshiftdb2 structure-paired fixtures unavailable")
@pytest.mark.parametrize("case", CASES, ids=[str(c["id"]) for c in CASES])
class TestRealSpectraProtonTotals:
    def test_reported_total_is_the_right_order_of_magnitude(
        self, case: dict[str, object]
    ) -> None:
        result = _analyse(case)
        structure = result["structure"]
        true_h = float(structure.total_hydrogens)  # type: ignore[attr-defined]
        reported = float(result["reported_total_h"])  # type: ignore[arg-type]
        assert reported <= true_h * MAX_TOTAL_H_RATIO, (
            f"{structure.formula} contains {true_h:g} H but the pipeline reports "  # type: ignore[attr-defined]
            f"{reported:.1f} H across {len(result['peaks'])} peaks "  # type: ignore[arg-type]
            f"({reported / true_h:.1f}x). Integrals presented as proton counts "
            "must be the right order of magnitude."
        )

    def test_no_single_peak_exceeds_the_whole_molecule(
        self, case: dict[str, object]
    ) -> None:
        """A resonance cannot contain more protons than the compound has."""
        result = _analyse(case)
        structure = result["structure"]
        true_h = float(structure.total_hydrogens)  # type: ignore[attr-defined]
        peaks = result["peaks"]
        assert isinstance(peaks, list)
        worst = max((float(p.integration_h) for p in peaks), default=0.0)
        assert worst <= true_h, (
            f"{structure.formula} has {true_h:g} H in total, but one peak is "  # type: ignore[attr-defined]
            f"reported as {worst:g} H. A single environment cannot hold more "
            "protons than the molecule contains."
        )

    def test_phantom_half_proton_peaks_do_not_dominate(
        self, case: dict[str, object]
    ) -> None:
        """Noise must not be promoted into protons.

        Clamping every detected maximum up to a 0.5 H floor turned a long tail
        of noise into a large, entirely fabricated share of the integral.
        """
        result = _analyse(case)
        peaks = result["peaks"]
        assert isinstance(peaks, list)
        if not peaks:
            return
        floor_peaks = [p for p in peaks if abs(float(p.integration_h) - 0.5) < 1e-9]
        floor_share = sum(float(p.integration_h) for p in floor_peaks) / max(
            1e-9, sum(float(p.integration_h) for p in peaks)
        )
        assert floor_share <= 0.25, (
            f"{len(floor_peaks)} of {len(peaks)} peaks sit exactly on the 0.5 H "
            f"floor and carry {floor_share:.0%} of the reported integral; that "
            "share is quantiser output rather than measured signal."
        )
