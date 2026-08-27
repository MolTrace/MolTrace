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
    rather than a finding. Measured: four instrument-processed 13C acquisitions
    came back at exactly the level-2 ceiling and were reported as 68 to 188
    distinct signals. No 13C spectrum of a real compound has 188 carbons, and a
    chemist shown that number stops trusting everything beside it.

    Both halves, because a warning on every spectrum is a warning nobody reads.
    """
    from moltrace.spectroscopy.peaks.gsd import _MAX_PEAKS_BY_LEVEL
    from nmrcheck.local_science import _DEFAULT_GSD_LEVEL, open_spectrum

    ceiling = _MAX_PEAKS_BY_LEVEL[_DEFAULT_GSD_LEVEL]
    results = [open_spectrum(s) for s in _acquisitions()]
    if not results:
        pytest.skip("no acquisitions in this checkout")

    saturated = [r for r in results if r["peak_count"] >= ceiling]
    clean = [r for r in results if r["peak_count"] < ceiling]
    assert saturated, "nothing saturates here — this guard is asserting against an empty set"

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
