"""Pins ``inferred_nmr_text`` onto the ``/nmr/raw-fid/process`` wire contract.

The frontend's ``InferredNmrTextPanel`` is mounted on the Raw FID tab and reads
``payload.inferred_nmr_text``.  ``NMRRawFIDProcessResponse`` carried no such
field, so the panel resolved ``null`` on every raw-FID upload and had never
rendered on that surface.

The failure was **silent**: the panel is deliberately quiet when the field is
missing (so it can be dropped into legacy result shapes), so there was no
console error, no empty card, and no way to tell "the analysis produced no
prose summary" apart from "the frontend is reading a field the response does
not carry".  A green suite and a passing review both survived it.

This is the third instance of that shape on this surface — ``dataset_root``
and ``acquisition_metadata`` were each read from a path a real response did
not use.  So the assertions here run against a **real Bruker archive** and
against the **serialized JSON**, not against a hand-built fixture and not
against the route's return object: a synthetic archive and its reader can
share the same wrong assumption, and an object attribute proves nothing about
the wire.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

HEADERS = {"x-api-key": "test-key"}

# Smallest real Bruker 1H archive in the bundle (~136 KB); also used by
# tests/test_e2e.py.
_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "nmrshiftdb2"
    / "raw"
    / "nmrshiftdb2_60000023_1h.zip"
)


def _client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'raw_fid_inferred_text.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app)


def _process_real_fixture(tmp_path) -> dict:
    if not _FIXTURE.exists():
        pytest.skip(f"Fixture {_FIXTURE.name} not present in test bundle")
    content = _FIXTURE.read_bytes()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/process",
            headers=HEADERS,
            data={
                "sample_id": "inferred-nmr-text",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "vendor": "auto",
                "processing_preset": "balanced",
                # No candidates_text: the ungrounded path is the one the Raw
                # FID tab actually hits, and the one whose integrals are
                # ratios rather than proton counts.
                "include_spectrum": "false",
            },
            files={"file": (_FIXTURE.name, content, "application/zip")},
        )
    assert response.status_code == 200, response.text
    return response.json()


def test_raw_fid_process_returns_inferred_nmr_text(tmp_path) -> None:
    """A real Bruker 1H archive must come back with a non-empty multiplet
    string at the top level of the JSON — the exact path the panel reads."""

    payload = _process_real_fixture(tmp_path)

    assert "inferred_nmr_text" in payload, (
        "/nmr/raw-fid/process response is missing inferred_nmr_text. "
        "InferredNmrTextPanel reads this key and fails silently without it — "
        f"top-level keys were {sorted(payload)}"
    )
    text = payload["inferred_nmr_text"]
    assert isinstance(text, str)
    assert text.strip(), (
        "inferred_nmr_text was present but empty for a real Bruker archive "
        f"that produced {payload.get('peak_count')} peaks. The field is wired "
        "but not populated."
    )


def test_raw_fid_inferred_nmr_text_keeps_the_reparseable_h_suffix(tmp_path) -> None:
    """The string is a machine format, not display copy.

    ``_peaks_to_nmr_text`` emits ``<value>H)`` and the result is fed back as
    ``AnalysisInputs.nmr_text`` and re-parsed; the parser requires the ``H``
    integral, so emitting ``rel.`` server-side would break the round trip.
    Relabelling for display is the frontend's job and is gated on the
    relative-integral disclosure in ``warnings``.
    """

    payload = _process_real_fixture(tmp_path)
    text = payload["inferred_nmr_text"]

    assert "H)" in text, (
        "inferred_nmr_text lost its H integral suffix. That string is "
        "re-parsed as AnalysisInputs.nmr_text — relabel for display in the "
        f"frontend, never at source. Got: {text[:200]!r}"
    )
    assert "rel." not in text, (
        "inferred_nmr_text was relabelled server-side. The re-parse would "
        f"raise PeakParseError. Got: {text[:200]!r}"
    )


def test_raw_fid_ungrounded_integrals_ship_their_disclosure(tmp_path) -> None:
    """Without a structure the integrals are ratios, not proton counts.

    The frontend rewrites ``H)`` to `` rel.)`` only when the payload's
    warnings carry the relative-integral disclosure, matched on two loose
    anchors.  If this pairing ever breaks, the panel renders ratios as if
    they were proton counts — a scientific misstatement, and one with no
    visible symptom.  Pin the anchors alongside the field they gate.
    """

    payload = _process_real_fixture(tmp_path)
    warnings = " ".join(payload.get("warnings") or [])

    for anchor in ("integrals are relative", "smallest resolved signal"):
        assert anchor in warnings, (
            f"Relative-integral disclosure anchor {anchor!r} is absent from "
            "the raw-FID warnings, so the frontend will render the "
            "inferred_nmr_text integrals as proton counts. Anchors live in "
            "moltrace_frontend/components/spectracheck/"
            f"spectracheck-relative-integrals.ts. Warnings were: {warnings!r}"
        )
