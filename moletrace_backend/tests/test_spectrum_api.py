import asyncio
import io
from tempfile import mkdtemp

from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import AccessContext, create_app, spectrum_analyze, spectrum_preview
from nmrcheck.database import init_db
from nmrcheck.settings import Settings

TOBRAMYCIN_SMILES = "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N"
TOBRAMYCIN_REFERENCE_TEXT = """'H NMR (500 MHz, D2O) 8 5.23 (d, J = 3.6 Hz, 1H), 5.08 (d, J = 3.9 Hz, 1H), 3.95 (ddd,
J= 10.3, 4.6, 2.6 Hz, 1H), 3.80 (dd, J = 6.6, 3.6 Hz, 2H), 3.68 (tdd, J = 9.2, 5.6, 3.1 Hz,
2H), 3.60 - 3.53 (т, 3H), 3.40 - 3.33 (m, 3H), 3.32 - 3.23 (m, 1H), 3.11 - 2.98 (m, 4H),
2.93 (tdd, J = 11.9,9.7, 4.1 Hz, 3H), 2.83 (dd, J = 13.6, 7.5 Hz, 1H), 2.07 (dt, J = 11.8,
4.5 Hz, 1H), 2.00 (dt, J = 13.0, 4.2 Hz, 1H), 1.71 - 1.60 (m, 1H), 1.27 (q, J = 12.5 Hz,
1H)"""
TRACE_CSV = """ppm,intensity
5.50,0
5.35,1
5.28,4
5.23,8
5.18,4
5.12,1
5.02,3
4.95,24
4.88,36
4.81,44
4.74,34
4.67,18
4.60,5
4.20,0
4.08,1
4.00,4
3.95,7
3.90,3
3.84,1
3.72,2
3.68,5
3.64,2
3.20,0
"""


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-spectrum-api-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/spectrum_api.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/spectrum/test",
        "query_string": b"",
    }
    return Request(scope)


def _build_upload() -> UploadFile:
    return UploadFile(filename="tobramycin.csv", file=io.BytesIO(TRACE_CSV.encode("utf-8")))


def test_spectrum_preview_api_accepts_reference_text_and_returns_comparison() -> None:
    async def run() -> None:
        preview = await spectrum_preview(
            request=_build_request(),
            file=_build_upload(),
            smiles=TOBRAMYCIN_SMILES,
            solvent="D2O",
            frequency_mhz=None,
            reference_ppm=None,
            reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
            peak_sensitivity=None,
            mask_solvent_regions=True,
            context=AccessContext(system_api_key=True),
        )

        assert preview.reference_nmr_text_normalized is not None
        assert preview.reference_nmr_text_normalized.startswith("1H NMR (500 MHz, D2O) δ 5.23")
        assert len(preview.reference_peaks) == 15
        assert preview.comparison is not None
        assert preview.comparison.structure_visible_h == 22.0
        assert preview.comparison.structure_reference_mismatch is True
        assert any(peak.j_values_hz for peak in preview.reference_peaks)

    asyncio.run(run())


def test_spectrum_analyze_api_accepts_manual_reviewed_nmr_text_override() -> None:
    manual_nmr_text = (
        "5.23 (d, 1H), 5.08 (d, 1H), 3.95 (m, 1H), 3.80 (m, 2H), 3.68 (m, 2H), "
        "3.56 (m, 3H), 3.37 (m, 3H), 3.28 (m, 1H), 3.04 (m, 4H), 2.93 (m, 3H), 1.66 (m, 1H)"
    )

    async def run() -> None:
        result = await spectrum_analyze(
            request=_build_request(),
            file=_build_upload(),
            smiles=TOBRAMYCIN_SMILES,
            sample_id=None,
            solvent="D2O",
            frequency_mhz=None,
            reference_ppm=None,
            reference_nmr_text=None,
            manual_nmr_text=manual_nmr_text,
            peak_sensitivity=None,
            mask_solvent_regions=True,
            context=AccessContext(system_api_key=True),
        )

        assert result.generated_inputs.nmr_text == manual_nmr_text
        assert result.analysis.notes
        assert "Reviewer-adjusted peak acceptance/exclusion decisions were used" in result.analysis.notes[0]

    asyncio.run(run())


def test_spectrum_analyze_api_returns_generated_nmr_text_with_j_values_when_available() -> None:
    async def run() -> None:
        result = await spectrum_analyze(
            request=_build_request(),
            file=_build_upload(),
            smiles=TOBRAMYCIN_SMILES,
            sample_id=None,
            solvent="D2O",
            frequency_mhz=500.0,
            reference_ppm=None,
            reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
            manual_nmr_text=None,
            peak_sensitivity=None,
            mask_solvent_regions=True,
            context=AccessContext(system_api_key=True),
        )

        assert "J = 3.6 Hz" in result.generated_inputs.nmr_text
        assert "J = 12.5 Hz" in result.generated_inputs.nmr_text

    asyncio.run(run())
