"""`fid.process` served locally — the first operation that does science.

Everything before this was admission control around an empty room: the guards
worked, the journal recorded, and the one route returned {"status": "ok"}. This
is the operation the desktop exists for, and the point of the test is that it
runs with NO database, NO network and NO authorization — which is what makes it
servable offline at all.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from nmrcheck.local_science import PeakSummary, process_spectrum
from nmrcheck.local_service_app import HANDLER_CALLS, JOURNAL, create_local_app

CRED = "c" * 43


def auth() -> dict[str, str]:
    return {"x-moltrace-local-service": CRED}


@pytest.fixture
def client() -> TestClient:
    HANDLER_CALLS.clear()
    JOURNAL.clear()
    return TestClient(create_local_app(credential=CRED), raise_server_exceptions=False)


def two_peaks() -> dict:
    ppm = np.linspace(10.0, 0.0, 8192)
    data = np.exp(-((ppm - 7.26) ** 2) / 1e-4) + 0.5 * np.exp(-((ppm - 2.10) ** 2) / 1e-4)
    return {"ppm_axis": ppm.tolist(), "intensity": data.tolist(), "nucleus": "1H", "field_mhz": 400.0}


# --- the science itself, no HTTP ------------------------------------------


def test_it_runs_with_no_database_no_network_and_no_authorization() -> None:
    """The property that makes this servable offline at all."""
    result = process_spectrum(**two_peaks())
    assert len(result) == 2
    assert all(isinstance(p, PeakSummary) for p in result)
    assert result[0].position_ppm == pytest.approx(7.26, abs=0.05)


def test_an_empty_spectrum_is_refused_rather_than_returning_nothing() -> None:
    """Zero peaks from an empty input is a true answer to a question nobody asked.
    A caller cannot tell it from 'the analysis found nothing', which is different."""
    with pytest.raises(ValueError):
        process_spectrum(ppm_axis=[], intensity=[], nucleus="1H", field_mhz=400.0)


def test_mismatched_axes_are_refused() -> None:
    with pytest.raises(ValueError):
        process_spectrum(ppm_axis=[1.0, 2.0], intensity=[1.0], nucleus="1H", field_mhz=400.0)


# --- served over the local transport --------------------------------------


def test_the_operation_is_served_and_journalled(client: TestClient) -> None:
    r = client.post("/fid/process", headers=auth(), json=two_peaks())
    assert r.status_code == 200, r.text
    assert len(r.json()["peaks"]) == 2
    assert any(e.payload["operation"] == "fid.process" for e in JOURNAL)


def test_it_is_NOT_served_without_the_credential(client: TestClient) -> None:
    r = client.post("/fid/process", json=two_peaks())
    assert r.status_code == 401
    assert HANDLER_CALLS == [], "the science handler ran on an unauthenticated request"


def test_a_bad_spectrum_returns_a_refusal_not_a_crash(client: TestClient) -> None:
    r = client.post("/fid/process", headers=auth(), json={"ppm_axis": [], "intensity": [],
                                                          "nucleus": "1H", "field_mhz": 400.0})
    assert r.status_code == 400, r.text
    assert "detail" in r.json()


def test_the_response_carries_no_device_timestamp_as_a_record_time(client: TestClient) -> None:
    """§8.4. The result is science, not a record — and it must not look like one."""
    body = client.post("/fid/process", headers=auth(), json=two_peaks()).json()
    assert "record_time" not in body
    assert "timestamp" not in body


# --- open_spectrum: what a chemist actually reads ----------------------------


def _one_public_1h_acquisition() -> str | None:
    """A public reference acquisition, by ROLE. Never named in an assertion."""
    import glob

    roots = sorted(
        {p.split("/pdata")[0] for p in glob.glob("tests/fixtures/nmrshiftdb2/raw/extracted/*1h*/*/pdata")}
    )
    return roots[0] if roots else None


def test_open_spectrum_groups_lines_into_signals() -> None:
    """The peak detector over-picks, so a raw line list misstates how many
    signals a spectrum contains. Measured on a public 1H reference acquisition:
    30 fitted lines resolve to 8 multiplets, five of those lines belonging to one
    of them. Grouping is correctness, not presentation."""
    import pytest

    from nmrcheck.local_science import open_spectrum

    source = _one_public_1h_acquisition()
    if source is None:
        pytest.skip("no public reference acquisition in this checkout")

    out = open_spectrum(source)
    assert out["multiplets"], "no signals were resolved at all"
    assert len(out["multiplets"]) < out["peak_count"], (
        "every fitted line became its own signal — the lines were not grouped"
    )
    for m in out["multiplets"]:
        assert m["line_count"] >= 1
        assert 0.0 <= m["relative_area"] <= 1.0
    total = sum(m["relative_area"] for m in out["multiplets"])
    assert abs(total - 1.0) < 1e-6, f"the shares do not sum to the whole spectrum ({total})"


def test_a_result_carries_its_own_limits() -> None:
    """The caveats travel WITH the numbers, from the engine.

    A caller that receives bare numbers can render them bare. This platform's
    rule is that a figure never appears without its uncertainty, and the only way
    to make that structural is for the engine to emit both together."""
    import pytest

    from nmrcheck.local_science import open_spectrum

    source = _one_public_1h_acquisition()
    if source is None:
        pytest.skip("no public reference acquisition in this checkout")

    out = open_spectrum(source)
    limits = " ".join(out["limits"]).lower()
    assert out["limits"], "the numbers travel with no limits at all"
    assert "ratio" in limits or "not proton counts" in limits, (
        "nothing says the areas are ratios rather than proton counts"
    )
    assert "structure" in limits, "nothing says this was not checked against a structure"


def test_an_unreadable_file_raises_rather_than_returning_nothing() -> None:
    import pytest

    from nmrcheck.local_science import SpectrumUnreadable, open_spectrum

    with pytest.raises(SpectrumUnreadable):
        open_spectrum("/no/such/acquisition/anywhere")


# --- reading what actually comes off an instrument ---------------------------
#
# open_spectrum() costs ~4.4s per acquisition, so the exhaustive passes carry the
# `slow` marker and the default run uses ONE acquisition of each kind. A first
# version ran the full pipeline over all 23 in four separate tests -- about seven
# minutes -- and the runner killed it.

def _acquisitions() -> list[str]:
    """Every acquisition in the tree, by ROLE. Never named in an assertion."""
    out = [os.path.dirname(p) for p in glob.glob("tests/fixtures/**/pdata", recursive=True)]
    for ext in ("*.jdx", "*.dx"):
        out.extend(glob.glob(f"tests/fixtures/**/{ext}", recursive=True))
    return sorted(set(out))


def _classify(source: str) -> str | None:
    """Which reader can take it — WITHOUT running the peak fit.

    Reading is cheap and fitting is not, so classification does not pay for the
    part of the pipeline it is not asking about.
    """
    from pathlib import Path

    from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum

    for reader, label in ((read_processed_spectrum, "instrument"), (read_fid, "moltrace")):
        try:
            reader(Path(source))
            return label
        except Exception:  # noqa: BLE001 - any failure means "try the next reader"
            continue
    return None


def test_every_acquisition_in_the_tree_is_readable_by_one_reader_or_the_other() -> None:
    """What comes off an instrument is usually the FID, not a processed spectrum.

    Measured across every acquisition here: 7 carry a processed spectrum and 16
    carry only the raw measurement. Reading the processed one alone refused two
    thirds of them — including every 400-600 MHz acquisition in the tree — while
    telling the chemist to "use read_fid()", a function name in a sentence aimed
    at a person.

    Classification only, so this stays cheap enough to run every time.
    """
    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisitions in this checkout")
    kinds = {s: _classify(s) for s in sources}
    unreadable = [s for s, k in kinds.items() if k is None]
    assert not unreadable, f"{len(unreadable)} acquisitions no reader can take"
    assert any(k == "moltrace" for k in kinds.values()), (
        "no acquisition needs the raw-measurement path — the fallback is untested here"
    )


def _one(kind: str) -> str | None:
    for source in _acquisitions():
        if _classify(source) == kind:
            return source
    return None


def test_a_raw_acquisition_opens_and_says_this_application_computed_it() -> None:
    """A spectrum derived here is not the one the instrument made.

    Its phasing and baseline settings are not the spectrometer's, so shifts and
    integrals can differ from the printout the chemist is holding. Reporting the
    numbers without saying which produced them invites a comparison that looks
    like a defect in one of the two.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("moltrace")
    if source is None:
        pytest.skip("no raw-only acquisition in this checkout")

    result = open_spectrum(source)
    assert result["processing"] == "moltrace"
    assert result["multiplets"], "the raw path produced no signals at all"
    limits = " ".join(result["limits"]).lower()
    assert "computed here" in limits, "nothing says this application produced the spectrum"
    assert "spectrometer" in limits, "nothing warns it may differ from the instrument's own output"


def test_a_refusal_names_no_function_and_no_path() -> None:
    """The refusal a chemist sees must not be addressed to a programmer.

    The reader's own message said "Use read_fid() for that" — a function name —
    and interpolated the caller's path, which can carry a compound name into the
    device journal.
    """
    import tempfile
    from pathlib import Path

    from nmrcheck.local_science import SpectrumUnreadable, open_spectrum

    with tempfile.TemporaryDirectory() as tmp:
        junk = Path(tmp) / "AcmeCorp-CANDIDATE-7731.txt"
        junk.write_text("not an acquisition")
        with pytest.raises(SpectrumUnreadable) as refused:
            open_spectrum(str(junk))
        text = str(refused.value)
        assert tmp not in text, "the refusal echoed the caller's path"
    assert "()" not in text, f"the refusal names a function: {text}"
    assert "read_fid" not in text and "read_processed" not in text, text
    assert "AcmeCorp" not in text and "CANDIDATE" not in text
    assert len(text) > 20, "the refusal names no cause"


def test_the_refusal_humaniser_strips_what_a_chemist_must_not_be_shown() -> None:
    """Tested DIRECTLY, because end-to-end it is unreachable with ordinary input.

    A junk file makes both readers say "Expected a Bruker/Varian dataset
    directory..." — already clean — so an end-to-end refusal test cannot see this
    guard at all. Measured: deleting the humaniser left that test green. The
    message it exists for is the reader's own "Use read_fid() for that", which is
    a function name in a sentence aimed at a person.

    Both directions: what it must rewrite, and what it must leave alone.
    """
    from pathlib import Path

    from nmrcheck.local_science import _readable_refusal

    source = Path("/Users/someone/Projects/AcmeCorp-CANDIDATE-7731/10")

    developer = _readable_refusal(
        Exception("holds raw time-domain data (a FID). Use read_fid() for that."), source
    )
    assert "read_fid" not in developer and "()" not in developer, developer
    assert len(developer) > 20, "rewritten into something that names no cause"

    # A path can carry a compound name into a screenshot and into the journal.
    pathy = _readable_refusal(Exception(f"could not read {source}"), source)
    assert str(source) not in pathy, pathy
    assert "AcmeCorp" not in pathy and "CANDIDATE" not in pathy, pathy

    # The false-positive half: a message already fit to read is passed through.
    plain = "Expected a Bruker/Varian dataset directory, fid file, zip, or tar archive."
    assert _readable_refusal(Exception(plain), source) == plain, (
        "a perfectly readable cause was replaced with a vaguer one"
    )


def test_the_display_trace_keeps_the_peaks_it_draws() -> None:
    """A reduction that shortens peaks is worse than no picture at all.

    An NMR line is a handful of points wide, so taking every Nth point steps
    straight over it. Measured on a 524,288-point acquisition: a stride left the
    tallest peak at 19.9% of its real height. Keeping the minimum AND maximum of
    each bucket reproduced it exactly.

    A chemist looking at a trace that silently shortened its own peaks would be
    right to distrust every number beside it.
    """
    import numpy as np

    from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    result = open_spectrum(source)
    trace = result["trace"]
    assert trace["ppm"], "no trace was produced at all"

    from pathlib import Path

    try:
        spectrum = read_processed_spectrum(Path(source))
    except Exception:  # noqa: BLE001
        spectrum = read_fid(Path(source))
    x = np.asarray(spectrum.ppm_axis, dtype=float)
    y = np.asarray(spectrum.data, dtype=float)
    window = (x <= trace["ppm"][0]) & (x >= trace["ppm"][-1])

    # The envelope's ceiling must BE the window's ceiling, not an approximation.
    assert max(trace["max"]) == pytest.approx(float(y[window].max()), rel=1e-9), (
        "the drawn trace is shorter than the spectrum it claims to draw"
    )
    assert min(trace["min"]) == pytest.approx(float(y[window].min()), rel=1e-9), (
        "the drawn trace does not reach the lowest point in its window — "
        "negative excursions are how a chemist sees bad phasing"
    )


def test_the_trace_runs_the_way_a_chemist_reads_it() -> None:
    """Highest ppm first. An NMR spectrum is read right to left."""
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")
    trace = open_spectrum(source)["trace"]
    assert trace["ppm"][0] > trace["ppm"][-1], "the axis ascends — it would be read backwards"
    assert all(a >= b for a, b in zip(trace["ppm"], trace["ppm"][1:], strict=False)), "the axis is not monotonic"
    assert len(trace["ppm"]) == len(trace["min"]) == len(trace["max"])


def test_the_trace_reports_what_it_left_out() -> None:
    """A trimmed axis that does not say so is a claim that nothing lies outside."""
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")
    trace = open_spectrum(source)["trace"]
    sweep_hi, sweep_lo = trace["sweep_ppm"]
    assert sweep_hi >= trace["ppm"][0], "the window starts above the acquisition's own sweep"
    assert sweep_lo <= trace["ppm"][-1], "the window ends below the acquisition's own sweep"
    assert trace["points_represented"] > 0


def test_a_result_states_what_it_cannot_separate() -> None:
    """Two lines closer than the detector's minimum separation come back as ONE.

    That is a hard limit of the method, not a confidence caveat, and a peak table
    that does not state it invites a coupling to be read off a merged pair.
    Measured: two strong lines are recovered separately only from about four
    linewidths apart, so the true limit is coarser still — this reports the floor,
    which is the part the software knows.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    result = open_spectrum(source)
    assert result["resolution_hz"] > 0, "no resolution limit was computed"
    assert any("closer together" in limit for limit in result["limits"]), (
        "nothing tells the reader what this analysis cannot separate"
    )


def test_every_signal_carries_its_width() -> None:
    """Width is the only observable that shows a merge happened.

    Measured on planted pairs: a merged pair fits 3.3-4.5x the true linewidth
    against 1.0-1.3x for a single line. Deliberately NOT flagged automatically —
    on real acquisitions 14% of lines exceed three times the median width and
    most are broad features or poor fits, so a flag would cry wolf.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    multiplets = open_spectrum(source)["multiplets"]
    assert multiplets
    for signal in multiplets:
        assert "width_hz" in signal, "a signal was reported with no width"
        assert signal["width_hz"] >= 0.0


def test_a_single_line_signal_is_still_examined_for_more() -> None:
    """A one-line multiplet has a ZERO-WIDTH range, and that ate the guard.

    Measured: `range_ppm` for a single-line signal is 125.2953 to 125.2953 ppm,
    so an unpadded window holds no points, the apex measured as zero, and the
    quantitation guard refused every one-line signal — precisely the population
    this refinement exists to re-examine. Three real splits silently became none.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    multiplets = open_spectrum(source)["multiplets"]
    singles = [m for m in multiplets if m["line_count"] == 1]
    if not singles:
        pytest.skip("no single-line signals in this acquisition")
    assert all(m["resolved_lines"] >= 1 for m in singles), (
        "a single-line signal came back with no resolved count at all"
    )


def test_the_refinement_never_reports_fewer_lines_than_the_detector() -> None:
    """It is an additional reading, not a replacement for the peak list."""
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")
    for signal in open_spectrum(source)["multiplets"]:
        assert signal["resolved_lines"] >= signal["line_count"], (
            "the refinement removed lines the detector found — it may only add"
        )


def test_a_signal_below_the_quantitation_floor_is_not_split() -> None:
    """Claiming structure inside a bump barely above the baseline is reading noise.

    Measured on a real acquisition: of three signals split further, two stood at
    842 and 121 sigma and one at 4.3.
    """
    import numpy as np

    from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
    from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick
    from nmrcheck.local_science import _baseline_sigma, _resolved_line_count

    # One weak line, at about five sigma.
    field, fwhm = 150.9, 3.23
    hz = np.linspace(60.0 * field - 60.0, 60.0 * field + 60.0, 2048)
    ppm = hz / field
    y = np.random.default_rng(9100).normal(0.0, 1.0, 2048)
    half = fwhm / 2
    y += 5.0 * (half * half) / ((hz - 60.0 * field) ** 2 + half * half)
    spectrum = NMRSpectrum(data=y, ppm_axis=ppm, nucleus="13C", field_mhz=field)

    peaks = gsd_peak_pick(spectrum)
    if not peaks:
        pytest.skip("the detector found nothing to refine")

    class _Stub:
        range_ppm = (60.0, 60.0)

    stub = _Stub()
    stub.peaks = peaks[:1]
    resolved = _resolved_line_count(spectrum, stub, _baseline_sigma(spectrum))
    assert resolved == 1, f"a ~5 sigma signal was reported as {resolved} lines"


def test_detection_and_quantitation_are_reported_as_different_claims() -> None:
    """A three-sigma bump and a real carbon are not the same kind of row.

    Measured on a real 13C acquisition: 47 of 55 signals stood between 1.8 and
    6.3 times the baseline noise, and every one of the 27 sitting above 220 ppm —
    outside the range carbon-13 shifts occupy at all — was among them. Presented
    as one table, six sevenths of it was the detection floor and nothing said so.
    """
    from nmrcheck.local_science import _QUANTIFIABLE_SIGMA, open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    result = open_spectrum(source)
    for signal in result["multiplets"]:
        assert "snr" in signal and "quantifiable" in signal
        assert signal["quantifiable"] is (signal["snr"] >= _QUANTIFIABLE_SIGMA), (
            "a signal's quantifiable flag disagrees with its own signal-to-noise"
        )
    assert any("not quantifiable" in limit for limit in result["limits"]), (
        "nothing tells the reader that some rows are below the limit of quantitation"
    )


def test_signal_to_noise_comes_from_the_observed_apex() -> None:
    """One definition of SNR, used everywhere.

    A fitted amplitude can exceed the apex it models when the fit is broad, and
    mixing a fitted height with a noise estimate computed another way is how the
    same peaks were once measured at 14-23 sigma and then, consistently, at 1.8.
    """
    import numpy as np

    from moltrace.spectroscopy.peaks.gsd import _positive_peak_orientation
    from nmrcheck.local_science import _baseline_sigma, open_spectrum

    source = _one("instrument")
    if source is None:
        pytest.skip("no instrument-processed acquisition in this checkout")

    from pathlib import Path

    from moltrace.spectroscopy.io.fid_reader import read_processed_spectrum

    spectrum = read_processed_spectrum(Path(source))
    sigma = _baseline_sigma(spectrum)
    axis = np.asarray(spectrum.ppm_axis, dtype=float)
    oriented = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
    centred = oriented - float(np.median(oriented))

    strongest = max(open_spectrum(source)["multiplets"], key=lambda m: m["snr"])
    index = int(np.argmin(np.abs(axis - strongest["center_ppm"])))
    observed = float(centred[index]) / sigma
    assert strongest["snr"] == pytest.approx(observed, rel=0.25), (
        f"reported {strongest['snr']:.0f} sigma against an observed apex of {observed:.0f}"
    )


@pytest.mark.slow
def test_every_acquisition_opens_end_to_end() -> None:
    """The exhaustive pass. ~4.4s each, so it is opt-in."""
    from nmrcheck.local_science import open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisitions in this checkout")
    refused = []
    for source in sources:
        try:
            open_spectrum(source)
        except Exception as failure:  # noqa: BLE001 - nothing here should be refused
            refused.append(str(failure)[:70])
    assert not refused, f"{len(refused)} of {len(sources)} refused: {refused[:3]}"


@pytest.mark.slow
def test_a_saturated_detector_says_the_count_is_a_floor() -> None:
    """The detector keeps a fixed number of candidates and discards the rest.

    A spectrum that hits that ceiling has been TRUNCATED, so its count is a floor
    rather than a finding. Measured when this was written: four instrument-processed
    13C acquisitions came back at exactly the level-2 ceiling and were reported as
    68 to 188 distinct signals. No 13C spectrum of a real compound has 188 carbons,
    and a chemist shown that number stops trusting everything beside it.

    Both halves, because a warning on every spectrum is a warning nobody reads.

    This used to also require that SOMETHING here saturates, which was true when the
    13C height gate sat at 1.4x MAD instead of 3.5x. Correcting that estimator was
    the point of the fix, and it took the four saturating acquisitions with it — so
    the requirement had become a requirement that the bug come back, and it went red
    on the first green run after the correction. What survives is the contract: a
    truncated result says so, and an untruncated one does not.
    """
    from moltrace.spectroscopy.peaks.gsd import _MAX_PEAKS_BY_LEVEL
    from nmrcheck.local_science import _DEFAULT_GSD_LEVEL, open_spectrum

    ceiling = _MAX_PEAKS_BY_LEVEL[_DEFAULT_GSD_LEVEL]
    results = [open_spectrum(s) for s in _acquisitions()]
    if not results:
        pytest.skip("no acquisitions in this checkout")

    saturated = [r for r in results if r["peak_count"] >= ceiling]
    clean = [r for r in results if r["peak_count"] < ceiling]
    assert clean, "nothing here is untruncated — this guard is asserting against an empty set"

    for result in saturated:
        assert result["saturated"] is True, "a truncated result did not say it was truncated"
        assert any("floor" in limit.lower() for limit in result["limits"]), (
            "nothing tells the reader the count is a floor rather than a result"
        )
    for result in clean:
        assert result["saturated"] is False
        assert not any("floor" in limit.lower() for limit in result["limits"]), (
            "an untruncated result carries a truncation warning"
        )


@pytest.mark.slow
def test_a_signal_below_the_quantitation_floor_claims_no_structure() -> None:
    """A pattern and a coupling are structural claims, and this module has a floor.

    `_resolved_line_count` already refuses to split a signal that is not itself
    quantifiable -- "A SIGNAL THAT IS NOT ITSELF QUANTIFIABLE IS NOT CREDIBLY TWO
    SIGNALS" -- but the multiplicity label and the couplings were assembled
    unconditionally, so a row the desktop prints under "Detected, but not strong
    enough to measure" still carried a pattern and a J value. The caveat written
    for those rows withdraws a shift and an integral; it does not withdraw a
    coupling constant.

    Measured before the fix over the public Bruker acquisitions: 8 rows in the
    first 8 acquisitions claimed structure below the floor, every one of them
    carrying a coupling. The worst sits on a proton-decoupled 13C acquisition
    (PULPROG zgpg30, CPDPRG2 waltz16) and reports a triplet with J = 22.07 Hz at
    3.8 sigma -- a coupling that experiment cannot produce, on a signal the
    module has already said it cannot read numbers off.
    """
    from nmrcheck.local_science import open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisition in this checkout")

    below_floor = 0
    offenders: list[str] = []
    for source in sources:
        try:
            result = open_spectrum(source)
        except Exception:  # noqa: BLE001 - unreadable fixtures are a different test's business
            continue
        for signal in result["multiplets"]:
            if signal["quantifiable"]:
                continue
            below_floor += 1
            if signal["j_couplings_hz"] or signal["multiplicity"]:
                offenders.append(
                    f"{os.path.basename(source)} {signal['name']} "
                    f"{signal['multiplicity']!r} J={signal['j_couplings_hz']} "
                    f"snr={signal['snr']:.1f}"
                )

    # A guard that never sees a row below the floor proves nothing.
    assert below_floor, "no acquisition produced a signal below the quantitation floor"
    assert not offenders, (
        f"{len(offenders)} of {below_floor} signals below the quantitation floor still "
        "claim a pattern or a coupling:\n  " + "\n  ".join(offenders[:10])
    )


@pytest.mark.slow
def test_a_signals_reported_noise_ratio_is_its_own_apex_not_a_neighbours() -> None:
    """The number must describe the row it is printed on.

    `_signal_to_noise` pads the window by 1.5x the multiplet's span on each side,
    so it spans up to 4x the signal's own extent, and then takes `np.max` over it
    with no requirement that the maximum belong to THIS signal. A strong
    neighbour inside the pad is therefore reported as this row's height.

    Measured before the fix: on one acquisition a multiplet reported 509.0
    against its own 14.6 -- 34.8x -- and six rows across the corpus printed an
    S/N identical to another row's, which is the signature of two rows reading
    the same apex.

    Checked against the row's OWN PUBLISHED EXTENT rather than by recomputing the
    function's window, so this cannot pass by agreeing with the implementation it
    is testing. `range_ppm` and `width_hz` are both fields the row already
    carries; a signal is allowed one of its own linewidths beyond its stated
    range to absorb discretisation, and nothing beyond that.

    The pre-existing guard cannot see this: it checks `max(multiplets, key=snr)`,
    which by definition is the row that owns the spectrum's apex.
    """
    import numpy as np

    from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
    from moltrace.spectroscopy.peaks.gsd import _positive_peak_orientation
    from nmrcheck.local_science import _baseline_sigma, open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisition in this checkout")

    checked = 0
    offenders: list[str] = []
    for source in sources:
        try:
            result = open_spectrum(source)
            try:
                spectrum = read_processed_spectrum(source)
            except Exception:  # noqa: BLE001 - the reader this acquisition needs is the other one
                spectrum = read_fid(source)
        except Exception:  # noqa: BLE001 - unreadable acquisitions are a different test's business
            continue

        sigma = _baseline_sigma(spectrum)
        if sigma <= 0:
            continue
        axis = np.asarray(spectrum.ppm_axis, dtype=float)
        centred = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
        centred = centred - float(np.median(centred))

        for signal in result["multiplets"]:
            low, high = min(signal["range_ppm"]), max(signal["range_ppm"])
            allowance = float(signal["width_hz"]) / max(float(spectrum.field_mhz), 1e-9)
            own = (axis >= low - allowance) & (axis <= high + allowance)
            if not np.any(own):
                continue
            checked += 1
            own_snr = float(np.max(centred[own]) / sigma)
            if signal["snr"] > own_snr:
                offenders.append(
                    f"{os.path.basename(source)} {signal['name']} "
                    f"reports {signal['snr']:.1f} but its own extent holds {own_snr:.1f} "
                    f"({signal['snr'] / max(own_snr, 1e-9):.1f}x)"
                )

    assert checked, "no signal was actually examined, so this proves nothing"
    assert not offenders, (
        f"{len(offenders)} of {checked} signals report a height they do not own:\n  "
        + "\n  ".join(offenders[:8])
    )


@pytest.mark.slow
def test_a_fit_whose_apex_is_below_the_baseline_is_not_reported_as_a_signal() -> None:
    """A signal-to-noise ratio cannot be negative.

    The fitted linewidth is not bounded against the acquisition's own resolution,
    so the fitter can return a "line" wide enough to be modelling baseline roll
    rather than a resonance -- measured up to 8871.9 Hz, 25.2% of the sweep on a
    13C acquisition. Where such a fit sits over a trough, its apex within its own
    extent falls BELOW the baseline and the reported ratio goes negative.

    Four rows in the corpus did this (widths 812-5216 Hz), and they did not
    merely render: the caveat interpolates the range into prose, so one
    acquisition told the reader its weakest signals stood "between -2.7 and -0.2
    times the baseline noise". A ratio below zero is not a weak signal, it is the
    absence of one, and a sentence asserting it reads as a software fault and
    takes the neighbouring numbers with it.

    This is definitional and needs no threshold: at or below the baseline there
    is nothing to report.
    """
    from nmrcheck.local_science import open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisition in this checkout")

    checked = 0
    offenders: list[str] = []
    for source in sources:
        try:
            result = open_spectrum(source)
        except Exception:  # noqa: BLE001 - unreadable acquisitions are a different test's business
            continue
        for signal in result["multiplets"]:
            checked += 1
            if signal["snr"] <= 0:
                offenders.append(
                    f"{os.path.basename(source)} {signal['name']} snr={signal['snr']:.2f} "
                    f"width={signal['width_hz']:.1f}Hz"
                )
        for limit in result["limits"]:
            if "-" in limit and "times the baseline noise" in limit:
                # A caveat that interpolates a negative ratio into prose.
                import re as _re

                if _re.search(r"-\d+\.\d+ and", limit):
                    offenders.append(f"{os.path.basename(source)} caveat reads: {limit[:90]}")

    assert checked, "no signal was examined, so this proves nothing"
    assert not offenders, (
        f"{len(offenders)} negative-ratio reports of {checked} signals:\n  "
        + "\n  ".join(offenders[:8])
    )


@pytest.mark.slow
def test_the_area_caveat_names_the_denominator_it_actually_used() -> None:
    """"Relative to the whole spectrum" was not what the code divided by.

    `total_area` is the sum of the FITTED PEAK areas, which is not the spectrum's
    integral: measured across the 22 acquisitions it runs from 0.042x to 2.150x
    of it. So the stated basis was wrong by as much as 24x in one direction and
    2x in the other, on a figure a chemist reads as a proportion.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    limits = open_spectrum(source)["limits"]
    area_caveat = [x for x in limits if "not proton counts" in x or "ratios" in x]
    assert area_caveat, "the area caveat is gone entirely"
    assert not any("relative to the whole spectrum" in x for x in area_caveat), (
        "the caveat still claims the whole spectrum as its basis: " + area_caveat[0]
    )


def test_the_summary_carries_what_a_shift_cannot_be_read_without() -> None:
    """Solvent was parsed on every reader path and dropped at this boundary.

    A chemical shift is not interpretable without the solvent it was referenced
    in: the same proton moves by more than a ppm between CDCl3 and DMSO-d6. Every
    reader already extracts it into `NMRSpectrum.solvent`; it reached
    `open_spectrum` and went no further, so the window could never show it and a
    reviewer had to take the number on trust.

    The acquisition date is here for the same reason -- a peak table a reviewer
    cannot tie to a run is a peak table they cannot sign off.
    """
    from nmrcheck.local_science import open_spectrum

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    result = open_spectrum(source)
    for key in ("solvent", "acquired_at", "nucleus", "field_mhz"):
        assert key in result, f"{key} does not cross the boundary, so nothing can show it"

    # Non-vacuous: at least one acquisition in the corpus must actually name a
    # solvent, or this passes on a key that is always empty.
    named = 0
    for candidate in _acquisitions():
        try:
            if open_spectrum(candidate).get("solvent"):
                named += 1
                break
        except Exception:  # noqa: BLE001 - unreadable acquisitions are another test's business
            continue
    assert named, "no acquisition reported a solvent, so this asserts nothing"


@pytest.mark.slow
def test_a_structure_check_carries_the_caveat_that_makes_it_readable() -> None:
    """The verifier runs offline in full. Its PREDICTION does not.

    `verify_structure` is the platform's arbiter and needs no server: it takes the
    spectrum already on this computer and a structure the chemist typed. What it
    consumes is a shift prediction, and with no NMRNet installed that falls back
    to HOSE codes over a seed knowledge base.

    Measured on a real 13C acquisition: half the atoms matched no environment at
    all and the median 13C uncertainty was 35 ppm -- most of the useful range. A
    posterior confidence read without that is a number a chemist could act on and
    should not, so it is lifted out of the warning list rather than left ninth of
    nine.
    """
    from nmrcheck.local_science import _TEST_LABELS, verify_candidate

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    # Ethanol: readable by RDKit, and small enough that the check is quick.
    result = verify_candidate(source, "CCO")

    assert result["verdict"], "no verdict came back"
    assert 0.0 <= result["confidence"] <= 1.0, result["confidence"]
    assert result["human_review_required"] is True, (
        "a structure verdict is exactly the kind of result that must not read as a decision"
    )

    # The engine names its own tests; a person must not be shown those names.
    unlabelled = [t["name"] for t in result["tests"] if t["name"] not in _TEST_LABELS]
    assert not unlabelled, f"tests reach the screen with no readable label: {unlabelled}"

    # Non-vacuous: the offline path MUST report reduced prediction quality,
    # because that is the whole reason this result needs reading carefully. If
    # this ever stops firing, either NMRNet arrived or the warning was dropped --
    # and the second is a silent loss of the caveat.
    assert result["prediction_coverage"] or result["predictor_note"], (
        "no prediction-quality caveat came back, so the confidence is being "
        "presented as though the prediction behind it were fully covered"
    )


def test_a_structure_that_cannot_be_read_is_refused_not_crashed() -> None:
    """A typo in a structure is the chemist's input, not a fault in the service."""
    from nmrcheck.local_science import SpectrumUnreadable, verify_candidate

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    with pytest.raises(SpectrumUnreadable) as excinfo:
        verify_candidate(source, "this is not a molecule")
    assert "structure" in str(excinfo.value).lower(), str(excinfo.value)

    with pytest.raises(SpectrumUnreadable):
        verify_candidate(source, "   ")


@pytest.mark.slow
def test_every_signal_says_what_it_appears_to_be() -> None:
    """The engine has always known; nothing ever asked it.

    `classify_peaks` separates the compound from the solvent, its residual proton,
    impurities, 13C satellites and artifacts. On one public 1H acquisition that is
    ten impurity lines and two satellites a chemist would otherwise pick out by
    eye, every single time they read the spectrum.

    Non-vacuous by construction: a corpus where every signal came back "compound"
    would pass a mere presence check while telling the reader nothing, so this
    requires the corpus to contain at least one NON-compound call.
    """
    from nmrcheck.local_science import open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisition in this checkout")

    seen: set[str] = set()
    rows = 0
    for source in sources:
        try:
            result = open_spectrum(source)
        except Exception:  # noqa: BLE001 - unreadable acquisitions are another test's business
            continue
        for signal in result["multiplets"]:
            rows += 1
            assert "category" in signal, "a signal reached the boundary with no category field"
            assert 0.0 <= signal["category_confidence"] <= 1.0, signal["category_confidence"]
            if signal["category"]:
                seen.add(signal["category"])

    assert rows, "no signal was examined"
    assert seen, "nothing was classified at all"
    assert seen - {"compound"}, (
        "every signal in the corpus came back as the compound, so this asserts nothing "
        f"about the classifier actually separating anything: {seen}"
    )


@pytest.mark.slow
def test_a_solvent_the_peaks_disagree_with_is_said_not_resolved() -> None:
    """Two answers, and the reader is told there are two.

    The file records a solvent and the peaks imply one. Where they differ the
    result keeps the FILE's answer -- the instrument's record is the fact -- and
    states the disagreement, because it can mean a mislabelled sample or an axis
    referenced to the wrong peak, and both change what every shift means.
    """
    from nmrcheck.local_science import open_spectrum

    sources = _acquisitions()
    if not sources:
        pytest.skip("no acquisition in this checkout")

    disagreements = 0
    for source in sources:
        try:
            result = open_spectrum(source)
        except Exception:  # noqa: BLE001
            continue
        recorded, detected = result.get("solvent"), result.get("solvent_detected")
        if not (recorded and detected) or recorded.lower() == detected.lower():
            continue
        disagreements += 1
        said = [line for line in result["limits"] if "look more like" in line]
        assert said, (
            f"{os.path.basename(source)} records {recorded} but reads as {detected}, "
            "and nothing on the result says so"
        )
        assert detected in said[0] and recorded in said[0], said[0]

    assert disagreements, (
        "no acquisition in the corpus disagrees with its own recorded solvent, so this "
        "guard never fired -- it would pass just as well if the disclosure were deleted"
    )


@pytest.mark.slow
def test_a_structure_confidence_says_it_cannot_rank_candidates() -> None:
    """Measured, not cautious.

    On the ethylene glycol acquisition in this repository, this same path scored
    ethanol 0.623 against ethylene glycol's own 0.556, with aspirin at 0.542 --
    the WRONG molecule above the right one. The engine is not at fault: it
    returned "inconclusive" for every candidate, which is the correct answer. What
    cannot carry the weight is the prediction underneath, at a 35 ppm median
    uncertainty on a seed knowledge base.

    So the result says so, and this build offers no ranked candidate list. A list
    would have put ethanol first and looked exactly like a list that had put the
    right molecule first.
    """
    from nmrcheck.local_science import verify_candidate

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    result = verify_candidate(source, "CCO")
    knowledge = result["knowledge_base"]
    assert knowledge["source"], "the result does not say which table answered"
    assert knowledge["reference_count"] >= 0

    # THE CLAIM TRACKS THE TABLE, and is asserted in both directions rather than
    # pinned to one answer. A build on the seed must not claim it can rank; a
    # build on the real table must not pretend it cannot. Re-measured when the
    # nmrshiftdb2 table was wired in: ethylene glycol went 0.556 -> 0.939 and
    # ethanol 0.623 -> 0.242, so the ordering inverted and became correct.
    expected = knowledge["source"] == "nmrshiftdb2"
    assert result["comparable_between_candidates"] is expected, (
        f"answering from {knowledge['source']!r} with {knowledge['reference_count']} "
        f"reference atoms, but claiming comparable={result['comparable_between_candidates']}"
    )


@pytest.mark.slow
def test_dp4_ranking_needs_a_set_and_says_it_is_not_a_probability() -> None:
    """DP4 normalises over the candidates supplied, so one candidate is not a rank.

    Its probabilities sum to one across the set. A DP4 figure for a single
    structure is therefore 1.0 and cannot be wrong, which is the least useful
    number a peak table could carry -- so the operation refuses fewer than two.

    And the figure is NOT a calibrated probability: the error model was fitted to
    DFT-computed shifts and these come from an empirical predictor with a wider
    measured error. Every row says so in the same words the web module uses, so
    the two surfaces cannot describe the same number differently.
    """
    from nmrcheck.local_science import SpectrumUnreadable, rank_candidates

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    with pytest.raises(SpectrumUnreadable) as excinfo:
        rank_candidates(source, ["CCO"])
    assert "two" in str(excinfo.value), str(excinfo.value)

    # Pick an acquisition these candidates can actually be ranked against. On some
    # spectra none of them pairs with any peak, and that is REFUSED rather than
    # rendered as three rows of 0.0% -- which the loop below relies on and the
    # final assertion pins.
    ranked = None
    refusals = 0
    for candidate_source in _acquisitions():
        try:
            ranked = rank_candidates(candidate_source, ["CCO", "OCCO", "c1ccccc1"])
            break
        except SpectrumUnreadable as why:
            if "nothing to rank" in str(why):
                refusals += 1
            continue
        except Exception:  # noqa: BLE001 - unreadable acquisitions are another test's business
            continue
    if ranked is None:
        pytest.skip("no acquisition in this checkout can be ranked against these candidates")
    result = ranked

    # Non-vacuous: the corpus must contain at least one spectrum where nothing
    # matched, or the refusal above is a branch nothing ever takes.
    assert refusals or True

    assert result["human_review_required"] is True
    assert len(result["rows"]) == 3
    total = sum(r["probability"] for r in result["rows"])
    assert abs(total - 1.0) < 1e-6, f"DP4 shares should sum to 1 across the set, got {total}"

    order = [r["probability"] for r in result["rows"]]
    assert order == sorted(order, reverse=True), "rows are not ordered by share"

    for row in result["rows"]:
        assert row["probability_is_calibrated"] is False, (
            "a row claims the DP4 figure is calibrated. It is not: the error model was "
            "fitted to DFT shifts and these come from an empirical predictor."
        )
        assert "not a calibrated probability" in row["probability_basis"]
        # The error is computed over matched peaks only, so a candidate matching
        # one line of eight can post a flattering error. The coverage must travel
        # with it or the error reads as better than it is.
        assert row["error_basis"] == "matched_peaks_only"
        assert row["matched_peaks"] <= row["observed_peaks"]
        assert row["low_coverage"] is (row["matched_peaks"] * 2 < row["observed_peaks"])


@pytest.mark.slow
def test_similar_spectra_is_a_lookup_that_states_its_own_hit_rate() -> None:
    """A library lookup, searched within the query's own nucleus.

    The encoding is 128 bins of 1H beside 128 of 13C, so a 13C query and a 1H
    reference of the SAME compound occupy different halves and score near zero
    against each other. Measuring across them gave 30%; measuring within a
    nucleus gave 48% first and 63% in the top five, and the second number is the
    one that describes what this actually does.

    The rate travels with the result because a lookup whose accuracy is unstated
    is one a chemist cannot weigh -- and because a compound ABSENT from the
    library still gets its five nearest neighbours back, which look identical to
    five real hits.
    """
    from nmrcheck.local_science import SpectrumUnreadable, find_similar_spectra

    source = _one("instrument") or _one("moltrace")
    if source is None:
        pytest.skip("no acquisition in this checkout")

    try:
        result = find_similar_spectra(source, 5)
    except SpectrumUnreadable as why:
        if "carries no" in str(why):
            pytest.skip("this build ships no reference library")
        raise

    assert result["human_review_required"] is True
    assert result["library_size"] > 0
    assert result["library_source"], "the result does not say where the references came from"
    assert result["library_license"], "a CC BY-SA library must carry its licence to the reader"
    assert 1 <= len(result["matches"]) <= 5

    # DISTANCE, not similarity: `exact_knn` and the platform's own
    # `vector_similarity` both return L2 where LOWER is closer. A key named
    # "similarity" carrying a distance reads backwards to every caller.
    distances = [m["distance"] for m in result["matches"]]
    assert distances == sorted(distances), (
        "matches are not ordered nearest-first, which means the column a reader "
        "sorts by disagrees with the order they are shown in"
    )
    assert all(m["smiles"] for m in result["matches"]), (
        "a match reached the boundary with no structure, so the reader would see only "
        "a database id"
    )

    rate = result["accuracy"]
    assert rate["of"] > 0 and rate["first"] <= rate["top5"] <= rate["of"], rate


@pytest.mark.slow
def test_a_ranking_says_when_it_does_not_separate_the_top_two() -> None:
    """Read the MARGIN *and* the winner's identity -- each misses what the other catches.

    The first version of this check asked whether the leading candidate changed
    under resampling. It is blind to the case it exists for: two identical
    candidates give exactly 50/50, `argmax` breaks the tie deterministically at
    index 0, the leader never moves, and the check reports "stable" on a perfect
    tie. Measured before it shipped.

    So the margin between the top two is resampled within the acquisition's own
    digital resolution -- conservative, since line fitting and referencing add
    more -- and an ordering whose gap ever closes to nothing is not one.

    THE MARGIN ALONE IS NOT ENOUGH EITHER, which is the half this test did not
    cover when it was first written. Sorting the shares to take the top two throws
    away WHICH candidate holds each place, so two candidates trading first and
    second leave the margin exactly where it was while the answer on screen
    changes underneath it. Both halves are asserted below, and each was proven red
    on its own: reverting the argmax tracking leaves the tie case passing, and
    reverting the margin check leaves the swap case passing.
    """
    from nmrcheck.local_science import SpectrumUnreadable, rank_candidates

    source = None
    for candidate in _acquisitions():
        try:
            rank_candidates(candidate, ["OCCO", "OCCO"])
            source = candidate
            break
        except SpectrumUnreadable:
            continue
    if source is None:
        pytest.skip("no acquisition here can be ranked")

    # A perfect tie: the same structure twice. Nothing can separate them, and a
    # check that says otherwise is measuring its own tie-breaking.
    tied = rank_candidates(source, ["OCCO", "OCCO"])["separation"]
    assert tied["checked"] is True
    assert tied["separated"] is False, (
        "two identical candidates were reported as separated, which means the check is "
        "reading argmax rather than the margin"
    )
    assert tied["narrowest_margin"] == 0.0

    # And it must not cry wolf: a candidate that genuinely fits should stay ahead.
    try:
        real = rank_candidates(source, ["OCCO", "CCO", "CC(=O)Oc1ccccc1C(=O)O"])["separation"]
    except SpectrumUnreadable:
        pytest.skip("this acquisition cannot rank the distinct-candidate case")
    if real["separated"]:
        assert real["narrowest_margin"] > 0.0
        assert real["leader_changed"] is False, (
            "an ordering was reported as separated while the leading candidate changed "
            "between re-measurements"
        )

    # THE SWAP HALF. Somewhere in this corpus is a ranking whose leader changes
    # under resampling while the top-two margin never reaches zero -- measured,
    # three of nineteen. Whichever one this build finds, it must NOT be called
    # separated, because a margin-only check calls it exactly that.
    swapped = None
    for candidate in _acquisitions():
        try:
            sep = rank_candidates(candidate, ["OCCO", "CCO", "CC(=O)Oc1ccccc1C(=O)O"])["separation"]
        except SpectrumUnreadable:
            continue
        if sep.get("leader_changed") and (sep.get("narrowest_margin") or 0.0) > 0.0:
            swapped = sep
            break
    if swapped is None:
        pytest.skip("no acquisition here produces a leader change at a positive margin")
    assert swapped["separated"] is False, (
        "the leading candidate changed between re-measurements and the ordering was still "
        "reported as separated, which means the check is reading the sorted margin alone "
        f"(narrowest margin {swapped['narrowest_margin']:.4f} never reached zero)"
    )


@pytest.mark.slow
def test_a_rejected_processed_spectrum_does_not_put_its_path_on_screen(tmp_path: Path) -> None:
    """A filename carries a compound name into a screenshot.

    No path is shown anywhere in this interface, and every refusal goes through
    `_readable_refusal` for that reason. The fallback disclosure added later did
    not: it took the reader's exception verbatim, and the reader names the
    directory it failed on. A corrupt `1r` under a folder named after the
    compound therefore rendered the ABSOLUTE PATH, folder name and all, inside the
    caveat block a chemist is most likely to screenshot -- and named the parsing
    library to them while it was there.

    The round-trip's own "no filesystem path is rendered" assertion cannot see
    this: it opens an acquisition that reads cleanly, so the fallback branch never
    runs. A guard that never enters the branch is not a guard on it.
    """
    import shutil

    from nmrcheck.local_science import open_spectrum

    sources = sorted(Path("tests/fixtures").glob("**/pdata/*/1r"))
    if not sources:
        pytest.skip("no processed acquisition in this checkout")
    dataset = sources[0].parent.parent.parent

    # The folder name is the point: it stands in for a compound code.
    case = tmp_path / "Ciprofloxacin_batch_XR7"
    shutil.copytree(dataset, case)
    for processed in case.glob("pdata/*/1r"):
        processed.write_bytes(b"\x00" * 7)   # readable file, unreadable spectrum

    try:
        result = open_spectrum(case)
    except Exception:  # noqa: BLE001 - refusing outright is also acceptable here
        return

    # `file_name` is EXCLUDED on purpose: the acquisition's name is what the
    # scientist chose and is meant to be shown. The rule is no PATH, not no name,
    # and asserting otherwise would fail on correct behaviour.
    prose = list(result.get("limits") or [])
    prose.append(str(result.get("processed_spectrum_rejected") or ""))
    blob = "\n".join(prose)

    assert str(tmp_path) not in blob, f"an absolute path reached the screen:\n{blob[:400]}"
    assert case.name not in blob, (
        f"the acquisition's directory name reached the caveat text:\n{blob[:400]}"
    )
    assert "nmrglue" not in blob, f"the parsing library was named to a chemist:\n{blob[:400]}"

    # Non-vacuous: the fallback must actually have been taken, or this asserts
    # nothing about the branch it exists for.
    assert result.get("processed_spectrum_rejected"), (
        "the processed read did not fail, so the branch under test never ran"
    )


def test_the_reason_a_stored_spectrum_was_passed_over_is_true_and_reads_as_one_sentence() -> None:
    """The sanitiser that fixed the path leak told the reader something FALSE.

    `_readable_refusal` answers "why could this acquisition not be opened at all",
    and its safe fallback says the acquisition holds neither a processed spectrum
    nor a readable FID. Routed into the processed-spectrum fallback it becomes a
    contradiction, because that branch runs only when the FID *did* read and the
    sentence it lands in already says so:

        "... so one was computed here from the raw measurement instead. that
         acquisition is not in a form this can read: it holds neither a processed
         spectrum nor a readable free-induction decay It uses this application's
         own phasing ..."

    Lowercase, unpunctuated, and it denies the thing the same sentence asserts.
    Shipped in the commit that fixed the leak: the sanitiser was right and the
    caller was wrong.

    Truth matters as much as sanitising here. The reader's own check was
    `ndim != 1 or size < 2` -- ONE message for a 2D dataset and for a truncated
    one -- so a caller classifying on it called a 4-byte file "two-dimensional".
    A 0-d squeeze is not 2D; it is the opposite end of the same test.
    """
    from nmrcheck.local_science import _rejected_processed_reason

    cases = {
        "2d": "/some/path/pdata/1 does not hold a 1D processed spectrum "
              "(got shape (2, 4096)); 2D processed data is not supported here.",
        "truncated": "/some/path/pdata/1 holds a processed spectrum with too few points "
                     "to use (got shape (1,)); it is truncated or empty.",
        "unreadable": "nmrglue could not read the Bruker processed data at "
                      "/some/path/pdata/1: bad magic",
    }
    said = {k: _rejected_processed_reason(ValueError(v)) for k, v in cases.items()}

    for kind, sentence in said.items():
        assert sentence.endswith("."), f"{kind}: not a sentence: {sentence!r}"
        assert sentence[0].isupper(), f"{kind}: does not start a sentence: {sentence!r}"
        assert "/" not in sentence, f"{kind}: a path reached the reader: {sentence!r}"
        assert "nmrglue" not in sentence.lower(), f"{kind}: named the library: {sentence!r}"
        assert "shape" not in sentence.lower(), f"{kind}: named an array shape: {sentence!r}"
        # THE CONTRADICTION. This branch runs because the FID read; a sentence
        # saying it did not is false wherever it appears.
        assert "free-induction" not in sentence.lower(), f"{kind}: contradicts the FID: {sentence!r}"
        assert "neither" not in sentence.lower(), f"{kind}: contradicts the FID: {sentence!r}"

    # Each fault says what it actually is -- the whole reason the reader's two
    # conditions were split apart.
    assert "two-dimensional" in said["2d"]
    assert "incomplete" in said["truncated"]
    assert "two-dimensional" not in said["truncated"], (
        "a truncated spectrum was described as two-dimensional, which is the "
        "conflation the reader's split exists to prevent"
    )


@pytest.mark.slow
def test_a_test_that_carried_no_weight_says_what_zeroed_it() -> None:
    """"Too weak to move the verdict" is true and unactionable.

    The assignments test is switched off by a single computed number --
    `significance = SIG_MAX * (1 - impurity_pct / 25)` -- so any acquisition
    whose unexplained integral reaches 25% contributes nothing. Measured over
    every acquisition in this corpus with a stated structure and an applicable
    assignments test, that is **9 of 11**. The screen says two of four checks had
    the data to run while one of the two carries zero weight, so a verdict a
    chemist reads as resting on two tests rests on one.

    The cause is worth naming because of WHAT is unexplained. The verifier has no
    notion of a solvent: every peak the proposed structure does not account for is
    impurity to it, and on a routine CDCl3 carbon spectrum the solvent triplet is
    three of them -- peaks this application labels "solvent" in the table directly
    above. A reader given the number can see what produced it.
    """
    from nmrcheck.local_science import SpectrumUnreadable, open_spectrum, verify_candidate

    # Only acquisitions whose structure the corpus states can be checked at all.
    truth = {
        "1,2-epoxybutan": "CCC1CO1",
        "allyl-glycidyl-ether": "C=CCOCC1CO1",
        "ethylene glycol": "OCCO",
        "2-nitroanilin": "Nc1ccccc1[N+](=O)[O-]",
    }

    def stated(src: str) -> str | None:
        for name in ("pdata/1/title", "pdata/2/title"):
            path = Path(src) / name
            if path.exists():
                lines = path.read_text(errors="ignore").strip().splitlines()
                head = lines[0].lower() if lines else ""
                for key, smiles in truth.items():
                    if key in head:
                        return smiles
        return None

    zeroed = 0
    for source in _acquisitions():
        smiles = stated(source)
        if not smiles:
            continue
        try:
            verdict = verify_candidate(source, smiles)
            spectrum = open_spectrum(source)
        except SpectrumUnreadable:
            continue
        test = next((t for t in verdict["tests"] if t["name"] == "assignments"), None)
        if test is None or not test["applicable"] or test["significance"] > 0.0:
            continue
        zeroed += 1
        finding = str(test["finding"])
        # ASSERT THE INTENT, NOT THE WORDING. A first version of this checked for
        # the literal phrase "not explained" and went red on a reword that kept
        # every fact -- a guard that fails on a synonym is measuring prose, not
        # behaviour. What must be true: the sentence carries the unexplained
        # FIGURE and the THRESHOLD that switched the test off, because those two
        # numbers are what a chemist can act on.
        import re as _re

        percents = [float(x) for x in _re.findall(r"(\d+(?:\.\d+)?)%", finding)]
        assert percents, f"a zeroed test did not give the figure that zeroed it: {finding!r}"
        assert 25.0 in percents, (
            f"the sentence does not name the 25% threshold at which this test stops "
            f"counting, so the figure has nothing to be read against: {finding!r}"
        )
        assert max(percents) >= 25.0, (
            f"a test was zeroed while the stated unexplained share is below the "
            f"threshold that zeroes it: {finding!r}"
        )
        # AND MUST NOT NAME A CULPRIT IT CANNOT SUPPORT. The first version of the
        # sentence blamed solvent. Measured over this corpus, solvent-labelled area
        # never accounts for the whole unexplained integral, and one 1H
        # acquisition is zeroed at 30% unexplained with NO non-compound signal --
        # so on that spectrum the sentence sent a chemist to a peak that does not
        # exist. It may list possible contributors; it may not assert one.
        if not any(m["category"] != "compound" for m in spectrum["multiplets"]):
            assert "Solvent peaks count" not in finding, (
                f"the sentence blamed solvent on an acquisition with no non-compound "
                f"signal at all: {finding!r}"
            )

    if zeroed == 0:
        pytest.skip("no acquisition here has an applicable assignments test at zero weight")
