"""Phase 11 legacy-parity verification.

Tests that legacy raw-FID responses now expose the same unified envelope as
the GSD endpoint:
  * ``peaks`` typed as ``LegacyEnrichedPeak[]`` (no longer ``dict[str, Any]``),
    surfacing the per-peak ``category`` + ``solvent_hit`` + ``impurity_match``
    fields that ``enrich_peaks`` was already injecting at runtime.
  * ``environments`` populated via ``cluster_into_environments``, with
    ``environment_count`` + ``environment_counts`` aggregates.

Once both detectors expose the same envelope the FE selector becomes a UI
choice rather than a contract-shape problem.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from tempfile import mkdtemp

import numpy as np
from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    create_app,
    nmr_raw_fid_preview_route,
    nmr_raw_fid_process_route,
)
from nmrcheck.database import init_db
from nmrcheck.models import (
    GSDPromptEnvironment,
    LegacyEnrichedPeak,
    NMRRawFIDPreviewResponse,
    NMRRawFIDProcessResponse,
)
from nmrcheck.settings import Settings


def _bruker_zip(sfo1_mhz: float = 500.0) -> bytes:
    """Minimal valid Bruker 1D zip with two analyte peaks + CHCl3 residual."""

    points = 1024
    sw_hz = 5000.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    # 3.65 + 1.26 analyte peaks plus 7.26 residual CHCl3.
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (7.26, 0.2)]:
        freq = (ppm - center_ppm) * sfo1_mhz
        fid += (
            amplitude
            * np.exp(2j * np.pi * freq * time_axis)
            * np.exp(-time_axis * 10.0)
        )
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = (
        "##TITLE= legacy envelope test fixture\n"
        f"##$TD= {points * 2}\n"
        f"##$SW_h= {sw_hz}\n"
        "##$SW= 10.0\n"
        f"##$SFO1= {sfo1_mhz}\n"
        f"##$BF1= {sfo1_mhz}\n"
        f"##$O1= {center_ppm * sfo1_mhz}\n"
        f"##$O1P= {center_ppm}\n"
        "##$NUC1= <1H>\n"
        "##$BYTORDA= 0\n"
        "##$DTYPA= 0\n"
        "##$GRPDLY= 0\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", acqus)
        archive.writestr("sample/pulseprogram", "zg30\n")
    return buffer.getvalue()


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-legacy-envelope-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/legacy_envelope.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "method": "POST",
            "path": "/nmr/raw-fid/process",
            "query_string": b"",
        }
    )


def _build_upload() -> UploadFile:
    return UploadFile(filename="sample.zip", file=io.BytesIO(_bruker_zip()))


def test_legacy_process_response_surfaces_typed_peak_categories() -> None:
    """Process-route peaks must validate as LegacyEnrichedPeak with category set."""

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="legacy-envelope-process",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert isinstance(result, NMRRawFIDProcessResponse)
        assert result.peaks, "process route must return at least one detected peak"
        # Every peak must validate as the new typed model -- THIS is the
        # Phase 11 contract win: the FE can now `peak.category` in TS
        # because schema.d.ts exposes LegacyEnrichedPeak instead of
        # `dict[str, Any]`.
        for peak in result.peaks:
            assert isinstance(peak, LegacyEnrichedPeak)
        # At least one peak must carry a structured category populated
        # by enrich_peaks (any value in the Literal union is acceptable;
        # the regression the FE flagged was that `category` was invisible
        # via the schema, not that classification was wrong).
        categorised = [p for p in result.peaks if p.category is not None]
        assert categorised, (
            "enrich_peaks must produce a structured category on at least one "
            "peak so the FE's typed schema sees it (Phase 11 fix)."
        )
        observed_categories = {p.category for p in categorised}
        valid_categories = {
            "compound", "solvent", "impurity", "artifact", "13C_satellite",
        }
        assert observed_categories.issubset(valid_categories), (
            f"All categories must be in the typed Literal union; "
            f"got {observed_categories - valid_categories}"
        )
        # At least one peak should also carry a structured solvent_hit or
        # impurity_match payload (the dict shapes FE tooltips render against).
        assert any(
            p.solvent_hit is not None or p.impurity_match is not None
            for p in categorised
        ), "At least one categorised peak must carry solvent_hit or impurity_match"

    asyncio.run(run())


def test_legacy_process_response_populates_environments() -> None:
    """Process-route environments must mirror GSD's clustered output shape."""

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="legacy-envelope-process-envs",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert result.environment_count == len(result.environments)
        assert result.environment_count >= 1
        # Same shape as GSDPromptEnvironment (the FE renders both via one
        # component).
        for env in result.environments:
            assert isinstance(env, GSDPromptEnvironment)
            assert env.peak_count >= 1
            assert env.multiplicity in {
                "s", "d", "t", "q", "quint", "sext", "sept", "m",
            }
            # Constituent indices must be valid offsets into peaks.
            for idx in env.constituent_peak_indices:
                assert 0 <= idx < len(result.peaks)
        # Aggregate counts must equal sum of category appearances.
        assert sum(result.environment_counts.values()) == result.environment_count

    asyncio.run(run())


def test_legacy_preview_response_envelope_matches() -> None:
    """Preview route exposes same env envelope (peaks may be sparser)."""

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="legacy-envelope-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert isinstance(result, NMRRawFIDPreviewResponse)
        # Preview route may emit zero peaks (depending on processing
        # preset + dataset) but must NEVER break the envelope contract.
        assert isinstance(result.peaks, list)
        assert isinstance(result.environments, list)
        assert result.environment_count == len(result.environments)
        assert isinstance(result.environment_counts, dict)
        for peak in result.peaks:
            assert isinstance(peak, LegacyEnrichedPeak)
        for env in result.environments:
            assert isinstance(env, GSDPromptEnvironment)

    asyncio.run(run())


def test_legacy_peak_model_preserves_long_tail_fields() -> None:
    """Pydantic extra='allow' must keep historical dict fields available."""

    # Validate that a legacy peak dict carrying many extra fields (like the
    # full enrich_peaks payload) doesn't lose data through the new model.
    raw = {
        "shift_ppm": 7.26,
        "multiplicity": "s",
        "integration_h": 1.0,
        "category": "solvent",
        "category_reason": "Falls inside CDCl3 residual window.",
        "solvent_hit": {"label": "residual CHCl3"},
        "impurity_match": {"label": "chloroform CH"},
        "chemical_region": "aromatic / alkene proton",
        "labile_hint": False,
        # Long-tail fields not declared in LegacyEnrichedPeak but present
        # in real enrich_peaks output -- must round-trip via extra='allow'.
        "reference_assignment": None,
        "structure_aware_disambiguation": "anomeric",
        "inventory_basis": "trace",
        "inventory_exclude": False,
    }
    peak = LegacyEnrichedPeak.model_validate(raw)
    dumped = peak.model_dump()
    for key in raw:
        assert key in dumped, f"long-tail field {key!r} was dropped by the new model"
    assert dumped["structure_aware_disambiguation"] == "anomeric"


def test_legacy_process_response_populates_per_peak_qc_metrics() -> None:
    """Phase 24: per-peak QC fit metrics populate via the post-detection fit pass.

    Verifies the FE's deferred regulatory-tier ask: legacy raw-FID peaks
    now carry ``fit_redchi`` / ``fit_rmse`` / ``fwhm_ppm`` /
    ``signal_to_noise`` / ``baseline_noise_sigma`` -- the same QC surface
    the GSD endpoint publishes in ``Peak.metadata``.
    """

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="legacy-qc-metrics",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=True,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert result.peaks, "process route returned no peaks"
        # baseline_noise_sigma should be the same value on every peak
        # (spectrum-wide noise estimate) and non-None as long as the trace
        # was non-empty.
        sigmas = {p.baseline_noise_sigma for p in result.peaks}
        assert len(sigmas - {None}) <= 1, (
            f"baseline_noise_sigma should be uniform across peaks; got {sigmas}"
        )
        assert any(p.baseline_noise_sigma is not None for p in result.peaks), (
            "At least one peak should carry baseline_noise_sigma."
        )
        # The fit may fail on some peaks (e.g., near spectrum edges) but at
        # least one should converge and produce a full QC quintuple.
        fully_fit = [
            p for p in result.peaks
            if p.fit_redchi is not None
            and p.fit_rmse is not None
            and p.fwhm_ppm is not None
            and p.signal_to_noise is not None
            and p.baseline_noise_sigma is not None
        ]
        assert fully_fit, (
            f"At least one peak should produce a complete QC quintuple. "
            f"Got {[(p.shift_ppm, p.fit_redchi, p.fit_rmse, p.fwhm_ppm, p.signal_to_noise) for p in result.peaks]}"
        )
        # Sanity ranges for a real Bruker synthetic spectrum:
        for p in fully_fit:
            assert p.fit_rmse >= 0
            assert p.fwhm_ppm > 0
            assert p.signal_to_noise > 0

    asyncio.run(run())


def test_openapi_schema_includes_legacy_enriched_peak_and_envs() -> None:
    """schema.d.ts will surface the new types after npm run generate:openapi."""

    tmpdir = mkdtemp(prefix="nmrcheck-legacy-envelope-openapi-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/openapi.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    schema = app.openapi()
    # LegacyEnrichedPeak must be in components.
    assert "LegacyEnrichedPeak" in schema["components"]["schemas"]
    legacy_peak_props = schema["components"]["schemas"]["LegacyEnrichedPeak"]["properties"]
    for required in ("shift_ppm", "category", "category_reason", "solvent_hit"):
        assert required in legacy_peak_props
    # Both raw-fid response models must expose environments + env_count.
    for response_model in ("NMRRawFIDPreviewResponse", "NMRRawFIDProcessResponse"):
        props = schema["components"]["schemas"][response_model]["properties"]
        for required in ("environments", "environment_count", "environment_counts"):
            assert required in props, f"{response_model} missing {required}"
