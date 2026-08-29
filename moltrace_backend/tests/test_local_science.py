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
