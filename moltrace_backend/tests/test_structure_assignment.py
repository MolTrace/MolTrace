"""Structure-constrained global assignment (default-off engine)."""

from __future__ import annotations

import pytest

from nmrcheck.structure_assignment import (
    ENV_FLAG,
    assign_from_smiles,
    assign_signals,
    enumerate_proton_environments,
    structure_assignment_enabled,
)

# Aromatic-protected sugar: one true anomeric H plus a benzylidene acetal CH.
BENZYLIDENE_GLUCOSIDE = "CO[C@H]1O[C@H]2CO[CH](c3ccccc3)O[C@H]2[C@H](O)[C@H]1O"
TOBRAMYCIN = (
    "NC[C@H]1O[C@H](O[C@@H]2[C@@H](N)C[C@@H](N)[C@H]"
    "(O[C@H]3O[C@H](CO)[C@@H](O)[C@H](N)[C@H]3O)[C@H]2O)[C@H](N)C[C@@H]1O"
)


class TestFeatureFlag:
    def test_default_is_off(self) -> None:
        assert structure_assignment_enabled({}) is False

    def test_explicit_enable_values(self) -> None:
        for value in ("1", "true", "TRUE", "yes", "on"):
            assert structure_assignment_enabled({ENV_FLAG: value}) is True
        for value in ("0", "false", "", "off"):
            assert structure_assignment_enabled({ENV_FLAG: value}) is False


class TestEnvironmentEnumeration:
    def test_equivalent_protons_form_one_environment(self) -> None:
        # tert-butyl: nine protons, one environment — not nine environments.
        envs = enumerate_proton_environments("CC(C)(C)O")
        methyl = [e for e in envs if e.proton_count == 9]
        assert methyl, f"expected a 9-proton environment, got {[e.proton_count for e in envs]}"

    def test_proton_counts_sum_to_the_molecular_formula(self) -> None:
        # Benzene: 6 aromatic H in a single symmetry class.
        envs = enumerate_proton_environments("c1ccccc1")
        assert sum(e.proton_count for e in envs) == 6
        assert len(envs) == 1

    def test_labile_environments_are_marked_exchangeable(self) -> None:
        envs = enumerate_proton_environments("CCO")
        labile = [e for e in envs if e.exchangeable]
        assert len(labile) == 1
        assert labile[0].proton_count == 1


class TestConservationIsStructural:
    def test_an_environment_cannot_absorb_more_protons_than_it_has(self) -> None:
        """The defect this engine exists to make impossible.

        Ten protons of observed signal sit in the 4.4-6.0 ppm window, but the
        structure supports only one anomeric proton there. Under window-based
        classification all ten were reported as anomeric. Here the anomeric
        environment's demand is its proton count, so it cannot receive more —
        no cap, no gate, no heuristic required.
        """
        envs = enumerate_proton_environments(BENZYLIDENE_GLUCOSIDE)
        anomeric = [e for e in envs if "anomeric" in e.kind]
        assert anomeric, "expected an anomeric environment"

        # Pile 10 H of signal into the anomeric window.
        signals = [(5.20, 4.0), (5.10, 4.0), (4.78, 1.0), (5.45, 1.0)]
        result = assign_signals(
            environments=envs, signals=signals, solvent="CDCl3"
        )
        assert result.feasible, result.notes
        for env in anomeric:
            assigned = result.assigned.get(env.key, 0.0)
            assert assigned <= env.proton_count + 1e-6, (
                f"{env.key} received {assigned} H but contains only "
                f"{env.proton_count}. Conservation must be a hard constraint."
            )

    def test_excess_signal_is_routed_to_the_contaminant_sink(self) -> None:
        """Unexplainable signal is reported, never forced onto a proton."""
        envs = enumerate_proton_environments("c1ccccc1")  # 6 aromatic H
        signals = [(7.26, 6.0), (1.25, 3.0)]  # 3 H the structure cannot host
        result = assign_signals(environments=envs, signals=signals, solvent="CDCl3")
        assert result.feasible, result.notes
        assert result.contaminant_h == pytest.approx(3.0, abs=1e-3)

    def test_missing_signal_is_unexplained_not_invented_contamination(self) -> None:
        envs = enumerate_proton_environments("c1ccccc1")  # 6 aromatic H
        result = assign_signals(
            environments=envs, signals=[(7.26, 4.0)], solvent="CDCl3"
        )
        assert result.feasible, result.notes
        assert result.unexplained_h == pytest.approx(2.0, abs=1e-3)
        assert result.contaminant_h == pytest.approx(0.0, abs=1e-6)


class TestSolventExchange:
    def test_labile_environments_are_excluded_in_an_exchanging_solvent(self) -> None:
        result = assign_from_smiles(
            smiles=TOBRAMYCIN,
            signals=[(5.12, 1.0), (5.05, 1.0), (3.90, 12.0), (2.85, 4.0), (1.60, 4.0)],
            solvent="D2O",
        )
        assert result.feasible, result.notes
        # Tobramycin carries 15 labile H (5 OH + 10 NH); in D2O none are visible.
        assert result.exchanged_h == pytest.approx(15.0, abs=1e-6)
        assert any("exchanges" in note for note in result.notes)

    def test_labile_environments_are_kept_in_a_non_exchanging_solvent(self) -> None:
        result = assign_from_smiles(
            smiles="CCO", signals=[(3.7, 2.0), (1.2, 3.0), (2.4, 1.0)], solvent="CDCl3"
        )
        assert result.feasible, result.notes
        assert result.exchanged_h == pytest.approx(0.0, abs=1e-6)


class TestAgainstTheWindowClassifier:
    """A/B: does the engine reach the classifier's answer independently?

    The window classifier gets the protected-sugar case right only because a
    conservation cap was added to it. The assignment engine has no cap — the
    proton count IS the constraint — so agreement here is evidence the two
    routes converge for the right reason rather than by shared special-casing.
    """

    def test_engine_reproduces_corrected_classification_without_a_cap(self) -> None:
        from nmrcheck.structure_assignment import class_rollup

        # Aromatic-protected glucoside: 5 aromatic H, ONE anomeric H, plus a
        # benzylidene acetal CH that resonates in the same 4.4-6.0 band.
        signals = [
            (7.45, 5.0),  # aromatic
            (5.52, 1.0),  # benzylidene acetal CH -> NOT anomeric
            (4.78, 1.0),  # true anomeric
            (4.25, 2.0),
            (3.70, 4.0),
            (3.40, 3.0),
        ]
        result = assign_from_smiles(
            smiles=BENZYLIDENE_GLUCOSIDE, signals=signals, solvent="CDCl3"
        )
        assert result.feasible, result.notes
        rollup = class_rollup(result)

        assert rollup["aromatic"] == pytest.approx(5.0, abs=1e-3)
        # Exactly one anomeric proton, even though 2 H of signal sit in the
        # anomeric window. No cap involved: the environment holds one proton.
        assert rollup["anomeric_or_olefinic"] == pytest.approx(1.0, abs=1e-3)
        # The benzylidene CH is counted as a protecting-group methine.
        assert rollup["aliphatic"] == pytest.approx(10.0, abs=1e-3)

    def test_arylidene_acetal_is_not_bucketed_as_anomeric(self) -> None:
        from nmrcheck.structure_assignment import bucket_for_kind

        assert bucket_for_kind("arylidene_acetal_proton") == "aliphatic"
        assert bucket_for_kind("anomeric_or_acetal_proton") == "anomeric_or_olefinic"
        assert bucket_for_kind("labile_OH") == "labile"


class TestAssignmentQuality:
    def test_signal_lands_on_the_environment_its_shift_predicts(self) -> None:
        # Ethylbenzene-like: aromatic H near 7.2, CH2 near 2.6, CH3 near 1.2.
        result = assign_from_smiles(
            smiles="CCc1ccccc1",
            signals=[(7.25, 5.0), (2.62, 2.0), (1.22, 3.0)],
            solvent="CDCl3",
        )
        assert result.feasible, result.notes
        by_signal: dict[int, str] = {}
        for flow in result.flows:
            by_signal.setdefault(flow["signal_index"], flow["kind"])
        assert "aromatic" in by_signal[0], f"7.25 ppm assigned to {by_signal[0]}"

    def test_payload_round_trips(self) -> None:
        payload = assign_from_smiles(
            smiles="CCO", signals=[(3.7, 2.0), (1.2, 3.0)], solvent="D2O"
        ).to_payload()
        assert payload["feasible"] is True
        assert isinstance(payload["environments"], list)
        assert all("assigned_h" in env for env in payload["environments"])
        assert payload["exchanged_h"] == pytest.approx(1.0, abs=1e-6)
