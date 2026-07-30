"""Golden-set A/B harness for the 1H proton-inventory pipeline.

Two layers of protection:

1. ``TestGoldenSnapshots`` freezes the full observed/expected/delta payload for
   a set of representative cases. Any behaviour change produces a reviewable,
   itemised diff instead of a silent renumbering. Regenerate deliberately with::

       MOLTRACE_GOLDEN_UPDATE=1 .venv/bin/python -m pytest tests/test_nmr_inventory_golden.py

2. ``TestScientificInvariants`` asserts statements that must hold for *any*
   molecule regardless of implementation. These are not snapshots — they encode
   chemistry, so a snapshot regeneration can never quietly bless a wrong result.

The ``protected_aminoglycoside_cd3od`` case reproduces a real reported defect: a
per-benzyl/Cbz-protected tobramycin derivative in CD3OD whose 4.4-6.0 ppm window
carries 8 H of benzylic OCH2Ph on top of the 2 genuine anomeric protons.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from nmrcheck.chemistry import structure_summary_from_smiles
from nmrcheck.models import StructureSummary
from nmrcheck.peak_categorization import (
    build_impurity_candidates,
    build_labile_hydrogen_summary,
    build_proton_inventory,
    enrich_peaks,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "nmr_inventory"
UPDATE_ENV = "MOLTRACE_GOLDEN_UPDATE"


def _peak(
    shift: float, mult: str, integration: float, *, text: bool = True
) -> dict[str, Any]:
    """Build a peak dict.

    ``text=True`` marks the peak as coming from a supplied 1H experimental
    string (``inventory_basis="nmr_text"``), which is how a pasted literature
    spectrum reaches the pipeline. ``text=False`` is the detector/spectrum
    basis used for real uploads, where residual-solvent and impurity-library
    windows are allowed to remove a peak from the analyte inventory.
    """
    peak: dict[str, Any] = {
        "shift_ppm": shift,
        "multiplicity": mult,
        "integration_h": integration,
        "j_values_hz": [],
    }
    if text:
        peak["inventory_basis"] = "nmr_text"
    return peak


# --- Case A -----------------------------------------------------------------
# Reported defect. The StructureSummary is built literally (not from SMILES) so
# the case pins the *reported numbers* independently of SMILES parsing:
#   69 H total, 6 labile NH, 63 non-labile, 35 aromatic, 28 aliphatic,
#   2 anomeric, 7 phenyl rings worth of aromatic atoms.
_PROTECTED_AMINOGLYCOSIDE = StructureSummary(
    smiles="[protected-aminoglycoside]",
    formula="C53H63N5O16",
    molecular_weight=1026.0,
    total_hydrogens=69,
    labile_hydrogens=6,
    oh_hydrogen_count=0,
    nh_hydrogen_count=6,
    sh_hydrogen_count=0,
    non_labile_hydrogens=63,
    aromatic_protons=35,
    aliphatic_protons=28,  # NOTE: RDKit counts every non-aromatic C-H, so this
    aromatic_atom_count=42,  # already contains the 2 anomeric H.
    olefinic_proton_count=0,
    anomeric_proton_count=2,
)

def _protected_aminoglycoside_peaks(*, text: bool) -> list[dict[str, Any]]:
    """Analyte peaks totalling 63 H, matching the reported panel.

    35 aromatic + 10 H in the 4.4-6.0 window (2 genuine anomeric doublets plus
    8 H of benzylic OCH2Ph from the protecting groups) + 18 H below 4.4 ppm.
    The two solvent resonances are always detector-basis so they stay out of
    the analyte total, exactly as the reported panel shows them.
    """
    return [
        _peak(7.30, "m", 35.0, text=text),  # 7 x C6H5
        _peak(5.45, "d", 1.0, text=text),  # anomeric H-1'
        _peak(5.30, "d", 1.0, text=text),  # anomeric H-1''
        _peak(5.20, "m", 4.0, text=text),  # benzylic OCH2Ph <- NOT anomeric
        _peak(5.10, "m", 4.0, text=text),  # benzylic OCH2Ph <- NOT anomeric
        _peak(4.87, "s", 30.0, text=False),  # HOD in CD3OD
        _peak(4.10, "m", 2.0, text=text),
        _peak(3.80, "m", 4.0, text=text),
        _peak(3.55, "m", 4.0, text=text),
        _peak(3.31, "s", 26.0, text=False),  # CHD2OD residual
        _peak(2.60, "m", 2.0, text=text),
        # The two broad singlets are detector-basis: they are contaminant
        # signals, not assignments from the experimental string. They are what
        # the reported panel surfaced as "labile candidates" whose stated
        # reason was, self-contradictingly, that they match an impurity shift.
        _peak(2.109, "br s", 0.5, text=False),
        _peak(1.95, "m", 3.0, text=text),
        _peak(1.55, "m", 3.0, text=text),
        _peak(1.247, "br s", 0.5, text=False),  # EtOAc / grease / n-hexane
    ]

# --- Cases B-D: real SMILES so chemistry.py changes are covered too ----------
_BENZYLIDENE_GLUCOSIDE = "CO[C@H]1O[C@H]2CO[CH](c3ccccc3)O[C@H]2[C@H](O)[C@H]1O"
_TOBRAMYCIN = (
    "NC[C@H]1O[C@H](O[C@@H]2[C@@H](N)C[C@@H](N)[C@H]"
    "(O[C@H]3O[C@H](CO)[C@@H](O)[C@H](N)[C@H]3O)[C@H]2O)[C@H](N)C[C@@H]1O"
)
_STYRENE = "C=Cc1ccccc1"


def _case_protected_aminoglycoside() -> dict[str, Any]:
    """Reported case: pasted 1H text, so analyte peaks survive the libraries."""
    return {
        "structure": _PROTECTED_AMINOGLYCOSIDE,
        "solvent": "CD3OD",
        "peaks": _protected_aminoglycoside_peaks(text=True),
    }


def _case_protected_aminoglycoside_spectrum() -> dict[str, Any]:
    """Same molecule and shifts arriving on the detector basis (a real upload).

    Without the nmr_text override the impurity library is free to claim analyte
    resonances: the 35 H aromatic multiplet lands 0.03 ppm from the tabulated
    benzene CH singlet, and an anomeric doublet lands 0.04 ppm from
    dichloromethane. Impurity assignment must not be able to delete the
    analyte's own signal from the proton inventory.
    """
    return {
        "structure": _PROTECTED_AMINOGLYCOSIDE,
        "solvent": "CD3OD",
        "peaks": _protected_aminoglycoside_peaks(text=False),
    }


def _case_protected_aminoglycoside_collapsed() -> dict[str, Any]:
    """Same molecule with the 4.4-6.0 band reported as ONE range multiplet.

    Literature experimental sections routinely report an envelope as a single
    assignment — "5.45-5.10 (m, 10H)". The parser keeps the range bounds but
    represents it at the midpoint, so the classifier sees one peak carrying
    10 H. A cap that selects the best N *peaks* then assigns all 10 H to
    anomeric, reproducing the original defect. The budget must be in protons.
    """
    return {
        "structure": _PROTECTED_AMINOGLYCOSIDE,
        "solvent": "CD3OD",
        "peaks": [
            _peak(7.30, "m", 35.0),
            _peak(5.25, "m", 10.0),  # 2 anomeric + 8 benzylic, unresolved
            _peak(3.60, "m", 18.0),
        ],
    }


def _case_benzylidene_glucoside() -> dict[str, Any]:
    # Aromatic-protected sugar: one true anomeric H (C-1) plus a benzylidene
    # acetal CH(Ph) that is a protecting group, not an anomeric proton.
    return {
        "structure": structure_summary_from_smiles(_BENZYLIDENE_GLUCOSIDE),
        "solvent": "CDCl3",
        "peaks": [
            _peak(7.45, "m", 5.0),
            _peak(5.52, "s", 1.0),  # benzylidene acetal CH(Ph)
            _peak(4.78, "d", 1.0),  # true anomeric H-1
            _peak(4.25, "m", 2.0),
            _peak(3.70, "m", 4.0),
            _peak(3.40, "s", 3.0),  # OMe
            _peak(2.40, "br s", 2.0),  # 2 x OH
        ],
    }


def _case_free_aminoglycoside() -> dict[str, Any]:
    # Control: unprotected aminoglycoside in D2O. The carbohydrate refinement
    # already works here today and must keep working.
    return {
        "structure": structure_summary_from_smiles(_TOBRAMYCIN),
        "solvent": "D2O",
        # Tobramycin is C18H37N5O9: 37 H total, 15 labile (5 OH + 10 NH),
        # 22 non-labile = 2 anomeric + 20 ring/chain CH/CH2. The analyte peaks
        # sum to exactly 22 H; HOD is detector-basis so it stays excluded.
        "peaks": [
            _peak(5.12, "d", 1.0),
            _peak(5.05, "d", 1.0),
            _peak(4.75, "s", 8.0, text=False),  # HOD
            _peak(3.90, "m", 6.0),
            _peak(3.45, "m", 6.0),
            _peak(2.85, "m", 4.0),
            _peak(1.90, "m", 2.0),
            _peak(1.40, "m", 2.0),
        ],
    }


def _case_olefinic_aromatic() -> dict[str, Any]:
    # Control: olefin + aromatic, no sugar. Guards against the carbohydrate
    # gate change leaking into ordinary alkene handling.
    return {
        "structure": structure_summary_from_smiles(_STYRENE),
        "solvent": "CDCl3",
        "peaks": [
            _peak(7.40, "m", 5.0),
            _peak(6.72, "dd", 1.0),
            _peak(5.75, "d", 1.0),
            _peak(5.25, "d", 1.0),
        ],
    }


CASES: dict[str, Any] = {
    "protected_aminoglycoside_cd3od": _case_protected_aminoglycoside,
    "protected_aminoglycoside_cd3od_spectrum": _case_protected_aminoglycoside_spectrum,
    "protected_aminoglycoside_cd3od_collapsed": _case_protected_aminoglycoside_collapsed,
    "benzylidene_glucoside_cdcl3": _case_benzylidene_glucoside,
    "free_aminoglycoside_d2o": _case_free_aminoglycoside,
    "olefinic_aromatic_cdcl3": _case_olefinic_aromatic,
}


def run_case(name: str) -> dict[str, Any]:
    """Run one case through the pipeline and return a normalised payload."""
    case = CASES[name]()
    structure: StructureSummary = case["structure"]
    solvent: str = case["solvent"]

    enriched = enrich_peaks(
        peaks=case["peaks"],
        nucleus="1H",
        solvent=solvent,
        structure=structure,
    )
    inventory = build_proton_inventory(
        peaks=enriched, structure=structure, nucleus="1H", solvent=solvent
    )
    labile = build_labile_hydrogen_summary(
        peaks=enriched, structure=structure, solvent=solvent
    )
    impurities = build_impurity_candidates(peaks=enriched)

    return {
        "solvent": solvent,
        "structure": {
            "formula": structure.formula,
            "total_hydrogens": structure.total_hydrogens,
            "labile_hydrogens": structure.labile_hydrogens,
            "non_labile_hydrogens": structure.non_labile_hydrogens,
            "aromatic_protons": structure.aromatic_protons,
            "aliphatic_protons": structure.aliphatic_protons,
            "aromatic_atom_count": structure.aromatic_atom_count,
            "anomeric_proton_count": structure.anomeric_proton_count,
            "olefinic_proton_count": structure.olefinic_proton_count,
        },
        "categories": [
            {
                "shift_ppm": p.get("shift_ppm"),
                "category": p.get("category"),
                "labile_hint": p.get("labile_hint"),
            }
            for p in enriched
        ],
        "inventory": inventory,
        "labile": labile,
        "impurities": impurities,
    }


def _normalise(value: Any) -> Any:
    """Round floats so trivial FP jitter never shows up as a golden diff."""
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    return value


@pytest.mark.parametrize("name", sorted(CASES))
class TestGoldenSnapshots:
    def test_matches_golden(self, name: str) -> None:
        actual = _normalise(run_case(name))
        path = GOLDEN_DIR / f"{name}.json"

        if os.environ.get(UPDATE_ENV):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
            pytest.skip(f"golden regenerated: {path.name}")

        assert path.exists(), (
            f"missing golden {path}; regenerate with {UPDATE_ENV}=1"
        )
        expected = json.loads(path.read_text())
        assert actual == expected, (
            f"{name}: output drifted from golden. Review the diff; regenerate "
            f"with {UPDATE_ENV}=1 only once the change is understood and intended."
        )


class TestImpurityIdentification:
    """A physical peak has one identity, ranked against its alternatives."""

    def test_residual_solvent_wins_ties_over_arbitrary_contaminants(self) -> None:
        from nmrcheck.impurities import match_h1_impurity_shifts

        matches = match_h1_impurity_shifts(7.26, "CDCl3")
        assert matches, "expected library hits at the CDCl3 residual shift"
        # 7.26 is the CDCl3 residual. Ranking used to break ties alphabetically,
        # which let "chloroform CH" outrank "solvent residual peak" on spelling.
        assert matches[0]["kind"] in {"residual", "water"}, (
            f"residual solvent should win at its own shift, got {matches[0]['label']}"
        )

    def test_partner_shifts_are_available_for_corroboration(self) -> None:
        from nmrcheck.impurities import partner_shifts_for_compound

        # Ethyl acetate is a multi-signal contaminant: identifying it from one
        # shift alone, with none of its other resonances present, is a
        # coincidence rather than an identification.
        partners = partner_shifts_for_compound("ethyl acetate", "CDCl3")
        assert len(partners) >= 2, (
            f"ethyl acetate should expose partner resonances, got {partners}"
        )

    def test_single_peak_yields_one_candidate_with_alternatives(self) -> None:
        from nmrcheck.models import Peak
        from nmrcheck.spectrum import _build_impurity_candidates

        # 1.247 ppm in CDCl3 sits inside the windows of several tabulated
        # contaminants at once (ethanol CH3, ethyl acetate CH3, grease CH2).
        candidates = _build_impurity_candidates(
            [Peak(shift_ppm=1.247, multiplicity="br s", integration_h=0.5, j_values_hz=[])],
            "CDCl3",
        )
        at_shift = [c for c in candidates if c.get("shift_ppm") == 1.247]
        assert len(at_shift) == 1, (
            f"one peak must yield one identity, got {len(at_shift)}: "
            f"{[c['library_match']['label'] for c in at_shift]}"
        )
        candidate = at_shift[0]
        assert candidate.get("alternatives"), "runners-up must be kept as alternatives"
        corroboration = candidate.get("corroboration") or {}
        assert "confirmed" in corroboration
        # The compound's other resonances are absent from this one-peak
        # spectrum, so the identification must not be presented as confirmed.
        assert corroboration.get("confirmed") is False
        assert "unconfirmed" in candidate["reason"]


@pytest.mark.parametrize("name", sorted(CASES))
class TestScientificInvariants:
    """Truths that hold for any molecule, independent of implementation."""

    def test_observed_anomeric_never_exceeds_structural_expectation(
        self, name: str
    ) -> None:
        result = run_case(name)
        expected = result["inventory"].get("expected") or {}
        observed = result["inventory"]["observed"]
        if "anomeric_or_olefinic" not in expected:
            pytest.skip("no structural expectation for this case")
        assert observed["anomeric_or_olefinic"] <= expected["anomeric_or_olefinic"], (
            f"{name}: assigned {observed['anomeric_or_olefinic']} H to a window the "
            f"structure can only supply {expected['anomeric_or_olefinic']} H for. "
            "A molecule cannot have more anomeric/olefinic protons than it has."
        )

    def test_expected_classes_partition_the_non_labile_total(self, name: str) -> None:
        result = run_case(name)
        expected = result["inventory"].get("expected") or {}
        if not expected:
            pytest.skip("no structural expectation for this case")
        parts = sum(
            float(expected.get(key, 0) or 0)
            for key in (
                "aromatic",
                "anomeric_or_olefinic",
                "aliphatic",
                "carbohydrate_sugar",
                "aldehyde",
                "carboxylic_acid",
            )
        )
        assert parts == float(expected["non_labile"]), (
            f"{name}: expected class rows sum to {parts} but the reported "
            f"non-labile total is {expected['non_labile']}. The per-class "
            "expectations must be a partition, otherwise the deltas can never "
            "all reach zero for a correct spectrum."
        )

    def test_one_physical_peak_yields_at_most_one_impurity_identity(
        self, name: str
    ) -> None:
        result = run_case(name)
        shifts = [c.get("shift_ppm") for c in result["impurities"]]
        duplicates = {s for s in shifts if shifts.count(s) > 1}
        assert not duplicates, (
            f"{name}: shifts {sorted(duplicates)} are each reported as more than "
            "one impurity. A physical peak has one identity; alternatives belong "
            "in a ranked list, not as sibling candidates."
        )

    def test_a_peak_is_never_both_impurity_and_labile_evidence(
        self, name: str
    ) -> None:
        result = run_case(name)
        impurity_shifts = {c.get("shift_ppm") for c in result["impurities"]}
        labile_shifts = {
            c.get("shift_ppm") for c in (result["labile"].get("observed") or [])
        }
        overlap = impurity_shifts & labile_shifts
        assert not overlap, (
            f"{name}: shifts {sorted(overlap)} are counted as curated impurities "
            "AND as exchangeable-proton evidence. The same peak cannot be both."
        )

    def test_class_partitions_conserve_each_peak_integration(
        self, name: str
    ) -> None:
        """A split multiplet must not lose or invent protons.

        When an unresolved signal is divided between two classes, the parts
        have to sum to the peak's own integration, otherwise the class rows
        stop agreeing with the grand total.
        """
        case = CASES[name]()
        structure = case["structure"]
        enriched = enrich_peaks(
            peaks=case["peaks"],
            nucleus="1H",
            solvent=case["solvent"],
            structure=structure,
        )
        for peak in enriched:
            partition = peak.get("inventory_partition")
            if not partition:
                continue
            integration = peak.get("integration_h")
            assert isinstance(integration, (int, float))
            assert sum(partition.values()) == pytest.approx(
                float(integration), abs=1e-3
            ), (
                f"{name}: peak at {peak.get('shift_ppm')} ppm partitions to "
                f"{sum(partition.values())} H but carries {integration} H"
            )

    def test_impurity_assignment_never_consumes_the_analyte_budget(
        self, name: str
    ) -> None:
        """Impurities are by definition minor components.

        A tabulated impurity shift lying within tolerance of an analyte
        resonance must not be grounds to delete that resonance: the structure
        is the stronger prior. Guards against e.g. a 35 H aromatic multiplet
        being reclassified as the benzene CH singlet and vanishing from the
        inventory.
        """
        result = run_case(name)
        expected = result["inventory"].get("expected") or {}
        if not expected:
            pytest.skip("no structural expectation for this case")
        observed_non_labile = float(result["inventory"]["observed"]["non_labile"])
        expected_non_labile = float(expected["non_labile"])
        assert observed_non_labile >= 0.5 * expected_non_labile, (
            f"{name}: only {observed_non_labile} of {expected_non_labile} expected "
            "non-labile H survived classification. The solvent/impurity libraries "
            "are consuming analyte signal rather than annotating it."
        )

    def test_exchanging_solvent_does_not_report_a_labile_deficit(
        self, name: str
    ) -> None:
        result = run_case(name)
        solvent = str(result["solvent"]).upper().replace("-", "")
        exchanging = solvent in {"D2O", "CD3OD", "METHANOLD4", "CD3OD+D2O"}
        if not exchanging:
            pytest.skip("solvent does not exchange labile protons")
        # Match the labile ROW specifically. A bare "labile" substring also
        # matches the unrelated "non_labile" row.
        deficit_warnings = [
            w
            for w in result["inventory"].get("warnings", [])
            if "Observed labile integration" in w
        ]
        assert not deficit_warnings, (
            f"{name}: solvent {result['solvent']} exchanges OH/NH, so their "
            f"absence is the expected result, not a deviation. Got: {deficit_warnings}"
        )
