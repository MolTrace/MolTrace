"""End-to-end Phase 0 smoke + determinism test (Prompt 19, deliverable #6).

One *real* Bruker FID flows through the entire SpectraCheck pipeline (Prompts
1-9) and on into the Phase 0 foundation:

    raw FID
      -> read_fid (Prompts 1-2)
      -> gsd_peak_pick -> auto_classify -> detect_multiplets -> integrate (3-9)
      -> data-validation gate (infra.validation)
      -> versioned output contract (infra.contract)
      -> ComplianceCore handoff: ICH Q2(R2) report stub + GAMP 5 D11 doc
      -> experiment tracking + content-addressed dataset pin (lineage)

Two properties are asserted:

* **smoke** -- the whole stack runs green on a genuine instrument file, the
  validation gate passes, the contract/ICH stub/GAMP doc are produced, and the
  run is tracked + the dataset pinned and restored with verified integrity; and
* **determinism** -- the structured ComplianceCore handoff is *byte-for-byte*
  identical across 10 independent runs of the same FID.  This is the invariant
  the regression gates and the 21 CFR Part 11 audit trail depend on.

Requires nmrglue (the ``fid`` extra); each test ``importorskip``s it.  The whole
module runs in ~1-2 s, so it stays in the default (non-``slow``) suite and is
picked up by the existing CI ``test`` job (``uv run pytest`` with ``--extra fid``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from moltrace.spectroscopy.infra.compliance import (
    build_ich_report_stub,
    render_gamp5_d11_template,
    render_ich_report_stub,
)
from moltrace.spectroscopy.infra.contract import (
    SCHEMA_VERSION,
    SpectraCheckContract,
    canonical_json,
    content_hash,
    contract_from_pipeline,
)
from moltrace.spectroscopy.infra.tracking import ExperimentTracker, NativeRunStore
from moltrace.spectroscopy.infra.validation import (
    assert_valid_spectrum_input,
    validate_spectrum_input,
)
from moltrace.spectroscopy.infra.versioning import LocalDatasetRemote, dataset_hash
from moltrace.spectroscopy.integration import integrate
from moltrace.spectroscopy.io.fid_reader import read_fid
from moltrace.spectroscopy.multiplet import detect_multiplets
from moltrace.spectroscopy.peaks import auto_classify, gsd_peak_pick

# Smallest real Bruker 1H dataset in the corpus (NMRShiftDB2 id 60000023).
_FIXTURE = (
    Path(__file__).parent / "fixtures" / "nmrshiftdb2" / "raw" / "nmrshiftdb2_60000023_1h.zip"
)

_GSD_LEVEL = 2
_MULTIPLET_TOLERANCE_HZ = 0.5
_INTEGRATION_METHOD = "edited_sum"
_DATASET_TAG = "nmrshiftdb2-60000023-1h"


def _spectrum_validation_payload(spectrum: Any) -> dict[str, Any]:
    """The dict the data-validation gate consumes for an inference input."""

    return {
        "nucleus": spectrum.nucleus,
        "field_mhz": spectrum.field_mhz,
        "ppm_axis": spectrum.ppm_axis,
        "intensity": spectrum.data,
    }


def _run_pipeline(fixture: Path) -> dict[str, Any]:
    """Run the full real-FID pipeline once and assemble the ComplianceCore handoff.

    Re-reads the FID from disk on every call (so the determinism guarantee covers
    the ingestion + Fourier transform too, not just the analysis stack) and fails
    loudly via the validation gate before any contract is emitted.  Returns both
    the live pipeline objects (for the smoke assertions) and the canonical,
    JSON-serialisable ``handoff`` bundle (for the determinism assertion).
    """

    spectrum = read_fid(fixture)

    # Data-validation gate: inference input must pass before it enters analysis.
    assert_valid_spectrum_input(_spectrum_validation_payload(spectrum))

    raw_peaks = gsd_peak_pick(spectrum, level=_GSD_LEVEL)
    peaks = auto_classify(raw_peaks, spectrum, spectrum.solvent)
    multiplets = detect_multiplets(peaks, tolerance_hz=_MULTIPLET_TOLERANCE_HZ)

    region_peaks = [p for p in peaks if p.category == "compound"] or list(peaks)
    lo = min(p.position_ppm for p in region_peaks)
    hi = max(p.position_ppm for p in region_peaks)
    integration = integrate(
        spectrum, (lo - 0.5, hi + 0.5), region_peaks, method=_INTEGRATION_METHOD
    )

    contract = contract_from_pipeline(spectrum, peaks, multiplets, integration)
    ich_stub = build_ich_report_stub(contract)

    # The structured artefact handed to the ComplianceCore.  Every field is a
    # pure function of the FID (no timestamps / run ids), so it is reproducible.
    handoff = {
        "contract": contract.to_envelope(),
        "ich_report_stub": ich_stub,
        "regulatory_hub": {
            "accepted": True,
            "content_hash": contract.content_hash(),
            "ich_guideline": ich_stub["ich_guideline"],
            "schema_version": SCHEMA_VERSION,
        },
    }

    return {
        "spectrum": spectrum,
        "peaks": peaks,
        "multiplets": multiplets,
        "integration": integration,
        "contract": contract,
        "ich_stub": ich_stub,
        "handoff": handoff,
    }


# --------------------------------------------------------------------------- #
# Smoke: the whole Phase 0 stack runs green on a real instrument file.
# --------------------------------------------------------------------------- #
def test_e2e_pipeline_runs_green(tmp_path) -> None:
    pytest.importorskip("nmrglue", reason="end-to-end FID smoke requires the `fid` extra")
    assert _FIXTURE.exists(), f"missing e2e fixture: {_FIXTURE}"

    result = _run_pipeline(_FIXTURE)
    spectrum = result["spectrum"]
    contract: SpectraCheckContract = result["contract"]
    stub = result["ich_stub"]

    # -- pipeline produced real, well-formed features --------------------- #
    assert spectrum.nucleus == "1H"
    assert spectrum.field_mhz > 0
    assert len(result["peaks"]) > 0
    assert len(result["multiplets"]) > 0
    assert result["integration"].method_used == _INTEGRATION_METHOD

    # -- the validation gate accepts this spectrum ----------------------- #
    report = validate_spectrum_input(_spectrum_validation_payload(spectrum))
    assert report.success
    assert report.failures == ()

    # -- versioned output contract --------------------------------------- #
    assert contract.nucleus == "1H"
    assert contract.classification_summary  # categories were assigned
    assert sum(contract.classification_summary.values()) == len(contract.peaks)
    chash = contract.content_hash()
    assert chash.startswith("sha256:")
    # envelope carries the schema version + the same content hash.
    envelope = contract.to_envelope()
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["content_hash"] == chash

    # -- ComplianceCore handoff: ICH Q2(R2) stub is hash-traceable ------- #
    assert stub["ich_guideline"] == "Q2(R2)"
    assert stub["evidence"]["contract_content_hash"] == chash
    ich_md = render_ich_report_stub(stub)
    assert "ICH Q2(R2) Report (Stub)" in ich_md
    assert chash in ich_md  # the content hash is printed in the report

    # -- GAMP 5 Appendix D11 validation document renders ----------------- #
    gamp_doc = render_gamp5_d11_template(
        system_name="MolTrace SpectraCheck",
        system_version="0.39.0",
        intended_use="Automated NMR structure verification for GxP release testing.",
    )
    assert "Computerised System Validation" in gamp_doc
    assert "Performance Qualification (PQ)" in gamp_doc

    # -- experiment tracking: log the run with the dataset-version link --- #
    tracker = ExperimentTracker(
        experiment="e2e",
        tracking_root=tmp_path / "runs",
        backend="native",
        git_sha="e2e-test-sha",
    )
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(canonical_json(result["handoff"]))
    with tracker.start_run(
        "e2e-smoke", params={"gsd_level": _GSD_LEVEL, "integration_method": _INTEGRATION_METHOD}
    ) as run:
        run.log_metrics(
            {
                "peak_count": float(len(result["peaks"])),
                "multiplet_count": float(len(result["multiplets"])),
                "integration_value": float(result["integration"].value),
            }
        )
        run.set_dataset_version(_DATASET_TAG)
        run.log_artifact(handoff_path)
        run_id = run.run_id

    record = NativeRunStore(tmp_path / "runs").read("e2e", run_id)
    assert record["git_sha"] == "e2e-test-sha"
    assert record["dataset_version"] == _DATASET_TAG
    assert record["metrics"]["peak_count"] == pytest.approx(len(result["peaks"]))
    assert record["artifacts"]  # the handoff bundle was logged

    # -- data versioning: pin the raw FID, restore, verify integrity ----- #
    remote = LocalDatasetRemote(tmp_path / "store")
    pinned = remote.pin(_FIXTURE, _DATASET_TAG)
    assert pinned.dataset_hash.startswith("sha256:")
    dest = tmp_path / "restored.zip"
    restored = remote.restore(_DATASET_TAG, dest)
    assert dest.exists()
    assert restored.dataset_hash == pinned.dataset_hash
    assert dataset_hash(dest) == pinned.dataset_hash


# --------------------------------------------------------------------------- #
# Determinism: the same FID, 10x, yields byte-identical structured output.
# --------------------------------------------------------------------------- #
def test_e2e_output_is_byte_identical_across_10_runs() -> None:
    pytest.importorskip("nmrglue", reason="end-to-end FID smoke requires the `fid` extra")
    assert _FIXTURE.exists(), f"missing e2e fixture: {_FIXTURE}"

    serialised: list[str] = []
    hashes: set[str] = set()
    for _ in range(10):
        result = _run_pipeline(_FIXTURE)
        serialised.append(canonical_json(result["handoff"]))
        hashes.add(result["contract"].content_hash())

    # Byte-for-byte identical canonical serialisation across all 10 runs.
    assert len(set(serialised)) == 1, "non-deterministic handoff across runs"
    # ...and a single stable contract content hash.
    assert len(hashes) == 1
    # The canonical bytes hash to the contract's embedded content hash's input,
    # i.e. re-hashing the handoff is itself stable.
    assert content_hash(serialised[0]) == content_hash(serialised[-1])


# --------------------------------------------------------------------------- #
# Ingestion determinism: read_fid alone is reproducible (isolates the FT stage).
# --------------------------------------------------------------------------- #
def test_e2e_read_fid_is_deterministic() -> None:
    pytest.importorskip("nmrglue", reason="end-to-end FID smoke requires the `fid` extra")
    assert _FIXTURE.exists(), f"missing e2e fixture: {_FIXTURE}"

    import numpy as np

    first = read_fid(_FIXTURE)
    second = read_fid(_FIXTURE)
    assert first.fingerprint_hash == second.fingerprint_hash
    assert np.array_equal(first.ppm_axis, second.ppm_axis)
    assert np.array_equal(first.data, second.data)
