"""Processed-spectrum ingest: Bruker pdata and JCAMP-DX (B2).

Why this exists
---------------
``read_fid`` handles raw **time-domain** data — Bruker/Varian FIDs, which MolTrace
then apodizes, Fourier-transforms and phases itself. But most customers hold
**processed** data: a Bruker ``pdata/N/1r``, or a JCAMP-DX export. Before this,
none of it could be ingested at all, which was the narrowest part of the ingest
surface and the thing gating evaluation against real spectra.

The distinction that makes this more than a file-format exercise
----------------------------------------------------------------
Processed data arrives already apodized, phased, baseline-corrected and
referenced **by someone else**. A quantitation claim over a spectrum an unknown
operator processed is a different evidentiary class from one over a FID we
processed ourselves — and in a regulated context that difference is the whole
point. So the reader's job is not only to load the numbers, it is to **record
what was already done to them** and to say so, rather than presenting vendor-
processed data as if MolTrace had derived it.

Hence the invariants below:

* the spectrum declares its domain, so nothing downstream can mistake vendor
  processing for ours;
* every processing step the vendor recorded is preserved verbatim;
* referencing is **read** from the file, never assumed — and when it cannot be
  established, that is stated rather than defaulted to zero;
* processed data is never re-processed (no second apodization or FT).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import FIDReaderError, read_processed_spectrum

_ROOT = Path(__file__).resolve().parents[2]

BRUKER_PDATA = _ROOT / "validation_fixtures/bruker/33/pdata/1"
BRUKER_PDATA_13C = (
    _ROOT
    / "tests/fixtures/nmrshiftdb2/raw/extracted"
    / "nmrshiftdb2_60001552_13c_bruker/b170412lsdk.EGlycol/1/pdata/1"
)
JCAMP_13C = (
    _ROOT
    / "tests/fixtures/nmrshiftdb2/raw/extracted"
    / "nmrshiftdb2_60000015_13c_bruker/2/spectrum.dx"
)


def _require(path: Path) -> Path:
    if not path.exists():  # pragma: no cover - fixtures ship with the repo
        pytest.skip(f"fixture missing: {path}")
    return path


@pytest.fixture(scope="module")
def bruker_1h():
    return read_processed_spectrum(_require(BRUKER_PDATA))


@pytest.fixture(scope="module")
def jcamp_13c():
    return read_processed_spectrum(_require(JCAMP_13C))


# --------------------------------------------------------------------------- #
# It loads at all
# --------------------------------------------------------------------------- #
def test_reads_a_bruker_pdata_directory(bruker_1h):
    assert bruker_1h.data.size > 1000
    assert bruker_1h.data.shape == bruker_1h.ppm_axis.shape
    assert np.all(np.isfinite(bruker_1h.data))
    assert bruker_1h.nucleus == "1H"
    assert bruker_1h.field_mhz == pytest.approx(500.16, abs=0.5)


def test_reads_a_jcampdx_file(jcamp_13c):
    assert jcamp_13c.data.size > 1000
    assert jcamp_13c.data.shape == jcamp_13c.ppm_axis.shape
    assert jcamp_13c.nucleus == "13C"
    assert jcamp_13c.field_mhz == pytest.approx(125.77, abs=0.5)


def test_axis_descends_like_read_fid(bruker_1h, jcamp_13c):
    """Downstream code assumes a descending ppm axis; both paths must match."""

    for spectrum in (bruker_1h, jcamp_13c):
        assert spectrum.ppm_axis[0] > spectrum.ppm_axis[-1]
        assert np.all(np.diff(spectrum.ppm_axis) < 0)


def test_ppm_axis_is_chemically_plausible(bruker_1h, jcamp_13c):
    """A mis-derived axis is the failure mode that silently ruins every shift."""

    assert -5.0 < bruker_1h.ppm_axis[-1] < bruker_1h.ppm_axis[0] < 20.0
    assert -20.0 < jcamp_13c.ppm_axis[-1] < jcamp_13c.ppm_axis[0] < 250.0


# --------------------------------------------------------------------------- #
# The part that makes it evidence rather than just numbers
# --------------------------------------------------------------------------- #
def test_domain_is_declared_so_vendor_processing_is_never_mistaken_for_ours(bruker_1h):
    """A processed spectrum must not be indistinguishable from one we derived."""

    assert bruker_1h.metadata["domain"] == "frequency"
    assert bruker_1h.metadata["processed_by"] == "vendor"


def test_vendor_processing_steps_are_preserved(bruker_1h):
    """What was already done to this data, recorded rather than discarded.

    Fixture 33 was apodized (WDW=1, LB=0.25 Hz) and phased (PHC0=-25.22). A
    reviewer must be able to see that MolTrace did not do those things.
    """

    provenance = bruker_1h.metadata["processing_provenance"]
    assert provenance["window_function"] == "exponential"
    assert provenance["line_broadening_hz"] == pytest.approx(0.25)
    assert provenance["phase_zero_order"] == pytest.approx(-25.22)
    assert provenance["phase_first_order"] == pytest.approx(0.0)
    assert provenance["source"] == "Bruker procs"


def test_referencing_is_read_from_the_file_not_assumed(bruker_1h):
    """A wrong reference shifts every peak; it must come from the data."""

    referencing = bruker_1h.metadata["referencing"]
    assert referencing["established"] is True
    assert referencing["basis"] == "Bruker procs SF/OFFSET"
    # OFFSET is the ppm of the first (leftmost) point, by definition.
    assert bruker_1h.ppm_axis[0] == pytest.approx(referencing["offset_ppm"], abs=1e-3)


def test_processed_data_is_not_reprocessed(bruker_1h):
    """No second apodization or FT — the vendor already did it.

    Re-transforming frequency-domain data would produce confident nonsense, so
    the metadata that read_fid uses to describe *its own* processing must be
    absent here rather than misleadingly present.
    """

    assert "apodization" not in bruker_1h.metadata
    assert "zero_fill_points" not in bruker_1h.metadata
    assert bruker_1h.metadata.get("moltrace_processing") == "none"


def test_fingerprint_is_populated(bruker_1h, jcamp_13c):
    """Dedup and audit both key on this."""

    for spectrum in (bruker_1h, jcamp_13c):
        assert spectrum.fingerprint_hash
        assert len(spectrum.fingerprint_hash) == 64
    assert bruker_1h.fingerprint_hash != jcamp_13c.fingerprint_hash


def test_jcamp_hz_axis_is_converted_using_the_observe_frequency(jcamp_13c):
    """JCAMP stores this fixture's axis in Hz; ppm needs the carrier frequency.

    Treating Hz as ppm would put every 13C peak at ~190x its true shift, which is
    obvious on inspection but silent in code.
    """

    referencing = jcamp_13c.metadata["referencing"]
    assert referencing["established"] is True
    assert "Hz" in referencing["basis"] or "ppm" in referencing["basis"]
    assert jcamp_13c.ppm_axis[0] < 250.0, "axis still looks like Hz, not ppm"


# --------------------------------------------------------------------------- #
# Ground truth — the tests that would actually catch a wrong axis
# --------------------------------------------------------------------------- #
def _peaks_ppm(spectrum, relative_threshold: float = 0.25):
    data, axis = spectrum.data, spectrum.ppm_axis
    threshold = float(np.max(data)) * relative_threshold
    return [
        float(axis[i])
        for i in range(1, data.size - 1)
        if data[i] > threshold and data[i] >= data[i - 1] and data[i] >= data[i + 1]
    ]


def test_ethylene_glycol_carbon_lands_at_its_literature_shift():
    """A known compound, a known answer.

    Ethylene glycol's two carbons are equivalent, so ¹³C shows a single line at
    ~63 ppm. Every structural assertion in this file would still pass with a
    subtly wrong axis; this one would not.
    """

    spectrum = read_processed_spectrum(_require(BRUKER_PDATA_13C))
    peaks = _peaks_ppm(spectrum)
    assert peaks, "no peaks found above threshold"
    assert any(61.0 < p < 65.0 for p in peaks), (
        f"expected the ethylene-glycol carbon near 63 ppm, found peaks at {peaks}"
    )


def test_jcamp_spectrum_shows_the_cdcl3_solvent_peak(jcamp_13c):
    """CDCl₃ resonates at 77.16/77.00/76.84 ppm — a built-in axis ruler.

    This fixture stores its axis in **Hz**, so the solvent peak landing at 77 ppm
    is direct evidence the Hz→ppm conversion used the right carrier frequency.
    Get that wrong and every shift is off by ~190x, with nothing to signal it.
    """

    peaks = _peaks_ppm(jcamp_13c)
    assert any(76.0 < p < 78.0 for p in peaks), (
        f"expected the CDCl3 triplet near 77 ppm, found peaks at {sorted(peaks, reverse=True)}"
    )


# --------------------------------------------------------------------------- #
# Refusals name their cause
# --------------------------------------------------------------------------- #
def test_missing_path_names_its_cause(tmp_path):
    with pytest.raises(FIDReaderError, match="does not exist"):
        read_processed_spectrum(tmp_path / "nope")


def test_directory_without_processed_data_names_its_cause(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FIDReaderError) as excinfo:
        read_processed_spectrum(tmp_path / "empty")
    message = str(excinfo.value)
    assert "1r" in message or "processed" in message.lower()


def test_a_raw_fid_directory_is_rejected_with_guidance(tmp_path):
    """Pointing this at a FID is a plausible mistake; the error must redirect."""

    dataset = tmp_path / "fid_only"
    dataset.mkdir()
    (dataset / "fid").write_bytes(b"\x00" * 128)
    (dataset / "acqus").write_text("##$TD= 128\n")

    with pytest.raises(FIDReaderError) as excinfo:
        read_processed_spectrum(dataset)
    assert "read_fid" in str(excinfo.value)


def test_data_is_finite_and_not_all_zero(bruker_1h, jcamp_13c):
    for spectrum in (bruker_1h, jcamp_13c):
        assert np.all(np.isfinite(spectrum.data))
        assert float(np.max(np.abs(spectrum.data))) > 0.0
        assert math.isfinite(float(np.sum(spectrum.data)))
