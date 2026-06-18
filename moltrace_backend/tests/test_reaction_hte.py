"""Tests for Repho R3: HTE / DoE plate-design engine (pure, deterministic).

These exercise only the engine (`reaction_hte`) — no app/client fixtures — so they are
independent of the rest of the API surface. The store/route wiring lands in a later slice.
"""

import csv
import io
import json

import pytest

from nmrcheck import reaction_hte as hte


def test_sobol_fills_plate_and_respects_bounds_and_fixed():
    design = hte.generate_plate_design(
        numeric={"temperature_c": (40, 80)},
        categorical={"solvent": ["MeCN", "THF", "DMF"]},
        fixed={"base": "K2CO3"},
        plate_format="96",
        strategy="sobol",
    )
    assert design["well_count"] == 96
    assert design["wells"][0]["well_id"] == "A1"
    assert design["wells"][-1]["well_id"] == "H12"
    for well in design["wells"]:
        c = well["conditions"]
        assert 40 <= c["temperature_c"] <= 80
        assert c["solvent"] in {"MeCN", "THF", "DMF"}
        assert c["base"] == "K2CO3"  # fixed applied to every well


def test_design_is_deterministic_for_a_seed():
    kwargs = dict(numeric={"t": (0, 1)}, categorical={"s": ["A", "B", "C"]}, plate_format="96", strategy="sobol")
    assert hte.generate_plate_design(**kwargs)["wells"] == hte.generate_plate_design(**kwargs)["wells"]


def test_lhs_fills_plate():
    assert hte.generate_plate_design(numeric={"t": (0, 1)}, plate_format="96", strategy="lhs")["well_count"] == 96


def test_factorial_is_full_grid_then_truncated():
    # 2 categorical (2 each) x numeric (3 levels) = 12 combinations
    design = hte.generate_plate_design(
        numeric={"t": (40, 80)},
        categorical={"s": ["A", "B"], "c": ["X", "Y"]},
        strategy="factorial",
        plate_format="96",
    )
    assert design["well_count"] == 12
    # truncation warning when the grid exceeds the plate
    big = hte.generate_plate_design(
        categorical={f"v{i}": ["a", "b", "c", "d"] for i in range(4)},  # 256 combos
        strategy="factorial",
        plate_format="96",
    )
    assert big["well_count"] == 96
    assert any("truncated" in w for w in big["warnings"])


def test_excluded_combinations_are_filtered():
    design = hte.generate_plate_design(
        categorical={"solvent": ["MeCN", "THF", "DMF"]},
        excluded=[{"solvent": "MeCN"}],
        plate_format="24",
        strategy="lhs",
    )
    assert design["well_count"] > 0
    assert all(w["conditions"]["solvent"] != "MeCN" for w in design["wells"])


def test_bo_init_caps_at_seed_population():
    design = hte.generate_plate_design(numeric={"t": (0, 1)}, plate_format="96", strategy="bo_init")
    assert design["well_count"] == 20  # min(20, capacity)


def test_well_ids_for_each_plate_format():
    assert hte.generate_plate_design(numeric={"t": (0, 1)}, plate_format="24")["wells"][-1]["well_id"] == "D6"
    assert hte.generate_plate_design(numeric={"t": (0, 1)}, plate_format="384")["wells"][-1]["well_id"] == "P24"


def test_export_csv_has_header_and_one_row_per_well():
    design = hte.generate_plate_design(
        numeric={"temperature_c": (40, 80)}, categorical={"solvent": ["MeCN", "THF"]}, plate_format="24"
    )
    out = hte.export_plate(design, "csv")
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == ["well_id", "temperature_c", "solvent"]
    assert len(rows) - 1 == design["well_count"]


def test_export_json_roundtrips():
    design = hte.generate_plate_design(numeric={"t": (0, 1)}, plate_format="24")
    parsed = json.loads(hte.export_plate(design, "json"))
    assert parsed["well_count"] == design["well_count"]
    assert parsed["plate_format"] == "24"


def test_unsupported_inputs_raise():
    with pytest.raises(ValueError):
        hte.generate_plate_design(plate_format="48")
    with pytest.raises(ValueError):
        hte.generate_plate_design(strategy="genetic")
    with pytest.raises(ValueError):
        hte.export_plate({"wells": []}, "xml")
