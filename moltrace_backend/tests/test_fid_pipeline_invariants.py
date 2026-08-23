"""Output-invariance goldens for the raw-FID pipeline (Prompt 2 science gate).

The Instant-FID latency work rewrites the *how* of ``process_bruker_1d_zip``
(single baseline estimate, decimated auto-phase scoring, decimated sensitivity
sweep, ndarray containers) while promising the *what* is untouched. These tests
are that promise, written before the optimizations: they run the real pipeline
over the public nmrshiftdb2 Bruker fixtures and pin every scientifically
meaningful output — chosen peak-detection sensitivity, the peak list (shifts,
integrals, multiplicities), phase mode and (p0, p1) to display precision,
baseline mode, and a downsampled-preview aggregate — to committed golden files.

A legitimate science change (Prompt 5 territory, not Prompt 2) re-baselines
visibly by regenerating the goldens and explaining the diff in the same commit:

    MOLTRACE_REGEN_FID_GOLDEN=1 uv run pytest tests/test_fid_pipeline_invariants.py -m ''

The fast tier (one small 1H fixture, both guidance modes) runs in the default
suite. The full corpus tier is marked ``slow`` like the other multi-FID guards.

Multiplicity is the one output that is a DISCRETE label derived by thresholding a
continuous fit — the resolved line count and the adjacent-line spacings that come
out of the deconvolution's ``least_squares`` pass. A quantity of that shape
inherits the fit's spread at its band edges, and a handful of genuinely-ambiguous
multiplets sit close enough to an edge that Linux/x86 LAPACK and macOS/ARM
Accelerate land on different labels from the same converged fit. Those peaks are
named, with the measurement that establishes the ambiguity, in the committed
:data:`BOUNDARY_REGISTER`; for them — and only them — the discrete label relaxes
to a stated set while shift and integration stay strictly pinned. Everything about
keeping that register honest is in ``boundary_register.json`` and in the guard-rail
tests at the foot of this module.
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "nmrshiftdb2"
NMREDATA = FIXTURES / "source" / "nmrshiftdb2rawdata.nmredata.sd"
GOLDEN_DIR = Path(__file__).parent / "golden" / "fid_invariants"
REGEN = os.environ.get("MOLTRACE_REGEN_FID_GOLDEN") == "1"

# Display precision for phase angles is 3 decimal places (fid.py rounds p0/p1
# with round(..., 3)); a half-unit-in-the-last-place bound on that rounding.
PHASE_TOL_DEG = 5e-3
SHIFT_TOL_PPM = 1e-4
INTEGRAL_TOL_H = 1e-3

# One small 1H fixture keeps the default-suite cost to a few seconds while the
# full corpus rides behind the slow marker with the other >30 s guards.
FAST_SPECTRA = {"60000023"}

# Genuinely-ambiguous multiplets, named with their evidence. See the file's own
# _comment block for the rules; the guard-rail tests at the foot of this module
# enforce them.
BOUNDARY_REGISTER_PATH = GOLDEN_DIR / "boundary_register.json"

# The register's size is pinned HERE rather than inside the register file, so
# adding an entry is a two-file edit a reviewer cannot miss. A register that grows
# between releases is a signal that a tolerance or a band edge is wrong -- growth
# is never routine maintenance, and a fixture may not be moved into the register
# to make a failing run pass.
EXPECTED_BOUNDARY_REGISTER_ENTRIES = 4

# "darwin-arm64" / "linux-x86_64" -- the axis the divergence runs along.
PLATFORM_TAG = f"{platform.system().lower()}-{platform.machine().lower()}"


def _load_boundary_register() -> dict[tuple[str, int], dict[str, Any]]:
    """(case_id, peak_index) -> register entry."""
    if not BOUNDARY_REGISTER_PATH.exists():
        return {}
    payload = json.loads(BOUNDARY_REGISTER_PATH.read_text())
    return {(entry["case"], int(entry["peak"])): entry for entry in payload["entries"]}


BOUNDARY_REGISTER = _load_boundary_register()

# What each registered peak actually produced in this run, so the register can be
# reported rather than buried in a file nobody opens.
_REGISTER_OBSERVATIONS: dict[tuple[str, int], str] = {}


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


def _cases() -> list[dict[str, Any]]:
    if not FIXTURES.exists():
        return []
    smiles, solvent = _structure_index()
    cases: list[dict[str, Any]] = []
    for archive in sorted((FIXTURES / "raw").glob("nmrshiftdb2_*_1h.zip")):
        spectrum_id = archive.stem.split("_")[1]
        base = {
            "spectrum_id": spectrum_id,
            "archive": archive,
            "nucleus": "1H",
            "solvent": solvent.get(spectrum_id) or None,
        }
        # Unguided: the 5-candidate sensitivity sweep, relative integrals.
        cases.append({**base, "config": "unguided", "smiles": None})
        # Structure-guided: the 7-candidate sweep plus deconvolution pass.
        if spectrum_id in smiles:
            cases.append({**base, "config": "guided", "smiles": smiles[spectrum_id]})
    for archive in sorted((FIXTURES / "raw").glob("nmrshiftdb2_*_13c.zip"))[:2]:
        spectrum_id = archive.stem.split("_")[1]
        cases.append(
            {
                "spectrum_id": spectrum_id,
                "archive": archive,
                "nucleus": "13C",
                "solvent": solvent.get(spectrum_id) or None,
                "config": "unguided",
                "smiles": None,
            }
        )
    return cases


CASES = _cases()


def _case_id(case: dict[str, Any]) -> str:
    return f"{case['spectrum_id']}_{case['nucleus'].lower()}_{case['config']}"


# No 1H-1H scalar coupling reaches this. The window the classifier actually
# applies (nmrcheck.gsd._MAX_J_HZ, 30.0) is tighter and carries its own corpus
# measurement; this is the looser backstop, stated independently here -- above
# that window, below the smallest spurious separation the corpus contains
# (43.52 Hz) -- so a future widening has to fail a test that never referenced
# the constant it widened. A J above this means two unrelated signals were
# clustered and reported as one first-order multiplet, which is what shipped
# while the window sat at 60 Hz.
IMPOSSIBLE_J_HZ = 35.0


def _assert_reported_couplings_are_physical(case_id: str, report: Any) -> None:
    """No peak may report a J that no proton-proton coupling can produce."""
    for index, peak in enumerate(report.inferred_peaks):
        for j_hz in peak.j_values_hz or ():
            assert float(j_hz) <= IMPOSSIBLE_J_HZ, (
                f"{case_id} peak {index} at {peak.shift_ppm:.3f} ppm reports "
                f"J = {float(j_hz):.2f} Hz as a {peak.multiplicity!r}. No 1H-1H "
                "coupling is that large, so those lines are separate signals "
                "that were clustered together, not one multiplet."
            )


def _run_pipeline(case: dict[str, Any]) -> dict[str, Any]:
    from nmrcheck.fid import process_bruker_1d_zip

    expected_total_h = expected_non_labile_h = None
    if case["smiles"] is not None:
        from nmrcheck.chemistry import structure_summary_from_smiles

        structure = structure_summary_from_smiles(case["smiles"])
        expected_total_h = structure.total_hydrogens
        expected_non_labile_h = structure.non_labile_hydrogens

    archive: Path = case["archive"]
    report = process_bruker_1d_zip(
        filename=archive.name,
        content=archive.read_bytes(),
        solvent=case["solvent"],
        nucleus=case["nucleus"],
        expected_total_h=expected_total_h,
        expected_non_labile_h=expected_non_labile_h,
    )
    _assert_reported_couplings_are_physical(_case_id(case), report)
    metadata = report.metadata or {}
    phase = metadata.get("phase") or {}
    baseline = metadata.get("baseline") or {}
    preview = report.preview_points
    y_values = [float(p.intensity) for p in preview]
    y_max = max(y_values) if y_values else 0.0
    x_at_y_max = float(preview[y_values.index(y_max)].shift_ppm) if y_values else 0.0
    return {
        "point_count": int(report.point_count),
        "phase": {
            "mode": phase.get("mode"),
            "p0": float(phase.get("p0") or 0.0),
            "p1": float(phase.get("p1") or 0.0),
            "correction_applied": bool(phase.get("correction_applied")),
        },
        "baseline": {
            "mode": baseline.get("mode"),
            "order": baseline.get("order"),
            "correction_applied": bool(baseline.get("correction_applied")),
        },
        "peak_detection_sensitivity": metadata.get("peak_detection_sensitivity"),
        "peaks": [
            {
                "shift_ppm": round(float(p.shift_ppm), 6),
                "integration_h": round(float(p.integration_h), 6),
                "multiplicity": p.multiplicity,
            }
            for p in report.inferred_peaks
        ],
        "preview": {
            "n": len(preview),
            "y_sum": float(sum(y_values)),
            "y_max": y_max,
            "x_at_y_max": x_at_y_max,
        },
    }


def _golden_path(case: dict[str, Any]) -> Path:
    return GOLDEN_DIR / f"{_case_id(case)}.json"


def _assert_matches_golden(
    observed: dict[str, Any], golden: dict[str, Any], case_id: str
) -> None:
    assert observed["point_count"] == golden["point_count"]

    assert observed["phase"]["mode"] == golden["phase"]["mode"]
    assert observed["phase"]["correction_applied"] == golden["phase"]["correction_applied"]
    assert observed["phase"]["p0"] == pytest.approx(golden["phase"]["p0"], abs=PHASE_TOL_DEG)
    assert observed["phase"]["p1"] == pytest.approx(golden["phase"]["p1"], abs=PHASE_TOL_DEG)

    assert observed["baseline"] == golden["baseline"]

    assert observed["peak_detection_sensitivity"] == pytest.approx(
        golden["peak_detection_sensitivity"], abs=1e-9
    )

    assert len(observed["peaks"]) == len(golden["peaks"]), (
        f"peak count changed: {len(golden['peaks'])} -> {len(observed['peaks'])}"
    )
    for i, (obs, gold) in enumerate(zip(observed["peaks"], golden["peaks"], strict=True)):
        entry = BOUNDARY_REGISTER.get((case_id, i))
        if entry is None:
            assert obs["multiplicity"] == gold["multiplicity"], f"peak {i} multiplicity"
        else:
            # A registered peak's DISCRETE label is relaxed -- to the stated set of
            # labels the fit is known to land on, never to anything at all. A label
            # outside that set means the fit reached a minimum the register has not
            # seen, which is a finding to investigate, not an entry to widen.
            allowed = entry["allowed_multiplicity"]
            assert obs["multiplicity"] in allowed, (
                f"peak {i} multiplicity {obs['multiplicity']!r} is not one of the labels "
                f"registered as ambiguous for {case_id} peak {i} ({'|'.join(allowed)}) "
                f"on {PLATFORM_TAG}. {entry['reason']} Investigate the new label; do not "
                "widen the entry to absorb it."
            )
        # Shift and integration stay strict for registered peaks too. Only the
        # discrete label inherits the fit's spread; these are continuous
        # quantities carrying their own measured tolerances, and a registered peak
        # that vanishes, moves, or re-integrates is still a failure.
        assert obs["shift_ppm"] == pytest.approx(gold["shift_ppm"], abs=SHIFT_TOL_PPM), (
            f"peak {i} shift"
        )
        assert obs["integration_h"] == pytest.approx(
            gold["integration_h"], abs=INTEGRAL_TOL_H
        ), f"peak {i} integration"

    # preview.n is the CARDINALITY of the down-sampled display trace, not a
    # scientific quantity — the meaningful content of the preview is pinned by
    # y_max / x_at_y_max / y_sum below, each already with a tolerance. The count
    # itself is |{per-bucket min/max indices} ∪ {LTTB-selected indices}| (see
    # nmrcheck.spectrum._downsample_points), and LTTB runs in a C extension built
    # from source with no pinned wheel, so which index it selects at a near-tie —
    # and therefore how many collide with the min/max set — varies by platform and
    # even by CI-runner microarchitecture. Fixture 60000016 was observed at 9561
    # and 9563 on different Linux runners for this reason. Tolerate that display
    # jitter (a real down-sampler regression moves the count by hundreds, not a
    # handful); keep the content assertions strict.
    assert observed["preview"]["n"] == pytest.approx(golden["preview"]["n"], abs=16)
    assert observed["preview"]["y_max"] == pytest.approx(
        golden["preview"]["y_max"], rel=1e-6
    )
    assert observed["preview"]["x_at_y_max"] == pytest.approx(
        golden["preview"]["x_at_y_max"], abs=SHIFT_TOL_PPM
    )
    assert observed["preview"]["y_sum"] == pytest.approx(
        golden["preview"]["y_sum"], rel=1e-5, abs=1e-9
    )
    assert math.isfinite(observed["preview"]["y_sum"])


def _record_register_observations(case_id: str, peaks: list[dict[str, Any]]) -> None:
    """Note what each registered peak produced here, for the end-of-run report.

    Recorded from real pipeline output only -- and before the assertions run, so a
    failing run still reports what it saw.
    """
    for index, peak in enumerate(peaks):
        if (case_id, index) in BOUNDARY_REGISTER:
            _REGISTER_OBSERVATIONS[(case_id, index)] = peak["multiplicity"]


def _check_case(case: dict[str, Any]) -> None:
    path = _golden_path(case)
    observed = _run_pipeline(case)
    _record_register_observations(_case_id(case), observed["peaks"])
    if REGEN:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(observed, indent=2, sort_keys=True) + "\n")
        return
    assert path.exists(), (
        f"Missing golden {path.name}; generate with MOLTRACE_REGEN_FID_GOLDEN=1"
    )
    golden = json.loads(path.read_text())
    _assert_matches_golden(observed, golden, _case_id(case))


def _boundary_register_report() -> list[str]:
    """The register, rendered for the terminal.

    Published with the results and reviewed at every run -- a register nobody reads
    is a register that grows.
    """
    header = (
        f"FID multiplet boundary register -- {len(BOUNDARY_REGISTER)} "
        f"entr{'y' if len(BOUNDARY_REGISTER) == 1 else 'ies'} on {PLATFORM_TAG}"
    )
    lines = [
        header,
        "-" * len(header),
        "Genuinely-ambiguous multiplets: the discrete label is relaxed to a stated set;",
        "shift and integration stay strictly pinned. Growth here is a signal that a",
        "tolerance or a band edge is wrong, never routine maintenance.",
    ]
    if not BOUNDARY_REGISTER:
        lines.append("  (register empty or missing)")
        return lines
    flags: list[str] = []
    for (case_id, peak_index), entry in sorted(BOUNDARY_REGISTER.items()):
        allowed = "|".join(entry["allowed_multiplicity"])
        recorded = entry["observed"].get(PLATFORM_TAG)
        seen = _REGISTER_OBSERVATIONS.get((case_id, peak_index))
        if seen is None:
            outcome = "not exercised in this run"
        elif recorded is None:
            outcome = f"this run: {seen!r} (no {PLATFORM_TAG} observation on record)"
        elif seen == recorded:
            outcome = f"this run: {seen!r} (as recorded)"
        else:
            outcome = f"this run: {seen!r} but the register records {recorded!r}"
            flags.append(
                f"  ! {case_id} peak {peak_index}: {PLATFORM_TAG} now reports {seen!r}, "
                f"not the recorded {recorded!r}. Re-measure the entry."
            )
        lines.append(
            f"  {case_id} peak {peak_index} @ {entry['shift_ppm']} ppm  "
            f"allowed {{{allowed}}}  {outcome}"
        )
    lines.extend(flags)
    return lines


@pytest.fixture(scope="module", autouse=True)
def _emit_boundary_register(request: pytest.FixtureRequest) -> Iterator[None]:
    """Print the register whenever this module runs, so it is reviewed rather
    than buried in a file nobody opens."""
    yield
    report = "\n".join(["", *_boundary_register_report(), ""])
    capture = request.config.pluginmanager.getplugin("capturemanager")
    if capture is None:
        print(report)
        return
    with capture.global_and_fixture_disabled():
        print(report)


FAST_CASES = [c for c in CASES if c["spectrum_id"] in FAST_SPECTRA and c["nucleus"] == "1H"]
SLOW_CASES = [c for c in CASES if c not in FAST_CASES]


@pytest.mark.skipif(not FAST_CASES, reason="nmrshiftdb2 fixtures unavailable")
@pytest.mark.parametrize("case", FAST_CASES, ids=_case_id)
def test_fid_pipeline_outputs_pinned_fast(case: dict[str, Any]) -> None:
    _check_case(case)


@pytest.mark.slow
@pytest.mark.skipif(not SLOW_CASES, reason="nmrshiftdb2 fixtures unavailable")
@pytest.mark.parametrize("case", SLOW_CASES, ids=_case_id)
def test_fid_pipeline_outputs_pinned_full_corpus(case: dict[str, Any]) -> None:
    _check_case(case)


# ---------------------------------------------------------------------------
# Boundary register guard rails
#
# These run in the DEFAULT suite (no `slow` marker, no fixtures) so the register
# is checked on every run, not only when the full corpus is exercised.
# ---------------------------------------------------------------------------

_REGISTER_ITEMS = sorted(BOUNDARY_REGISTER.items())
_MULTIPLICITY_VOCABULARY = ("s", "br s", "d", "t", "q", "p", "sext", "sept", "dd", "m")


def _register_item_id(item: tuple[tuple[str, int], dict[str, Any]]) -> str:
    (case_id, peak_index), _ = item
    return f"{case_id}_peak{peak_index}"


def _result_with_peaks(peaks: list[dict[str, Any]]) -> dict[str, Any]:
    """A minimal pipeline-result shape carrying just the peak list under test."""
    return {
        "point_count": 1024,
        "phase": {"mode": "auto", "p0": 1.0, "p1": 2.0, "correction_applied": True},
        "baseline": {"mode": "auto", "order": 3, "correction_applied": True},
        "peak_detection_sensitivity": 0.06,
        "peaks": peaks,
        "preview": {"n": 100, "y_sum": 1.0, "y_max": 1.0, "x_at_y_max": 1.0},
    }


def _golden_peaks(case_id: str) -> list[dict[str, Any]]:
    return list(json.loads((GOLDEN_DIR / f"{case_id}.json").read_text())["peaks"])


def test_boundary_register_size_is_pinned() -> None:
    """The register may not grow silently.

    The count lives in this module, not in the register file, so adding an entry
    is a two-file edit a reviewer cannot miss. A register that grows between
    releases is the signal that a tolerance or a band edge is wrong.
    """
    assert len(BOUNDARY_REGISTER) == EXPECTED_BOUNDARY_REGISTER_ENTRIES


@pytest.mark.parametrize("item", _REGISTER_ITEMS, ids=_register_item_id)
def test_every_registered_label_passes_on_the_committed_goldens(
    item: tuple[tuple[str, int], dict[str, Any]],
) -> None:
    """One golden set, every platform.

    This is what the register buys: each label the fit is known to land on is
    substituted into the real committed golden and must be accepted, so Linux and
    macOS agree without maintaining two golden sets.
    """
    (case_id, peak_index), entry = item
    golden_peaks = _golden_peaks(case_id)
    for label in entry["allowed_multiplicity"]:
        observed_peaks = [dict(peak) for peak in golden_peaks]
        observed_peaks[peak_index]["multiplicity"] = label
        _assert_matches_golden(
            _result_with_peaks(observed_peaks), _result_with_peaks(golden_peaks), case_id
        )


@pytest.mark.parametrize("item", _REGISTER_ITEMS, ids=_register_item_id)
def test_unregistered_multiplicity_change_still_fails(
    item: tuple[tuple[str, int], dict[str, Any]],
) -> None:
    """The whole point: only the registered peak is exempt. Every OTHER peak in
    the same golden still fails hard on a label change."""
    (case_id, peak_index), _ = item
    golden_peaks = _golden_peaks(case_id)
    others = [i for i in range(len(golden_peaks)) if (case_id, i) not in BOUNDARY_REGISTER]
    assert others, f"{case_id}: nothing left unregistered to guard"
    for other in others:
        observed_peaks = [dict(peak) for peak in golden_peaks]
        observed_peaks[other]["multiplicity"] = "REGRESSED"
        with pytest.raises(AssertionError, match=f"peak {other} multiplicity"):
            _assert_matches_golden(
                _result_with_peaks(observed_peaks), _result_with_peaks(golden_peaks), case_id
            )


@pytest.mark.parametrize("item", _REGISTER_ITEMS, ids=_register_item_id)
def test_registered_peak_rejects_a_label_outside_its_allowed_set(
    item: tuple[tuple[str, int], dict[str, Any]],
) -> None:
    """The relaxation is to a stated SET of labels, not to anything at all."""
    (case_id, peak_index), entry = item
    allowed = set(entry["allowed_multiplicity"])
    outside = next(label for label in _MULTIPLICITY_VOCABULARY if label not in allowed)
    golden_peaks = _golden_peaks(case_id)
    observed_peaks = [dict(peak) for peak in golden_peaks]
    observed_peaks[peak_index]["multiplicity"] = outside
    with pytest.raises(AssertionError, match="not one of the labels registered"):
        _assert_matches_golden(
            _result_with_peaks(observed_peaks), _result_with_peaks(golden_peaks), case_id
        )


@pytest.mark.parametrize("item", _REGISTER_ITEMS, ids=_register_item_id)
@pytest.mark.parametrize(
    "field, delta",
    [("shift_ppm", 10 * SHIFT_TOL_PPM), ("integration_h", 10 * INTEGRAL_TOL_H)],
)
def test_registered_peak_still_pins_shift_and_integration(
    item: tuple[tuple[str, int], dict[str, Any]], field: str, delta: float
) -> None:
    """Only the discrete label is relaxed. Shift and integration are continuous
    quantities carrying their own measured tolerances, so a registered peak that
    moves or re-integrates is still a failure."""
    (case_id, peak_index), _ = item
    golden_peaks = _golden_peaks(case_id)
    observed_peaks = [dict(peak) for peak in golden_peaks]
    observed_peaks[peak_index][field] = observed_peaks[peak_index][field] + delta
    with pytest.raises(AssertionError, match=f"peak {peak_index}"):
        _assert_matches_golden(
            _result_with_peaks(observed_peaks), _result_with_peaks(golden_peaks), case_id
        )


@pytest.mark.parametrize("item", _REGISTER_ITEMS, ids=_register_item_id)
def test_boundary_register_entry_is_admissible(
    item: tuple[tuple[str, int], dict[str, Any]],
) -> None:
    """An entry with no recorded reason, evidence, or provenance is not admissible.

    Also enforces the staleness rule: an entry whose recorded platform observations
    have collapsed onto a single label is no longer an ambiguity and must be
    removed, not kept as a silent exemption.
    """
    (case_id, peak_index), entry = item
    where = f"{case_id} peak {peak_index}"

    golden_path = GOLDEN_DIR / f"{case_id}.json"
    assert golden_path.exists(), f"{where}: register names a golden that does not exist"
    golden_peaks = _golden_peaks(case_id)
    assert 0 <= peak_index < len(golden_peaks), f"{where}: peak index out of range"
    gold = golden_peaks[peak_index]

    # The entry is bound to the peak's IDENTITY, so a re-mint that reorders or
    # re-shifts the peak list invalidates the exemption instead of silently
    # transferring it to a different peak.
    assert entry["shift_ppm"] == pytest.approx(gold["shift_ppm"], abs=SHIFT_TOL_PPM), (
        f"{where}: register shift {entry['shift_ppm']} no longer matches the golden's "
        f"{gold['shift_ppm']} — the entry is stale; re-establish it or remove it"
    )

    allowed = entry["allowed_multiplicity"]
    assert isinstance(allowed, list) and len(set(allowed)) >= 2, (
        f"{where}: a single allowed label is not an ambiguity"
    )
    assert gold["multiplicity"] in allowed, (
        f"{where}: the golden's own label {gold['multiplicity']!r} is not in {allowed}"
    )

    observed = entry["observed"]
    assert observed, f"{where}: no platform observations recorded"
    assert set(observed.values()) <= set(allowed), (
        f"{where}: observed labels {sorted(set(observed.values()))} exceed {allowed}"
    )
    assert len(set(observed.values())) >= 2, (
        f"{where}: every recorded platform now reports {sorted(set(observed.values()))[0]!r} "
        "— the peak agrees across platforms, so the exemption is stale and the entry must "
        "be removed, not kept"
    )

    assert entry["reason"].strip(), f"{where}: an entry with no reason is not admissible"
    evidence = entry["evidence"]
    assert evidence.get("measurement", "").strip(), f"{where}: no measured evidence recorded"
    assert float(evidence["flip_perturbation_relative"]) > 0.0, (
        f"{where}: no perturbation scale recorded for the label flip"
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry["added"]), f"{where}: bad added date"
    assert entry["added_by"].strip(), f"{where}: no attribution"


def test_boundary_register_has_no_duplicate_entries() -> None:
    payload = json.loads(BOUNDARY_REGISTER_PATH.read_text())
    keys = [(entry["case"], int(entry["peak"])) for entry in payload["entries"]]
    assert len(keys) == len(set(keys)), "duplicate (case, peak) in the boundary register"


def test_boundary_register_leaves_the_fast_tier_alone() -> None:
    """No exemption may touch the fixture the default suite runs, so macOS
    development keeps a fully strict multiplicity gate."""
    offenders = [
        case_id for case_id, _ in BOUNDARY_REGISTER if case_id.split("_")[0] in FAST_SPECTRA
    ]
    assert not offenders, f"boundary register must not exempt the fast tier: {offenders}"
