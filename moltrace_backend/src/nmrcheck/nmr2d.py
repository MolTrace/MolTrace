from __future__ import annotations

from .nmr2d_analyzer import analyze_nmr2d, analyze_nmr2d_preview
from .nmr2d_models import (
    NMR2DAnalysisReport,
    NMR2DAnalyzeRequest,
    NMR2DAnalyzeResult,
    NMR2DContourPoint,
    NMR2DCorrelationEvidence,
    NMR2DExperiment,
    NMR2DExperimentType,
    NMR2DPeak,
    NMR2DPreview,
    NMR2DPreviewReport,
    NMR2DRunRecord,
)
from .nmr2d_parser import (
    NMR2DParseError,
    is_2d_matrix_preview_upload,
    parse_2d_matrix_preview,
    parse_processed_2d_nmr,
)


def parse_nmr2d_upload(
    filename: str,
    content: bytes,
    *,
    experiment_hint: str | None = None,
    include_contour_preview: bool = False,
    contour_limit: int = 800,
) -> NMR2DPreview:
    """Parse a processed 2D NMR peak table without requiring a raw 2D matrix."""
    if is_2d_matrix_preview_upload(
        filename,
        content,
        include_contour_preview=include_contour_preview,
    ):
        return parse_2d_matrix_preview(
            filename,
            content,
            experiment_hint=experiment_hint,
            max_points=contour_limit,
        )
    return parse_processed_2d_nmr(
        filename,
        content,
        experiment_hint=experiment_hint,
        include_contour_preview=include_contour_preview,
        contour_limit=contour_limit,
    )


def parse_nmr2d_table(
    filename: str,
    content: bytes,
    *,
    experiment_type: str | None = None,
) -> NMR2DPreview:
    """Compatibility wrapper for processed 2D peak-table uploads."""
    return parse_nmr2d_upload(filename, content, experiment_hint=experiment_type)


__all__ = [
    "NMR2DAnalysisReport",
    "NMR2DAnalyzeRequest",
    "NMR2DAnalyzeResult",
    "NMR2DContourPoint",
    "NMR2DCorrelationEvidence",
    "NMR2DExperiment",
    "NMR2DExperimentType",
    "NMR2DParseError",
    "NMR2DPeak",
    "NMR2DPreview",
    "NMR2DPreviewReport",
    "NMR2DRunRecord",
    "analyze_nmr2d",
    "analyze_nmr2d_preview",
    "is_2d_matrix_preview_upload",
    "parse_2d_matrix_preview",
    "parse_nmr2d_table",
    "parse_nmr2d_upload",
    "parse_processed_2d_nmr",
]
