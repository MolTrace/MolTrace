"""A structure is an advantage on the FID path, not an entry requirement.

`POST /raw-fid/{id}/process` required `smiles`. That put the most valuable part
of the product -- turning a vendor FID into a phased, baseline-corrected,
peak-picked spectrum -- behind knowing the answer in advance. The people who
most need it are the ones who do not yet know what they made.

The structure is still worth supplying, and the response now says exactly what
it bought:

* it grounds the proton budget, so integrals become absolute proton counts
  instead of ratios;
* it lets the deterministic verifier run at all, since verification means
  "does this spectrum match THIS structure" and there is nothing to match
  without one.

So without a structure the processing is identical and the analysis is absent
-- not empty, not a guess, absent -- and `analysis`/`generated_inputs` are None.

**The disclosure is the safety condition for the whole change.** Measured on a
real 500 MHz spectrum (validation fixture 33, MeOD): with a 6 H budget the
integrals read 0.008 H, 0.098 H, 0.094 H, 1.0 H...; with no budget the same
peaks read 1.0 H, 14 H, 13.5 H, 123.5 H, 115 H. The ratios are identical -- the
scale is anchored to the smallest resolved signal instead of to a molecule --
but nothing in the response said so, and "123.5H" in an NMR string reads as a
proton count. Eleven warnings were emitted on that spectrum and not one
mentioned it.

That defect predates this change and is not confined to this route: ten call
sites can produce a spectrum with no structural budget. The disclosure is
therefore attached by one shared helper at every one of them, rather than as a
note on the route being touched -- a guard applied to a single caller of a
symmetric condition is the recurring bug shape in this codebase.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

REFERENCE_TEXT = "3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"


def _bruker_acqus(points: int) -> str:
    return f"""##TITLE= process without structure
##$TD= {points * 2}
##$SW_h= 5000.0
##$SW= 10.0
##$SFO1= 500.0
##$BF1= 500.0
##$O1= 2000.0
##$O1P= 4.0
##$NUC1= <1H>
##$SOLVENT= <CDCl3>
##$PULPROG= <zg30>
##$TE= 298.0
##$RG= 32
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""


def _bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.1, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(-time_axis * 10.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", _bruker_acqus(points))
    return buffer.getvalue()


@pytest.fixture
def vault_client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'no_structure.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_vault_dir=str(tmp_path / "raw_data_vault"),
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _upload(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/raw-fid/upload",
        headers=headers,
        files={"file": ("sample.zip", _bruker_zip(), "application/zip")},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["raw_archive_id"])


def _relative_integral_warning(warnings: list[str]) -> str | None:
    for warning in warnings:
        lowered = warning.lower()
        if "relative" in lowered and ("smallest" in lowered or "anchor" in lowered):
            return warning
    return None


class TestProcessingNoLongerNeedsTheAnswerUpFront:
    def test_a_fid_processes_with_no_structure(self, vault_client) -> None:
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"manual_nmr_text": REFERENCE_TEXT},
            )

        assert response.status_code == 200, (
            f"processing was refused without a structure: {response.status_code} "
            f"{response.text[:300]}"
        )

    def test_the_spectrum_is_the_same_spectrum(self, vault_client) -> None:
        """The structure grounds interpretation; it does not change the physics."""
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            without = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"manual_nmr_text": REFERENCE_TEXT},
            )
            with_structure = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
            )

        assert without.status_code == 200, without.text
        assert with_structure.status_code == 200, with_structure.text
        assert len(without.json()["preview"]["preview_points"]) == len(
            with_structure.json()["preview"]["preview_points"]
        )

    def test_no_structure_means_no_verdict_rather_than_a_guess(self, vault_client) -> None:
        """Absent, not empty. A verdict with nothing to verify would be a fiction."""
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"manual_nmr_text": REFERENCE_TEXT},
            )

        body = response.json()
        assert body["analysis"] is None, "a verdict was produced with no structure to verify"
        assert body["generated_inputs"] is None

    def test_supplying_a_structure_still_verifies(self, vault_client) -> None:
        """The existing contract is untouched when the structure is supplied."""
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
            )

        body = response.json()
        assert response.status_code == 200, response.text
        assert body["analysis"] is not None
        assert body["generated_inputs"]["smiles"] == "CCO"


class TestTheIntegralsSayWhatScaleTheyAreOn:
    """The safety condition. Without this the change ships a misleading number."""

    def test_no_structure_discloses_that_integrals_are_relative(self, vault_client) -> None:
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"manual_nmr_text": REFERENCE_TEXT},
            )

        warnings = response.json()["preview"]["warnings"]
        found = _relative_integral_warning(warnings)
        assert found is not None, (
            "integrals were reported with no structural budget and nothing said "
            f"they are relative. Warnings were: {warnings}"
        )

    def test_the_disclosure_names_its_cause(self, vault_client) -> None:
        """A warning that does not say what to do about it is noise."""
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"manual_nmr_text": REFERENCE_TEXT},
            )

        found = _relative_integral_warning(response.json()["preview"]["warnings"]) or ""
        assert "structure" in found.lower(), f"the cause is not named: {found!r}"

    def test_a_supplied_structure_removes_the_disclosure(self, vault_client) -> None:
        """It must be a real condition, not a banner printed unconditionally."""
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(
                f"/raw-fid/{archive_id}/process",
                headers=headers,
                data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
            )

        warnings = response.json()["preview"]["warnings"]
        assert _relative_integral_warning(warnings) is None, (
            "the relative-integral warning appeared even though a structure "
            f"grounded the proton budget: {warnings}"
        )

    def test_the_preview_route_discloses_it_too(self, vault_client) -> None:
        """The sibling route already accepted a missing structure and said nothing.

        Fixing only the route under change would be the half-applied guard this
        codebase keeps producing.
        """
        client, headers = vault_client
        with client:
            archive_id = _upload(client, headers)
            response = client.post(f"/raw-fid/{archive_id}/preview", headers=headers)

        assert response.status_code == 200, response.text
        warnings = response.json()["warnings"]
        assert _relative_integral_warning(warnings) is not None, (
            f"the preview route reports integrals on an undisclosed scale: {warnings}"
        )
