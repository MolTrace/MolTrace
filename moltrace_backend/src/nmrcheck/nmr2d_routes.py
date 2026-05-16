from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from .database import get_nmr2d_run_by_id, save_nmr2d_run, update_nmr2d_run_review_status
from .compound_classes import normalize_compound_class
from .dept import DeptAptParseError, analyze_dept_apt_preview, parse_dept_apt_table
from .exceptions import StructureParseError
from .nmr2d_models import NMR2DAnalysisReport, NMR2DPreview, NMR2DRunRecord
from .nmr2d import NMR2DParseError, analyze_nmr2d, parse_nmr2d_upload

router = APIRouter(prefix="/nmr2d", tags=["2D NMR"])


class NMR2DRunReviewUpdate(BaseModel):
    review_status: Literal["pending_review", "approved", "rejected", "needs_revision"]
    comment: str | None = Field(default=None, max_length=1000)


def _feature_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state.settings, "enable_2d_nmr", False))


def _contour_preview_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state.settings, "enable_2d_contour_preview", True))


def _raw_2d_fid_beta_enabled(request: Request) -> bool:
    return bool(getattr(request.app.state.settings, "enable_raw_2d_fid_beta", False))


def require_nmr2d_enabled(request: Request) -> None:
    if not _feature_enabled(request):
        raise HTTPException(status_code=404, detail="2D NMR evidence engine is disabled by feature flag.")


def _require_contour_preview_if_requested(request: Request, include_contour_preview: bool) -> None:
    if include_contour_preview and not _contour_preview_enabled(request):
        raise HTTPException(
            status_code=403,
            detail="2D contour preview is disabled by feature flag ENABLE_2D_CONTOUR_PREVIEW.",
        )


@router.get("/status")
def nmr2d_status(request: Request) -> dict[str, object]:
    raw_beta_enabled = _raw_2d_fid_beta_enabled(request)
    return {
        "enabled": _feature_enabled(request),
        "feature_flag": "ENABLE_2D_NMR",
        "contour_preview_enabled": _contour_preview_enabled(request),
        "contour_preview_feature_flag": "ENABLE_2D_CONTOUR_PREVIEW",
        "raw_2d_fid_beta_enabled": raw_beta_enabled,
        "raw_2d_fid_beta_feature_flag": "ENABLE_RAW_2D_FID_BETA",
        "supported_experiments": ["COSY", "HSQC", "HMQC", "HMBC"],
        "raw_2d_fid_processing": "beta_enabled_stub" if raw_beta_enabled else "disabled",
        "guarded_release": True,
    }


@router.post("/preview", response_model=NMR2DPreview, dependencies=[Depends(require_nmr2d_enabled)])
async def nmr2d_preview(
    request: Request,
    file: UploadFile = File(...),
    experiment: str | None = Form(default=None),
    compound_class: str | None = Form(default=None),
    include_contour_preview: bool = Form(default=False),
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> NMR2DPreview:
    _require_contour_preview_if_requested(request, include_contour_preview)
    filename = file.filename or "processed_2d_nmr.csv"
    content = await file.read()
    normalized_compound_class = normalize_compound_class(compound_class)
    try:
        preview = parse_nmr2d_upload(
            filename,
            content,
            experiment_hint=experiment,
            include_contour_preview=include_contour_preview,
        )
        preview = preview.model_copy(
            update={"metadata": {**preview.metadata, "compound_class": normalized_compound_class}}
        )
    except (NMR2DParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    api = __import__("nmrcheck.api", fromlist=["_audit_from_context"])
    api._audit_from_context(
        request,
        context=context,
        event_type="nmr2d.preview",
        message="Processed 2D NMR table previewed.",
        metadata={
            "filename": filename,
            "experiments": preview.experiments,
            "peak_count": preview.peak_count,
            "compound_class": normalized_compound_class,
        },
    )
    return preview


@router.post("/analyze", response_model=NMR2DAnalysisReport, dependencies=[Depends(require_nmr2d_enabled)])
async def nmr2d_analyze(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    compound_class: str | None = Form(default=None),
    proton_nmr_text: str | None = Form(default=None),
    carbon13_text: str | None = Form(default=None),
    experiment: str | None = Form(default=None),
    include_contour_preview: bool = Form(default=False),
    analysis_id: int | None = Form(default=None),
    save_run: bool = Form(default=True),
    dept_apt_file: UploadFile | None = File(default=None),
    dept_apt_experiment_type: str | None = Form(default=None),
    apt_positive: str = Form(default="CH_CH3"),
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> NMR2DAnalysisReport:
    _require_contour_preview_if_requested(request, include_contour_preview)
    filename = file.filename or "processed_2d_nmr.csv"
    content = await file.read()
    normalized_compound_class = normalize_compound_class(compound_class)
    try:
        preview = parse_nmr2d_upload(
            filename,
            content,
            experiment_hint=experiment,
            include_contour_preview=include_contour_preview,
        )
        preview = preview.model_copy(
            update={"metadata": {**preview.metadata, "compound_class": normalized_compound_class}}
        )
        dept_apt_peaks = None
        dept_apt_metadata = None
        if dept_apt_file is not None:
            dept_content = await dept_apt_file.read()
            if dept_content:
                dept_preview = parse_dept_apt_table(
                    dept_apt_file.filename or "dept_apt_peaks.csv",
                    dept_content,
                    experiment_type=dept_apt_experiment_type,
                    apt_positive=apt_positive,
                )
                dept_result = analyze_dept_apt_preview(
                    dept_preview,
                    carbon13_text=carbon13_text,
                    solvent=solvent,
                )
                dept_apt_peaks = dept_result.preview.peaks
                dept_apt_metadata = {
                    "filename": dept_apt_file.filename or "dept_apt_peaks.csv",
                    "experiment_detected": dept_result.preview.experiment_detected,
                    "typed_peak_count": dept_result.typed_peak_count,
                    "type_summary": dept_result.type_summary,
                    "matched_carbon13_count": dept_result.matched_carbon13_count,
                    "dept_apt_consistency_score": dept_result.dept_apt_consistency_score,
                    "apt_positive_convention": dept_result.preview.metadata.get("apt_positive_convention"),
                    "warnings": list(dict.fromkeys([*dept_result.warnings, *dept_result.preview.warnings])),
                    "notes": dept_result.notes,
                }
        report = analyze_nmr2d(
            smiles=smiles,
            preview=preview,
            sample_id=sample_id,
            solvent=solvent,
            proton_nmr_text=proton_nmr_text,
            carbon13_text=carbon13_text,
            dept_apt_peaks=dept_apt_peaks,
            dept_apt_metadata=dept_apt_metadata,
        )
        report = report.model_copy(
            update={"metadata": {**report.metadata, "compound_class": normalized_compound_class}}
        )
    except (NMR2DParseError, DeptAptParseError, StructureParseError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_id = None
    if save_run:
        run = save_nmr2d_run(
            request.app.state.session_factory,
            report,
            source_filename=filename,
            user_id=getattr(context, "user_id", None),
            analysis_id=analysis_id,
        )
        run_id = run.id
        report = report.model_copy(update={"run_id": run_id})
    api = __import__("nmrcheck.api", fromlist=["_audit_from_context"])
    api._audit_from_context(
        request,
        context=context,
        event_type="nmr2d.analyze",
        message="Processed 2D NMR evidence analyzed." if not save_run else "Processed 2D NMR evidence analyzed and saved.",
        entity_type="nmr2d_run" if save_run else None,
        entity_id=run_id,
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "experiments": report.experiments,
            "overall_score": report.overall_score,
            "compound_class": normalized_compound_class,
            "human_review_required": True,
            "saved_run": save_run,
        },
    )
    return report


@router.get("/runs/{run_id}", response_model=NMR2DRunRecord, dependencies=[Depends(require_nmr2d_enabled)])
def nmr2d_run_report(
    run_id: int,
    request: Request,
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> NMR2DRunRecord:
    user_id = None if getattr(context, "system_api_key", False) else getattr(context, "user_id", None)
    record = get_nmr2d_run_by_id(request.app.state.session_factory, run_id=run_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="2D NMR run not found.")
    return record


@router.get("/runs/{run_id}/report", response_model=NMR2DAnalysisReport, dependencies=[Depends(require_nmr2d_enabled)])
def nmr2d_run_evidence_report(
    run_id: int,
    request: Request,
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> NMR2DAnalysisReport:
    user_id = None if getattr(context, "system_api_key", False) else getattr(context, "user_id", None)
    record = get_nmr2d_run_by_id(request.app.state.session_factory, run_id=run_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="2D NMR run not found.")
    return record.report


@router.post("/runs/{run_id}/review", response_model=NMR2DRunRecord, dependencies=[Depends(require_nmr2d_enabled)])
def update_nmr2d_run_review(
    run_id: int,
    payload: NMR2DRunReviewUpdate,
    request: Request,
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> NMR2DRunRecord:
    user_id = None if getattr(context, "system_api_key", False) else getattr(context, "user_id", None)
    try:
        record = update_nmr2d_run_review_status(
            request.app.state.session_factory,
            run_id=run_id,
            review_status=payload.review_status,
            reviewer_user_id=getattr(context, "user_id", None),
            comment=payload.comment,
            user_id=user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="2D NMR run not found.")
    return record


@router.post("/raw/preview", dependencies=[Depends(require_nmr2d_enabled)])
def nmr2d_raw_preview_stub(
    request: Request,
    context=Depends(__import__("nmrcheck.api", fromlist=["require_access_context"]).require_access_context),
) -> dict[str, object]:
    if not _raw_2d_fid_beta_enabled(request):
        raise HTTPException(
            status_code=403,
            detail="Raw 2D FID/SER beta is disabled by feature flag ENABLE_RAW_2D_FID_BETA.",
        )
    return {
        "implemented": False,
        "detail": "Raw 2D FID/SER processing is intentionally deferred; upload processed COSY/HSQC/HMQC/HMBC peak tables for this guarded release.",
    }
