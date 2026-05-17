from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .nmr2d_models import (
    NMR2DAnalyzeRequest,
    NMR2DAnalyzeResult,
    NMR2DCorrelationEvidence,
    NMR2DExperimentType,
    NMR2DPeak,
    NMR2DPreviewReport,
    NMR2DRunRecord,
)

DiagnosticLabel = Literal[
    "consistent",
    "possible_overlap_or_missing_labile_signals",
    "possible_impurity_or_incorrect_assignment",
    "invalid_input",
]

JobStatus = Literal["pending", "queued", "processing", "completed", "failed"]
DataMode = Literal["live", "demo", "partially_synced", "unavailable", "stale"]
AIEvidenceModule = Literal["spectracheck", "regulatory", "reactions", "ai_services"]
AIEvidenceStatus = Literal["draft", "pending_review", "approved", "rejected", "contradiction"]
AIEvidenceReviewStatus = Literal["approved", "rejected", "pending_review"]
AIEvidenceRiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
ActionTokenPurpose = Literal["verify_email", "reset_password"]
ReviewStatus = Literal["pending_review", "approved", "rejected", "needs_revision"]
ReviewAction = Literal["approve", "reject", "override", "request_changes", "review"]
FIDPresetId = Literal[
    "baseline_preserve",
    "balanced",
    "sensitive_weak_peaks",
    "higher_resolution",
    "custom",
]

_PLAIN_TEXT_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")


def generated_at_utc() -> datetime:
    return datetime.now(UTC)


def sanitize_optional_plain_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch if ch in {"\n", "\t"} or ord(ch) >= 32 else " " for ch in text)
    text = "\n".join(line.strip() for line in text.splitlines()).strip()
    return text or None


FIDQualityLabel = Literal["good", "review", "poor", "failed"]
MolTraceEvidenceLabel = Literal[
    "best_supported",
    "plausible",
    "requires_review",
    "conflicting_evidence",
    "insufficient_evidence",
    "invalid_structure",
]


class EvidenceInputProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(min_length=1, max_length=100)
    source: Literal["form", "json", "upload", "derived"]
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=100)


class RawArchiveRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    user_id: int | None = None
    filename: str = Field(min_length=1, max_length=255)
    content_type: str | None = Field(default=None, max_length=100)
    byte_size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    storage_path: str = Field(min_length=1)
    vendor_detected: str = Field(min_length=1, max_length=100)
    dataset_root: str | None = Field(default=None, max_length=500)
    required_files_present: bool = False
    files_found: list[str] = Field(default_factory=list)
    acquisition_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    immutable: bool = True
    raw_archive_id: str | None = Field(default=None, min_length=64, max_length=64)


class RawArchivePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archive: RawArchiveRecord
    already_stored: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class RawArchiveExportManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exported_at: datetime
    raw_archive: RawArchiveRecord | None = None
    raw_archive_id: str | None = None
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    original_filename: str | None = None
    storage_backend: str | None = None
    include_original_archive: bool = False
    sha256_verified: bool = False
    files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Peak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_ppm: float = Field(ge=-50.0, le=260.0)
    multiplicity: str = Field(min_length=1, max_length=20)
    integration_h: float = Field(gt=0.0, le=50.0)
    j_values_hz: list[float] = Field(default_factory=list)


class StructureSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smiles: str
    formula: str
    molecular_weight: float
    total_hydrogens: int
    labile_hydrogens: int
    # Per-element breakdown of the labile-H total. The three sum to
    # ``labile_hydrogens`` for any valid neutral structure. Drives the exact
    # "(OH)" / "(OH/NH)" / "(OH/NH/SH)" subset shown in the labile-H reasoning.
    oh_hydrogen_count: int = 0
    nh_hydrogen_count: int = 0
    sh_hydrogen_count: int = 0
    non_labile_hydrogens: int
    aromatic_protons: int
    aliphatic_protons: int
    aromatic_atom_count: int
    # Olefinic vs anomeric proton counts: used by the 1H peak categoriser to
    # disambiguate peaks in the 4.4–6.0 ppm window. Tobramycin-style
    # carbohydrates have anomeric_proton_count > 0 and olefinic_proton_count
    # == 0; vinyl-containing molecules have the inverse. Both default to 0
    # for back-compat with older serialised summaries.
    olefinic_proton_count: int = 0
    anomeric_proton_count: int = 0


class SolventHeuristicHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solvent: str
    signal_label: str
    expected_ppm: float
    observed_ppm: float
    delta_ppm: float = Field(ge=0.0)
    kind: Literal["residual", "water", "exchange", "impurity"]


class AnalysisInputs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "sample_id": "cmpd-001",
                    "smiles": "CCO",
                    "nmr_text": "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)",
                    "solvent": "CDCl3",
                }
            ]
        },
    )

    sample_id: str | None = Field(default=None, max_length=100)
    smiles: str = Field(min_length=1, max_length=500)
    nmr_text: str = Field(min_length=3, max_length=10_000)
    solvent: str | None = Field(default=None, max_length=50)

    @field_validator("sample_id", "solvent", mode="before")
    @classmethod
    def _optional_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("smiles", "nmr_text", mode="before")
    @classmethod
    def _required_trim(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value


class AnalysisValidationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    smiles: str | None = Field(default=None, max_length=500)
    nmr_text: str | None = Field(default=None, max_length=10_000)
    solvent: str | None = Field(default=None, max_length=50)

    @field_validator("sample_id", "smiles", "nmr_text", "solvent", mode="before")
    @classmethod
    def _optional_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: DiagnosticLabel
    confidence: float = Field(ge=0.0, le=1.0)
    sample_id: str | None = None
    solvent: str | None = None
    expected_total_h: int
    expected_non_labile_h: int
    expected_labile_h: int
    observed_total_h: float
    rounded_observed_total_h: int
    delta_total_h: int
    parsed_peak_count: int
    notes: list[str]
    peaks: list[Peak]
    structure: StructureSummary
    solvent_signal_hits: list[SolventHeuristicHit] = Field(default_factory=list)
    pattern_alerts: list[str] = Field(default_factory=list)
    proton_evidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    proton_evidence: dict[str, Any] = Field(default_factory=dict)


class BatchAnalysisInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnalysisInputs] = Field(min_length=1, max_length=100)


class BatchAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnalysisReport]
    total_items: int


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    structure_valid: bool
    nmr_text_valid: bool
    structure_nmr_match: bool = False
    analysis_ready: bool = False
    parseable_peak_count: int
    expected_visible_h: float | None = None
    observed_total_h: float | None = None
    adjusted_observed_total_h: float | None = None
    delta_visible_h: float | None = None
    parsed_peaks: list[Peak] = Field(default_factory=list)
    structure: StructureSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SpectrumPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_ppm: float = Field(ge=-50.0, le=260.0)
    intensity: float


class SpectrumPeakMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_peak: Peak
    extracted_peak: Peak
    reference_raw_text: str
    reference_shift_start_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    reference_shift_end_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    delta_ppm: float = Field(ge=0.0)
    status: Literal["matched", "shifted"]
    multiplicity_match: bool
    integration_match: bool


class SpectrumMissingReferencePeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_peak: Peak
    reference_raw_text: str
    reference_shift_start_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    reference_shift_end_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)


class SpectrumExtraPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extracted_peak: Peak


class SpectrumComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched: list[SpectrumPeakMatch] = Field(default_factory=list)
    missing_reference: list[SpectrumMissingReferencePeak] = Field(default_factory=list)
    extra_spectrum: list[SpectrumExtraPeak] = Field(default_factory=list)
    matched_count: int = Field(ge=0, default=0)
    shifted_count: int = Field(ge=0, default=0)
    missing_count: int = Field(ge=0, default=0)
    extra_count: int = Field(ge=0, default=0)
    multiplicity_match_count: int = Field(ge=0, default=0)
    integration_match_count: int = Field(ge=0, default=0)
    total_shift_delta_ppm: float = Field(ge=0.0, default=0.0)
    reference_total_h: float = Field(ge=0.0, default=0.0)
    extracted_total_h: float = Field(ge=0.0, default=0.0)
    structure_visible_h: float | None = Field(default=None, ge=0.0)
    reference_structure_delta_h: float | None = None
    extracted_structure_delta_h: float | None = None
    reference_extracted_delta_h: float | None = None
    structure_reference_mismatch: bool = False
    structure_extracted_mismatch: bool = False
    notes: list[str] = Field(default_factory=list)


class SpectrumPreviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    format_detected: str
    source_mode: Literal["trace", "peak_table"]
    point_count: int = Field(ge=0)
    preview_points: list[SpectrumPoint] = Field(default_factory=list)
    inferred_peaks: list[Peak] = Field(default_factory=list)
    inferred_nmr_text: str = ""
    reference_nmr_text_normalized: str | None = None
    reference_peaks: list[Peak] = Field(default_factory=list)
    comparison: SpectrumComparisonReport | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpectrumAnalyzeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview: SpectrumPreviewReport
    generated_inputs: AnalysisInputs
    analysis: AnalysisReport


class FIDProcessingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_preset: FIDPresetId = "balanced"
    zero_fill_factor: int = Field(default=2, ge=1, le=8)
    fourier_transform: str = "fft_1d"
    apodization_mode: str = "exponential"
    line_broadening_hz: float = Field(default=0.3, ge=0.0, le=10.0)
    apply_group_delay: bool = True
    auto_phase: bool = True
    auto_baseline: bool = True
    phase_mode: str = "auto"
    phase_p0: float = 0.0
    phase_p1: float = 0.0
    baseline_correction: str = "bernstein"
    baseline_order: int = Field(default=3, ge=1, le=8)
    baseline_lock_visual_only: bool = True
    peak_sensitivity: float | None = Field(default=None, ge=0.02, le=0.45)
    mask_solvent_regions: bool = True
    max_preview_points: int = Field(default=700, ge=100, le=5000)
    display_mode: Literal["real", "magnifier"] = "real"
    vertical_gain: float = Field(default=1.0, ge=1.0, le=1_000_000.0)
    debug_preview: bool = False


class FIDProcessingRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor: str = "unknown"
    nucleus: str = "1H"
    processing_preset: str = "balanced"
    digital_filter_correction: str = "auto"
    apodization_mode: str = "exponential"
    line_broadening_hz: float = Field(default=0.3, ge=0.0, le=10.0)
    zero_fill_factor: int = Field(default=2, ge=1, le=8)
    fourier_transform: str = "fft_1d"
    phase_mode: str = "auto"
    phase_p0: float = 0.0
    phase_p1: float = 0.0
    baseline_correction: str = "bernstein"
    baseline_order: int = Field(default=3, ge=1, le=8)
    reference_ppm: float | None = None
    solvent: str | None = None
    peak_sensitivity: float | None = Field(default=None, ge=0.02, le=0.45)
    mask_solvent_regions: bool = True
    display_mode: Literal["real", "magnifier"] = "real"
    vertical_gain: float = Field(default=1.0, ge=1.0, le=1_000_000.0)
    debug_preview: bool = False


class FIDProcessingPreset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: FIDPresetId
    label: str
    description: str
    settings: dict[str, Any] = Field(default_factory=dict)


class FIDQADiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quality_score: float = Field(ge=0.0, le=1.0)
    quality_label: FIDQualityLabel
    dynamic_range: float = Field(ge=0.0)
    noise_estimate: float = Field(ge=0.0)
    baseline_offset_ratio: float = Field(ge=0.0)
    saturation_clipping_proxy: float = Field(ge=0.0, le=1.0)
    point_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class FIDProcessingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_format_detected: str
    dataset_folder: str
    selected_preset: str = "Balanced"
    nucleus: str = "1H"
    solvent: str | None = None
    reference_ppm: float | None = None
    reference_shift_applied_ppm: float = 0.0
    reference_peak_selection: dict[str, Any] = Field(default_factory=dict)
    group_delay_correction_applied: bool = False
    automatic_phase_correction: bool = False
    automatic_baseline_correction: bool = False
    zero_filling: dict[str, Any] = Field(default_factory=dict)
    line_broadening: dict[str, Any] = Field(default_factory=dict)
    phase_settings: dict[str, Any] = Field(default_factory=dict)
    baseline_correction: dict[str, Any] = Field(default_factory=dict)
    digital_filter_correction_status: str = "not_applied"
    qa_diagnostics: FIDQADiagnostics
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    processing_recipe: FIDProcessingRecipe = Field(default_factory=FIDProcessingRecipe)
    acquisition_parameters: dict[str, Any] = Field(default_factory=dict)
    raw_dataset_files_found: dict[str, bool] = Field(default_factory=dict)
    raw_upload_provenance: dict[str, Any] = Field(default_factory=dict)
    analysis_artifact_policy: dict[str, Any] = Field(default_factory=dict)
    nmrglue_used: bool = False
    pulseprogram_present: bool = False
    pdata_present: bool = False
    extracted_peak_list: list[Peak] = Field(default_factory=list)
    reviewer_signoff_required: bool = True
    human_review_status: str = "pending_review"
    warnings: list[str] = Field(default_factory=list)


class FIDPreviewReport(SpectrumPreviewReport):
    model_config = ConfigDict(extra="forbid")

    fid_run_id: int | None = None
    processing_metadata: FIDProcessingMetadata


class FIDProcessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview: FIDPreviewReport
    generated_inputs: AnalysisInputs
    analysis: AnalysisReport


NMRFrontendNucleus = Literal["1H", "13C"]


class NMRProcessedPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    nucleus: NMRFrontendNucleus
    filename: str
    point_count: int = Field(ge=0)
    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    x_label: str = "ppm"
    y_label: str = "intensity"
    reversed_x_axis: bool = True
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NMRProcessedAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    nucleus: NMRFrontendNucleus
    filename: str
    point_count: int = Field(ge=0)
    peak_count: int = Field(ge=0)
    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    x_label: str = "ppm"
    y_label: str = "intensity"
    reversed_x_axis: bool = True
    peaks: list[dict[str, Any]] = Field(default_factory=list)
    solvent_warnings: list[str] = Field(default_factory=list)
    impurity_warnings: list[str] = Field(default_factory=list)
    impurity_candidates: list[dict[str, Any]] = Field(default_factory=list)
    predicted_vs_observed: list[dict[str, Any]] = Field(default_factory=list)
    labile_hydrogen_summary: dict[str, Any] = Field(default_factory=dict)
    peak_category_summary: dict[str, int] = Field(default_factory=dict)
    # Aggregated proton inventory: observed-vs-expected counts by chemical
    # class (aromatic / aliphatic / labile / non-labile, plus aldehyde and
    # carboxyl detail) computed by ``build_proton_inventory``. Empty dict for
    # 13C-only analyses. See peak_categorization.py for the literature basis.
    proton_inventory: dict[str, Any] = Field(default_factory=dict)
    dp4_ranking: list[dict[str, Any]] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    analysis_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NMRRawFIDPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    filename: str
    raw_sha256: str = Field(min_length=64, max_length=64)
    vendor_detected: str
    nucleus: NMRFrontendNucleus
    solvent: str | None = None
    acquisition_parameters: dict[str, Any] = Field(default_factory=dict)
    file_inventory: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NMRRawFIDProcessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    filename: str
    raw_sha256: str = Field(min_length=64, max_length=64)
    vendor_detected: str
    nucleus: NMRFrontendNucleus
    processing_preset: str
    processing_parameters: dict[str, Any] = Field(default_factory=dict)
    point_count: int = Field(ge=0)
    # Peak-level results (parity with /nmr/processed/analyze). Populated by
    # running ``enrich_peaks`` over the FID-derived ``inferred_peaks`` so the
    # Raw FID tab can mount the same EnrichedPickedPeaksPanel +
    # SpectraCheckEvidencePanels composite as the Processed tab.
    peak_count: int = Field(default=0, ge=0)
    peaks: list[dict[str, Any]] = Field(default_factory=list)
    peak_category_summary: dict[str, int] = Field(default_factory=dict)
    labile_hydrogen_summary: dict[str, Any] = Field(default_factory=dict)
    proton_inventory: dict[str, Any] = Field(default_factory=dict)
    impurity_candidates: list[dict[str, Any]] = Field(default_factory=list)
    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    x_label: str = "ppm"
    y_label: str = "intensity"
    reversed_x_axis: bool = True
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    """A single (structure, observed-spectrum) pair for the SpectraCheck benchmark.

    Designed for /benchmark/spectracheck/run. The case carries everything the
    benchmark needs to score across the 5 layers: a candidate SMILES (the
    "true" structure to evaluate against), the observed NMR text or peak list,
    plus optional ranking candidates and an audit envelope.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=200)
    smiles: str = Field(min_length=1, max_length=500)
    nucleus: NMRFrontendNucleus = "1H"
    solvent: str | None = Field(default=None, max_length=50)
    observed_nmr_text: str = Field(min_length=3, max_length=10_000)
    # Optional ranking field: pipe-block of candidate SMILES, same format as
    # the existing candidate-comparison flow. The "true" SMILES above is what
    # we expect the system to rank in the top-k.
    candidate_block: str | None = Field(default=None, max_length=20_000)
    # Optional provenance fields the regulatory_evidence layer scores.
    sample_id: str | None = Field(default=None, max_length=100)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    operator: str | None = Field(default=None, max_length=200)
    instrument: str | None = Field(default=None, max_length=200)
    notes: list[str] = Field(default_factory=list)


class BenchmarkLayerScore(BaseModel):
    """A single layer's score with the components that produced it."""

    model_config = ConfigDict(extra="forbid")

    name: Literal[
        "peak_level_accuracy",
        "structural_ranking",
        "explainability",
        "robustness",
        "regulatory_evidence",
    ]
    score: float = Field(ge=0.0, le=1.0)
    components: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class BenchmarkCaseResult(BaseModel):
    """Per-case scorecard."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    smiles: str
    nucleus: NMRFrontendNucleus
    solvent: str | None = None
    overall_score: float = Field(ge=0.0, le=1.0)
    layers: list[BenchmarkLayerScore]
    summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BenchmarkAggregate(BaseModel):
    """Per-layer mean across the suite."""

    model_config = ConfigDict(extra="forbid")

    layer: Literal[
        "peak_level_accuracy",
        "structural_ranking",
        "explainability",
        "robustness",
        "regulatory_evidence",
    ]
    mean_score: float = Field(ge=0.0, le=1.0)
    case_count: int = Field(ge=0)
    min_score: float = Field(ge=0.0, le=1.0)
    max_score: float = Field(ge=0.0, le=1.0)


class BenchmarkRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cases: list[BenchmarkCase] = Field(min_length=1, max_length=200)
    # Robustness probe: drop the N hottest peaks (by integration) and re-score
    # peak-level accuracy. Default 1; range 0..3 is plenty for a smoke check.
    robustness_drop_peaks: int = Field(default=1, ge=0, le=5)


class BenchmarkRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(ge=0)
    overall_mean_score: float = Field(ge=0.0, le=1.0)
    aggregates: list[BenchmarkAggregate]
    cases: list[BenchmarkCaseResult]
    notes: list[str] = Field(default_factory=list)


class FIDRunReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction | None = None
    comment: str | None = Field(default=None, max_length=4000)


class FIDRunReviewDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    run_id: int
    reviewer_user_id: int
    action: ReviewAction
    previous_status: ReviewStatus
    new_status: ReviewStatus
    comment: str | None = None
    created_at: datetime


class FIDRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int | None = None
    analysis_id: int | None = None
    raw_archive_id: int | None = None
    raw_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime
    sample_id: str | None = None
    filename: str
    selected_preset: str
    quality_label: FIDQualityLabel
    quality_score: float = Field(ge=0.0, le=1.0)
    review_status: ReviewStatus = "pending_review"
    reviewer_user_id: int | None = None
    reviewed_at: datetime | None = None
    reviewer_comment: str | None = None
    preview: FIDPreviewReport
    processing_metadata: FIDProcessingMetadata
    processing_recipe: dict[str, Any] = Field(default_factory=dict)
    derived_spectrum_metadata: dict[str, Any] = Field(default_factory=dict)
    review_decision_count: int = 0


class FIDRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: FIDRunRecord
    raw_fid_provenance: dict[str, Any] = Field(default_factory=dict)
    processing_assumptions: dict[str, Any] = Field(default_factory=dict)
    qa_diagnostics: FIDQADiagnostics
    inferred_peak_list: list[Peak] = Field(default_factory=list)
    review_decisions: list[FIDRunReviewDecisionRecord] = Field(default_factory=list)


class Carbon13Peak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_ppm: float = Field(ge=-50.0, le=260.0)
    intensity: float | None = None
    assignment: str | None = Field(default=None, max_length=200)
    region: str | None = None
    carbon_type: str | None = None
    is_likely_solvent: bool = False
    is_likely_impurity: bool = False
    impurity_matches: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Carbon13Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    smiles: str = Field(min_length=1, max_length=500)
    carbon13_text: str = Field(min_length=1, max_length=20_000)
    solvent: str | None = Field(default=None, max_length=50)
    sample_id: str | None = Field(default=None, max_length=100)

    @field_validator("smiles", "carbon13_text", mode="before")
    @classmethod
    def _required_trim(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value

    @field_validator("solvent", "sample_id", mode="before")
    @classmethod
    def _optional_trim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class Carbon13UploadPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    source_mode: str
    observed_signal_count: int
    peaks: list[Carbon13Peak] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Carbon13RegionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    region: str
    count: int
    shifts_ppm: list[float] = Field(default_factory=list)


class Carbon13AnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    smiles: str
    solvent: str | None = None
    expected_carbon_atoms: int
    observed_carbon_signals: int
    delta_carbon_signals: int
    label: Literal[
        "carbon_count_consistent",
        "possible_overlap_or_missing_weak_carbons",
        "possible_extra_carbons_or_impurity",
        "invalid_input",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    peaks: list[Carbon13Peak] = Field(default_factory=list)
    region_summary: list[Carbon13RegionSummary] = Field(default_factory=list)
    solvent_warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    carbon13_match_score: float | None = None
    carbon_count_score: float | None = None
    region_consistency_score: float | None = None
    solvent_exclusion_score: float | None = None
    dept_apt_consistency_score: float | None = None
    expected_region_summary: dict[str, int] = Field(default_factory=dict)
    observed_region_summary: dict[str, int] = Field(default_factory=dict)
    evidence_summary: list[str] = Field(default_factory=list)
    structure: StructureSummary | None = None


DeptAptExperimentType = Literal["DEPT90", "DEPT135", "DEPT", "APT", "UNKNOWN"]
DeptAptCarbonType = Literal["C", "CH", "CH2", "CH3", "CH_OR_CH3", "CH2_OR_C"]
DeptAptPhase = Literal["positive", "negative", "unknown"]


class DeptAptPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment: DeptAptExperimentType = "UNKNOWN"
    shift_ppm: float = Field(ge=-50.0, le=260.0)
    intensity: float | None = None
    phase: DeptAptPhase = "unknown"
    carbon_type: DeptAptCarbonType | None = None
    assignment: str | None = Field(default=None, max_length=200)
    matched_carbon13_shift_ppm: float | None = None
    warnings: list[str] = Field(default_factory=list)


class DeptAptPreviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    experiment_detected: DeptAptExperimentType = "UNKNOWN"
    peak_count: int = 0
    peaks: list[DeptAptPeak] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeptAptAnalyzeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview: DeptAptPreviewReport
    carbon13_peak_count: int = 0
    matched_carbon13_count: int = 0
    missing_carbon13_count: int = 0
    extra_dept_apt_count: int = 0
    typed_peak_count: int = 0
    dept_apt_consistency_score: float | None = Field(default=None, ge=0.0, le=1.0)
    type_summary: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProtonEvidencePeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shift_ppm: float = Field(ge=-5.0, le=20.0)
    multiplicity: str
    integration_h: float
    region: str
    is_likely_solvent: bool = False
    is_likely_water: bool = False
    notes: list[str] = Field(default_factory=list)


class ProtonEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    smiles: str
    solvent: str | None = None
    expected_total_h: int
    expected_non_labile_h: int
    expected_labile_h: int
    observed_total_h: float
    observed_non_solvent_h: float
    solvent_or_water_h: float
    delta_total_h: float
    delta_non_solvent_h: float
    label: DiagnosticLabel
    overall_score: float = Field(ge=0.0, le=1.0)
    integration_score: float = Field(ge=0.0, le=1.0)
    solvent_exclusion_score: float = Field(ge=0.0, le=1.0)
    region_support_score: float = Field(ge=0.0, le=1.0)
    peaks: list[ProtonEvidencePeak] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    structure: StructureSummary | None = None


class SpectralEvidenceScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nucleus: str
    score: float = Field(ge=0.0, le=1.0)
    matched_count: int = 0
    unmatched_observed_count: int = 0
    unmatched_expected_count: int = 0
    notes: list[str] = Field(default_factory=list)


class CandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    smiles: str = Field(min_length=1, max_length=1000)
    role: str | None = Field(default=None, max_length=100)

    @field_validator("smiles", mode="before")
    @classmethod
    def _trim_smiles(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("Candidate SMILES cannot be empty.")
        return value

    @field_validator("name", "role", mode="before")
    @classmethod
    def _optional_trim_candidate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CandidateComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    proton_nmr_text: str | None = Field(default=None, max_length=20_000)
    carbon13_text: str | None = Field(default=None, max_length=20_000)
    # Structural class prior supplied from the SpectraCheck workspace. When
    # set, candidate scoring may apply class-specific weighting; when omitted,
    # scoring runs with default priors. Canonical values are enumerated in
    # ``moltrace_backend/src/nmrcheck/compound_classes.py``.
    compound_class: str | None = Field(default=None, max_length=64)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=25)

    @field_validator(
        "sample_id",
        "solvent",
        "proton_nmr_text",
        "carbon13_text",
        "compound_class",
        mode="before",
    )
    @classmethod
    def _optional_trim_evidence(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CandidateScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure_validity_score: float = Field(ge=0.0, le=1.0)
    proton_score: float | None = Field(default=None, ge=0.0, le=1.0)
    carbon13_score: float | None = Field(default=None, ge=0.0, le=1.0)
    dept_apt_score: float | None = Field(default=None, ge=0.0, le=1.0)
    nmr2d_score: float | None = Field(default=None, ge=0.0, le=1.0)
    formula_match_score: float | None = Field(default=None, ge=0.0, le=1.0)


class CandidateComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    label: Literal["best_supported", "supported", "ambiguous", "weak_support", "invalid_structure"]
    total_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: CandidateScoreBreakdown
    formula: str | None = None
    exact_mass: float | None = None
    proton_label: str | None = None
    carbon13_label: str | None = None
    evidence_summary: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    # Echo of the structural-class prior the caller supplied (if any).
    compound_class: str | None = None
    # Full audit payload of the per-class prior application: original weights,
    # multipliers, post-renormalisation weights, and human-readable notes. Set
    # only when a recognised class with a non-trivial multiplier table was
    # supplied. See compound_class_priors.CompoundClassPriorReport.
    compound_class_prior_applied: dict[str, Any] | None = None
    candidate_count: int
    best_candidate: CandidateComparisonItem | None = None
    ranked_candidates: list[CandidateComparisonItem] = Field(default_factory=list)
    ambiguity_alerts: list[str] = Field(default_factory=list)
    evidence_layers_used: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SpectralSimilarityMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_ppm: float
    reference_ppm: float
    delta_ppm: float
    score: float = Field(ge=0.0, le=1.0)


class NMR2DCrossPeakMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_f2_ppm: float
    observed_f1_ppm: float
    reference_f2_ppm: float
    reference_f1_ppm: float
    delta_f2_ppm: float
    delta_f1_ppm: float
    score: float = Field(ge=0.0, le=1.0)


class SpectralSimilarityLayerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: Literal["1H", "13C", "COSY", "HSQC", "HMQC", "HMBC", "2D"]
    vector_score: float | None = Field(default=None, ge=0.0, le=1.0)
    set_score: float | None = Field(default=None, ge=0.0, le=1.0)
    combined_score: float = Field(ge=0.0, le=1.0)
    observed_count: int = 0
    reference_count: int = 0
    matched_count: int = 0
    unmatched_observed_count: int = 0
    unmatched_reference_count: int = 0
    matches: list[SpectralSimilarityMatch] = Field(default_factory=list)
    crosspeak_matches: list[NMR2DCrossPeakMatch] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpectralSimilarityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    observed_proton_text: str | None = Field(default=None, max_length=20_000)
    reference_proton_text: str | None = Field(default=None, max_length=20_000)
    observed_carbon13_text: str | None = Field(default=None, max_length=20_000)
    reference_carbon13_text: str | None = Field(default=None, max_length=20_000)

    @field_validator(
        "sample_id",
        "solvent",
        "observed_proton_text",
        "reference_proton_text",
        "observed_carbon13_text",
        "reference_carbon13_text",
        mode="before",
    )
    @classmethod
    def _optional_trim_similarity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class SpectralSimilarityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    overall_score: float = Field(ge=0.0, le=1.0)
    label: Literal[
        "high_similarity", "moderate_similarity", "low_similarity", "insufficient_evidence"
    ]
    layers: list[SpectralSimilarityLayerResult] = Field(default_factory=list)
    evidence_layers_used: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictedNMRPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nucleus: Literal["1H", "13C"]
    shift_ppm: float
    uncertainty_ppm: float = Field(ge=0.0)
    atom_index: int | None = None
    attached_h: int | None = Field(default=None, ge=0)
    integration_h: float | None = Field(default=None, ge=0.0)
    carbon_type: str | None = None
    multiplicity_hint: str | None = None
    environment: str | None = None
    source: Literal["heuristic_rdkit", "external", "ml_placeholder"] = "heuristic_rdkit"
    warnings: list[str] = Field(default_factory=list)


class PredictedNMRReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    smiles: str
    formula: str | None = None
    molecular_weight: float | None = None
    prediction_method: str
    confidence_label: Literal["high", "medium", "low", "invalid_structure"]
    proton_peaks: list[PredictedNMRPeak] = Field(default_factory=list)
    carbon13_peaks: list[PredictedNMRPeak] = Field(default_factory=list)
    predicted_hsqc_crosspeaks: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidatePredictedNMRMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    observed_proton_text: str | None = Field(default=None, max_length=20_000)
    observed_carbon13_text: str | None = Field(default=None, max_length=20_000)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=25)

    @field_validator(
        "sample_id", "solvent", "observed_proton_text", "observed_carbon13_text", mode="before"
    )
    @classmethod
    def _optional_trim_predicted_match(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CandidatePredictedNMRMatchEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates_text: str = Field(min_length=1, max_length=100_000)
    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    observed_proton_text: str | None = Field(default=None, max_length=20_000)
    observed_carbon13_text: str | None = Field(default=None, max_length=20_000)
    nmr2d_experiment_type: str | None = Field(default=None, max_length=50)

    @field_validator(
        "candidates_text",
        "sample_id",
        "solvent",
        "observed_proton_text",
        "observed_carbon13_text",
        "nmr2d_experiment_type",
        mode="before",
    )
    @classmethod
    def _trim_evidence_form_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CandidatePredictedNMRMatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    label: Literal[
        "best_predicted_match",
        "predicted_match",
        "ambiguous",
        "weak_match",
        "invalid_structure",
    ]
    evidence_label: MolTraceEvidenceLabel = "requires_review"
    total_score: float = Field(ge=0.0, le=1.0)
    prediction: PredictedNMRReport | None = None
    proton_similarity: SpectralSimilarityLayerResult | None = None
    carbon13_similarity: SpectralSimilarityLayerResult | None = None
    nmr2d_similarity: SpectralSimilarityLayerResult | None = None
    evidence_summary: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    human_review_status: ReviewStatus = "pending_review"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidatePredictedNMRMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    candidate_count: int
    best_candidate: CandidatePredictedNMRMatchItem | None = None
    ranked_candidates: list[CandidatePredictedNMRMatchItem] = Field(default_factory=list)
    ambiguity_alerts: list[str] = Field(default_factory=list)
    evidence_layers_used: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    input_provenance: list[EvidenceInputProvenance] = Field(default_factory=list)
    human_review_required: bool = True
    human_review_status: ReviewStatus = "pending_review"
    metadata: dict[str, Any] = Field(default_factory=dict)


MassIonMode = Literal["positive", "negative", "neutral"]
HRMSMatchLabel = Literal[
    "exact_mass_match", "possible_match", "outside_tolerance", "invalid_structure"
]


class HRMSAdductInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ion_mode: MassIonMode
    charge: int
    mass_shift: float
    description: str


class HRMSFormulaInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formula: str
    exact_mass: float
    dbe: float | None = None
    element_counts: dict[str, int] = Field(default_factory=dict)
    isotope_m_plus_1_percent: float | None = None
    isotope_m_plus_2_percent: float | None = None


class HRMSCandidateMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    label: HRMSMatchLabel
    formula: str | None = None
    neutral_exact_mass: float | None = None
    theoretical_mz: float | None = None
    observed_mz: float
    ppm_error: float | None = None
    abs_mass_error_da: float | None = None
    ppm_score: float = Field(ge=0.0, le=1.0)
    isotope_score: float | None = Field(default=None, ge=0.0, le=1.0)
    dbe: float | None = None
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HRMSCandidateMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    observed_mz: float = Field(gt=0.0)
    adduct: str = Field(default="[M+H]+", max_length=50)
    ion_mode: MassIonMode | None = None
    ppm_tolerance: float = Field(default=5.0, gt=0.0, le=100.0)
    observed_m_plus_1_percent: float | None = Field(default=None, ge=0.0)
    observed_m_plus_2_percent: float | None = Field(default=None, ge=0.0)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=50)

    @field_validator("sample_id", "compound_class", "adduct", mode="before")
    @classmethod
    def _optional_trim_hrms_candidate(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class HRMSCandidateMatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    observed_mz: float
    adduct: HRMSAdductInfo
    ppm_tolerance: float
    candidate_count: int
    best_match: HRMSCandidateMatch | None = None
    ranked_candidates: list[HRMSCandidateMatch] = Field(default_factory=list)
    exact_match_count: int = 0
    possible_match_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HRMSFormulaSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_mz: float = Field(gt=0.0)
    adduct: str = Field(default="[M+H]+", max_length=50)
    ppm_tolerance: float = Field(default=5.0, gt=0.0, le=100.0)
    max_c: int = Field(default=40, ge=0, le=120)
    max_h: int = Field(default=100, ge=0, le=250)
    max_n: int = Field(default=6, ge=0, le=20)
    max_o: int = Field(default=12, ge=0, le=40)
    max_s: int = Field(default=4, ge=0, le=12)
    max_p: int = Field(default=2, ge=0, le=8)
    max_cl: int = Field(default=4, ge=0, le=10)
    max_br: int = Field(default=3, ge=0, le=8)
    require_nonnegative_dbe: bool = True
    max_results: int = Field(default=50, ge=1, le=500)


class HRMSFormulaSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_mz: float
    neutral_mass: float
    adduct: HRMSAdductInfo
    ppm_tolerance: float
    formula_count: int
    formulas: list[HRMSFormulaInfo] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


MSMSCandidateLabel = Literal[
    "consistent_with_msms", "partial_msms_support", "weak_or_no_msms_support", "invalid_structure"
]


class MSMSPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mz: float = Field(gt=0.0)
    intensity: float = Field(ge=0.0)
    relative_intensity: float | None = Field(default=None, ge=0.0, le=100.0)


class MSMSNeutralLossHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragment_mz: float
    intensity: float
    relative_intensity: float
    loss_name: str
    observed_loss_da: float
    expected_loss_da: float
    error_da: float
    ppm_error: float | None = None
    chemically_plausible: bool = True
    interpretation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSFragmentMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peak_mz: float
    intensity: float
    relative_intensity: float
    theoretical_mz: float
    ppm_error: float
    formula: str | None = None
    fragment_type: str
    explanation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSCandidateAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    label: MSMSCandidateLabel
    formula: str | None = None
    precursor_theoretical_mz: float | None = None
    precursor_ppm_error: float | None = None
    precursor_score: float = Field(ge=0.0, le=1.0)
    fragment_match_count: int = 0
    neutral_loss_count: int = 0
    explained_peak_count: int = 0
    explained_intensity_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    candidate_score: float = Field(default=0.0, ge=0.0, le=1.0)
    fragment_matches: list[MSMSFragmentMatch] = Field(default_factory=list)
    neutral_loss_hits: list[MSMSNeutralLossHit] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSAnnotationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    precursor_mz: float = Field(gt=0.0)
    adduct: str = Field(default="[M+H]+", max_length=50)
    ion_mode: MassIonMode | None = None
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    min_relative_intensity: float = Field(default=1.0, ge=0.0, le=100.0)
    max_peaks_to_annotate: int = Field(default=50, ge=1, le=250)
    peaks: list[MSMSPeak] | None = Field(default=None, max_length=1000)
    peak_list_text: str | None = Field(default=None, max_length=100_000)
    candidates: list[CandidateInput] = Field(default_factory=list, max_length=50)

    @field_validator("sample_id", "compound_class", "adduct", "peak_list_text", mode="before")
    @classmethod
    def _optional_trim_msms(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class MSMSAnnotationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    precursor_mz: float
    adduct: HRMSAdductInfo
    mz_tolerance_da: float
    ppm_tolerance: float
    peak_count: int
    annotated_peak_count: int
    candidate_count: int
    best_candidate: MSMSCandidateAnnotation | None = None
    ranked_candidates: list[MSMSCandidateAnnotation] = Field(default_factory=list)
    neutral_loss_hits: list[MSMSNeutralLossHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


MSMSFragmentationTreeLabel = Literal[
    "strong_fragmentation_tree_support",
    "plausible_fragmentation_tree_support",
    "weak_fragmentation_tree_support",
    "contradictory_fragmentation_tree",
    "invalid_structure",
]
MSMSFragmentationNodeType = Literal["precursor", "observed_peak", "hypothesized_fragment"]
MSMSFragmentationEdgeType = Literal[
    "neutral_loss", "candidate_fragment_match", "series_loss", "precursor_match"
]


class MSMSFragmentationTreeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    mz: float
    intensity: float | None = None
    relative_intensity: float | None = Field(default=None, ge=0.0, le=100.0)
    formula: str | None = None
    node_type: MSMSFragmentationNodeType
    annotation: str | None = None
    explained: bool = False
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSFragmentationTreeEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_id: str
    child_id: str
    relation_type: MSMSFragmentationEdgeType
    loss_name: str | None = None
    observed_loss_da: float | None = None
    expected_loss_da: float | None = None
    error_da: float | None = None
    ppm_error: float | None = None
    chemically_plausible: bool = True
    diagnostic: bool = False
    explanation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSDiagnosticLossEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loss_name: str
    fragment_mz: float
    observed_loss_da: float
    expected_loss_da: float
    relative_intensity: float
    chemically_plausible: bool
    diagnostic_class: str
    interpretation: str


class MSMSFragmentationTreeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    label: MSMSFragmentationTreeLabel
    formula: str | None = None
    precursor_theoretical_mz: float | None = None
    precursor_ppm_error: float | None = None
    precursor_score: float = Field(default=0.0, ge=0.0, le=1.0)
    tree_score: float = Field(default=0.0, ge=0.0, le=1.0)
    explained_peak_count: int = 0
    explained_intensity_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    diagnostic_loss_count: int = 0
    contradiction_count: int = 0
    max_tree_depth: int = 0
    nodes: list[MSMSFragmentationTreeNode] = Field(default_factory=list)
    edges: list[MSMSFragmentationTreeEdge] = Field(default_factory=list)
    diagnostic_hits: list[MSMSDiagnosticLossEvidence] = Field(default_factory=list)
    contradiction_flags: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MSMSFragmentationTreeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    precursor_mz: float = Field(gt=0.0)
    adduct: str = Field(default="[M+H]+", max_length=50)
    ion_mode: MassIonMode | None = None
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    min_relative_intensity: float = Field(default=1.0, ge=0.0, le=100.0)
    max_peaks_to_analyze: int = Field(default=75, ge=1, le=500)
    max_tree_depth: int = Field(default=3, ge=1, le=8)
    peaks: list[MSMSPeak] | None = Field(default=None, max_length=2000)
    peak_list_text: str | None = Field(default=None, max_length=100_000)
    candidates: list[CandidateInput] = Field(default_factory=list, max_length=50)

    @field_validator("sample_id", "compound_class", "adduct", "peak_list_text", mode="before")
    @classmethod
    def _optional_trim_fragmentation_tree(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class MSMSFragmentationTreeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    precursor_mz: float
    adduct: HRMSAdductInfo
    mz_tolerance_da: float
    ppm_tolerance: float
    peak_count: int
    analyzed_peak_count: int
    candidate_count: int
    best_candidate: MSMSFragmentationTreeCandidate | None = None
    ranked_candidates: list[MSMSFragmentationTreeCandidate] = Field(default_factory=list)
    global_neutral_loss_hits: list[MSMSNeutralLossHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


MS1IsotopeClusterLabel = Literal[
    "clear_isotope_cluster", "possible_isotope_cluster", "single_peak_only"
]
MS1HalogenSignature = Literal[
    "none_detected",
    "chlorine_like",
    "bromine_like",
    "mixed_or_high_m_plus_2",
    "sulfur_or_silicon_possible",
    "unknown",
]
MS1AdductInferenceLabel = Literal[
    "strong_adduct_evidence", "plausible_adduct", "weak_adduct_evidence", "incompatible_adduct"
]


class MS1Peak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mz: float = Field(gt=0.0)
    intensity: float = Field(ge=0.0)
    relative_intensity: float | None = Field(default=None, ge=0.0, le=100.0)


class MS1IsotopeClusterPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isotope_label: Literal["M", "M+1", "M+2", "M+3"]
    mz: float
    expected_mz: float
    delta_da: float
    relative_intensity: float = Field(ge=0.0, le=100.0)
    ppm_error: float | None = None
    spacing_from_m0_da: float | None = None


class MS1IsotopeCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monoisotopic_mz: float
    charge: int = Field(ge=1, le=5)
    label: MS1IsotopeClusterLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    m_plus_1_percent: float | None = Field(default=None, ge=0.0)
    m_plus_2_percent: float | None = Field(default=None, ge=0.0)
    estimated_carbon_count: float | None = Field(default=None, ge=0.0)
    halogen_signature: MS1HalogenSignature = "unknown"
    peaks: list[MS1IsotopeClusterPeak] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MS1AdductPeakEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adduct: str
    observed_mz: float
    expected_mz: float
    ppm_error: float
    relative_intensity: float = Field(ge=0.0, le=100.0)


class MS1AdductInferenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    label: MS1AdductInferenceLabel
    adduct: HRMSAdductInfo
    observed_mz: float
    neutral_mass: float
    formula_count: int = 0
    top_formulas: list[HRMSFormulaInfo] = Field(default_factory=list)
    isotope_score: float | None = Field(default=None, ge=0.0, le=1.0)
    adduct_pair_count: int = 0
    adduct_peak_matches: list[MS1AdductPeakEvidence] = Field(default_factory=list)
    candidate_score: float = Field(ge=0.0, le=1.0)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MS1AdductInferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    peak_list_text: str | None = Field(default=None, max_length=100_000)
    peaks: list[MS1Peak] | None = Field(default=None, max_length=5000)
    ion_mode: MassIonMode | None = "positive"
    target_mz: float | None = Field(default=None, gt=0.0)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=10.0, gt=0.0, le=500.0)
    isotope_mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=1.0)
    min_relative_intensity: float = Field(default=0.2, ge=0.0, le=100.0)
    max_peaks_to_analyze: int = Field(default=200, ge=1, le=5000)
    max_charge: int = Field(default=3, ge=1, le=5)
    max_clusters: int = Field(default=20, ge=1, le=100)
    perform_formula_search: bool = True
    formula_candidates_per_adduct: int = Field(default=5, ge=1, le=50)
    max_c: int = Field(default=20, ge=0, le=120)
    max_h: int = Field(default=60, ge=0, le=250)
    max_n: int = Field(default=4, ge=0, le=20)
    max_o: int = Field(default=8, ge=0, le=40)
    max_s: int = Field(default=2, ge=0, le=12)
    max_p: int = Field(default=1, ge=0, le=8)
    max_cl: int = Field(default=2, ge=0, le=10)
    max_br: int = Field(default=1, ge=0, le=8)
    require_nonnegative_dbe: bool = True

    @field_validator("sample_id", "compound_class", "peak_list_text", mode="before")
    @classmethod
    def _optional_trim_ms1_adduct(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class MS1AdductInferenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    ion_mode: MassIonMode | str
    peak_count: int
    analyzed_peak_count: int
    primary_mz: float
    inferred_charge: int | None = None
    inferred_m_plus_1_percent: float | None = None
    inferred_m_plus_2_percent: float | None = None
    isotope_clusters: list[MS1IsotopeCluster] = Field(default_factory=list)
    best_adduct_candidate: MS1AdductInferenceCandidate | None = None
    adduct_candidates: list[MS1AdductInferenceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


UnifiedConfidenceLabel = Literal[
    "high_confidence_candidate",
    "moderate_confidence_candidate",
    "low_confidence_candidate",
    "conflicting_evidence",
    "insufficient_evidence",
    "invalid_structure",
]
UnifiedConfidenceBand = Literal["high", "medium", "low", "conflicting", "insufficient"]
UnifiedEvidenceLayerName = Literal[
    "predicted_nmr",
    "hrms_exact_mass",
    "adduct_isotope",
    "msms_annotation",
    "fragmentation_tree",
    "lcms_feature_family",
]


class UnifiedEvidenceLayerScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: UnifiedEvidenceLayerName
    label: str
    used: bool = False
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    weight: float = Field(default=0.0, ge=0.0)
    status: str
    agreement: bool = False
    contradiction: bool = False
    evidence_count: int = 0
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnifiedCandidateConfidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    compound_class: str | None = Field(default=None, max_length=64)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=25)

    observed_proton_text: str | None = Field(default=None, max_length=50_000)
    observed_carbon13_text: str | None = Field(default=None, max_length=50_000)
    observed_nmr2d_text: str | None = Field(default=None, max_length=100_000)
    observed_nmr2d_experiment_type: NMR2DExperimentType | None = None

    hrms_observed_mz: float | None = Field(default=None, gt=0.0)
    hrms_adduct: str | None = Field(default=None, max_length=50)
    ion_mode: MassIonMode | None = None
    hrms_ppm_tolerance: float = Field(default=5.0, gt=0.0, le=100.0)
    observed_m_plus_1_percent: float | None = Field(default=None, ge=0.0)
    observed_m_plus_2_percent: float | None = Field(default=None, ge=0.0)

    ms1_peak_list_text: str | None = Field(default=None, max_length=100_000)
    ms1_peaks: list[MS1Peak] | None = Field(default=None, max_length=5000)
    use_inferred_adduct: bool = True
    adduct_ppm_tolerance: float = Field(default=10.0, gt=0.0, le=500.0)
    isotope_mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=1.0)
    ms1_min_relative_intensity: float = Field(default=0.2, ge=0.0, le=100.0)
    ms1_max_peaks_to_analyze: int = Field(default=200, ge=1, le=5000)
    max_charge: int = Field(default=3, ge=1, le=5)
    perform_adduct_formula_search: bool = True
    formula_candidates_per_adduct: int = Field(default=5, ge=1, le=50)
    formula_max_c: int = Field(default=20, ge=0, le=120)
    formula_max_h: int = Field(default=60, ge=0, le=250)
    formula_max_n: int = Field(default=4, ge=0, le=20)
    formula_max_o: int = Field(default=8, ge=0, le=40)
    formula_max_s: int = Field(default=2, ge=0, le=12)
    formula_max_p: int = Field(default=1, ge=0, le=8)
    formula_max_cl: int = Field(default=2, ge=0, le=10)
    formula_max_br: int = Field(default=1, ge=0, le=8)

    msms_peak_list_text: str | None = Field(default=None, max_length=100_000)
    msms_precursor_mz: float | None = Field(default=None, gt=0.0)
    msms_adduct: str | None = Field(default=None, max_length=50)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    msms_ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    msms_min_relative_intensity: float = Field(default=1.0, ge=0.0, le=100.0)
    msms_max_peaks_to_analyze: int = Field(default=75, ge=1, le=500)
    max_tree_depth: int = Field(default=3, ge=1, le=8)

    # Week 39: optional LC-MS feature-family consensus bridge.
    # These are dictionaries because this request is declared before the
    # concrete LCMS consensus models below; the bridge validates them later.
    lcms_consensus_result: dict[str, Any] | None = None
    lcms_consensus_request: dict[str, Any] | None = None
    lcms_family_table_text: str | None = Field(default=None, max_length=2_000_000)
    lcms_anchor_adduct: str | None = Field(default=None, max_length=50)
    lcms_mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    lcms_ppm_tolerance: float = Field(default=10.0, gt=0.0, le=500.0)
    lcms_min_family_consensus_score: float = Field(default=0.42, ge=0.0, le=1.0)
    lcms_require_promoted_family: bool = True
    lcms_selected_family_id: str | None = Field(default=None, max_length=100)
    lcms_layer_weight: float = Field(default=0.12, ge=0.0, le=1.0)

    layer_weights: dict[str, float] = Field(default_factory=dict)
    ambiguity_delta_threshold: float = Field(default=0.05, ge=0.0, le=1.0)

    @field_validator(
        "lcms_family_table_text", "lcms_anchor_adduct", "lcms_selected_family_id", mode="before"
    )
    @classmethod
    def _trim_lcms_bridge_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator(
        "sample_id",
        "solvent",
        "compound_class",
        "observed_proton_text",
        "observed_carbon13_text",
        "observed_nmr2d_text",
        "hrms_adduct",
        "msms_adduct",
        "ms1_peak_list_text",
        "msms_peak_list_text",
        mode="before",
    )
    @classmethod
    def _optional_trim_unified_confidence(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class UnifiedCandidateConfidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    formula: str | None = None
    exact_mass: float | None = None
    label: UnifiedConfidenceLabel
    confidence_band: UnifiedConfidenceBand
    confidence_score: float = Field(ge=0.0, le=1.0)
    raw_weighted_score: float = Field(ge=0.0, le=1.0)
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    agreement_count: int = 0
    contradiction_count: int = 0
    missing_layers: list[str] = Field(default_factory=list)
    layers: list[UnifiedEvidenceLayerScore] = Field(default_factory=list)
    layer_scores: dict[str, float | None] = Field(default_factory=dict)
    evidence_summary: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnifiedCandidateConfidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    selected_adduct: str
    candidate_count: int
    best_candidate: UnifiedCandidateConfidenceItem | None = None
    ranked_candidates: list[UnifiedCandidateConfidenceItem] = Field(default_factory=list)
    evidence_layers_used: list[str] = Field(default_factory=list)
    global_contradictions: list[str] = Field(default_factory=list)
    ambiguity_alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    component_metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    layer: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    source_tab: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    evidence_summary: list[str] = Field(default_factory=list, max_length=100)
    contradictions: list[str] = Field(default_factory=list, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    notes: list[str] = Field(default_factory=list, max_length=100)
    endpoint: str | None = Field(default=None, max_length=300)
    response: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = Field(default=None, max_length=100)
    provenance: dict[str, Any] | None = None
    selected_for_unified: bool

    @field_validator(
        "id",
        "layer",
        "title",
        "source_tab",
        "status",
        "label",
        "summary",
        "endpoint",
        "created_at",
        mode="before",
    )
    @classmethod
    def _trim_bundle_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("evidence_summary", "contradictions", "warnings", "notes", mode="before")
    @classmethod
    def _coerce_bundle_string_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []


class UnifiedEvidenceBundleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    solvent: str | None = Field(default=None, max_length=50)
    candidates_text: str | None = Field(default=None, max_length=100_000)
    evidence_items: list[EvidenceBundleItem] = Field(default_factory=list, max_length=200)
    metadata: dict[str, Any] | None = None

    @field_validator("sample_id", "solvent", "candidates_text", mode="before")
    @classmethod
    def _trim_bundle_request_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


UnifiedEvidenceBundleLabel = Literal[
    "high_confidence_candidate",
    "moderate_confidence_candidate",
    "low_confidence_candidate",
    "conflicting_evidence",
    "insufficient_evidence",
    "requires_review",
]


class UnifiedEvidenceBundleConfidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    solvent: str | None = None
    selected_adduct: str = "[M+H]+"
    candidate_count: int = Field(ge=0)
    best_candidate: UnifiedCandidateConfidenceItem | None = None
    ranked_candidates: list[UnifiedCandidateConfidenceItem] = Field(default_factory=list)
    evidence_layers_used: list[str] = Field(default_factory=list)
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    agreement_count: int = Field(ge=0)
    contradiction_count: int = Field(ge=0)
    missing_layers: list[str] = Field(default_factory=list)
    global_contradictions: list[str] = Field(default_factory=list)
    ambiguity_alerts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    label: UnifiedEvidenceBundleLabel
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    component_metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    items: list[str] = Field(default_factory=list)


StructureElucidationReportStatus = Literal[
    "draft_requires_review",
    "review_ready",
    "approved_for_release",
    "blocked_by_contradictions",
    "insufficient_evidence",
]
StructureElucidationReleaseGate = Literal[
    "requires_human_review",
    "approved_for_release",
    "blocked_by_contradictions",
    "insufficient_evidence",
]
StructureElucidationIntendedUse = Literal[
    "research_decision_support",
    "qc_batch_record",
    "regulatory_support",
    "training_or_education",
]


class StructureElucidationReportCandidateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    name: str | None = None
    role: str | None = None
    smiles: str
    formula: str | None = None
    exact_mass: float | None = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    confidence_band: UnifiedConfidenceBand
    label: UnifiedConfidenceLabel
    evidence_completeness: float = Field(ge=0.0, le=1.0)
    agreement_count: int = 0
    contradiction_count: int = 0
    missing_layers: list[str] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StructureElucidationReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_title: str = Field(
        default="Regulatory-ready Structure Elucidation Report", min_length=3, max_length=200
    )
    sample_id: str | None = Field(default=None, max_length=100)
    project_name: str | None = Field(default=None, max_length=200)
    prepared_by: str | None = Field(default=None, max_length=200)
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=4000)
    review_status: ReviewStatus | None = None
    intended_use: StructureElucidationIntendedUse = "research_decision_support"
    require_human_approval: bool = True
    requestor_notes: str | None = Field(default=None, max_length=8000)

    raw_data_sha256: str | None = Field(default=None, max_length=128)
    source_files: list[str] = Field(default_factory=list, max_length=50)
    processing_history: list[str] = Field(default_factory=list, max_length=100)

    unified_confidence_request: UnifiedCandidateConfidenceRequest | None = None
    unified_confidence_result: UnifiedCandidateConfidenceResult | None = None

    @field_validator(
        "sample_id",
        "project_name",
        "prepared_by",
        "reviewer_name",
        "reviewer_comment",
        "requestor_notes",
        "raw_data_sha256",
        mode="before",
    )
    @classmethod
    def _optional_trim_structure_report_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("source_files", "processing_history", mode="before")
    @classmethod
    def _trim_structure_report_lists(cls, value: list[str] | tuple[str, ...] | None) -> list[str]:
        if value is None:
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class StructureElucidationReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str
    generated_at: datetime
    report_title: str
    sample_id: str | None = None
    project_name: str | None = None
    prepared_by: str | None = None
    reviewer_name: str | None = None
    review_status: ReviewStatus | None = None
    reviewer_comment: str | None = None
    intended_use: StructureElucidationIntendedUse
    status: StructureElucidationReportStatus
    release_gate: StructureElucidationReleaseGate
    human_review_required: bool = True
    human_review_approved: bool = False

    best_candidate: StructureElucidationReportCandidateSummary | None = None
    ranked_candidates: list[StructureElucidationReportCandidateSummary] = Field(
        default_factory=list
    )
    selected_adduct: str | None = None
    evidence_layers_used: list[str] = Field(default_factory=list)
    evidence_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    agreement_count: int = 0
    contradiction_count: int = 0
    global_contradictions: list[str] = Field(default_factory=list)
    ambiguity_alerts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    provenance: dict[str, Any] = Field(default_factory=dict)
    sections: list[EvidenceReportSection] = Field(default_factory=list)
    json_report: dict[str, Any] = Field(default_factory=dict)
    html_report: str = ""


RegulatoryJurisdictionStatus = Literal["active", "inactive"]
RegulatorySourceType = Literal[
    "guidance",
    "regulation",
    "internal_sop",
    "company_policy",
    "scientific_report",
    "analytical_report",
    "other",
]
RegulatorySourceStatus = Literal["draft", "active", "deprecated", "archived"]
RegulatoryDossierStatus = Literal[
    "draft",
    "in_review",
    "ready",
    "blocked",
    "approved",
    "archived",
]
RegulatoryRequirementCategory = Literal[
    "identity",
    "analytical_evidence",
    "impurities",
    "safety",
    "stability",
    "manufacturing",
    "documentation",
    "labeling",
    "submission",
    "claim_support",
    "other",
]
RegulatoryRequirementPriority = Literal["low", "medium", "high", "critical"]
RegulatoryRequirementStatus = Literal[
    "not_started",
    "in_progress",
    "evidence_needed",
    "review_needed",
    "satisfied",
    "blocked",
    "not_applicable",
]
RegulatoryEvidenceType = Literal[
    "spectracheck_report",
    "unified_evidence",
    "qc_assessment",
    "raw_file_hash",
    "reaction_experiment",
    "reaction_report",
    "analytical_artifact",
    "human_note",
    "other",
]
RegulatoryEvidenceStatus = Literal["linked", "needs_review", "accepted", "rejected"]
RegulatoryQueryStatus = Literal[
    "queued",
    "answered",
    "insufficient_sources",
    "failed",
    "requires_review",
]
RegulatoryAnswerConfidence = Literal["low", "medium", "high", "insufficient_sources"]
RegulatoryRiskLevel = Literal["low", "medium", "high", "critical", "unknown"]
RegulatoryReviewDecisionValue = Literal["approve", "needs_changes", "reject", "defer"]
RegulatoryChangeAlertSeverity = Literal["info", "warning", "critical"]
RegulatoryChangeAlertStatus = Literal["open", "acknowledged", "resolved"]
RegulatoryReadinessStatus = Literal["draft", "requires_review", "ready_for_review", "blocked"]


class RegulatoryJurisdictionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=240)
    region: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, max_length=8)
    authority_name: str | None = Field(default=None, max_length=240)
    status: RegulatoryJurisdictionStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "region", "country_code", "authority_name", mode="before")
    @classmethod
    def _trim_regulatory_jurisdiction_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryJurisdiction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    region: str | None = None
    country_code: str | None = None
    authority_name: str | None = None
    status: RegulatoryJurisdictionStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    citation_label: str
    section_title: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
    quote_excerpt: str | None = None
    summary: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatorySourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    source_type: RegulatorySourceType
    jurisdiction_id: int | None = None
    source_url: str | None = None
    source_date: datetime | None = None
    retrieved_at: datetime | None = None
    version: str | None = None
    file_id: int | None = None
    sha256: str | None = None
    text_excerpt: str | None = None
    status: RegulatorySourceStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    citations: list[RegulatoryCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatorySourceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=10_000)
    jurisdiction_id: int | None = None
    source_type: RegulatorySourceType | None = None
    limit: int = Field(default=10, ge=1, le=100)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query", mode="before")
    @classmethod
    def _trim_regulatory_source_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatorySourceSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    sources: list[RegulatorySourceDocument] = Field(default_factory=list)
    citations: list[RegulatoryCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryDossierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None
    sample_id: int | None = None
    spectracheck_session_id: int | None = None
    reaction_project_id: int | None = None
    title: str = Field(min_length=1, max_length=300)
    product_name: str | None = Field(default=None, max_length=240)
    compound_name: str | None = Field(default=None, max_length=240)
    jurisdiction_id: int | None = None
    intended_use: str | None = Field(default=None, max_length=500)
    status: RegulatoryDossierStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "product_name", "compound_name", "intended_use", mode="before")
    @classmethod
    def _trim_regulatory_dossier_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryDossierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None
    sample_id: int | None = None
    spectracheck_session_id: int | None = None
    reaction_project_id: int | None = None
    title: str | None = Field(default=None, max_length=300)
    product_name: str | None = Field(default=None, max_length=240)
    compound_name: str | None = Field(default=None, max_length=240)
    jurisdiction_id: int | None = None
    intended_use: str | None = Field(default=None, max_length=500)
    status: RegulatoryDossierStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "product_name", "compound_name", "intended_use", mode="before")
    @classmethod
    def _trim_regulatory_dossier_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int | None = None
    sample_id: int | None = None
    spectracheck_session_id: int | None = None
    reaction_project_id: int | None = None
    title: str
    product_name: str | None = None
    compound_name: str | None = None
    jurisdiction_id: int | None = None
    intended_use: str | None = None
    status: RegulatoryDossierStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryRequirementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    category: RegulatoryRequirementCategory = "other"
    requirement_text: str = Field(min_length=1, max_length=40_000)
    priority: RegulatoryRequirementPriority = "medium"
    status: RegulatoryRequirementStatus = "not_started"
    citation_ids_json: list[int] = Field(default_factory=list)
    evidence_link_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "requirement_text", mode="before")
    @classmethod
    def _trim_regulatory_requirement_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryRequirementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    category: RegulatoryRequirementCategory | None = None
    requirement_text: str | None = Field(default=None, max_length=40_000)
    priority: RegulatoryRequirementPriority | None = None
    status: RegulatoryRequirementStatus | None = None
    citation_ids_json: list[int] | None = None
    evidence_link_ids_json: list[int] | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "requirement_text", mode="before")
    @classmethod
    def _trim_regulatory_requirement_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    title: str
    category: RegulatoryRequirementCategory
    requirement_text: str
    priority: RegulatoryRequirementPriority
    status: RegulatoryRequirementStatus
    citation_ids_json: list[int] = Field(default_factory=list)
    evidence_link_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryEvidenceLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: int | None = None
    evidence_type: RegulatoryEvidenceType = "other"
    resource_id: int | None = None
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=20_000)
    status: RegulatoryEvidenceStatus = "linked"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "summary", mode="before")
    @classmethod
    def _trim_regulatory_evidence_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    requirement_id: int | None = None
    evidence_type: RegulatoryEvidenceType
    resource_id: int | None = None
    title: str
    summary: str
    status: RegulatoryEvidenceStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryQueryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=20_000)
    jurisdiction_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("question", mode="before")
    @classmethod
    def _trim_regulatory_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    query_id: int
    answer_text: str
    confidence_label: RegulatoryAnswerConfidence
    citation_ids_json: list[int] = Field(default_factory=list)
    missing_sources_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    citations: list[RegulatoryCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RegulatoryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int | None = None
    question: str
    jurisdiction_id: int | None = None
    status: RegulatoryQueryStatus
    answer_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    answer: RegulatoryAnswer | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryRiskAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    overall_risk: RegulatoryRiskLevel
    risk_factors_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_evidence_json: list[dict[str, Any]] = Field(default_factory=list)
    contradictions_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    citation_ids_json: list[int] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RegulatoryReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str | None = Field(default=None, max_length=200)
    decision: RegulatoryReviewDecisionValue
    rationale: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "rationale", mode="before")
    @classmethod
    def _trim_regulatory_review_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    reviewer_name: str | None = None
    decision: RegulatoryReviewDecisionValue
    rationale: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryChangeAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    jurisdiction_id: int | None = None
    source_id: int | None = None
    title: str
    message: str
    severity: RegulatoryChangeAlertSeverity
    status: RegulatoryChangeAlertStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryReadinessReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    status: RegulatoryReadinessStatus
    summary_json: dict[str, Any] = Field(default_factory=dict)
    requirements_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_json: list[dict[str, Any]] = Field(default_factory=list)
    gaps_json: list[dict[str, Any]] = Field(default_factory=list)
    risks_json: dict[str, Any] = Field(default_factory=dict)
    citation_ids_json: list[int] = Field(default_factory=list)
    review_status_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


RegulatoryRuleSourceType = Literal[
    "ich",
    "fda",
    "ema",
    "usp",
    "pmda",
    "health_canada",
    "internal_sop",
    "custom",
]
RegulatoryRuleSetStatus = Literal["draft", "active", "deprecated", "archived"]
ImpurityRuleType = Literal["reporting", "identification", "qualification"]
ImpurityRuleAppliesTo = Literal[
    "drug_substance",
    "drug_product",
    "process_impurity",
    "degradation_product",
    "unspecified",
]
ResidualSolventClass = Literal["class_1", "class_2", "class_3", "other", "unknown"]
NitrosamineRiskCategory = Literal[
    "nitrosamine_possible",
    "nitrosamine_confirmed",
    "n_nitroso_motif",
    "cpca_review_required",
    "unknown",
]
QNMRReadinessStatus = Literal[
    "not_assessed",
    "draft",
    "ready_for_review",
    "gaps_identified",
    "reviewed",
]
AnalyticalMethodType = Literal[
    "qnmr",
    "nmr_qualitative",
    "hrms",
    "lcms",
    "msms",
    "hplc",
    "uplc",
    "other",
]
AnalyticalValidationStatus = Literal[
    "not_started",
    "in_progress",
    "gaps_identified",
    "ready_for_review",
    "reviewed",
]
RegulatoryActionType = Literal[
    "impurity_reporting",
    "impurity_identification",
    "impurity_qualification",
    "residual_solvent_review",
    "nitrosamine_risk_review",
    "qnmr_validation_gap",
    "ai_governance_gap",
    "jurisdictional_review",
    "source_needed",
    "human_review",
    "other",
]
RegulatoryActionSeverity = Literal["info", "warning", "high", "critical"]
RegulatoryActionStatus = Literal["open", "in_progress", "resolved", "dismissed", "deferred"]
BatchRegulatoryAssessmentStatus = Literal[
    "not_assessed",
    "ready_for_review",
    "action_required",
    "blocked",
    "reviewed",
]
ImpurityType = Literal[
    "process_impurity",
    "degradation_product",
    "residual_solvent",
    "nitrosamine",
    "unknown",
    "other",
]
ImpurityEvidenceSource = Literal[
    "nmr_peak",
    "ms_peak",
    "lcms_feature",
    "reaction_route",
    "user_entered",
    "report",
    "unknown",
]
ImpurityThresholdTriggered = Literal[
    "none",
    "reporting",
    "identification",
    "qualification",
    "review_required",
]
ImpurityRiskStatus = Literal["draft", "needs_review", "action_required", "accepted", "dismissed"]
AIGovernanceStatus = Literal[
    "not_assessed",
    "gaps_identified",
    "ready_for_review",
    "reviewed",
]


class ImpurityThresholdRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_type: ImpurityRuleType
    threshold_percent: float | None = Field(default=None, ge=0)
    threshold_amount_mg_per_day: float | None = Field(default=None, ge=0)
    applies_to: ImpurityRuleAppliesTo = "unspecified"
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ImpurityThresholdRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    rule_set_id: int
    rule_type: ImpurityRuleType
    threshold_percent: float | None = None
    threshold_amount_mg_per_day: float | None = None
    applies_to: ImpurityRuleAppliesTo
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ResidualSolventRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solvent_name: str = Field(min_length=1, max_length=160)
    solvent_class: ResidualSolventClass = "unknown"
    permitted_daily_exposure: float | None = Field(default=None, ge=0)
    concentration_limit: float | None = Field(default=None, ge=0)
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("solvent_name", mode="before")
    @classmethod
    def _trim_solvent_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ResidualSolventRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    rule_set_id: int
    solvent_name: str
    solvent_class: ResidualSolventClass
    permitted_daily_exposure: float | None = None
    concentration_limit: float | None = None
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class NitrosamineRiskRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_category: NitrosamineRiskCategory = "unknown"
    structural_pattern: str | None = Field(default=None, max_length=10_000)
    acceptable_intake: float | None = Field(default=None, ge=0)
    ai_limit: float | None = Field(default=None, ge=0)
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class NitrosamineRiskRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    rule_set_id: int
    risk_category: NitrosamineRiskCategory
    structural_pattern: str | None = None
    acceptable_intake: float | None = None
    ai_limit: float | None = None
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryRuleSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    jurisdiction_id: int | None = Field(default=None, ge=1)
    version: str = Field(min_length=1, max_length=120)
    source_type: RegulatoryRuleSourceType = "custom"
    source_ids_json: list[int] = Field(default_factory=list)
    status: RegulatoryRuleSetStatus = "draft"
    impurity_threshold_rules_json: list[ImpurityThresholdRuleCreate] = Field(default_factory=list)
    residual_solvent_rules_json: list[ResidualSolventRuleCreate] = Field(default_factory=list)
    nitrosamine_risk_rules_json: list[NitrosamineRiskRuleCreate] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "version", mode="before")
    @classmethod
    def _trim_rule_set_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatoryRuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    jurisdiction_id: int | None = None
    version: str
    source_type: RegulatoryRuleSourceType
    source_ids_json: list[int] = Field(default_factory=list)
    status: RegulatoryRuleSetStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    impurity_threshold_rules_json: list[ImpurityThresholdRule] = Field(default_factory=list)
    residual_solvent_rules_json: list[ResidualSolventRule] = Field(default_factory=list)
    nitrosamine_risk_rules_json: list[NitrosamineRiskRule] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class QNMRComplianceProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analytical_target_profile_json: dict[str, Any] = Field(default_factory=dict)
    validation_parameters_json: dict[str, Any] = Field(default_factory=dict)
    calibration_method: str | None = Field(default=None, max_length=200)
    internal_standard: str | None = Field(default=None, max_length=200)
    acquisition_parameters_json: dict[str, Any] = Field(default_factory=dict)
    uncertainty_summary_json: dict[str, Any] = Field(default_factory=dict)
    q2_q14_readiness_status: QNMRReadinessStatus | None = None
    citations_json: list[int] | list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QNMRComplianceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    analytical_target_profile_json: dict[str, Any] = Field(default_factory=dict)
    validation_parameters_json: dict[str, Any] = Field(default_factory=dict)
    calibration_method: str | None = None
    internal_standard: str | None = None
    acquisition_parameters_json: dict[str, Any] = Field(default_factory=dict)
    uncertainty_summary_json: dict[str, Any] = Field(default_factory=dict)
    q2_q14_readiness_status: QNMRReadinessStatus
    citations_json: list[Any] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class AnalyticalMethodValidationProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_type: AnalyticalMethodType = "other"
    analytical_target_profile_json: dict[str, Any] = Field(default_factory=dict)
    accuracy_json: dict[str, Any] | None = None
    precision_json: dict[str, Any] | None = None
    specificity_json: dict[str, Any] | None = None
    linearity_json: dict[str, Any] | None = None
    range_json: dict[str, Any] | None = None
    robustness_json: dict[str, Any] | None = None
    lod_loq_json: dict[str, Any] | None = None
    validation_status: AnalyticalValidationStatus | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AnalyticalMethodValidationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    method_type: AnalyticalMethodType
    analytical_target_profile_json: dict[str, Any] = Field(default_factory=dict)
    accuracy_json: dict[str, Any] | None = None
    precision_json: dict[str, Any] | None = None
    specificity_json: dict[str, Any] | None = None
    linearity_json: dict[str, Any] | None = None
    range_json: dict[str, Any] | None = None
    robustness_json: dict[str, Any] | None = None
    lod_loq_json: dict[str, Any] | None = None
    validation_status: AnalyticalValidationStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryActionItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: int | None = Field(default=None, ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    evidence_link_id: int | None = Field(default=None, ge=1)
    requirement_id: int | None = Field(default=None, ge=1)
    action_type: RegulatoryActionType = "human_review"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=40_000)
    severity: RegulatoryActionSeverity = "warning"
    status: RegulatoryActionStatus = "open"
    due_date: datetime | None = None
    assigned_to: str | None = Field(default=None, max_length=200)
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryActionItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: RegulatoryActionType | None = None
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=40_000)
    severity: RegulatoryActionSeverity | None = None
    status: RegulatoryActionStatus | None = None
    due_date: datetime | None = None
    assigned_to: str | None = Field(default=None, max_length=200)
    citation_ids_json: list[int] | None = None
    metadata_json: dict[str, Any] | None = None


class RegulatoryActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int | None = None
    batch_id: int | None = None
    compound_id: int | None = None
    evidence_link_id: int | None = None
    requirement_id: int | None = None
    action_type: RegulatoryActionType
    title: str
    description: str
    severity: RegulatoryActionSeverity
    status: RegulatoryActionStatus
    due_date: datetime | None = None
    assigned_to: str | None = None
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class BatchRegulatoryAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class BatchRegulatoryAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    batch_id: int | None = None
    compound_id: int | None = None
    overall_status: BatchRegulatoryAssessmentStatus
    impurity_summary_json: dict[str, Any] = Field(default_factory=dict)
    residual_solvent_summary_json: dict[str, Any] = Field(default_factory=dict)
    nitrosamine_summary_json: dict[str, Any] = Field(default_factory=dict)
    qnmr_summary_json: dict[str, Any] = Field(default_factory=dict)
    ai_governance_summary_json: dict[str, Any] = Field(default_factory=dict)
    action_item_ids_json: list[int] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ImpurityRiskRegisterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impurity_name: str | None = Field(default=None, max_length=240)
    impurity_type: ImpurityType = "unknown"
    source: ImpurityEvidenceSource = "user_entered"
    observed_level_percent: float | None = Field(default=None, ge=0)
    observed_amount: float | None = Field(default=None, ge=0)
    threshold_triggered: ImpurityThresholdTriggered | None = None
    structural_assignment: str | None = Field(default=None, max_length=20_000)
    compound_id: int | None = Field(default=None, ge=1)
    evidence_link_id: int | None = Field(default=None, ge=1)
    status: ImpurityRiskStatus | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ImpurityRiskRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    impurity_name: str | None = None
    impurity_type: ImpurityType
    source: ImpurityEvidenceSource
    observed_level_percent: float | None = None
    observed_amount: float | None = None
    threshold_triggered: ImpurityThresholdTriggered
    structural_assignment: str | None = None
    compound_id: int | None = None
    evidence_link_id: int | None = None
    action_item_id: int | None = None
    status: ImpurityRiskStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ResidualSolventAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    solvents_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class NitrosamineWatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    structure_text: str | None = Field(default=None, max_length=200_000)
    risk_signals_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIGovernanceRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_system_name: str = Field(min_length=1, max_length=240)
    model_version_id: int | None = Field(default=None, ge=1)
    method_id: int | None = Field(default=None, ge=1)
    workflow_run_id: int | None = Field(default=None, ge=1)
    evidence_item_ids_json: list[int] = Field(default_factory=list)
    explainability_summary_json: dict[str, Any] = Field(default_factory=dict)
    human_override_available: bool = False
    validation_record_ids_json: list[int] = Field(default_factory=list)
    governance_status: AIGovernanceStatus | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIGovernanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    ai_system_name: str
    model_version_id: int | None = None
    method_id: int | None = None
    workflow_run_id: int | None = None
    evidence_item_ids_json: list[int] = Field(default_factory=list)
    explainability_summary_json: dict[str, Any] = Field(default_factory=dict)
    human_override_available: bool
    validation_record_ids_json: list[int] = Field(default_factory=list)
    governance_status: AIGovernanceStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class JurisdictionalRequirementMapCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jurisdiction_id: int = Field(ge=1)
    rule_set_id: int | None = Field(default=None, ge=1)
    compare_jurisdiction_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class JurisdictionalRequirementMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    jurisdiction_id: int
    rule_set_id: int | None = None
    requirement_summary_json: dict[str, Any] = Field(default_factory=dict)
    threshold_summary_json: dict[str, Any] = Field(default_factory=dict)
    differences_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


RegulatoryWatcherSourceType = Literal[
    "fda_guidance",
    "ema_guideline",
    "ich_guideline",
    "usp_chapter",
    "pmda_guidance",
    "health_canada_guidance",
    "internal_sop",
    "company_policy",
    "custom_url",
    "uploaded_document",
    "other",
]
RegulatorySourceWatcherFrequency = Literal["manual", "daily", "weekly", "monthly", "quarterly"]
RegulatorySourceWatcherStatus = Literal["active", "paused", "archived", "error"]
RegulatorySourceVersionStatus = Literal["current", "superseded", "draft", "archived"]
RegulatorySurveillanceRunStatus = Literal["completed", "warning", "error", "no_change"]
RegulatorySurveillanceRunType = Literal["manual", "uploaded_document", "scheduled"]
RegulatoryChangeType = Literal[
    "new_source",
    "text_changed",
    "metadata_changed",
    "citation_changed",
    "threshold_changed",
    "status_changed",
    "deprecated",
    "no_change",
    "parse_error",
]
RegulatoryChangeSeverity = Literal["info", "warning", "high", "critical"]
RegulatoryChangeReviewStatus = Literal[
    "unreviewed", "in_review", "accepted", "rejected", "deferred"
]
RegulatoryChangeDiffType = Literal["text", "citation", "threshold", "metadata", "rule"]
RegulatoryImpactAssessmentStatus = Literal["draft", "ready_for_review", "reviewed", "blocked"]
RegulatoryRuleUpdateProposalType = Literal[
    "create_rule",
    "update_threshold",
    "update_citation",
    "deprecate_rule",
    "create_action_item",
    "update_jurisdiction_map",
    "other",
]
RegulatoryRuleUpdateProposalStatus = Literal[
    "proposed", "approved", "rejected", "applied", "deferred"
]
RegulatoryImpactNotificationStatus = Literal["unread", "read", "dismissed", "resolved"]


class RegulatorySourceWatcherCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=300)
    source_type: RegulatoryWatcherSourceType = "other"
    jurisdiction_id: int | None = Field(default=None, ge=1)
    source_url: str | None = Field(default=None, max_length=2_000)
    check_frequency: RegulatorySourceWatcherFrequency = "manual"
    status: RegulatorySourceWatcherStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "source_url", mode="before")
    @classmethod
    def _trim_watcher_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatorySourceWatcherUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, max_length=300)
    source_type: RegulatoryWatcherSourceType | None = None
    jurisdiction_id: int | None = Field(default=None, ge=1)
    source_url: str | None = Field(default=None, max_length=2_000)
    check_frequency: RegulatorySourceWatcherFrequency | None = None
    status: RegulatorySourceWatcherStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "source_url", mode="before")
    @classmethod
    def _trim_watcher_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatorySourceWatcher(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int | None = None
    title: str
    source_type: RegulatoryWatcherSourceType
    jurisdiction_id: int | None = None
    source_url: str | None = None
    check_frequency: RegulatorySourceWatcherFrequency
    status: RegulatorySourceWatcherStatus
    last_checked_at: datetime | None = None
    last_change_detected_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatorySurveillanceRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watcher_id: int | None = Field(default=None, ge=1)
    source_id: int | None = Field(default=None, ge=1)
    run_type: RegulatorySurveillanceRunType = "manual"
    version_label: str | None = Field(default=None, max_length=120)
    source_date: datetime | None = None
    file_id: int | None = Field(default=None, ge=1)
    uploaded_text: str | None = Field(default=None, max_length=1_000_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_watcher_or_source(self) -> RegulatorySurveillanceRunCreate:
        if self.watcher_id is None and self.source_id is None:
            raise ValueError("watcher_id or source_id is required.")
        return self

    @field_validator("version_label", "uploaded_text", mode="before")
    @classmethod
    def _trim_run_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RegulatorySourceVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    watcher_id: int | None = None
    version_label: str | None = None
    source_date: datetime | None = None
    retrieved_at: datetime
    file_id: int | None = None
    sha256: str | None = None
    content_hash: str | None = None
    normalized_text_hash: str | None = None
    text_excerpt: str | None = None
    status: RegulatorySourceVersionStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatorySurveillanceRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    watcher_id: int | None = None
    source_id: int | None = None
    run_type: RegulatorySurveillanceRunType
    status: RegulatorySurveillanceRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    created_version_id: int | None = None
    change_event_id: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatorySourceVersionCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_version_id: int = Field(ge=1)
    new_version_id: int = Field(ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatorySourceVersionCompareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int
    old_version_id: int
    new_version_id: int
    changed: bool
    change_type: RegulatoryChangeType
    diff_summary: str
    before_excerpt: str | None = None
    after_excerpt: str | None = None
    affected_topics_json: list[str] = Field(default_factory=list)
    old_normalized_text_hash: str | None = None
    new_normalized_text_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryChangeDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    change_event_id: int
    diff_type: RegulatoryChangeDiffType
    before_excerpt: str | None = None
    after_excerpt: str | None = None
    diff_summary: str
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryChangeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    old_version_id: int | None = None
    new_version_id: int
    change_type: RegulatoryChangeType
    severity: RegulatoryChangeSeverity
    title: str
    summary: str
    affected_topics_json: list[str] = Field(default_factory=list)
    affected_rule_set_ids_json: list[int] = Field(default_factory=list)
    affected_dossier_ids_json: list[int] = Field(default_factory=list)
    human_review_required: bool = True
    review_status: RegulatoryChangeReviewStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    diffs: list[RegulatoryChangeDiff] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RegulatoryChangeReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: RegulatoryChangeReviewStatus
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=10_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryImpactAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RegulatoryImpactAssessmentStatus | None = None
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryImpactAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    change_event_id: int
    status: RegulatoryImpactAssessmentStatus
    impacted_dossiers_json: list[int] = Field(default_factory=list)
    impacted_requirements_json: list[int] = Field(default_factory=list)
    impacted_action_items_json: list[int] = Field(default_factory=list)
    impacted_rule_sets_json: list[int] = Field(default_factory=list)
    impacted_ai_governance_records_json: list[int] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryRuleUpdateProposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_set_id: int | None = Field(default=None, ge=1)
    proposal_type: RegulatoryRuleUpdateProposalType = "other"
    title: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=40_000)
    proposed_changes_json: dict[str, Any] = Field(default_factory=dict)
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryRuleUpdateProposalReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=40_000)
    rationale: str | None = Field(default=None, max_length=40_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_reviewer_rationale(self) -> RegulatoryRuleUpdateProposalReviewRequest:
        if not (self.reviewer_comment or self.rationale):
            raise ValueError("reviewer_comment or rationale is required.")
        return self


class RegulatoryRuleUpdateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    change_event_id: int
    rule_set_id: int | None = None
    proposal_type: RegulatoryRuleUpdateProposalType
    title: str
    rationale: str
    proposed_changes_json: dict[str, Any] = Field(default_factory=dict)
    citation_ids_json: list[int] = Field(default_factory=list)
    status: RegulatoryRuleUpdateProposalStatus
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class RegulatoryImpactNotificationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RegulatoryImpactNotificationStatus | None = None
    metadata_json: dict[str, Any] | None = None


class RegulatoryImpactNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    change_event_id: int | None = None
    dossier_id: int | None = None
    action_item_id: int | None = None
    severity: RegulatoryChangeSeverity
    title: str
    message: str
    status: RegulatoryImpactNotificationStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class RegulatoryDossierChangeImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: int
    change_events: list[RegulatoryChangeEvent] = Field(default_factory=list)
    impact_assessments: list[RegulatoryImpactAssessment] = Field(default_factory=list)
    rule_update_proposals: list[RegulatoryRuleUpdateProposal] = Field(default_factory=list)
    notifications: list[RegulatoryImpactNotification] = Field(default_factory=list)
    action_item_ids_json: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


KnowledgeSourceType = Literal[
    "journal_article",
    "patent",
    "supporting_information",
    "regulatory_guidance",
    "internal_sop",
    "analytical_report",
    "eln_export",
    "project_note",
    "method_validation_document",
    "spectracheck_report",
    "reaction_report",
    "regulatory_report",
    "other",
]
KnowledgeSourceStatus = Literal["draft", "active", "archived", "deprecated", "needs_review"]
KnowledgeReliabilityLabel = Literal["high", "medium", "low", "unknown"]
KnowledgeSourceParseStatus = Literal["not_parsed", "parsed", "partial", "failed"]
KnowledgeExtractionType = Literal[
    "reaction",
    "analytical",
    "regulatory",
    "mixed",
    "citation_only",
    "training_candidate",
    "benchmark_candidate",
]
KnowledgeExtractionStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
KnowledgeReviewStatus = Literal["unreviewed", "accepted", "rejected", "needs_changes"]
KnowledgeRegulatoryTopic = Literal[
    "impurity_threshold",
    "residual_solvent",
    "nitrosamine",
    "qnmr",
    "method_validation",
    "ai_governance",
    "jurisdictional_map",
    "reporting",
    "other",
]
KnowledgeReviewRecordType = Literal[
    "reaction",
    "analytical",
    "regulatory",
    "citation",
    "training_candidate",
    "benchmark_candidate",
]
KnowledgeTaskStatus = Literal[
    "open", "in_review", "accepted", "rejected", "needs_changes", "deferred"
]
KnowledgeTargetType = Literal[
    "compound",
    "batch",
    "spectracheck_session",
    "reaction_project",
    "reaction_experiment",
    "regulatory_dossier",
    "report",
    "method_registry_entry",
    "workflow_template",
    "training_dataset_candidate",
    "benchmark_dataset_candidate",
    "model_improvement_queue_item",
    "other",
]
KnowledgeTrainingDatasetType = Literal[
    "nmr_prediction",
    "nmr_structure_elucidation",
    "msms_annotation",
    "lcms_feature",
    "reaction_optimization",
    "regulatory_extraction",
    "method_validation",
    "ai_governance",
]
KnowledgeCandidateStatus = Literal["proposed", "accepted", "rejected", "needs_review"]
KnowledgeBenchmarkType = Literal[
    "nmr_candidate_ranking",
    "nmr_shift_prediction",
    "msms_annotation",
    "lcms_feature_consensus",
    "reaction_optimization",
    "regulatory_rag",
    "regulatory_compliance",
]
DatasetSplitRecommendation = Literal["train", "validation", "test", "holdout", "unknown"]
LeakageRiskLabel = Literal["low", "medium", "high", "unknown"]
ModelImprovementSourceType = Literal[
    "error_case",
    "low_confidence_prediction",
    "failed_qc",
    "human_override",
    "new_reviewed_record",
    "benchmark_failure",
    "drift_alert",
]
ModelImprovementTargetModule = Literal[
    "spectracheck", "msms", "lcms", "reaction_optimization", "regulatory", "report"
]
ModelImprovementPriority = Literal["low", "medium", "high", "critical"]
ModelImprovementStatus = Literal["open", "in_review", "resolved", "dismissed"]
FeatureFamily = Literal["nmr", "ms", "lcms", "reaction", "regulatory", "compound", "workflow"]
DatasetVersionStatus = Literal["draft", "ready_for_review", "approved", "archived"]


class KnowledgeSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    source_type: KnowledgeSourceType = "other"
    source_url: str | None = Field(default=None, max_length=2_000)
    doi: str | None = Field(default=None, max_length=200)
    patent_number: str | None = Field(default=None, max_length=120)
    jurisdiction_id: int | None = Field(default=None, ge=1)
    publisher: str | None = Field(default=None, max_length=240)
    publication_date: datetime | None = None
    status: KnowledgeSourceStatus = "draft"
    reliability_label: KnowledgeReliabilityLabel = "unknown"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "source_url", "doi", "patent_number", "publisher", mode="before")
    @classmethod
    def _trim_source_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class KnowledgeSourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    source_type: KnowledgeSourceType | None = None
    source_url: str | None = Field(default=None, max_length=2_000)
    doi: str | None = Field(default=None, max_length=200)
    patent_number: str | None = Field(default=None, max_length=120)
    jurisdiction_id: int | None = Field(default=None, ge=1)
    publisher: str | None = Field(default=None, max_length=240)
    publication_date: datetime | None = None
    status: KnowledgeSourceStatus | None = None
    reliability_label: KnowledgeReliabilityLabel | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "source_url", "doi", "patent_number", "publisher", mode="before")
    @classmethod
    def _trim_source_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    source_type: KnowledgeSourceType
    source_url: str | None = None
    doi: str | None = None
    patent_number: str | None = None
    jurisdiction_id: int | None = None
    publisher: str | None = None
    publication_date: datetime | None = None
    status: KnowledgeSourceStatus
    reliability_label: KnowledgeReliabilityLabel
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class KnowledgeSourceFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    file_id: int | None = None
    filename: str | None = None
    sha256: str | None = None
    content_type: str | None = None
    parsed_text_hash: str | None = None
    parse_status: KnowledgeSourceParseStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class KnowledgeExtractionRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int | None = Field(default=None, ge=1)
    source_file_id: int | None = Field(default=None, ge=1)
    extraction_type: KnowledgeExtractionType = "mixed"
    model_or_method: str | None = Field(default=None, max_length=200)
    method_version: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _requires_source_anchor(self) -> KnowledgeExtractionRunCreate:
        if self.source_id is None and self.source_file_id is None:
            raise ValueError("source_id or source_file_id is required.")
        return self


class KnowledgeExtractionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int | None = None
    source_file_id: int | None = None
    extraction_type: KnowledgeExtractionType
    status: KnowledgeExtractionStatus
    model_or_method: str | None = None
    method_version: str | None = None
    extracted_count: int
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ExtractedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int
    source_file_id: int | None = None
    citation_label: str
    page_number: int | None = None
    section_title: str | None = None
    paragraph_number: int | None = None
    quote_excerpt: str | None = None
    summary: str | None = None
    confidence_score: float | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ExtractedReactionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    extraction_run_id: int
    source_id: int
    citation_ids_json: list[int] = Field(default_factory=list)
    reaction_name: str | None = None
    reaction_type: str | None = None
    substrate_summary: str | None = None
    product_summary: str | None = None
    product_smiles: str | None = None
    reagent_json: list[dict[str, Any]] = Field(default_factory=list)
    solvent_json: list[dict[str, Any]] = Field(default_factory=list)
    catalyst_json: list[dict[str, Any]] = Field(default_factory=list)
    ligand_json: list[dict[str, Any]] = Field(default_factory=list)
    base_json: list[dict[str, Any]] = Field(default_factory=list)
    additive_json: list[dict[str, Any]] = Field(default_factory=list)
    temperature_c: float | None = None
    time_h: float | None = None
    concentration: str | None = None
    scale: str | None = None
    yield_percent: float | None = None
    conversion_percent: float | None = None
    selectivity_percent: float | None = None
    ee_percent: float | None = None
    impurity_summary: str | None = None
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    outcome_json: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = None
    review_status: KnowledgeReviewStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ExtractedAnalyticalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    extraction_run_id: int
    source_id: int
    citation_ids_json: list[int] = Field(default_factory=list)
    compound_name: str | None = None
    structure_input: str | None = None
    structure_format: str | None = None
    formula: str | None = None
    exact_mass: float | None = None
    nmr_1h_text: str | None = None
    nmr_13c_text: str | None = None
    nmr_2d_summary: str | None = None
    hrms_text: str | None = None
    msms_summary: str | None = None
    solvent: str | None = None
    frequency_mhz: float | None = None
    analytical_method: str | None = None
    confidence_score: float | None = None
    review_status: KnowledgeReviewStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ExtractedRegulatoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    extraction_run_id: int
    source_id: int
    citation_ids_json: list[int] = Field(default_factory=list)
    jurisdiction_id: int | None = None
    topic: KnowledgeRegulatoryTopic
    requirement_text: str | None = None
    threshold_summary_json: dict[str, Any] | None = None
    rule_candidate_json: dict[str, Any] | None = None
    action_candidate_json: dict[str, Any] | None = None
    confidence_score: float | None = None
    review_status: KnowledgeReviewStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class KnowledgeReviewTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_run_id: int | None = Field(default=None, ge=1)
    record_type: KnowledgeReviewRecordType
    record_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    status: KnowledgeTaskStatus = "open"
    assigned_to: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class KnowledgeReviewTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    status: KnowledgeTaskStatus | None = None
    assigned_to: str | None = Field(default=None, max_length=200)
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=10_000)
    metadata_json: dict[str, Any] | None = None


class KnowledgeReviewTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    extraction_run_id: int | None = None
    record_type: KnowledgeReviewRecordType
    record_id: int
    title: str
    status: KnowledgeTaskStatus
    assigned_to: str | None = None
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class KnowledgeRecordReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: KnowledgeReviewRecordType
    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=10_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class KnowledgeRecordReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: KnowledgeReviewRecordType
    record_id: int
    review_status: str
    reviewer_name: str
    reviewer_comment: str
    message: str
    human_review_required: bool = True


class KnowledgeGraphLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: KnowledgeReviewRecordType
    target_type: KnowledgeTargetType
    target_id: KnowledgeGraphResourceId
    relation_type: str = Field(min_length=1, max_length=64)
    confidence_label: CompoundConfidenceLabel = "requires_review"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    record_type: KnowledgeReviewRecordType
    record_id: int
    target_type: KnowledgeTargetType
    target_id: KnowledgeGraphResourceId
    relation_type: str
    confidence_label: CompoundConfidenceLabel
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    sources: list[KnowledgeSource] = Field(default_factory=list)
    reaction_records: list[ExtractedReactionRecord] = Field(default_factory=list)
    analytical_records: list[ExtractedAnalyticalRecord] = Field(default_factory=list)
    regulatory_records: list[ExtractedRegulatoryRecord] = Field(default_factory=list)
    citations: list[ExtractedCitation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class TrainingDatasetCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int | None = Field(default=None, ge=1)
    record_type: KnowledgeReviewRecordType
    record_id: int = Field(ge=1)
    dataset_type: KnowledgeTrainingDatasetType
    status: KnowledgeCandidateStatus = "proposed"
    quality_flags_json: list[str] = Field(default_factory=list)
    citation_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TrainingDatasetCandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: KnowledgeCandidateStatus | None = None
    quality_flags_json: list[str] | None = None
    citation_ids_json: list[int] | None = None
    metadata_json: dict[str, Any] | None = None


class TrainingDatasetCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int | None = None
    record_type: KnowledgeReviewRecordType
    record_id: int
    dataset_type: KnowledgeTrainingDatasetType
    status: KnowledgeCandidateStatus
    quality_flags_json: list[str] = Field(default_factory=list)
    citation_ids_json: list[int] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class BenchmarkDatasetCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: int | None = Field(default=None, ge=1)
    record_type: KnowledgeReviewRecordType
    record_id: int = Field(ge=1)
    benchmark_type: KnowledgeBenchmarkType
    status: KnowledgeCandidateStatus = "proposed"
    split_recommendation: DatasetSplitRecommendation = "unknown"
    leakage_risk_label: LeakageRiskLabel = "unknown"
    quality_flags_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class BenchmarkDatasetCandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: KnowledgeCandidateStatus | None = None
    split_recommendation: DatasetSplitRecommendation | None = None
    leakage_risk_label: LeakageRiskLabel | None = None
    quality_flags_json: list[str] | None = None
    metadata_json: dict[str, Any] | None = None


class BenchmarkDatasetCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_id: int | None = None
    record_type: KnowledgeReviewRecordType
    record_id: int
    benchmark_type: KnowledgeBenchmarkType
    status: KnowledgeCandidateStatus
    split_recommendation: DatasetSplitRecommendation
    leakage_risk_label: LeakageRiskLabel
    quality_flags_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ModelImprovementQueueItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ModelImprovementSourceType
    target_module: ModelImprovementTargetModule
    linked_record_type: KnowledgeReviewRecordType | None = None
    linked_record_id: int | None = Field(default=None, ge=1)
    priority: ModelImprovementPriority = "medium"
    status: ModelImprovementStatus = "open"
    summary: str = Field(min_length=1, max_length=40_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelImprovementQueueItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: ModelImprovementPriority | None = None
    status: ModelImprovementStatus | None = None
    summary: str | None = Field(default=None, max_length=40_000)
    metadata_json: dict[str, Any] | None = None


class ModelImprovementQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_type: ModelImprovementSourceType
    target_module: ModelImprovementTargetModule
    linked_record_type: KnowledgeReviewRecordType | None = None
    linked_record_id: int | None = None
    priority: ModelImprovementPriority
    status: ModelImprovementStatus
    summary: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class FeatureRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: str = Field(min_length=1, max_length=64)
    record_id: int = Field(ge=1)
    feature_family: FeatureFamily
    features_json: dict[str, Any] = Field(default_factory=dict)
    feature_version: str = Field(default="v1", min_length=1, max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    record_type: str
    record_id: int
    feature_family: FeatureFamily
    features_json: dict[str, Any] = Field(default_factory=dict)
    feature_version: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class DatasetVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=64)
    source_record_ids_json: list[dict[str, Any] | int] = Field(default_factory=list)
    split_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    leakage_warnings_json: list[str] = Field(default_factory=list)
    status: DatasetVersionStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DatasetVersionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=64)
    source_record_ids_json: list[dict[str, Any] | int] | None = None
    split_json: dict[str, Any] | None = None
    quality_summary_json: dict[str, Any] | None = None
    leakage_warnings_json: list[str] | None = None
    status: DatasetVersionStatus | None = None
    metadata_json: dict[str, Any] | None = None


class DatasetVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dataset_type: str
    name: str
    version: str
    source_record_ids_json: list[Any] = Field(default_factory=list)
    split_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    leakage_warnings_json: list[str] = Field(default_factory=list)
    status: DatasetVersionStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


MLDomain = Literal[
    "nmr",
    "ms",
    "lcms",
    "reaction",
    "regulatory",
    "report",
    "multimodal",
]
MLTaskType = Literal[
    "regression",
    "classification",
    "ranking",
    "retrieval",
    "extraction",
    "generation",
    "calibration",
    "scoring",
]
MLTaskStatus = Literal["active", "experimental", "deprecated", "disabled"]
FeaturePipelineStatus = Literal["active", "experimental", "deprecated"]
MLModelFamily = Literal[
    "baseline",
    "linear",
    "random_forest",
    "gradient_boosting",
    "gaussian_process",
    "graph_neural_network",
    "transformer",
    "retrieval",
    "rule_based",
    "external",
]
MLTrainingRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "canceled",
    "requires_review",
]
MLEvaluationRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
]
ModelArtifactStatus = Literal[
    "trained",
    "evaluated",
    "deployment_candidate",
    "approved",
    "rejected",
    "deprecated",
]
ModelCardApprovalStatus = Literal[
    "draft",
    "ready_for_review",
    "approved",
    "rejected",
    "deprecated",
]
ModelMetricSplit = Literal["train", "validation", "test", "holdout", "benchmark", "unknown"]
CalibrationMethod = Literal[
    "reliability_curve",
    "isotonic",
    "platt",
    "conformal",
    "heuristic",
    "not_assessed",
]
CalibrationStatus = Literal[
    "not_assessed",
    "acceptable",
    "warning",
    "failed",
    "requires_review",
]
ErrorAnalysisSliceType = Literal[
    "molecule_class",
    "nucleus",
    "solvent",
    "mass_range",
    "reaction_type",
    "variable_type",
    "jurisdiction",
    "source_type",
    "confidence_bin",
    "other",
]
ErrorAnalysisSeverity = Literal["info", "warning", "high", "critical"]
OODMethod = Literal["feature_distance", "embedding_distance", "rule_based", "unknown"]
OODStatus = Literal[
    "not_assessed",
    "acceptable",
    "warning",
    "failed",
    "requires_review",
]
DeploymentTargetModule = Literal[
    "spectracheck",
    "msms",
    "lcms",
    "reaction_optimization",
    "regulatory",
    "report",
    "knowledge_extraction",
]
DeploymentCandidateStatus = Literal[
    "proposed",
    "in_review",
    "approved_for_internal_use",
    "approved_for_production",
    "rejected",
    "deprecated",
]
PredictionServiceConfigStatus = Literal["draft", "active", "disabled"]


class MLTaskDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    domain: MLDomain
    task_type: MLTaskType
    description: str = Field(default="", max_length=20_000)
    default_metric: str = Field(default="review_required", max_length=120)
    required_dataset_type: str = Field(min_length=1, max_length=120)
    status: MLTaskStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MLTaskDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    task_key: str
    name: str
    domain: MLDomain
    task_type: MLTaskType
    description: str
    default_metric: str
    required_dataset_type: str
    status: MLTaskStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeaturePipelineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=80)
    task_key: str = Field(min_length=1, max_length=120)
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)
    feature_steps_json: list[dict[str, Any]] = Field(default_factory=list)
    status: FeaturePipelineStatus = "experimental"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeaturePipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    version: str
    task_key: str
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)
    feature_steps_json: list[dict[str, Any]] = Field(default_factory=list)
    status: FeaturePipelineStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MLTrainingRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1, max_length=120)
    dataset_version_id: int | None = Field(default=None, ge=1)
    feature_pipeline_id: int | None = Field(default=None, ge=1)
    model_family: MLModelFamily = "baseline"
    model_name: str = Field(min_length=1, max_length=200)
    model_version: str = Field(min_length=1, max_length=80)
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    experimental: bool = False


class MLTrainingRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    task_key: str
    dataset_version_id: int
    feature_pipeline_id: int | None = None
    model_family: MLModelFamily
    model_name: str
    model_version: str
    status: MLTrainingRunStatus
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    training_metrics_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    model_artifact_id: int | None = None
    human_review_required: bool = True


class MLTrainingRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_run_id: int
    task_key: str
    dataset_version_id: int
    status: MLTrainingRunStatus
    model_family: MLModelFamily
    model_artifact_id: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class MLEvaluationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    training_run_id: int | None = Field(default=None, ge=1)
    model_artifact_id: int | None = Field(default=None, ge=1)
    benchmark_dataset_id: int | None = Field(default=None, ge=1)
    dataset_version_id: int | None = Field(default=None, ge=1)
    status: MLEvaluationRunStatus = "queued"
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    slice_metrics_json: dict[str, Any] = Field(default_factory=dict)
    confusion_summary_json: dict[str, Any] | None = None
    calibration_summary_json: dict[str, Any] | None = None
    error_examples_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MLEvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    training_run_id: int | None = None
    model_artifact_id: int | None = None
    benchmark_dataset_id: int | None = None
    dataset_version_id: int | None = None
    status: MLEvaluationRunStatus
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    slice_metrics_json: dict[str, Any] = Field(default_factory=dict)
    confusion_summary_json: dict[str, Any] | None = None
    calibration_summary_json: dict[str, Any] | None = None
    error_examples_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True
    metric_records: list[ModelMetric] = Field(default_factory=list)


class MLEvaluationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: int
    status: MLEvaluationRunStatus
    metrics: dict[str, Any] = Field(default_factory=dict)
    slice_metrics: dict[str, Any] = Field(default_factory=dict)
    error_examples: list[dict[str, Any]] = Field(default_factory=list)
    calibration_summary: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ModelArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    training_run_id: int
    model_name: str
    model_version: str
    model_family: MLModelFamily
    artifact_uri: str | None = None
    artifact_sha256: str | None = None
    model_hash: str | None = None
    task_key: str
    status: ModelArtifactStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_artifact_id: int = Field(ge=1)
    task_key: str = Field(min_length=1, max_length=120)
    intended_use: str = Field(min_length=1, max_length=20_000)
    limitations: str = Field(min_length=1, max_length=20_000)
    training_data_summary_json: dict[str, Any] = Field(default_factory=dict)
    evaluation_summary_json: dict[str, Any] = Field(default_factory=dict)
    bias_risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    out_of_domain_summary_json: dict[str, Any] = Field(default_factory=dict)
    calibration_summary_json: dict[str, Any] = Field(default_factory=dict)
    human_review_summary_json: dict[str, Any] = Field(default_factory=dict)
    approval_status: ModelCardApprovalStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_use: str | None = Field(default=None, max_length=20_000)
    limitations: str | None = Field(default=None, max_length=20_000)
    training_data_summary_json: dict[str, Any] | None = None
    evaluation_summary_json: dict[str, Any] | None = None
    bias_risk_summary_json: dict[str, Any] | None = None
    out_of_domain_summary_json: dict[str, Any] | None = None
    calibration_summary_json: dict[str, Any] | None = None
    human_review_summary_json: dict[str, Any] | None = None
    approval_status: ModelCardApprovalStatus | None = None
    metadata_json: dict[str, Any] | None = None


class ModelCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    model_artifact_id: int
    task_key: str
    intended_use: str
    limitations: str
    training_data_summary_json: dict[str, Any] = Field(default_factory=dict)
    evaluation_summary_json: dict[str, Any] = Field(default_factory=dict)
    bias_risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    out_of_domain_summary_json: dict[str, Any] = Field(default_factory=dict)
    calibration_summary_json: dict[str, Any] = Field(default_factory=dict)
    human_review_summary_json: dict[str, Any] = Field(default_factory=dict)
    approval_status: ModelCardApprovalStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    evaluation_run_id: int
    metric_name: str
    metric_value: float
    metric_unit: str | None = None
    split: ModelMetricSplit
    passed: bool | None = None
    threshold: float | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CalibrationAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_artifact_id: int = Field(ge=1)
    evaluation_run_id: int | None = Field(default=None, ge=1)
    calibration_method: CalibrationMethod = "not_assessed"
    calibration_metrics_json: dict[str, Any] = Field(default_factory=dict)
    status: CalibrationStatus = "not_assessed"
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CalibrationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    model_artifact_id: int
    evaluation_run_id: int | None = None
    calibration_method: CalibrationMethod
    calibration_metrics_json: dict[str, Any] = Field(default_factory=dict)
    status: CalibrationStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ErrorAnalysisSliceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: int = Field(ge=1)
    slice_name: str = Field(min_length=1, max_length=200)
    slice_type: ErrorAnalysisSliceType = "other"
    sample_count: int = Field(ge=0)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    representative_errors_json: list[dict[str, Any]] = Field(default_factory=list)
    severity: ErrorAnalysisSeverity = "info"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ErrorAnalysisSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    evaluation_run_id: int
    slice_name: str
    slice_type: ErrorAnalysisSliceType
    sample_count: int
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    representative_errors_json: list[dict[str, Any]] = Field(default_factory=list)
    severity: ErrorAnalysisSeverity
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OutOfDomainAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_artifact_id: int = Field(ge=1)
    dataset_version_id: int | None = Field(default=None, ge=1)
    method: OODMethod = "rule_based"
    ood_summary_json: dict[str, Any] = Field(default_factory=dict)
    high_risk_regions_json: list[dict[str, Any]] = Field(default_factory=list)
    status: OODStatus = "requires_review"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OutOfDomainAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    model_artifact_id: int
    dataset_version_id: int | None = None
    method: OODMethod
    ood_summary_json: dict[str, Any] = Field(default_factory=dict)
    high_risk_regions_json: list[dict[str, Any]] = Field(default_factory=list)
    status: OODStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeploymentCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_artifact_id: int = Field(ge=1)
    model_card_id: int | None = Field(default=None, ge=1)
    target_module: DeploymentTargetModule
    target_endpoint: str | None = Field(default=None, max_length=300)
    status: DeploymentCandidateStatus = "proposed"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeploymentCandidateApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=20_000)
    status: Literal["approved_for_internal_use", "approved_for_production"] = (
        "approved_for_internal_use"
    )
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeploymentCandidateRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeploymentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    model_artifact_id: int
    model_card_id: int | None = None
    target_module: DeploymentTargetModule
    target_endpoint: str | None = None
    status: DeploymentCandidateStatus
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DeploymentCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: int
    model_artifact_id: int
    target_module: DeploymentTargetModule
    status: DeploymentCandidateStatus
    reviewer_name: str | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PredictionServiceConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_module: DeploymentTargetModule
    service_key: str | None = Field(default=None, max_length=120)
    active_model_artifact_id: int | None = Field(default=None, ge=1)
    fallback_model_artifact_id: int | None = Field(default=None, ge=1)
    routing_rules_json: dict[str, Any] = Field(default_factory=dict)
    confidence_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    ood_rules_json: dict[str, Any] = Field(default_factory=dict)
    fallback_rules_json: dict[str, Any] = Field(default_factory=dict)
    human_review_rules_json: dict[str, Any] = Field(default_factory=dict)
    max_batch_size: int | None = Field(default=None, ge=1)
    status: PredictionServiceConfigStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionServiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    target_module: DeploymentTargetModule
    active_model_artifact_id: int | None = None
    fallback_model_artifact_id: int | None = None
    routing_rules_json: dict[str, Any] = Field(default_factory=dict)
    confidence_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    ood_rules_json: dict[str, Any] = Field(default_factory=dict)
    fallback_rules_json: dict[str, Any] = Field(default_factory=dict)
    human_review_rules_json: dict[str, Any] = Field(default_factory=dict)
    max_batch_size: int | None = None
    status: PredictionServiceConfigStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


AIServiceTargetModule = Literal[
    "spectracheck",
    "msms",
    "lcms",
    "reaction_optimization",
    "regulatory",
    "knowledge_extraction",
    "report",
    "multimodal",
]
AIServiceStatus = Literal["draft", "active", "disabled", "experimental"]
PredictionRunStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
PredictionOODStatus = Literal[
    "in_domain",
    "possible_ood",
    "out_of_domain",
    "not_assessed",
]
PredictionResultType = Literal[
    "nmr_shift_prediction",
    "nmr_candidate_ranking",
    "msms_annotation_score",
    "lcms_feature_classification",
    "reaction_outcome_prediction",
    "reaction_recommendation_score",
    "regulatory_extraction",
    "citation_support",
    "quality_score",
    "other",
]
InferenceExplanationType = Literal[
    "feature_importance",
    "matched_evidence",
    "nearest_neighbors",
    "spectral_similarity",
    "rules",
    "citation_support",
    "uncertainty",
    "ood",
    "unavailable",
]
PredictionFeedbackType = Literal[
    "accepted",
    "rejected",
    "corrected",
    "uncertain",
    "useful",
    "not_useful",
    "error_case",
    "other",
]
ActiveLearningReason = Literal[
    "low_confidence",
    "high_uncertainty",
    "out_of_domain",
    "human_correction",
    "model_disagreement",
    "benchmark_gap",
    "rare_chemistry",
    "regulatory_high_risk",
    "other",
]
ActiveLearningPriority = Literal["low", "medium", "high", "critical"]
ActiveLearningSourceModule = Literal[
    "spectracheck",
    "msms",
    "lcms",
    "reaction_optimization",
    "regulatory",
    "knowledge_extraction",
    "report",
]
ActiveLearningStatus = Literal[
    "proposed",
    "accepted",
    "rejected",
    "queued_for_dataset",
    "resolved",
]
ShadowEvaluationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
]
CanaryDeploymentStatus = Literal[
    "proposed",
    "running",
    "paused",
    "approved",
    "rejected",
    "rolled_back",
]
ModelMonitoringEventType = Literal[
    "prediction_completed",
    "low_confidence",
    "out_of_domain",
    "high_error",
    "human_rejection",
    "feedback_received",
    "drift_warning",
    "service_failure",
    "fallback_used",
    "other",
]
ModelMonitoringSeverity = Literal["info", "warning", "high", "critical"]


class AIServiceRegistryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    target_module: AIServiceTargetModule
    task_key: str = Field(min_length=1, max_length=120)
    active_model_artifact_id: int | None = Field(default=None, ge=1)
    fallback_model_artifact_id: int | None = Field(default=None, ge=1)
    prediction_service_config_id: int | None = Field(default=None, ge=1)
    status: AIServiceStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIServiceRegistryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    target_module: AIServiceTargetModule | None = None
    task_key: str | None = Field(default=None, max_length=120)
    active_model_artifact_id: int | None = Field(default=None, ge=1)
    fallback_model_artifact_id: int | None = Field(default=None, ge=1)
    prediction_service_config_id: int | None = Field(default=None, ge=1)
    status: AIServiceStatus | None = None
    metadata_json: dict[str, Any] | None = None


class AIServiceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    name: str
    target_module: AIServiceTargetModule
    task_key: str
    active_model_artifact_id: int | None = None
    fallback_model_artifact_id: int | None = None
    prediction_service_config_id: int | None = None
    status: AIServiceStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    target_module: AIServiceTargetModule
    task_key: str
    model_artifact_id: int | None = None
    deployment_candidate_id: int | None = None
    dataset_version_id: int | None = None
    request_summary_json: dict[str, Any] = Field(default_factory=dict)
    input_hash: str | None = None
    status: PredictionRunStatus
    prediction_result_id: int | None = None
    confidence_score: float | None = None
    uncertainty_json: dict[str, Any] = Field(default_factory=dict)
    ood_status: PredictionOODStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    prediction_run_id: int
    result_type: PredictionResultType
    output_json: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = None
    uncertainty_json: dict[str, Any] = Field(default_factory=dict)
    explanation_id: int | None = None
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InferenceExplanationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_run_id: int | None = Field(default=None, ge=1)
    explanation_type: InferenceExplanationType = "unavailable"
    explanation_json: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=20_000)
    warnings_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InferenceExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    prediction_run_id: int | None = None
    explanation_type: InferenceExplanationType
    explanation_json: dict[str, Any] = Field(default_factory=dict)
    summary: str
    warnings_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    dataset_version_id: int | None = Field(default=None, ge=1)
    model_artifact_id: int | None = Field(default=None, ge=1)
    request_json: dict[str, Any] = Field(default_factory=dict)
    candidate_summaries_json: list[dict[str, Any]] = Field(default_factory=list)
    requested_result_type: PredictionResultType | None = None
    experimental: bool = False
    development_mode: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_run_id: int
    service_key: str
    model_artifact_id: int | None = None
    deployment_candidate_id: int | None = None
    status: PredictionRunStatus
    result: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float | None = None
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    ood_status: PredictionOODStatus
    explanation: InferenceExplanation | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ModelRoutingDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    target_module: AIServiceTargetModule | None = None
    experimental: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelRoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    target_module: AIServiceTargetModule
    selected_model_artifact_id: int | None = None
    fallback_model_artifact_id: int | None = None
    reason: str
    routing_metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_type: PredictionFeedbackType
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=20_000)
    corrected_output_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    prediction_run_id: int
    feedback_type: PredictionFeedbackType
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    corrected_output_json: dict[str, Any] | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PredictionFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: int
    prediction_run_id: int
    feedback_type: PredictionFeedbackType
    active_learning_candidate_id: int | None = None
    model_improvement_item_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PredictionReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=20_000)
    decision: PredictionFeedbackType = "accepted"
    corrected_output_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ActiveLearningCandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_run_id: int | None = Field(default=None, ge=1)
    source_module: ActiveLearningSourceModule
    reason: ActiveLearningReason
    priority: ActiveLearningPriority = "medium"
    status: ActiveLearningStatus = "proposed"
    linked_model_improvement_item_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ActiveLearningCandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: ActiveLearningPriority | None = None
    status: ActiveLearningStatus | None = None
    linked_model_improvement_item_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] | None = None


class ActiveLearningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    prediction_run_id: int | None = None
    source_module: ActiveLearningSourceModule
    reason: ActiveLearningReason
    priority: ActiveLearningPriority
    status: ActiveLearningStatus
    linked_model_improvement_item_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ShadowEvaluationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    production_model_artifact_id: int | None = Field(default=None, ge=1)
    candidate_model_artifact_id: int = Field(ge=1)
    dataset_version_id: int | None = Field(default=None, ge=1)
    status: ShadowEvaluationStatus = "queued"
    comparison_metrics_json: dict[str, Any] = Field(default_factory=dict)
    disagreement_examples_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ShadowEvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    production_model_artifact_id: int | None = None
    candidate_model_artifact_id: int
    dataset_version_id: int | None = None
    status: ShadowEvaluationStatus
    comparison_metrics_json: dict[str, Any] = Field(default_factory=dict)
    disagreement_examples_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CanaryDeploymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    candidate_model_artifact_id: int = Field(ge=1)
    target_module: AIServiceTargetModule
    traffic_percent: float = Field(ge=0, le=100)
    status: CanaryDeploymentStatus = "proposed"
    monitoring_summary_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CanaryReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CanaryDeploymentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    candidate_model_artifact_id: int
    target_module: AIServiceTargetModule
    traffic_percent: float
    status: CanaryDeploymentStatus
    monitoring_summary_json: dict[str, Any] = Field(default_factory=dict)
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelMonitoringEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=120)
    model_artifact_id: int | None = Field(default=None, ge=1)
    event_type: ModelMonitoringEventType = "other"
    severity: ModelMonitoringSeverity = "info"
    message: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelMonitoringEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    service_key: str
    model_artifact_id: int | None = None
    event_type: ModelMonitoringEventType
    severity: ModelMonitoringSeverity
    message: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class AIModelMonitoringSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_count: int
    active_service_count: int
    prediction_count: int
    requires_review_count: int
    low_confidence_event_count: int
    ood_event_count: int
    feedback_count: int
    active_learning_candidate_count: int
    recent_events: list[ModelMonitoringEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


class PredictionAuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_run: PredictionRun
    result: PredictionResult | None = None
    feedback: list[PredictionFeedback] = Field(default_factory=list)
    active_learning_candidates: list[ActiveLearningCandidate] = Field(default_factory=list)


ProductProgramKey = Literal["spectracheck", "regulatory_hub", "reaction_optimization"]
ProductProgramStatus = Literal["active", "hidden", "deprecated"]
ModulePriorityContext = Literal[
    "global",
    "dashboard",
    "project",
    "sample",
    "report",
    "onboarding",
    "settings",
]
CrossModuleTriggerType = Literal[
    "manual",
    "spectracheck_result",
    "regulatory_action",
    "reaction_outcome",
    "report_generation",
]
CrossModuleWorkflowStatus = Literal["active", "draft", "archived"]
SpectroscopyBridgeStatus = Literal[
    "draft",
    "ready_for_review",
    "action_items_created",
    "blocked",
    "reviewed",
]
RegulatoryReactionBridgeStatus = Literal[
    "draft",
    "constraints_created",
    "ready_for_review",
    "blocked",
    "reviewed",
]
RegulatoryConstraintType = Literal[
    "impurity_limit",
    "residual_solvent_limit",
    "nitrosamine_risk_avoidance",
    "qnmr_validation_requirement",
    "ai_governance_requirement",
    "jurisdictional_requirement",
    "other",
]
CrossModuleSeverity = Literal["info", "warning", "high", "critical"]
RegulatoryConstraintStatus = Literal["draft", "active", "reviewed", "archived"]
ComplianceObjectiveStatus = Literal["draft", "active", "reviewed", "archived"]
CTDModule3BundleStatus = Literal["draft", "ready_for_review", "approved_internal", "blocked"]
CrossModuleActionType = Literal[
    "create_dossier",
    "link_evidence",
    "run_regulatory_assessment",
    "create_reaction_constraint",
    "run_reaction_optimization",
    "update_report",
    "review_required",
    "other",
]
CrossModuleActionStatus = Literal["open", "in_progress", "resolved", "dismissed", "blocked"]
CommandCenterScope = Literal[
    "global",
    "project",
    "compound",
    "batch",
    "sample",
    "session",
    "dossier",
]


class ProductProgramRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    program_key: ProductProgramKey
    display_name: str
    display_order: int
    description: str
    status: ProductProgramStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProductProgramOrderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_order_json: list[ProductProgramKey]
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModulePriorityMapPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context: ModulePriorityContext = "global"
    program_order_json: list[ProductProgramKey]
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModulePriorityMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    context: ModulePriorityContext
    program_order_json: list[ProductProgramKey]
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleWorkflowTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20_000)
    program_sequence_json: list[ProductProgramKey] = Field(default_factory=list)
    trigger_type: CrossModuleTriggerType = "manual"
    required_inputs_json: dict[str, Any] = Field(default_factory=dict)
    optional_inputs_json: dict[str, Any] = Field(default_factory=dict)
    status: CrossModuleWorkflowStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleWorkflowTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    template_key: str
    name: str
    description: str
    program_sequence_json: list[ProductProgramKey] = Field(default_factory=list)
    trigger_type: CrossModuleTriggerType
    required_inputs_json: dict[str, Any] = Field(default_factory=dict)
    optional_inputs_json: dict[str, Any] = Field(default_factory=dict)
    status: CrossModuleWorkflowStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SpectroscopyToRegulatoryBridgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spectracheck_session_id: int | None = Field(default=None, ge=1)
    evidence_item_id: int | None = Field(default=None, ge=1)
    report_id: int | None = Field(default=None, ge=1)
    dossier_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    bridge_status: SpectroscopyBridgeStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SpectroscopyToRegulatoryBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    spectracheck_session_id: int | None = None
    evidence_item_id: int | None = None
    report_id: int | None = None
    dossier_id: int | None = None
    compound_id: int | None = None
    batch_id: int | None = None
    bridge_status: SpectroscopyBridgeStatus
    extracted_regulatory_signals_json: dict[str, Any] = Field(default_factory=dict)
    created_requirement_ids_json: list[int] = Field(default_factory=list)
    created_action_item_ids_json: list[int] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryToReactionBridgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: int | None = Field(default=None, ge=1)
    regulatory_action_item_id: int | None = Field(default=None, ge=1)
    reaction_project_id: int | None = Field(default=None, ge=1)
    compound_id: int | None = Field(default=None, ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    bridge_status: RegulatoryReactionBridgeStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryToReactionBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int | None = None
    regulatory_action_item_id: int | None = None
    reaction_project_id: int | None = None
    compound_id: int | None = None
    batch_id: int | None = None
    bridge_status: RegulatoryReactionBridgeStatus
    regulatory_constraints_json: list[dict[str, Any]] = Field(default_factory=list)
    optimization_objectives_json: dict[str, Any] = Field(default_factory=dict)
    created_constraint_ids_json: list[int] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleBridgeReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str = Field(min_length=1, max_length=200)
    reviewer_comment: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryConstraintSetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier_id: int | None = Field(default=None, ge=1)
    source_action_item_ids_json: list[int] = Field(default_factory=list)
    constraint_type: RegulatoryConstraintType = "other"
    constraint_json: dict[str, Any] = Field(default_factory=dict)
    severity: CrossModuleSeverity = "warning"
    status: RegulatoryConstraintStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryConstraintSetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraint_json: dict[str, Any] | None = None
    severity: CrossModuleSeverity | None = None
    status: RegulatoryConstraintStatus | None = None
    metadata_json: dict[str, Any] | None = None


class RegulatoryConstraintSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    dossier_id: int | None = None
    source_action_item_ids_json: list[int] = Field(default_factory=list)
    constraint_type: RegulatoryConstraintType
    constraint_json: dict[str, Any] = Field(default_factory=dict)
    severity: CrossModuleSeverity
    status: RegulatoryConstraintStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ComplianceDrivenOptimizationObjectiveCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    regulatory_constraint_set_id: int | None = Field(default=None, ge=1)
    objective_json: dict[str, Any] = Field(default_factory=dict)
    scalarization_json: dict[str, Any] = Field(default_factory=dict)
    hard_constraints_json: dict[str, Any] = Field(default_factory=dict)
    soft_constraints_json: dict[str, Any] = Field(default_factory=dict)
    status: ComplianceObjectiveStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ComplianceDrivenOptimizationObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    regulatory_constraint_set_id: int | None = None
    objective_json: dict[str, Any] = Field(default_factory=dict)
    scalarization_json: dict[str, Any] = Field(default_factory=dict)
    hard_constraints_json: dict[str, Any] = Field(default_factory=dict)
    soft_constraints_json: dict[str, Any] = Field(default_factory=dict)
    status: ComplianceObjectiveStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CTDModule3ReportBundleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spectracheck_report_id: int | None = Field(default=None, ge=1)
    regulatory_readiness_report_id: int | None = Field(default=None, ge=1)
    batch_assessment_id: int | None = Field(default=None, ge=1)
    qnmr_compliance_id: int | None = Field(default=None, ge=1)
    impurity_register_id: int | None = Field(default=None, ge=1)
    ai_governance_record_id: int | None = Field(default=None, ge=1)
    report_json: dict[str, Any] = Field(default_factory=dict)
    report_html: str | None = Field(default=None, max_length=2_000_000)
    status: CTDModule3BundleStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CTDModule3ReportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int
    spectracheck_report_id: int | None = None
    regulatory_readiness_report_id: int | None = None
    batch_assessment_id: int | None = None
    qnmr_compliance_id: int | None = None
    impurity_register_id: int | None = None
    ai_governance_record_id: int | None = None
    report_json: dict[str, Any] = Field(default_factory=dict)
    report_html: str | None = None
    report_sha256: str | None = None
    status: CTDModule3BundleStatus
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleActionItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_program: ProductProgramKey
    target_program: ProductProgramKey
    source_resource_type: str = Field(min_length=1, max_length=120)
    source_resource_id: int = Field(ge=1)
    target_resource_type: str | None = Field(default=None, max_length=120)
    target_resource_id: int | None = Field(default=None, ge=1)
    action_type: CrossModuleActionType = "other"
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=40_000)
    severity: CrossModuleSeverity = "warning"
    status: CrossModuleActionStatus = "open"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleActionItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_resource_type: str | None = Field(default=None, max_length=120)
    target_resource_id: int | None = Field(default=None, ge=1)
    action_type: CrossModuleActionType | None = None
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=40_000)
    severity: CrossModuleSeverity | None = None
    status: CrossModuleActionStatus | None = None
    metadata_json: dict[str, Any] | None = None


class CrossModuleActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_program: ProductProgramKey
    target_program: ProductProgramKey
    source_resource_type: str
    source_resource_id: int
    target_resource_type: str | None = None
    target_resource_id: int | None = None
    action_type: CrossModuleActionType
    title: str
    description: str
    severity: CrossModuleSeverity
    status: CrossModuleActionStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CrossModuleCommandCenterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scope: CommandCenterScope
    scope_id: int | None = None
    spectracheck_summary_json: dict[str, Any] = Field(default_factory=dict)
    regulatory_summary_json: dict[str, Any] = Field(default_factory=dict)
    reaction_summary_json: dict[str, Any] = Field(default_factory=dict)
    open_cross_module_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


MobileDeviceType = Literal["phone", "tablet", "desktop", "unknown"]
MobileSessionStatus = Literal["active", "revoked", "expired"]
MobilePreferredHome = Literal[
    "dashboard",
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "review_queue",
]
MobileActionType = Literal[
    "review_decision",
    "evidence_comment",
    "regulatory_action_update",
    "reaction_execution_update",
    "report_review",
    "qc_override",
    "other",
]
MobileDraftStatus = Literal["draft", "queued_for_sync", "synced", "rejected", "expired"]
MobileNotificationType = Literal[
    "job_completed",
    "job_failed",
    "regulatory_action_due",
    "review_required",
    "report_ready",
    "reaction_execution_update",
    "qc_failure",
    "system_alert",
    "other",
]
MobileSeverity = Literal["info", "warning", "high", "critical"]
MobileNotificationStatus = Literal["unread", "read", "dismissed"]
MobileSummaryScope = Literal[
    "global",
    "project",
    "sample",
    "session",
    "dossier",
    "reaction_project",
    "compound",
    "batch",
]
MobileSyncItemStatus = Literal["synced", "rejected", "skipped"]


class MobileNavigationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_key: ProductProgramKey
    display_name: str
    display_order: int
    route: str


class MobileDeviceSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    device_label: str | None = Field(default=None, max_length=200)
    device_type: MobileDeviceType = "unknown"
    platform: str | None = Field(default=None, max_length=120)
    browser: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileDeviceSessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    device_label: str | None = Field(default=None, max_length=200)
    device_type: MobileDeviceType | None = None
    platform: str | None = Field(default=None, max_length=120)
    browser: str | None = Field(default=None, max_length=120)
    status: MobileSessionStatus | None = None
    metadata_json: dict[str, Any] | None = None


class MobileDeviceSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_email: EmailStr | None = None
    device_label: str | None = None
    device_type: MobileDeviceType
    platform: str | None = None
    browser: str | None = None
    last_seen_at: datetime
    status: MobileSessionStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileViewPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    device_session_id: int | None = Field(default=None, ge=1)
    preferred_home: MobilePreferredHome | None = None
    compact_mode: bool | None = None
    bottom_nav_enabled: bool | None = None
    reduce_motion: bool | None = None
    high_contrast: bool | None = None
    metadata_json: dict[str, Any] | None = None


class MobileViewPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_email: EmailStr | None = None
    device_session_id: int | None = None
    preferred_home: MobilePreferredHome
    compact_mode: bool
    bottom_nav_enabled: bool
    reduce_motion: bool
    high_contrast: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    navigation_order: list[MobileNavigationItem]
    preferred_home: MobilePreferredHome
    view_preference: MobileViewPreference
    offline_enabled: bool = True
    draft_sync_required: bool = True
    safety_rules: list[str] = Field(default_factory=list)


class MobileActionDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    device_session_id: int | None = Field(default=None, ge=1)
    action_type: MobileActionType = "other"
    target_type: str = Field(min_length=1, max_length=120)
    target_id: str = Field(min_length=1, max_length=120)
    draft_payload_json: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "queued_for_sync"] = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileActionDraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: MobileActionType | None = None
    target_type: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=120)
    draft_payload_json: dict[str, Any] | None = None
    status: MobileDraftStatus | None = None
    metadata_json: dict[str, Any] | None = None


class MobileActionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_email: EmailStr | None = None
    device_session_id: int | None = None
    action_type: MobileActionType
    target_type: str
    target_id: str
    draft_payload_json: dict[str, Any] = Field(default_factory=dict)
    status: MobileDraftStatus
    validation_warnings_json: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_session_id: int | None = Field(default=None, ge=1)
    draft_ids: list[int] = Field(default_factory=list, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileSyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    device_session_id: int | None = None
    synced_count: int
    rejected_count: int
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileSyncItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: int
    action_type: MobileActionType
    target_type: str
    target_id: str
    status: MobileSyncItemStatus
    validation_messages: list[str] = Field(default_factory=list)
    audit_event_ids: list[int] = Field(default_factory=list)


class MobileSyncResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: MobileSyncResult
    items: list[MobileSyncItemResult] = Field(default_factory=list)


class MobilePushSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    endpoint: str = Field(min_length=8, max_length=4000)
    subscription_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobilePushSubscription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_email: EmailStr | None = None
    endpoint_hash: str = Field(min_length=64, max_length=64)
    subscription_json: dict[str, Any] = Field(default_factory=dict)
    status: MobileSessionStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileNotificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: EmailStr | None = None
    notification_type: MobileNotificationType = "other"
    title: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1, max_length=4000)
    target_type: str | None = Field(default=None, max_length=120)
    target_id: str | None = Field(default=None, max_length=120)
    severity: MobileSeverity = "info"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileNotificationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: MobileNotificationStatus
    metadata_json: dict[str, Any] | None = None


class MobileNotification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_email: EmailStr | None = None
    notification_type: MobileNotificationType
    title: str
    message: str
    target_type: str | None = None
    target_id: str | None = None
    severity: MobileSeverity
    status: MobileNotificationStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompactModuleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scope: MobileSummaryScope
    scope_id: str | None = None
    spectracheck_summary_json: dict[str, Any] = Field(default_factory=dict)
    regulatory_summary_json: dict[str, Any] = Field(default_factory=dict)
    reaction_summary_json: dict[str, Any] = Field(default_factory=dict)
    action_summary_json: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MobileDashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_order: list[ProductProgramKey]
    summary: CompactModuleSummary
    compact_payload: bool = True
    generated_at: datetime
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class MobileCommandCenterSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_key: ProductProgramKey
    display_name: str
    display_order: int
    summary_json: dict[str, Any] = Field(default_factory=dict)


class MobileCommandCenterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_order: list[ProductProgramKey]
    sections: list[MobileCommandCenterSection]
    action_summary_json: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class MobileResourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: str
    target_id: str
    title: str | None = None
    status: str | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    generated_at: datetime
    compact_payload: bool = True


class MobileActionQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Literal["cross_module_action", "draft", "notification", "job"]
    title: str
    status: str
    severity: MobileSeverity = "info"
    target_type: str | None = None
    target_id: str | None = None
    action_type: str | None = None
    module_key: str | None = None
    created_at: datetime | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)


class MobileActionQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MobileActionQueueItem] = Field(default_factory=list)
    counts_json: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class MobileReportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    report_type: str
    title: str
    version: int | None = None
    created_at: datetime
    target_type: str
    target_id: str
    preview_sections: list[dict[str, Any]] = Field(default_factory=list)
    omitted_sections: list[str] = Field(default_factory=list)
    raw_appendices_included: bool = False
    compact_payload: bool = True


class MobileJobsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_count: int
    failed_count: int
    completed_count: int
    review_required_count: int
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: datetime
    compact_payload: bool = True
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class MobileOfflineSafeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offline_drafts_allowed: bool = True
    server_sync_required: bool = True
    final_decisions_offline: bool = False
    safety_rules: list[str] = Field(default_factory=list)
    draft_counts_json: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class MLModelHealthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_count: int
    active_task_count: int
    experimental_task_count: int
    feature_pipeline_count: int
    training_run_count: int
    evaluation_run_count: int
    model_artifact_count: int
    active_model_count: int
    experimental_model_count: int
    trained_model_count: int
    evaluated_model_count: int
    deployment_candidate_count: int
    approved_deployment_candidate_count: int
    deprecated_model_count: int
    active_prediction_config_count: int
    latest_training_runs: list[MLTrainingRunResponse] = Field(default_factory=list)
    latest_evaluation_runs: list[MLEvaluationRunResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


CompoundType = Literal[
    "target",
    "product",
    "starting_material",
    "reagent",
    "impurity",
    "intermediate",
    "metabolite",
    "unknown",
    "reference_standard",
    "other",
]
CompoundStatus = Literal["draft", "active", "archived", "needs_review"]
CompoundStructureFormat = Literal["smiles", "mol", "sdf", "inchi", "name_only", "unknown"]
CompoundStereochemistryStatus = Literal[
    "specified", "partial", "unspecified", "ambiguous", "unknown"
]
CompoundSaltSolventStatus = Literal["parent", "salt", "solvate", "mixture", "unknown"]
CompoundStructureSource = Literal[
    "user_entered",
    "spectracheck_candidate",
    "reaction_product",
    "regulatory_dossier",
    "imported_sdf",
    "report",
    "other",
]
CompoundStructureValidationStatus = Literal["valid", "invalid", "ambiguous", "not_checked"]
CompoundStructureReviewerStatus = Literal["unreviewed", "accepted", "rejected", "needs_changes"]
CompoundAliasType = Literal[
    "common_name",
    "iupac",
    "internal_code",
    "batch_name",
    "supplier_name",
    "registry_number",
    "other",
]
CompoundBatchSourceType = Literal[
    "synthesized",
    "purchased",
    "isolated",
    "reference_standard",
    "imported",
    "unknown",
]
CompoundBatchStatus = Literal[
    "draft", "active", "consumed", "archived", "failed_qc", "needs_review"
]
SampleAliquotStatus = Literal["available", "consumed", "archived", "unknown"]
CompoundRelationshipType = Literal[
    "parent_of",
    "salt_of",
    "solvate_of",
    "isomer_of",
    "stereoisomer_of",
    "analogue_of",
    "impurity_of",
    "metabolite_of",
    "precursor_of",
    "product_of",
    "intermediate_of",
    "duplicate_candidate",
    "other",
]
CompoundConfidenceLabel = Literal["low", "medium", "high", "requires_review"]
CompoundEvidenceResourceType = Literal[
    "spectracheck_session",
    "unified_evidence",
    "evidence_item",
    "reaction_experiment",
    "reaction_project",
    "regulatory_dossier",
    "report",
    "file",
    "artifact",
    "qc_assessment",
    "review_decision",
    "workflow_run",
    "other",
]
CompoundEvidenceLinkStatus = Literal["linked", "accepted", "rejected", "needs_review"]
KnowledgeGraphResourceId = str | int


class CompoundEntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: str | None = Field(default=None, max_length=300)
    registry_id: str | None = Field(default=None, max_length=160)
    compound_type: CompoundType = "unknown"
    status: CompoundStatus = "draft"
    original_structure_input: str | None = Field(default=None, max_length=200_000)
    original_structure_format: CompoundStructureFormat | None = None
    stereochemistry_status: CompoundStereochemistryStatus = "unknown"
    salt_solvent_status: CompoundSaltSolventStatus = "unknown"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("preferred_name", "registry_id", mode="before")
    @classmethod
    def _trim_compound_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundEntityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: str | None = Field(default=None, max_length=300)
    registry_id: str | None = Field(default=None, max_length=160)
    compound_type: CompoundType | None = None
    status: CompoundStatus | None = None
    original_structure_input: str | None = Field(default=None, max_length=200_000)
    original_structure_format: CompoundStructureFormat | None = None
    stereochemistry_status: CompoundStereochemistryStatus | None = None
    salt_solvent_status: CompoundSaltSolventStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("preferred_name", "registry_id", mode="before")
    @classmethod
    def _trim_compound_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    preferred_name: str | None = None
    registry_id: str | None = None
    compound_type: CompoundType
    status: CompoundStatus
    original_structure_input: str | None = None
    original_structure_format: CompoundStructureFormat | None = None
    canonical_smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    molecular_formula: str | None = None
    exact_mass: float | None = None
    stereochemistry_status: CompoundStereochemistryStatus
    salt_solvent_status: CompoundSaltSolventStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompoundStructureRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure_input: str = Field(min_length=1, max_length=200_000)
    structure_format: CompoundStructureFormat = "unknown"
    source: CompoundStructureSource = "user_entered"
    validation_status: CompoundStructureValidationStatus | None = None
    reviewer_status: CompoundStructureReviewerStatus = "unreviewed"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompoundStructureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    compound_id: int
    structure_input: str
    structure_format: CompoundStructureFormat
    canonical_smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    formula: str | None = None
    exact_mass: float | None = None
    source: CompoundStructureSource
    normalization_warnings_json: list[str] = Field(default_factory=list)
    validation_status: CompoundStructureValidationStatus
    reviewer_status: CompoundStructureReviewerStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompoundAliasCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1, max_length=300)
    alias_type: CompoundAliasType = "other"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("alias", mode="before")
    @classmethod
    def _trim_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundAlias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    compound_id: int
    alias: str
    alias_type: CompoundAliasType
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompoundBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound_id: int = Field(ge=1)
    batch_code: str = Field(min_length=1, max_length=160)
    lot_code: str | None = Field(default=None, max_length=160)
    source_type: CompoundBatchSourceType = "unknown"
    reaction_experiment_id: int | None = Field(default=None, ge=1)
    spectracheck_session_id: int | None = Field(default=None, ge=1)
    regulatory_dossier_id: int | None = Field(default=None, ge=1)
    amount: float | None = Field(default=None, ge=0)
    amount_unit: str | None = Field(default=None, max_length=64)
    purity_percent: float | None = Field(default=None, ge=0, le=100)
    purity_method: str | None = Field(default=None, max_length=160)
    status: CompoundBatchStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("batch_code", "lot_code", "amount_unit", "purity_method", mode="before")
    @classmethod
    def _trim_batch_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound_id: int | None = Field(default=None, ge=1)
    batch_code: str | None = Field(default=None, max_length=160)
    lot_code: str | None = Field(default=None, max_length=160)
    source_type: CompoundBatchSourceType | None = None
    reaction_experiment_id: int | None = Field(default=None, ge=1)
    spectracheck_session_id: int | None = Field(default=None, ge=1)
    regulatory_dossier_id: int | None = Field(default=None, ge=1)
    amount: float | None = Field(default=None, ge=0)
    amount_unit: str | None = Field(default=None, max_length=64)
    purity_percent: float | None = Field(default=None, ge=0, le=100)
    purity_method: str | None = Field(default=None, max_length=160)
    status: CompoundBatchStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("batch_code", "lot_code", "amount_unit", "purity_method", mode="before")
    @classmethod
    def _trim_batch_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    compound_id: int
    batch_code: str
    lot_code: str | None = None
    source_type: CompoundBatchSourceType
    reaction_experiment_id: int | None = None
    spectracheck_session_id: int | None = None
    regulatory_dossier_id: int | None = None
    amount: float | None = None
    amount_unit: str | None = None
    purity_percent: float | None = None
    purity_method: str | None = None
    status: CompoundBatchStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SampleAliquotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=160)
    aliquot_code: str | None = Field(default=None, max_length=160)
    amount: float | None = Field(default=None, ge=0)
    amount_unit: str | None = Field(default=None, max_length=64)
    storage_location: str | None = Field(default=None, max_length=300)
    status: SampleAliquotStatus = "unknown"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sample_id", "aliquot_code", "amount_unit", "storage_location", mode="before")
    @classmethod
    def _trim_aliquot_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class SampleAliquot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    batch_id: int
    sample_id: str | None = None
    aliquot_code: str | None = None
    amount: float | None = None
    amount_unit: str | None = None
    storage_location: str | None = None
    status: SampleAliquotStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompoundRelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_compound_id: int = Field(ge=1)
    relationship_type: CompoundRelationshipType = "other"
    confidence_label: CompoundConfidenceLabel = "requires_review"
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CompoundRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_compound_id: int
    target_compound_id: int
    relationship_type: CompoundRelationshipType
    confidence_label: CompoundConfidenceLabel
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompoundEvidenceLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound_id: int | None = Field(default=None, ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    sample_id: str | None = Field(default=None, max_length=160)
    resource_type: CompoundEvidenceResourceType
    resource_id: KnowledgeGraphResourceId
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=20_000)
    status: CompoundEvidenceLinkStatus = "linked"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sample_id", "title", "summary", mode="before")
    @classmethod
    def _trim_evidence_link_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _requires_registry_anchor(self) -> CompoundEvidenceLinkCreate:
        if self.compound_id is None and self.batch_id is None and not self.sample_id:
            raise ValueError("Evidence link requires compound_id, batch_id, or sample_id.")
        return self


class CompoundEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    compound_id: int | None = None
    batch_id: int | None = None
    sample_id: str | None = None
    resource_type: CompoundEvidenceResourceType
    resource_id: KnowledgeGraphResourceId
    title: str
    summary: str | None = None
    status: CompoundEvidenceLinkStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScientificKnowledgeGraphEdgeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1, max_length=64)
    source_id: KnowledgeGraphResourceId
    target_type: str = Field(min_length=1, max_length=64)
    target_id: KnowledgeGraphResourceId
    relation_type: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=300)
    confidence_label: CompoundConfidenceLabel = "requires_review"
    evidence_link_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_type", "target_type", "relation_type", "label", mode="before")
    @classmethod
    def _trim_graph_edge_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ScientificKnowledgeGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source_type: str
    source_id: KnowledgeGraphResourceId
    target_type: str
    target_id: KnowledgeGraphResourceId
    relation_type: str
    label: str | None = None
    confidence_label: CompoundConfidenceLabel
    evidence_link_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ScientificKnowledgeGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_type: str
    node_id: KnowledgeGraphResourceId
    label: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ScientificKnowledgeGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[ScientificKnowledgeGraphNode] = Field(default_factory=list)
    edges: list[ScientificKnowledgeGraphEdge] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompoundRegistrySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=300)
    alias: str | None = Field(default=None, max_length=300)
    registry_id: str | None = Field(default=None, max_length=160)
    inchikey: str | None = Field(default=None, max_length=64)
    formula: str | None = Field(default=None, max_length=120)
    exact_mass_min: float | None = Field(default=None, ge=0)
    exact_mass_max: float | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("name", "alias", "registry_id", "inchikey", "formula", mode="before")
    @classmethod
    def _trim_search_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _check_exact_mass_range(self) -> CompoundRegistrySearchRequest:
        if (
            self.exact_mass_min is not None
            and self.exact_mass_max is not None
            and self.exact_mass_min > self.exact_mass_max
        ):
            raise ValueError("exact_mass_min must be less than or equal to exact_mass_max.")
        return self


class CompoundRegistrySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compounds: list[CompoundEntity] = Field(default_factory=list)
    total: int = 0
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompoundRegistryLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compound_id: int = Field(ge=1)
    batch_id: int | None = Field(default=None, ge=1)
    sample_id: str | None = Field(default=None, max_length=160)
    title: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=20_000)
    status: CompoundEvidenceLinkStatus = "linked"
    relation_type: str | None = Field(default=None, max_length=64)
    confidence_label: CompoundConfidenceLabel = "requires_review"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sample_id", "title", "summary", "relation_type", mode="before")
    @classmethod
    def _trim_link_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class CompoundRegistryLinkResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_link: CompoundEvidenceLink
    graph_edge: ScientificKnowledgeGraphEdge
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


LCMSSourceFormat = Literal[
    "auto", "processed_peak_table", "mzML", "mzXML", "unsupported_vendor", "unknown"
]
LCMSDetectedSourceFormat = Literal[
    "processed_peak_table", "mzML", "mzXML", "unsupported_vendor", "unknown"
]
LCMSImportLabel = Literal[
    "ready_for_downstream_ms", "metadata_only", "unsupported_vendor_format", "invalid_input"
]
LCMSPolarity = Literal["positive", "negative", "unknown"]


class LCMSPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mz: float = Field(gt=0.0)
    intensity: float = Field(ge=0.0)
    relative_intensity: float = Field(ge=0.0, le=100.0)


class LCMSChromatogramPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    ms_level: int = Field(ge=1, le=2)
    retention_time_min: float | None = Field(default=None, ge=0.0)
    total_ion_current: float | None = Field(default=None, ge=0.0)
    base_peak_mz: float | None = Field(default=None, gt=0.0)
    base_peak_intensity: float | None = Field(default=None, ge=0.0)


class LCMSScanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    ms_level: int = Field(ge=1, le=2)
    retention_time_min: float | None = Field(default=None, ge=0.0)
    precursor_mz: float | None = Field(default=None, gt=0.0)
    polarity: LCMSPolarity = "unknown"
    peak_count: int = Field(ge=0)
    total_ion_current: float | None = Field(default=None, ge=0.0)
    base_peak_mz: float | None = Field(default=None, gt=0.0)
    base_peak_intensity: float | None = Field(default=None, ge=0.0)
    warnings: list[str] = Field(default_factory=list)


class LCMSImportedSpectrum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    ms_level: int = Field(ge=1, le=2)
    retention_time_min: float | None = Field(default=None, ge=0.0)
    precursor_mz: float | None = Field(default=None, gt=0.0)
    polarity: LCMSPolarity = "unknown"
    peak_count: int = Field(ge=0)
    peaks: list[LCMSPeak] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LCMSExtractedPrecursor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    precursor_mz: float = Field(gt=0.0)
    retention_time_min: float | None = Field(default=None, ge=0.0)
    peak_count: int = Field(ge=0)
    total_ion_current: float | None = Field(default=None, ge=0.0)


class LCMSImportBridgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    filename: str | None = Field(default=None, max_length=300)
    source_format: LCMSSourceFormat = "auto"
    source_text: str = Field(min_length=1, max_length=5_000_000)
    preferred_msms_precursor_mz: float | None = Field(default=None, gt=0.0)
    min_relative_intensity: float = Field(default=0.5, ge=0.0, le=100.0)
    max_ms1_peaks: int = Field(default=250, ge=1, le=5000)
    max_msms_peaks_per_spectrum: int = Field(default=250, ge=1, le=5000)
    max_peaks_per_spectrum: int = Field(default=50, ge=1, le=1000)
    max_scans_to_report: int = Field(default=250, ge=1, le=5000)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)

    @field_validator("sample_id", "compound_class", "filename", mode="before")
    @classmethod
    def _optional_trim_lcms_import(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class LCMSImportBridgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    filename: str | None = None
    source_format: LCMSDetectedSourceFormat
    file_sha256: str
    immutable_raw_data: bool = True
    label: LCMSImportLabel
    scan_count: int = Field(ge=0)
    ms1_scan_count: int = Field(ge=0)
    ms2_scan_count: int = Field(ge=0)
    chromatogram: list[LCMSChromatogramPoint] = Field(default_factory=list)
    scans: list[LCMSScanSummary] = Field(default_factory=list)
    imported_spectra: list[LCMSImportedSpectrum] = Field(default_factory=list)
    extracted_ms1_peak_count: int = Field(ge=0)
    extracted_ms1_peak_list_text: str = ""
    extracted_msms_spectrum_count: int = Field(ge=0)
    extracted_msms_peak_list_text: str = ""
    selected_msms_scan_id: str | None = None
    selected_msms_precursor_mz: float | None = Field(default=None, gt=0.0)
    primary_ms1_mz: float | None = Field(default=None, gt=0.0)
    extracted_precursors: list[LCMSExtractedPrecursor] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LCMSFeaturePurityLabel = Literal[
    "high_purity", "possible_coelution", "poor_peak_purity", "not_assessed"
]
LCMSFeatureLabel = Literal[
    "clean_feature", "possible_coelution", "weak_or_no_feature", "invalid_input"
]


class LCMSXICPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_mz: float = Field(gt=0.0)
    scan_id: str
    retention_time_min: float = Field(ge=0.0)
    intensity: float = Field(ge=0.0)
    relative_intensity: float = Field(ge=0.0, le=100.0)


class LCMSCoelutingIon(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mz: float = Field(gt=0.0)
    area: float = Field(ge=0.0)
    relative_area_percent: float = Field(ge=0.0, le=100.0)
    max_intensity: float = Field(ge=0.0)
    correlation_to_target: float | None = Field(default=None, ge=-1.0, le=1.0)


class LCMSFeaturePurityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str
    target_mz: float = Field(gt=0.0)
    apex_rt_min: float = Field(ge=0.0)
    rt_window_start_min: float = Field(ge=0.0)
    rt_window_end_min: float = Field(ge=0.0)
    purity_percent: float = Field(ge=0.0, le=100.0)
    label: LCMSFeaturePurityLabel
    top_coeluting_ions: list[LCMSCoelutingIon] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LCMSLinkedMSMSSpectrum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: str
    precursor_mz: float = Field(gt=0.0)
    retention_time_min: float | None = Field(default=None, ge=0.0)
    precursor_error_da: float
    precursor_error_ppm: float
    peak_count: int = Field(ge=0)
    total_ion_current: float | None = Field(default=None, ge=0.0)


class LCMSFeaturePeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_id: str
    target_mz: float = Field(gt=0.0)
    observed_mz: float | None = Field(default=None, gt=0.0)
    apex_rt_min: float = Field(ge=0.0)
    start_rt_min: float = Field(ge=0.0)
    end_rt_min: float = Field(ge=0.0)
    apex_intensity: float = Field(ge=0.0)
    area: float = Field(ge=0.0)
    width_min: float = Field(ge=0.0)
    scan_count: int = Field(ge=0)
    signal_to_noise: float = Field(ge=0.0)
    purity: LCMSFeaturePurityReport
    linked_msms_spectra: list[LCMSLinkedMSMSSpectrum] = Field(default_factory=list)
    label: LCMSFeatureLabel
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LCMSFeatureDetectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    filename: str | None = Field(default=None, max_length=300)
    source_format: LCMSSourceFormat = "auto"
    source_text: str = Field(min_length=1, max_length=5_000_000)
    target_mz_values: list[float] = Field(default_factory=list, max_length=100)
    target_mz_text: str | None = Field(default=None, max_length=4000)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    min_relative_feature_height: float = Field(default=5.0, ge=0.0, le=100.0)
    min_peak_height: float = Field(default=0.0, ge=0.0)
    min_scans_per_feature: int = Field(default=2, ge=1, le=100)
    smoothing_window: int = Field(default=1, ge=1, le=25)
    purity_rt_window_min: float = Field(default=0.20, ge=0.0, le=10.0)
    top_coeluting_ions: int = Field(default=5, ge=0, le=50)
    max_features: int = Field(default=20, ge=1, le=200)
    max_scans_to_report: int = Field(default=1000, ge=1, le=20000)
    max_xic_points: int = Field(default=5000, ge=1, le=200000)

    @field_validator("sample_id", "compound_class", "filename", "target_mz_text", mode="before")
    @classmethod
    def _optional_trim_lcms_feature_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("target_mz_values")
    @classmethod
    def _positive_targets(cls, value: list[float]) -> list[float]:
        for item in value:
            if item <= 0:
                raise ValueError("target_mz_values must contain only positive values.")
        return value


class LCMSFeatureDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    filename: str | None = None
    source_format: LCMSDetectedSourceFormat
    file_sha256: str
    immutable_raw_data: bool = True
    label: LCMSImportLabel
    scan_count: int = Field(ge=0)
    ms1_scan_count: int = Field(ge=0)
    ms2_scan_count: int = Field(ge=0)
    target_count: int = Field(ge=0)
    feature_count: int = Field(ge=0)
    clean_feature_count: int = Field(ge=0)
    coeluting_feature_count: int = Field(ge=0)
    weak_feature_count: int = Field(ge=0)
    best_feature: LCMSFeaturePeak | None = None
    features: list[LCMSFeaturePeak] = Field(default_factory=list)
    xic_points: list[LCMSXICPoint] = Field(default_factory=list)
    chromatogram: list[LCMSChromatogramPoint] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LCMSRunRole = Literal["sample", "blank", "qc", "reference"]
LCMSFeatureGroupLabel = Literal[
    "sample_enriched_feature",
    "sample_only_feature",
    "possible_background_feature",
    "blank_like_feature",
    "blank_only_background",
    "low_abundance_feature",
    "reference_or_qc_only",
    "invalid_input",
]
LCMSFeatureGroupingLabel = Literal[
    "ready_for_candidate_scoring",
    "review_background_before_scoring",
    "metadata_only",
    "invalid_input",
]


class LCMSFeatureGroupingRunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1, max_length=100)
    role: LCMSRunRole = "sample"
    filename: str | None = Field(default=None, max_length=300)
    source_format: LCMSSourceFormat = "auto"
    source_text: str = Field(min_length=1, max_length=5_000_000)

    @field_validator("run_id", "filename", mode="before")
    @classmethod
    def _trim_grouping_run_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class LCMSRunAlignmentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    role: LCMSRunRole
    filename: str | None = None
    source_format: LCMSDetectedSourceFormat | str
    file_sha256: str
    raw_feature_count: int = Field(ge=0)
    aligned_feature_count: int = Field(ge=0)
    rt_shift_min: float
    anchor_match_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class LCMSFeatureGroupMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    role: LCMSRunRole | str
    source_format: LCMSDetectedSourceFormat | str
    file_sha256: str
    feature_id: str
    target_mz: float = Field(gt=0.0)
    observed_mz: float = Field(gt=0.0)
    raw_apex_rt_min: float = Field(ge=0.0)
    aligned_apex_rt_min: float = Field(ge=0.0)
    rt_shift_applied_min: float
    area: float = Field(ge=0.0)
    apex_intensity: float = Field(ge=0.0)
    purity_percent: float = Field(ge=0.0, le=100.0)
    purity_label: str
    feature_label: str
    linked_msms_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class LCMSFeatureRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: str
    label: str
    partner_group_id: str
    observed_delta_mz: float = Field(ge=0.0)
    expected_delta_mz: float = Field(ge=0.0)
    rt_delta_min: float = Field(ge=0.0)
    evidence_summary: str


class LCMSFeatureGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    representative_mz: float = Field(gt=0.0)
    representative_rt_min: float = Field(ge=0.0)
    label: LCMSFeatureGroupLabel
    member_count: int = Field(ge=0)
    roles_present: list[str] = Field(default_factory=list)
    sample_area: float = Field(ge=0.0)
    blank_area: float = Field(ge=0.0)
    qc_area: float = Field(default=0.0, ge=0.0)
    reference_area: float = Field(default=0.0, ge=0.0)
    blank_ratio: float = Field(default=0.0, ge=0.0)
    blank_subtracted_area: float = Field(ge=0.0)
    members: list[LCMSFeatureGroupMember] = Field(default_factory=list)
    relationships: list[LCMSFeatureRelationship] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LCMSFeatureGroupingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    runs: list[LCMSFeatureGroupingRunInput] = Field(default_factory=list, max_length=20)
    reference_run_id: str | None = Field(default=None, max_length=100)

    target_mz_values: list[float] = Field(default_factory=list, max_length=200)
    target_mz_text: str | None = Field(default=None, max_length=8000)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    min_relative_feature_height: float = Field(default=5.0, ge=0.0, le=100.0)
    min_peak_height: float = Field(default=0.0, ge=0.0)
    min_scans_per_feature: int = Field(default=2, ge=1, le=100)
    smoothing_window: int = Field(default=1, ge=1, le=25)
    purity_rt_window_min: float = Field(default=0.20, ge=0.0, le=10.0)
    top_coeluting_ions: int = Field(default=5, ge=0, le=50)
    max_features_per_run: int = Field(default=50, ge=1, le=500)
    max_scans_to_report: int = Field(default=2000, ge=1, le=50000)
    max_xic_points: int = Field(default=5000, ge=1, le=200000)
    exclude_weak_features: bool = True

    align_retention_times: bool = True
    alignment_anchor_mz_values: list[float] = Field(default_factory=list, max_length=100)
    alignment_anchor_mz_text: str | None = Field(default=None, max_length=4000)
    group_rt_tolerance_min: float = Field(default=0.12, ge=0.0, le=10.0)
    family_rt_tolerance_min: float = Field(default=0.15, ge=0.0, le=10.0)
    rt_alignment_search_window_min: float = Field(default=1.0, ge=0.0, le=30.0)
    max_rt_shift_min: float = Field(default=2.0, ge=0.0, le=30.0)

    blank_subtraction_factor: float = Field(default=1.0, ge=0.0, le=100.0)
    blank_area_ratio_threshold: float = Field(default=0.30, ge=0.0, le=100.0)
    possible_background_ratio_threshold: float = Field(default=0.10, ge=0.0, le=100.0)
    min_blank_subtracted_area: float = Field(default=0.0, ge=0.0)
    annotate_feature_families: bool = True
    max_runs: int = Field(default=10, ge=1, le=50)
    max_groups_to_report: int = Field(default=100, ge=1, le=1000)

    @field_validator(
        "sample_id",
        "compound_class",
        "reference_run_id",
        "target_mz_text",
        "alignment_anchor_mz_text",
        mode="before",
    )
    @classmethod
    def _trim_grouping_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("target_mz_values", "alignment_anchor_mz_values")
    @classmethod
    def _positive_grouping_mz_values(cls, value: list[float]) -> list[float]:
        for item in value:
            if item <= 0:
                raise ValueError("m/z values must be positive.")
        return value


class LCMSFeatureGroupingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    run_count: int = Field(ge=0)
    reference_run_id: str
    label: LCMSFeatureGroupingLabel
    group_count: int = Field(ge=0)
    sample_enriched_group_count: int = Field(ge=0)
    background_group_count: int = Field(ge=0)
    blank_subtracted_group_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    alignment_summaries: list[LCMSRunAlignmentSummary] = Field(default_factory=list)
    groups: list[LCMSFeatureGroup] = Field(default_factory=list)
    feature_table_text: str = ""
    recommended_next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LCMSFeatureFamilyMemberRole = Literal[
    "anchor_feature",
    "isotope_m_plus_1",
    "isotope_m_plus_2",
    "isotope_m_plus_1_z2",
    "adduct_sodium",
    "adduct_potassium",
    "adduct_ammonium",
    "in_source_loss",
    "coeluting_unassigned",
]
LCMSFeatureFamilyConsensusLabel = Literal[
    "high_confidence_feature_family",
    "moderate_confidence_feature_family",
    "low_confidence_feature_family",
    "conflicting_or_background_family",
    "insufficient_family_evidence",
]
LCMSFeatureFamilyConsensusResultLabel = Literal[
    "ready_for_candidate_scoring",
    "review_conflicting_families",
    "insufficient_consensus",
    "invalid_input",
]


class LCMSFeatureFamilyRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_type: str
    label: str
    anchor_group_id: str
    partner_group_id: str
    partner_role: LCMSFeatureFamilyMemberRole | str
    observed_delta_mz: float = Field(ge=0.0)
    expected_delta_mz: float = Field(ge=0.0)
    mz_error_da: float = Field(ge=0.0)
    rt_delta_min: float = Field(ge=0.0)
    intensity_ratio_percent: float = Field(ge=0.0)
    evidence_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_summary: str


class LCMSFeatureFamilyLayerScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    label: str
    used: bool
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: str
    contradiction: bool = False
    evidence_count: int = Field(ge=0)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LCMSFeatureFamilyMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    family_role: LCMSFeatureFamilyMemberRole | str
    representative_mz: float = Field(gt=0.0)
    representative_rt_min: float = Field(ge=0.0)
    label: LCMSFeatureGroupLabel | str
    sample_area: float = Field(ge=0.0)
    blank_area: float = Field(ge=0.0)
    blank_ratio: float = Field(ge=0.0)
    blank_subtracted_area: float = Field(ge=0.0)
    member_count: int = Field(ge=0)
    linked_msms_count: int = Field(ge=0)


class LCMSFeatureFamilyConsensus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str
    anchor_group_id: str
    anchor_mz: float = Field(gt=0.0)
    anchor_rt_min: float = Field(ge=0.0)
    label: LCMSFeatureFamilyConsensusLabel
    promoted_for_candidate_scoring: bool
    consensus_score: float = Field(ge=0.0, le=1.0)
    evidence_layer_count: int = Field(ge=0)
    contradiction_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    member_count: int = Field(ge=0)
    members: list[LCMSFeatureFamilyMember] = Field(default_factory=list)
    relationships: list[LCMSFeatureFamilyRelationship] = Field(default_factory=list)
    layer_scores: list[LCMSFeatureFamilyLayerScore] = Field(default_factory=list)
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LCMSFeatureFamilyConsensusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    grouping_result: LCMSFeatureGroupingResult | None = None
    groups: list[LCMSFeatureGroup] = Field(default_factory=list, max_length=1000)
    feature_table_text: str | None = Field(default=None, max_length=2_000_000)
    anchor_group_id: str | None = Field(default=None, max_length=100)
    formula: str | None = Field(default=None, max_length=100)
    expected_anchor_adduct: str = Field(default="[M+H]+", max_length=40)

    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=20.0, gt=0.0, le=500.0)
    family_rt_tolerance_min: float = Field(default=0.15, ge=0.0, le=10.0)
    min_blank_subtracted_area: float = Field(default=0.0, ge=0.0)
    blank_area_ratio_threshold: float = Field(default=0.30, ge=0.0, le=100.0)
    possible_background_ratio_threshold: float = Field(default=0.10, ge=0.0, le=100.0)
    include_background_groups: bool = False
    require_sample_enrichment: bool = True

    score_isotope_relationships: bool = True
    score_adduct_relationships: bool = True
    score_in_source_losses: bool = True
    isotope_ratio_absolute_tolerance_percent: float = Field(default=5.0, ge=0.1, le=100.0)
    isotope_ratio_relative_tolerance: float = Field(default=0.45, ge=0.05, le=2.0)
    isotope_ratio_plausible_max_percent: float = Field(default=70.0, ge=0.1, le=200.0)
    minimum_expected_isotope_percent: float = Field(default=0.5, ge=0.0, le=100.0)
    adduct_ratio_min_percent: float = Field(default=0.5, ge=0.0, le=1000.0)
    adduct_ratio_max_percent: float = Field(default=400.0, ge=0.0, le=10000.0)
    in_source_loss_ratio_max_percent: float = Field(default=300.0, ge=0.0, le=10000.0)
    max_family_members: int = Field(default=12, ge=1, le=100)
    max_families_to_report: int = Field(default=50, ge=1, le=500)
    min_consensus_score_to_promote: float = Field(default=0.62, ge=0.0, le=1.0)

    @field_validator(
        "sample_id",
        "compound_class",
        "feature_table_text",
        "anchor_group_id",
        "formula",
        "expected_anchor_adduct",
        mode="before",
    )
    @classmethod
    def _trim_lcms_consensus_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class LCMSFeatureFamilyConsensusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    label: LCMSFeatureFamilyConsensusResultLabel
    input_group_count: int = Field(ge=0)
    family_count: int = Field(ge=0)
    promoted_family_count: int = Field(ge=0)
    conflicting_family_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    families: list[LCMSFeatureFamilyConsensus] = Field(default_factory=list)
    best_family: LCMSFeatureFamilyConsensus | None = None
    family_table_text: str = ""
    recommended_next_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LCMSCandidateFeatureFamilyLabel = Literal[
    "matches_promoted_feature_family",
    "matches_review_feature_family",
    "no_mass_match_to_consensus_family",
    "no_eligible_consensus_family",
    "candidate_invalid",
]


class LCMSCandidateFeatureFamilyMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=0)
    name: str | None = None
    role: str | None = None
    smiles: str
    formula: str | None = None
    exact_mass: float | None = None
    adduct: str
    expected_mz: float | None = Field(default=None, gt=0.0)
    best_family_id: str | None = None
    best_family_label: LCMSFeatureFamilyConsensusLabel | str | None = None
    best_family_anchor_mz: float | None = Field(default=None, gt=0.0)
    best_family_anchor_rt_min: float | None = Field(default=None, ge=0.0)
    family_consensus_score: float | None = Field(default=None, ge=0.0, le=1.0)
    mz_error_da: float | None = Field(default=None, ge=0.0)
    mz_error_ppm: float | None = None
    score: float = Field(ge=0.0, le=1.0)
    label: LCMSCandidateFeatureFamilyLabel
    promoted_family: bool = False
    contradiction: bool = False
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LCMSConsensusCandidateBridgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    compound_class: str | None = Field(default=None, max_length=64)
    candidates: list[CandidateInput] = Field(min_length=1, max_length=25)
    lcms_consensus_result: LCMSFeatureFamilyConsensusResult | None = None
    lcms_consensus_request: LCMSFeatureFamilyConsensusRequest | None = None
    lcms_family_table_text: str | None = Field(default=None, max_length=2_000_000)
    adduct: str = Field(default="[M+H]+", max_length=50)
    mz_tolerance_da: float = Field(default=0.02, gt=0.0, le=2.0)
    ppm_tolerance: float = Field(default=10.0, gt=0.0, le=500.0)
    min_family_consensus_score: float = Field(default=0.42, ge=0.0, le=1.0)
    require_promoted_family: bool = True
    selected_family_id: str | None = Field(default=None, max_length=100)

    @field_validator(
        "sample_id",
        "compound_class",
        "lcms_family_table_text",
        "adduct",
        "selected_family_id",
        mode="before",
    )
    @classmethod
    def _trim_lcms_bridge_request_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class LCMSConsensusCandidateBridgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    adduct: str
    candidate_count: int = Field(ge=0)
    family_count: int = Field(ge=0)
    eligible_family_count: int = Field(ge=0)
    promoted_family_count: int = Field(ge=0)
    best_match: LCMSCandidateFeatureFamilyMatch | None = None
    matches: list[LCMSCandidateFeatureFamilyMatch] = Field(default_factory=list)
    evidence_table_text: str = ""
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


LCMSLibraryDereplicationLabel = Literal[
    "candidate_matches_require_review",
    "metadata_only_no_identification",
    "insufficient_evidence_for_dereplication",
    "invalid_input",
]


class LCMSLibraryDereplicationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = None
    filename: str | None = None
    file_sha256: str | None = None
    adduct: str = "[M+H]+"
    label: LCMSLibraryDereplicationLabel
    status: str
    candidate_count: int = Field(ge=0)
    family_count: int = Field(ge=0)
    eligible_family_count: int = Field(ge=0)
    promoted_family_count: int = Field(ge=0)
    best_match: LCMSCandidateFeatureFamilyMatch | None = None
    matches: list[LCMSCandidateFeatureFamilyMatch] = Field(default_factory=list)
    evidence_table_text: str = ""
    evidence_summary: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class StoredAnalysisRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    label: DiagnosticLabel
    sample_id: str | None = None
    solvent: str | None = None
    smiles: str
    nmr_text: str
    expected_total_h: int
    observed_total_h: float
    confidence: float
    notes: list[str]
    parsed_peak_count: int = 0
    delta_total_h: int = 0
    job_id: int | None = None
    user_id: int | None = None
    review_status: ReviewStatus = "pending_review"
    reviewer_user_id: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    final_label: str | None = None
    hours_saved_estimate: float = 0.0


class FullStoredAnalysisRecord(StoredAnalysisRecord):
    model_config = ConfigDict(extra="forbid")

    full_report: AnalysisReport


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_project_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    user_id: int
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    sample_count: int = 0
    analysis_count: int = 0
    linked_analysis_count: int = 0


class ProjectSampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, max_length=100)
    smiles: str = Field(min_length=1, max_length=500)
    nmr_text: str = Field(min_length=3, max_length=10_000)
    solvent: str | None = Field(default=None, max_length=50)
    analysis_id: int | None = Field(default=None, ge=1)

    @field_validator("sample_id", "solvent", mode="before")
    @classmethod
    def _trim_optional_sample_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("smiles", "nmr_text", mode="before")
    @classmethod
    def _trim_required_sample_fields(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("This field cannot be empty.")
        return value


class ProjectSampleAnalysisLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: int = Field(ge=1)


class ProjectSampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    analysis_id: int | None = None
    sample_id: str | None = None
    smiles: str
    nmr_text: str
    solvent: str | None = None
    created_at: datetime
    updated_at: datetime


SpectraCheckProjectStatus = Literal["active", "archived"]
SpectraCheckSampleStatus = Literal[
    "draft",
    "analyzing",
    "review_required",
    "approved",
    "rejected",
    "archived",
]
SpectraCheckSessionStatus = Literal[
    "draft",
    "analyzing",
    "evidence_ready",
    "review_required",
    "approved",
    "blocked",
    "archived",
]
SpectraCheckReviewStatus = Literal[
    "unreviewed",
    "needs_changes",
    "approved_plausible",
    "approved_confirmed",
    "rejected",
    "deferred",
]


ProvenanceMetadataInput = dict[str, Any] | str | None


def _coerce_provenance_metadata(
    value: ProvenanceMetadataInput, *, field_name: str
) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"{field_name} must be a JSON object.") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} must be a JSON object.")
        return parsed
    raise ValueError(f"{field_name} must be a JSON object.")


def _merge_provenance_metadata_aliases(
    base: dict[str, Any] | None,
    *,
    provenance_metadata_json: ProvenanceMetadataInput = None,
    provenance_metadata: ProvenanceMetadataInput = None,
) -> tuple[dict[str, Any] | None, bool]:
    merged_provenance: dict[str, Any] = {}
    merged_provenance.update(
        _coerce_provenance_metadata(
            provenance_metadata_json,
            field_name="provenance_metadata_json",
        )
    )
    merged_provenance.update(
        _coerce_provenance_metadata(
            provenance_metadata,
            field_name="provenance_metadata",
        )
    )
    if not merged_provenance:
        return (base, False)
    output = dict(base or {})
    existing = output.get("provenance_metadata")
    if isinstance(existing, dict):
        output["provenance_metadata"] = {**existing, **merged_provenance}
    else:
        output["provenance_metadata"] = merged_provenance
    return (output, True)


class SpectraCheckProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: SpectraCheckProjectStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_project_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_project_create_provenance_metadata(self) -> SpectraCheckProjectCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SpectraCheckProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: SpectraCheckProjectStatus | None = None
    metadata_json: dict[str, Any] | None = None
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_project_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_project_update_provenance_metadata(self) -> SpectraCheckProjectUpdate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed:
            self.metadata_json = merged or {}
            self.__pydantic_fields_set__.add("metadata_json")
        return self


class SpectraCheckProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    status: SpectraCheckProjectStatus
    created_at: datetime
    updated_at: datetime
    owner_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SpectraCheckSampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=200)
    molecule_name: str | None = Field(default=None, max_length=200)
    solvent: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=10_000)
    status: SpectraCheckSampleStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator(
        "sample_id", "display_name", "molecule_name", "solvent", "notes", mode="before"
    )
    @classmethod
    def _trim_sample_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_sample_create_provenance_metadata(self) -> SpectraCheckSampleCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SpectraCheckSampleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str | None = Field(default=None, min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=200)
    molecule_name: str | None = Field(default=None, max_length=200)
    solvent: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=10_000)
    status: SpectraCheckSampleStatus | None = None
    metadata_json: dict[str, Any] | None = None
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator(
        "sample_id", "display_name", "molecule_name", "solvent", "notes", mode="before"
    )
    @classmethod
    def _trim_sample_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_sample_update_provenance_metadata(self) -> SpectraCheckSampleUpdate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed:
            self.metadata_json = merged or {}
            self.__pydantic_fields_set__.add("metadata_json")
        return self


class SpectraCheckSampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    sample_id: str
    display_name: str | None = None
    molecule_name: str | None = None
    solvent: str | None = None
    notes: str | None = None
    status: SpectraCheckSampleStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes_list: list[str] = Field(default_factory=list)


class SpectraCheckSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(ge=1)
    sample_pk: int | None = Field(default=None, ge=1)
    sample_id: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=300)
    status: SpectraCheckSessionStatus = "draft"
    shared_inputs_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("sample_id", "title", mode="before")
    @classmethod
    def _trim_session_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _requires_sample_reference(self) -> SpectraCheckSessionCreate:
        if self.sample_pk is None and not self.sample_id:
            raise ValueError("Session creation requires sample_pk or sample_id.")
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SpectraCheckSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    status: SpectraCheckSessionStatus | None = None
    shared_inputs_json: dict[str, Any] | None = None
    latest_unified_evidence_json: dict[str, Any] | None = None
    latest_report_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("title", mode="before")
    @classmethod
    def _trim_session_update_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_session_update_provenance_metadata(self) -> SpectraCheckSessionUpdate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed:
            self.metadata_json = merged or {}
            self.__pydantic_fields_set__.add("metadata_json")
        return self


class SpectraCheckSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    sample_pk: int
    sample_id: str
    title: str | None = None
    status: SpectraCheckSessionStatus
    shared_inputs_json: dict[str, Any] = Field(default_factory=dict)
    latest_unified_evidence_json: dict[str, Any] | None = None
    latest_report_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SpectraCheckEvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    source_tab: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    evidence_summary_json: list[str] = Field(default_factory=list, max_length=100)
    contradictions_json: list[str] = Field(default_factory=list, max_length=100)
    warnings_json: list[str] = Field(default_factory=list, max_length=100)
    notes_json: list[str] = Field(default_factory=list, max_length=100)
    endpoint: str | None = Field(default=None, max_length=300)
    request_preview_json: dict[str, Any] | None = None
    response_json: dict[str, Any] = Field(default_factory=dict)
    selected_for_unified: bool = False
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator(
        "layer", "title", "source_tab", "status", "label", "summary", "endpoint", mode="before"
    )
    @classmethod
    def _trim_evidence_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator(
        "evidence_summary_json", "contradictions_json", "warnings_json", "notes_json", mode="before"
    )
    @classmethod
    def _coerce_evidence_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @model_validator(mode="after")
    def _merge_evidence_create_provenance_metadata(self) -> SpectraCheckEvidenceCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.provenance_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.provenance_json = merged
        return self


class SpectraCheckEvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    source_tab: str | None = Field(default=None, min_length=1, max_length=100)
    status: str | None = Field(default=None, min_length=1, max_length=100)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str | None = Field(default=None, max_length=160)
    summary: str | None = Field(default=None, max_length=4000)
    evidence_summary_json: list[str] | None = Field(default=None, max_length=100)
    contradictions_json: list[str] | None = Field(default=None, max_length=100)
    warnings_json: list[str] | None = Field(default=None, max_length=100)
    notes_json: list[str] | None = Field(default=None, max_length=100)
    endpoint: str | None = Field(default=None, max_length=300)
    request_preview_json: dict[str, Any] | None = None
    response_json: dict[str, Any] | None = None
    selected_for_unified: bool | None = None
    provenance_json: dict[str, Any] | None = None
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator(
        "layer", "title", "source_tab", "status", "label", "summary", "endpoint", mode="before"
    )
    @classmethod
    def _trim_evidence_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator(
        "evidence_summary_json", "contradictions_json", "warnings_json", "notes_json", mode="before"
    )
    @classmethod
    def _coerce_optional_evidence_lists(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        return SpectraCheckEvidenceCreate._coerce_evidence_lists(value)

    @model_validator(mode="after")
    def _merge_evidence_update_provenance_metadata(self) -> SpectraCheckEvidenceUpdate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.provenance_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed:
            self.provenance_json = merged or {}
            self.__pydantic_fields_set__.add("provenance_json")
        return self


class SpectraCheckEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    layer: str
    title: str
    source_tab: str
    status: str
    score: float | None = None
    label: str | None = None
    summary: str | None = None
    evidence_summary_json: list[str] = Field(default_factory=list)
    contradictions_json: list[str] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    request_preview_json: dict[str, Any] | None = None
    response_json: dict[str, Any] = Field(default_factory=dict)
    selected_for_unified: bool
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    created_at: datetime
    updated_at: datetime


class SpectraCheckUnifiedEvidenceSave(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    unified_evidence_json: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("unified_evidence_json", "latest_unified_evidence_json"),
    )
    status: SpectraCheckSessionStatus = "evidence_ready"
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] | None = None
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _merge_unified_save_provenance_metadata(self) -> SpectraCheckUnifiedEvidenceSave:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed:
            self.metadata_json = merged or {}
            self.__pydantic_fields_set__.add("metadata_json")
        return self


class SpectraCheckUnifiedEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    latest_unified_evidence_json: dict[str, Any] | None = None
    status: SpectraCheckSessionStatus
    updated_at: datetime
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SpectraCheckReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SpectraCheckReviewStatus
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=10_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("reviewer_name", "reviewer_comment", mode="before")
    @classmethod
    def _trim_review_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_review_create_provenance_metadata(self) -> SpectraCheckReviewCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SpectraCheckReviewDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    status: SpectraCheckReviewStatus
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SpectraCheckAuditEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    event_type: str
    message: str
    actor_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SpectraCheckReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_title: str = Field(min_length=1, max_length=300)
    status: str = Field(default="draft_requires_review", min_length=1, max_length=64)
    report_json: dict[str, Any] = Field(default_factory=dict)
    report_html: str | None = Field(default=None, max_length=2_000_000)
    report_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("report_title", "status", "report_html", "report_sha256", mode="before")
    @classmethod
    def _trim_report_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_report_create_provenance_metadata(self) -> SpectraCheckReportCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SpectraCheckReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    report_title: str
    status: str
    report_json: dict[str, Any] = Field(default_factory=dict)
    report_html: str | None = None
    report_sha256: str | None = None
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


FileStorageBackend = Literal["local", "s3", "other"]
ManagedFileKind = Literal[
    "processed_nmr",
    "raw_fid",
    "nmr2d_peak_table",
    "dept_apt_peak_table",
    "ms_peak_table",
    "msms_spectrum",
    "ms_raw",
    "lcms_mzml",
    "lcms_mzxml",
    "lcms_raw",
    "lcms_peak_table",
    "spectrum_table",
    "spectrum_jcamp",
    "spectrum_vendor",
    "spectrum_archive",
    "report",
    "other",
]
SessionFileRole = Literal[
    "processed_1h",
    "processed_13c",
    "raw_fid_1h",
    "raw_fid_13c",
    "nmr2d",
    "dept_apt",
    "ms1",
    "msms",
    "lcms",
    "spectrum_reference",
    "report_source",
    "other",
]
AnalysisJobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
ArtifactType = Literal[
    "spectrum_preview",
    "peak_table",
    "processed_spectrum",
    "nmr_metadata",
    "nmr_2d",
    "msms_annotation",
    "fragmentation_tree",
    "msms_fragmentation_tree",
    "lcms_import",
    "lcms_feature_detection",
    "lcms_feature_grouping",
    "lcms_feature_family_consensus",
    "lcms_feature_table",
    "unified_evidence",
    "report_json",
    "report_html",
    "job_artifact",
    "other",
]


class FileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    file_id: int
    filename: str
    original_filename: str
    content_type: str | None = None
    file_size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    storage_backend: FileStorageBackend
    storage_key: str
    file_kind: ManagedFileKind
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SessionFileLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: int = Field(ge=1)
    role: SessionFileRole = "other"
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _merge_session_file_link_provenance_metadata(self) -> SessionFileLinkCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class SessionFileLinkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    file_id: int
    role: SessionFileRole
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    file: FileRecord | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalysisJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int | None = Field(default=None, ge=1)
    sample_id: str | None = Field(default=None, max_length=100)
    project_id: int | None = Field(default=None, ge=1)
    job_type: str = Field(min_length=1, max_length=100)
    input_file_ids_json: list[int] = Field(default_factory=list, max_length=100)
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    provenance_metadata_json: ProvenanceMetadataInput = Field(default=None, exclude=True)
    provenance_metadata: ProvenanceMetadataInput = Field(default=None, exclude=True)

    @field_validator("sample_id", "job_type", mode="before")
    @classmethod
    def _trim_job_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _merge_job_create_provenance_metadata(self) -> AnalysisJobCreate:
        merged, changed = _merge_provenance_metadata_aliases(
            self.metadata_json,
            provenance_metadata_json=self.provenance_metadata_json,
            provenance_metadata=self.provenance_metadata,
        )
        if changed and merged is not None:
            self.metadata_json = merged
        return self


class AnalysisJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    job_id: int
    session_id: int | None = None
    sample_id: str | None = None
    project_id: int | None = None
    job_type: str
    status: AnalysisJobStatus
    progress_percent: float = Field(ge=0.0, le=100.0)
    current_step: str | None = None
    input_file_ids_json: list[int] = Field(default_factory=list)
    parameters_json: dict[str, Any] = Field(default_factory=dict)
    result_json: dict[str, Any] | None = None
    error_message: str | None = None
    artifact_ids: list[int] = Field(default_factory=list)
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class JobEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    job_id: int
    event_type: str
    message: str
    progress_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    artifact_id: int
    job_id: int | None = None
    session_id: int | None = None
    artifact_type: ArtifactType
    title: str
    content_type: str
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    storage_key: str | None = None
    download_url: str | None = None
    artifact_json: dict[str, Any] | None = None
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


VisualizationViewerType = Literal[
    "spectrum_1d",
    "nmr_2d",
    "msms_mirror",
    "chromatogram",
    "fragmentation_tree",
    "table",
    "metadata",
    "json",
]


class Spectrum1DVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: list[float] = Field(default_factory=list)
    y: list[float] = Field(default_factory=list)
    x_label: str = "ppm"
    y_label: str = "intensity"
    reversed_x_axis: bool = True
    peaks: list[dict[str, Any]] | None = None
    overlays: list[dict[str, Any]] | None = None


class NMR2DVisualizationPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    f2_ppm: float
    f1_ppm: float
    intensity: float | None = None
    label: str | None = None
    status: str | None = None


class NMR2DVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    peaks: list[NMR2DVisualizationPeak] = Field(default_factory=list)
    experiment: str = "UNKNOWN"


class MSMSMirrorPeak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mz: float
    intensity: float
    label: str | None = None


class MSMSMirrorVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_peaks: list[MSMSMirrorPeak] = Field(default_factory=list)
    reference_peaks: list[MSMSMirrorPeak] | None = None
    fragment_matches: list[dict[str, Any]] | None = None
    precursor_mz: float | None = None
    adduct: str | None = None


class ChromatogramTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rt: list[float] = Field(default_factory=list)
    intensity: list[float] = Field(default_factory=list)
    type: str
    mz: float | None = None


class ChromatogramVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    traces: list[ChromatogramTrace] = Field(default_factory=list)
    features: list[dict[str, Any]] | None = None


class FragmentationTreeVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    diagnostic_hits: list[Any] | None = None
    contradictions: list[Any] | None = None


class TableVisualizationData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str | dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any] | list[Any]] = Field(default_factory=list)


VisualizationData = (
    Spectrum1DVisualizationData
    | NMR2DVisualizationData
    | MSMSMirrorVisualizationData
    | ChromatogramVisualizationData
    | FragmentationTreeVisualizationData
    | TableVisualizationData
    | dict[str, Any]
)


class VisualizationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: int | str | None = None
    artifact_type: str
    title: str
    viewer_type: VisualizationViewerType
    data: VisualizationData
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualizationNormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: int | str | None = None
    artifact_type: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=300)
    artifact_json: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


CollaborationRole = Literal["owner", "admin", "scientist", "reviewer", "viewer"]
TeamMemberStatus = Literal["active", "invited", "disabled"]
SessionReviewerStatus = Literal["assigned", "in_review", "completed", "removed"]
EvidenceCommentType = Literal["note", "question", "concern", "contradiction", "approval_note"]
ReviewTaskStatus = Literal["open", "in_progress", "resolved", "dismissed"]
ReviewTaskPriority = Literal["low", "medium", "high", "critical"]
ApprovalDecision = Literal[
    "approved_plausible",
    "approved_confirmed",
    "rejected",
    "needs_changes",
    "deferred",
]
ReportLockStatus = Literal["unlocked", "locked", "released"]
SecureSharePermission = Literal["view", "comment", "review"]


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        value = str(value).strip()
        if not value:
            raise ValueError("Organization name cannot be empty.")
        return value


class OrganizationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TeamMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: str = Field(min_length=3, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    role: CollaborationRole
    status: TeamMemberStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_email", "display_name", mode="before")
    @classmethod
    def _trim_member_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class TeamMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    role: CollaborationRole | None = None
    status: TeamMemberStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def _trim_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class TeamMemberRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    organization_id: int
    user_email: str
    display_name: str | None = None
    role: CollaborationRole
    status: TeamMemberStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProjectPermissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: str = Field(min_length=3, max_length=255)
    role: CollaborationRole
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_email", mode="before")
    @classmethod
    def _normalize_permission_email(cls, value: str) -> str:
        value = str(value).strip().lower()
        if not value:
            raise ValueError("user_email cannot be empty.")
        return value


class ProjectPermissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: CollaborationRole | None = None
    metadata_json: dict[str, Any] | None = None


class ProjectPermissionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int
    user_email: str
    role: CollaborationRole
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SessionReviewerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_email: str = Field(min_length=3, max_length=255)
    assigned_by: str | None = Field(default=None, max_length=255)
    status: SessionReviewerStatus = "assigned"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_email", "assigned_by", mode="before")
    @classmethod
    def _trim_reviewer_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class SessionReviewerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SessionReviewerStatus | None = None
    metadata_json: dict[str, Any] | None = None


class SessionReviewerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    reviewer_email: str
    assigned_by: str | None = None
    status: SessionReviewerStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvidenceCommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: int | None = Field(default=None, ge=1)
    artifact_id: int | None = Field(default=None, ge=1)
    author_email: str | None = Field(default=None, max_length=255)
    comment: str = Field(min_length=1, max_length=20_000)
    comment_type: EvidenceCommentType = "note"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("author_email", "comment", mode="before")
    @classmethod
    def _trim_comment_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class EvidenceCommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, min_length=1, max_length=20_000)
    comment_type: EvidenceCommentType | None = None
    resolved: bool | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("comment", mode="before")
    @classmethod
    def _trim_updated_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class EvidenceCommentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    evidence_id: int | None = None
    artifact_id: int | None = None
    author_email: str | None = None
    comment: str
    comment_type: EvidenceCommentType
    resolved: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReviewTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    assigned_to: str | None = Field(default=None, max_length=255)
    status: ReviewTaskStatus = "open"
    priority: ReviewTaskPriority = "medium"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "assigned_to", mode="before")
    @classmethod
    def _trim_task_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class ReviewTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    assigned_to: str | None = Field(default=None, max_length=255)
    status: ReviewTaskStatus | None = None
    priority: ReviewTaskPriority | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "description", "assigned_to", mode="before")
    @classmethod
    def _trim_updated_task_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class ReviewTaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    title: str
    description: str | None = None
    assigned_to: str | None = None
    status: ReviewTaskStatus
    priority: ReviewTaskPriority
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ApprovalRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: int | None = Field(default=None, ge=1)
    report_id: int | None = Field(default=None, ge=1)
    approver_email: str | None = Field(default=None, max_length=255)
    decision: ApprovalDecision
    rationale: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("approver_email", "rationale", mode="before")
    @classmethod
    def _trim_approval_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    session_id: int
    evidence_id: int | None = None
    report_id: int | None = None
    approver_email: str | None = None
    decision: ApprovalDecision
    rationale: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int | None = Field(default=None, ge=1)
    locked_by: str | None = Field(default=None, max_length=255)
    lock_reason: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("locked_by", "lock_reason", mode="before")
    @classmethod
    def _trim_lock_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value.lower() if "@" in value else value or None


class ReportReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    override_approval_requirement: bool = False
    rationale: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rationale", mode="before")
    @classmethod
    def _trim_release_rationale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReportLock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    report_id: int
    session_id: int
    locked_by: str | None = None
    lock_reason: str | None = None
    status: ReportLockStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class SecureShareLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = Field(default=None, ge=1)
    session_id: int | None = Field(default=None, ge=1)
    report_id: int | None = Field(default=None, ge=1)
    permission: SecureSharePermission = "view"
    expires_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _requires_share_target(self) -> SecureShareLinkCreate:
        if self.project_id is None and self.session_id is None and self.report_id is None:
            raise ValueError("A share link requires project_id, session_id, or report_id.")
        return self


class SecureShareLinkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int | None = None
    session_id: int | None = None
    report_id: int | None = None
    token_hash: str
    permission: SecureSharePermission
    expires_at: datetime | None = None
    revoked: bool
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    token: str | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


MethodCategory = Literal[
    "nmr",
    "ms",
    "lcms",
    "unified_confidence",
    "report",
    "qc",
    "reaction",
    "regulatory",
    "workflow",
]
MethodRegistryStatus = Literal["active", "deprecated", "experimental", "disabled"]
ModelFamily = Literal["heuristic", "ml", "dft", "rules", "external", "hybrid"]
ProfileStatus = Literal["active", "deprecated", "experimental"]
ThresholdCategory = Literal["qc", "nmr", "ms", "lcms", "report", "unified_confidence"]
BenchmarkCategory = Literal["nmr", "ms", "lcms", "unified_confidence", "qc", "report"]
ValidationRunStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
DriftSeverity = Literal["info", "warning", "error", "critical"]
DriftAlertStatus = Literal["open", "acknowledged", "resolved"]
MethodComparisonStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]


def _normalize_registry_slug(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "-")
    normalized = "".join(ch for ch in normalized if ch.isalnum() or ch in {"-", "_"})
    if not normalized:
        raise ValueError("slug cannot be empty.")
    return normalized


class MethodRegistryEntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160)
    category: MethodCategory
    version: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=20_000)
    implementation_module: str | None = Field(default=None, max_length=255)
    endpoint_paths_json: list[str] = Field(default_factory=list, max_length=200)
    default_scoring_profile_id: int | None = Field(default=None, ge=1)
    default_threshold_profile_id: int | None = Field(default=None, ge=1)
    status: MethodRegistryStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "version", "description", "implementation_module", mode="before")
    @classmethod
    def _trim_method_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        return _normalize_registry_slug(value)


class MethodRegistryEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=160)
    category: MethodCategory | None = None
    version: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1, max_length=20_000)
    implementation_module: str | None = Field(default=None, max_length=255)
    endpoint_paths_json: list[str] | None = Field(default=None, max_length=200)
    default_scoring_profile_id: int | None = Field(default=None, ge=1)
    default_threshold_profile_id: int | None = Field(default=None, ge=1)
    status: MethodRegistryStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_registry_slug(value)


class MethodRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    category: MethodCategory
    version: str
    description: str
    implementation_module: str | None = None
    endpoint_paths_json: list[str] = Field(default_factory=list)
    default_scoring_profile_id: int | None = None
    default_threshold_profile_id: int | None = None
    status: MethodRegistryStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ModelVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: int | None = Field(default=None, ge=1)
    model_name: str = Field(min_length=1, max_length=200)
    model_family: ModelFamily
    version: str = Field(min_length=1, max_length=64)
    training_data_summary: str | None = Field(default=None, max_length=20_000)
    validation_summary: str | None = Field(default=None, max_length=20_000)
    model_hash: str | None = Field(default=None, max_length=128)
    artifact_uri: str | None = Field(default=None, max_length=2000)
    status: MethodRegistryStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ModelVersionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: int | None = Field(default=None, ge=1)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_family: ModelFamily | None = None
    version: str | None = Field(default=None, min_length=1, max_length=64)
    training_data_summary: str | None = Field(default=None, max_length=20_000)
    validation_summary: str | None = Field(default=None, max_length=20_000)
    model_hash: str | None = Field(default=None, max_length=128)
    artifact_uri: str | None = Field(default=None, max_length=2000)
    status: MethodRegistryStatus | None = None
    metadata_json: dict[str, Any] | None = None


class ModelVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    method_id: int | None = None
    model_name: str
    model_family: ModelFamily
    version: str
    training_data_summary: str | None = None
    validation_summary: str | None = None
    model_hash: str | None = None
    artifact_uri: str | None = None
    status: MethodRegistryStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScoringProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    method_id: int | None = Field(default=None, ge=1)
    weights_json: dict[str, Any] = Field(default_factory=dict)
    scoring_rules_json: dict[str, Any] = Field(default_factory=dict)
    label_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=20_000)
    status: ProfileStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        return _normalize_registry_slug(value)


class ScoringProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=160)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    method_id: int | None = Field(default=None, ge=1)
    weights_json: dict[str, Any] | None = None
    scoring_rules_json: dict[str, Any] | None = None
    label_thresholds_json: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=20_000)
    status: ProfileStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_registry_slug(value)


class ScoringProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    version: str
    method_id: int | None = None
    weights_json: dict[str, Any] = Field(default_factory=dict)
    scoring_rules_json: dict[str, Any] = Field(default_factory=dict)
    label_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    status: ProfileStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ThresholdProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    category: ThresholdCategory
    thresholds_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=20_000)
    status: ProfileStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        return _normalize_registry_slug(value)


class ThresholdProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=160)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    category: ThresholdCategory | None = None
    thresholds_json: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=20_000)
    status: ProfileStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_registry_slug(value)


class ThresholdProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    version: str
    category: ThresholdCategory
    thresholds_json: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    status: ProfileStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BenchmarkDatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)
    category: BenchmarkCategory
    description: str = Field(min_length=1, max_length=20_000)
    dataset_hash: str | None = Field(default=None, max_length=128)
    sample_count: int | None = Field(default=None, ge=0)
    ground_truth_summary: str | None = Field(default=None, max_length=20_000)
    data_uri: str | None = Field(default=None, max_length=2000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("slug", mode="before")
    @classmethod
    def _normalize_slug(cls, value: str) -> str:
        return _normalize_registry_slug(value)


class BenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    version: str
    category: BenchmarkCategory
    description: str
    dataset_hash: str | None = None
    sample_count: int | None = None
    ground_truth_summary: str | None = None
    data_uri: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ValidationMetricCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str = Field(min_length=1, max_length=160)
    metric_value: float
    metric_unit: str | None = Field(default=None, max_length=64)
    target_value: float | None = None
    passed: bool | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DriftAlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    severity: DriftSeverity = "warning"
    title: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=20_000)
    metric_name: str | None = Field(default=None, max_length=160)
    baseline_value: float | None = None
    current_value: float | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)
    benchmark_dataset_id: int | None = Field(default=None, ge=1)
    status: ValidationRunStatus = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metrics: list[ValidationMetricCreate] = Field(default_factory=list)
    drift_alerts: list[DriftAlertCreate] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_run_id: int
    metric_name: str
    metric_value: float
    metric_unit: str | None = None
    target_value: float | None = None
    passed: bool | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    benchmark_dataset_id: int | None = None
    status: ValidationRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metrics: list[ValidationMetric] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DriftAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    method_id: int | None = None
    model_version_id: int | None = None
    severity: DriftSeverity
    title: str
    message: str
    metric_name: str | None = None
    baseline_value: float | None = None
    current_value: float | None = None
    status: DriftAlertStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MethodComparisonRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_method_id: int | None = Field(default=None, ge=1)
    candidate_method_id: int | None = Field(default=None, ge=1)
    benchmark_dataset_id: int | None = Field(default=None, ge=1)
    status: MethodComparisonStatus = "queued"
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    winner: str | None = Field(default=None, max_length=160)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MethodComparisonRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    baseline_method_id: int | None = None
    candidate_method_id: int | None = None
    benchmark_dataset_id: int | None = None
    status: MethodComparisonStatus
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    winner: str | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ModelHealthSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_count: int
    active_method_count: int
    model_version_count: int
    validation_run_count: int
    open_drift_alert_count: int
    latest_validation_runs: list[ValidationRun] = Field(default_factory=list)
    drift_alerts: list[DriftAlert] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


DependencyStatus = Literal["ok", "warning", "error", "unknown"]
SystemHealthStatus = Literal["healthy", "degraded", "unhealthy"]
SecurityEventType = Literal[
    "login_success",
    "login_failure",
    "permission_denied",
    "token_error",
    "suspicious_request",
    "rate_limit",
    "admin_action",
    "share_link_created",
    "share_link_revoked",
    "report_released",
    "other",
]
SecuritySeverity = Literal["info", "warning", "error", "critical"]
DebugBundleScope = Literal["system", "project", "sample", "session", "job", "report"]
DebugBundleStatus = Literal["created", "failed"]


class DependencyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: DependencyStatus
    latency_ms: float | None = None
    message: str | None = None
    metadata_json: dict[str, Any] | None = None


class SystemHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SystemHealthStatus
    timestamp: datetime
    backend_version: str
    environment: str
    uptime_seconds: float | None = None
    checks: list[DependencyCheck] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SystemHealthStatus
    backend_version: str
    api_version: str | None = None
    database_status: DependencyStatus
    storage_status: DependencyStatus
    job_queue_status: DependencyStatus
    worker_status: DependencyStatus
    openapi_available: bool
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


class EnvironmentCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    required_variables_present: bool
    missing_variables: list[str] = Field(default_factory=list)
    unsafe_variables: list[str] = Field(default_factory=list)
    public_variables: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    unit: str | None = None
    status: str | None = None
    metadata_json: dict[str, Any] | None = None


class SecurityEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: SecurityEventType = "other"
    severity: SecuritySeverity = "info"
    actor_email: str | None = Field(default=None, max_length=255)
    ip_address: str | None = Field(default=None, max_length=100)
    user_agent: str | None = Field(default=None, max_length=500)
    resource_type: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=100)
    message: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "actor_email",
        "ip_address",
        "user_agent",
        "resource_type",
        "resource_id",
        "message",
        mode="before",
    )
    @classmethod
    def _trim_security_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class SecurityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    event_type: SecurityEventType
    severity: SecuritySeverity
    actor_email: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    message: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SecuritySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_events: int
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    counts_by_severity: dict[str, int] = Field(default_factory=dict)
    open_warnings: int = 0
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DebugBundleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    scope: DebugBundleScope = "system"
    resource_id: str | None = Field(default=None, max_length=100)
    include_recent_audit_events: bool = True
    include_file_hashes: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DebugBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    scope: DebugBundleScope
    resource_id: str | None = None
    status: DebugBundleStatus
    bundle_sha256: str | None = None
    storage_key: str | None = None
    created_at: datetime
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


UsageEventStatus = Literal["started", "succeeded", "failed", "canceled", "warning"]
UsageEventSource = Literal["frontend", "backend", "worker", "system"]
AutomationTaskCategory = Literal[
    "nmr",
    "ms",
    "lcms",
    "workflow",
    "qc",
    "report",
    "review",
    "regulatory",
    "reaction",
    "system",
]
RoiScope = Literal["global", "project", "session", "user"]
FeedbackType = Literal[
    "useful",
    "not_useful",
    "confusing",
    "bug",
    "feature_request",
    "other",
]
RenewalValueScope = Literal["global", "project", "organization"]


class UsageEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=100)
    project_id: int | None = None
    sample_id: str | None = Field(default=None, max_length=100)
    session_id: int | None = None
    workflow_run_id: int | None = None
    job_id: int | None = None
    artifact_id: int | None = None
    report_id: int | None = None
    user_email: str | None = Field(default=None, max_length=255)
    status: UsageEventStatus | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    estimated_minutes_saved: float | None = Field(default=None, ge=0)
    event_source: UsageEventSource = "backend"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type", "sample_id", "user_email", mode="before")
    @classmethod
    def _trim_usage_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class UsageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    event_type: str
    project_id: int | None = None
    sample_id: str | None = None
    session_id: int | None = None
    workflow_run_id: int | None = None
    job_id: int | None = None
    artifact_id: int | None = None
    report_id: int | None = None
    user_email: str | None = None
    status: UsageEventStatus | None = None
    duration_seconds: float | None = None
    estimated_minutes_saved: float | None = None
    event_source: UsageEventSource
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AutomationTaskDefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=240)
    category: AutomationTaskCategory
    default_minutes_saved: float = Field(ge=0)
    description: str = Field(min_length=1, max_length=10_000)
    enabled: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_key", "name", "description", mode="before")
    @classmethod
    def _trim_task_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class AutomationTaskDefinitionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=240)
    category: AutomationTaskCategory | None = None
    default_minutes_saved: float | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=10_000)
    enabled: bool | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_task_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class AutomationTaskDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    task_key: str
    name: str
    category: AutomationTaskCategory
    default_minutes_saved: float
    description: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AutomationRunMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    task_key: str
    project_id: int | None = None
    session_id: int | None = None
    workflow_run_id: int | None = None
    job_id: int | None = None
    status: str
    minutes_saved: float
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RoiSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scope: RoiScope
    scope_id: str | None = None
    period_start: datetime
    period_end: datetime
    tasks_automated: int
    total_minutes_saved: float
    total_hours_saved: float
    reports_generated: int
    workflows_completed: int
    analyses_completed: int
    review_tasks_completed: int
    failed_jobs: int
    qc_warnings: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


class AnalyticsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_events: int
    tasks_automated: int
    total_minutes_saved: float
    total_hours_saved: float
    reports_generated: int
    workflows_completed: int
    analyses_completed: int
    failed_jobs: int
    qc_warnings: int
    counts_by_event_type: dict[str, int] = Field(default_factory=dict)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    data_mode: DataMode = "live"
    last_synced_at: datetime | None = None
    generated_at: datetime = Field(default_factory=generated_at_utc)


class WorkflowAnalyticsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflows_started: int
    workflows_completed: int
    workflows_failed: int
    total_minutes_saved: float
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserFeedbackEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None = None
    session_id: int | None = None
    user_email: str | None = Field(default=None, max_length=255)
    feedback_type: FeedbackType
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=5_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_email", "comment", mode="before")
    @classmethod
    def _trim_feedback_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class UserFeedbackEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    project_id: int | None = None
    session_id: int | None = None
    user_email: str | None = None
    feedback_type: FeedbackType
    rating: int | None = None
    comment: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RenewalValueReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: RenewalValueScope = "global"
    scope_id: str | None = Field(default=None, max_length=100)
    period_start: datetime | None = None
    period_end: datetime | None = None
    title: str | None = Field(default=None, max_length=300)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scope_id", "title", mode="before")
    @classmethod
    def _trim_renewal_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class RenewalValueReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scope: RenewalValueScope
    scope_id: str | None = None
    period_start: datetime
    period_end: datetime
    title: str
    summary_json: dict[str, Any] = Field(default_factory=dict)
    report_json: dict[str, Any] = Field(default_factory=dict)
    report_html: str | None = None
    report_sha256: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


ReactionObjective = Literal[
    "maximize_yield",
    "maximize_selectivity",
    "minimize_impurity",
    "maximize_conversion",
    "multi_objective",
    "custom",
]
ReactionProjectStatus = Literal["draft", "active", "paused", "completed", "archived"]
ReactionVariableType = Literal["categorical", "numeric", "boolean", "text"]
ReactionExperimentStatus = Literal["planned", "running", "completed", "failed", "excluded"]
ReactionOptimizationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
]
ReactionOptimizationModelType = Literal[
    "rule_based",
    "response_surface",
    "random_forest_placeholder",
    "bayesian_placeholder",
]
ReactionRecommendationLabel = Literal[
    "recommended_next_experiment",
    "promising_condition",
    "exploratory_condition",
    "control_condition",
    "high_expected_improvement",
    "exploratory_candidate",
    "cost_efficient_candidate",
    "safety_blocked",
    "requires_human_review",
    "insufficient_data",
]
ReactionRecommendationStatus = Literal[
    "proposed",
    "approved",
    "rejected",
    "scheduled",
    "completed",
]


class ReactionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yield_percent: float | None = Field(default=None, ge=0, le=100)
    conversion_percent: float | None = Field(default=None, ge=0, le=100)
    selectivity_percent: float | None = Field(default=None, ge=0, le=100)
    impurity_percent: float | None = Field(default=None, ge=0, le=100)
    isolated_yield_percent: float | None = Field(default=None, ge=0, le=100)
    lcms_area_percent: float | None = Field(default=None, ge=0, le=100)
    nmr_purity_percent: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=10_000)


class ReactionProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=20_000)
    objective: ReactionObjective = "maximize_yield"
    status: ReactionProjectStatus = "draft"
    target_product_name: str | None = Field(default=None, max_length=240)
    target_product_smiles: str | None = Field(default=None, max_length=10_000)
    owner_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "name",
        "description",
        "target_product_name",
        "target_product_smiles",
        mode="before",
    )
    @classmethod
    def _trim_reaction_project_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=240)
    description: str | None = Field(default=None, max_length=20_000)
    objective: ReactionObjective | None = None
    status: ReactionProjectStatus | None = None
    target_product_name: str | None = Field(default=None, max_length=240)
    target_product_smiles: str | None = Field(default=None, max_length=10_000)
    metadata_json: dict[str, Any] | None = None

    @field_validator(
        "name",
        "description",
        "target_product_name",
        "target_product_smiles",
        mode="before",
    )
    @classmethod
    def _trim_reaction_project_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    description: str | None = None
    objective: ReactionObjective
    status: ReactionProjectStatus
    target_product_name: str | None = None
    target_product_smiles: str | None = None
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionVariableCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    variable_type: ReactionVariableType
    unit: str | None = Field(default=None, max_length=80)
    allowed_values_json: list[Any] | dict[str, Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    default_value: Any | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "unit", mode="before")
    @classmethod
    def _trim_reaction_variable_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionVariableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=160)
    variable_type: ReactionVariableType | None = None
    unit: str | None = Field(default=None, max_length=80)
    allowed_values_json: list[Any] | dict[str, Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    default_value: Any | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("name", "unit", mode="before")
    @classmethod
    def _trim_reaction_variable_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    name: str
    variable_type: ReactionVariableType
    unit: str | None = None
    allowed_values_json: list[Any] | dict[str, Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    default_value: Any | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_code: str = Field(min_length=1, max_length=120)
    status: ReactionExperimentStatus = "planned"
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    outcome_json: dict[str, Any] = Field(default_factory=dict)
    linked_spectracheck_session_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("experiment_code", mode="before")
    @classmethod
    def _trim_reaction_experiment_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExperimentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_code: str | None = Field(default=None, max_length=120)
    status: ReactionExperimentStatus | None = None
    conditions_json: dict[str, Any] | None = None
    outcome_json: dict[str, Any] | None = None
    linked_spectracheck_session_id: int | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("experiment_code", mode="before")
    @classmethod
    def _trim_reaction_experiment_update_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    experiment_code: str
    status: ReactionExperimentStatus
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    outcome_json: dict[str, Any] = Field(default_factory=dict)
    outcome: ReactionOutcome = Field(default_factory=ReactionOutcome)
    linked_spectracheck_session_id: int | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionOptimizationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_type: ReactionOptimizationModelType = "rule_based"
    objective: ReactionObjective | None = None
    max_recommendations: int = Field(default=5, ge=1, le=20)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionOptimizationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    status: ReactionOptimizationStatus
    model_type: ReactionOptimizationModelType
    objective: ReactionObjective
    input_experiment_count: int
    recommendations_json: list[dict[str, Any]] = Field(default_factory=list)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionRecommendationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(default=1, ge=1)
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    predicted_outcome_json: dict[str, Any] = Field(default_factory=dict)
    uncertainty_json: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=1, max_length=20_000)
    label: ReactionRecommendationLabel = "requires_human_review"
    status: ReactionRecommendationStatus = "proposed"
    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rationale", "reviewer_name", "reviewer_comment", mode="before")
    @classmethod
    def _trim_reaction_recommendation_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionRecommendationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str | None = Field(default=None, max_length=200)
    reviewer_comment: str | None = Field(default=None, max_length=20_000)
    rationale: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "reviewer_comment", "rationale", mode="before")
    @classmethod
    def _trim_reaction_review_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    optimization_run_id: int | None = None
    rank: int
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    predicted_outcome_json: dict[str, Any] = Field(default_factory=dict)
    uncertainty_json: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    label: ReactionRecommendationLabel
    status: ReactionRecommendationStatus
    reviewer_name: str | None = None
    reviewer_comment: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


ReactionObjectiveProfileType = Literal[
    "maximize_yield",
    "maximize_selectivity",
    "minimize_impurity",
    "maximize_conversion",
    "multi_objective",
    "custom",
]
ReactionSurrogateModelType = Literal[
    "gaussian_process",
    "random_forest",
    "extra_trees",
    "tpe_like",
    "rule_based_fallback",
]
ReactionBayesianOptimizationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
]
ReactionBayesianOptimizationAlgorithm = Literal[
    "gaussian_process_ei",
    "gaussian_process_ucb",
    "random_forest_ei",
    "tpe_like",
    "rule_based_fallback",
    "llm_guided_advisory",
]
ReactionSafetyStatus = Literal["allowed", "warning", "blocked", "unknown"]
ReactionAcquisitionCandidateLabel = Literal[
    "high_expected_improvement",
    "exploratory_candidate",
    "cost_efficient_candidate",
    "safety_blocked",
    "requires_human_review",
    "insufficient_data",
]
ReactionRecommendationBatchStatus = Literal[
    "proposed",
    "partially_approved",
    "approved",
    "rejected",
    "archived",
]
ReactionBenchmarkStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]


class ReactionDesignSpaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variables_json: dict[str, Any] = Field(default_factory=dict)
    categorical_variables_json: dict[str, Any] = Field(default_factory=dict)
    numeric_variables_json: dict[str, Any] = Field(default_factory=dict)
    boolean_variables_json: dict[str, Any] = Field(default_factory=dict)
    fixed_conditions_json: dict[str, Any] = Field(default_factory=dict)
    excluded_conditions_json: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionDesignSpaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variables_json: dict[str, Any] | None = None
    categorical_variables_json: dict[str, Any] | None = None
    numeric_variables_json: dict[str, Any] | None = None
    boolean_variables_json: dict[str, Any] | None = None
    fixed_conditions_json: dict[str, Any] | None = None
    excluded_conditions_json: list[dict[str, Any]] | dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class ReactionDesignSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    variables_json: dict[str, Any] = Field(default_factory=dict)
    categorical_variables_json: dict[str, Any] = Field(default_factory=dict)
    numeric_variables_json: dict[str, Any] = Field(default_factory=dict)
    boolean_variables_json: dict[str, Any] = Field(default_factory=dict)
    fixed_conditions_json: dict[str, Any] = Field(default_factory=dict)
    excluded_conditions_json: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionObjectiveProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_type: ReactionObjectiveProfileType = "maximize_yield"
    weights_json: dict[str, Any] = Field(default_factory=dict)
    target_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    hard_constraints_json: dict[str, Any] = Field(default_factory=dict)
    soft_constraints_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionObjectiveProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_type: ReactionObjectiveProfileType | None = None
    weights_json: dict[str, Any] | None = None
    target_thresholds_json: dict[str, Any] | None = None
    hard_constraints_json: dict[str, Any] | None = None
    soft_constraints_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class ReactionObjectiveProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    objective_type: ReactionObjectiveProfileType
    weights_json: dict[str, Any] = Field(default_factory=dict)
    target_thresholds_json: dict[str, Any] = Field(default_factory=dict)
    hard_constraints_json: dict[str, Any] = Field(default_factory=dict)
    soft_constraints_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionCostProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reagent_costs_json: dict[str, Any] = Field(default_factory=dict)
    solvent_costs_json: dict[str, Any] = Field(default_factory=dict)
    catalyst_costs_json: dict[str, Any] = Field(default_factory=dict)
    ligand_costs_json: dict[str, Any] = Field(default_factory=dict)
    availability_json: dict[str, Any] = Field(default_factory=dict)
    max_cost_per_experiment: float | None = Field(default=None, ge=0)
    cost_penalty_weight: float | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionCostProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reagent_costs_json: dict[str, Any] | None = None
    solvent_costs_json: dict[str, Any] | None = None
    catalyst_costs_json: dict[str, Any] | None = None
    ligand_costs_json: dict[str, Any] | None = None
    availability_json: dict[str, Any] | None = None
    max_cost_per_experiment: float | None = Field(default=None, ge=0)
    cost_penalty_weight: float | None = Field(default=None, ge=0)
    metadata_json: dict[str, Any] | None = None


class ReactionCostProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    reagent_costs_json: dict[str, Any] = Field(default_factory=dict)
    solvent_costs_json: dict[str, Any] = Field(default_factory=dict)
    catalyst_costs_json: dict[str, Any] = Field(default_factory=dict)
    ligand_costs_json: dict[str, Any] = Field(default_factory=dict)
    availability_json: dict[str, Any] = Field(default_factory=dict)
    max_cost_per_experiment: float | None = None
    cost_penalty_weight: float | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionSafetyConstraintProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked_reagents_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    blocked_solvents_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    max_temperature_c: float | None = None
    max_pressure_bar: float | None = Field(default=None, ge=0)
    incompatible_pairs_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    required_controls_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    safety_notes_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionSafetyConstraintProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked_reagents_json: list[Any] | dict[str, Any] | None = None
    blocked_solvents_json: list[Any] | dict[str, Any] | None = None
    max_temperature_c: float | None = None
    max_pressure_bar: float | None = Field(default=None, ge=0)
    incompatible_pairs_json: list[Any] | dict[str, Any] | None = None
    required_controls_json: list[Any] | dict[str, Any] | None = None
    safety_notes_json: list[Any] | dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class ReactionSafetyConstraintProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    blocked_reagents_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    blocked_solvents_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    max_temperature_c: float | None = None
    max_pressure_bar: float | None = None
    incompatible_pairs_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    required_controls_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    safety_notes_json: list[Any] | dict[str, Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionSurrogateModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    bo_run_id: int | None = None
    model_type: ReactionSurrogateModelType
    model_version: str
    training_experiment_count: int
    feature_encoding_json: dict[str, Any] = Field(default_factory=dict)
    objective_summary_json: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionAcquisitionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    bo_run_id: int
    rank: int
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    predicted_score: float | None = None
    expected_improvement: float | None = None
    uncertainty: float | None = None
    estimated_cost: float | None = None
    safety_status: ReactionSafetyStatus = "unknown"
    acquisition_score: float | None = None
    rationale: str
    label: ReactionAcquisitionCandidateLabel
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionBayesianOptimizationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: ReactionBayesianOptimizationAlgorithm = "gaussian_process_ei"
    batch_size: int = Field(default=5, ge=1, le=20)
    exploration_weight: float | None = Field(default=None, ge=0)
    cost_aware: bool = False
    safety_aware: bool = True
    include_negative_outcomes: bool = False
    candidate_count: int = Field(default=64, ge=1, le=1000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionBayesianOptimizationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    bo_run_id: int
    reaction_project_id: int
    status: ReactionBayesianOptimizationStatus
    algorithm: ReactionBayesianOptimizationAlgorithm
    model_type: ReactionSurrogateModelType
    batch_size: int
    exploration_weight: float | None = None
    cost_aware: bool
    safety_aware: bool
    input_experiment_count: int
    candidate_count: int
    recommendations_json: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[ReactionAcquisitionCandidate] = Field(default_factory=list)
    diagnostics_json: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionRecommendationBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bo_run_id: int | None = None
    recommendations_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionRecommendationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    bo_run_id: int | None = None
    status: ReactionRecommendationBatchStatus
    recommendations_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionOptimizationBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_name: str = Field(default="phase50_replay", min_length=1, max_length=200)
    algorithm: ReactionBayesianOptimizationAlgorithm = "rule_based_fallback"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("benchmark_name", mode="before")
    @classmethod
    def _trim_benchmark_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionOptimizationBenchmarkRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int | None = None
    benchmark_name: str
    algorithm: ReactionBayesianOptimizationAlgorithm
    status: ReactionBenchmarkStatus
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    trajectory_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


ReactionAdvisorRunStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
ReactionAdvisorMode = Literal[
    "rule_based_mechanistic",
    "llm_guided_placeholder",
    "llm_guided_configured",
    "hybrid_bo_llm",
]
ReactionMechanisticConfidenceLabel = Literal["low", "medium", "high", "speculative"]
ReactionMechanisticHypothesisStatus = Literal["proposed", "accepted", "rejected", "revised"]
ReactionConditionCritiqueRecommendation = Literal[
    "accept_for_review",
    "modify_before_review",
    "reject_or_deprioritize",
    "insufficient_information",
]
ReactionLiteraturePriorSourceType = Literal[
    "user_note",
    "literature_reference",
    "internal_history",
    "model_prior",
    "rule_based_prior",
]


class ReactionOptimizationAdvisorRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bo_run_id: int | None = None
    recommendation_batch_id: int | None = None
    advisor_mode: ReactionAdvisorMode = "rule_based_mechanistic"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionOptimizationAdvisorRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    advisor_run_id: int
    reaction_project_id: int
    bo_run_id: int | None = None
    recommendation_batch_id: int | None = None
    status: ReactionAdvisorRunStatus
    advisor_mode: ReactionAdvisorMode
    input_summary_json: dict[str, Any] = Field(default_factory=dict)
    advisor_output_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    recommendation_count: int = 0
    critiques: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    agreements: list[dict[str, Any]] = Field(default_factory=list)
    disagreements: list[dict[str, Any]] = Field(default_factory=list)
    suggested_controls: list[dict[str, Any]] = Field(default_factory=list)
    suggested_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReactionMechanisticHypothesisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    hypothesis: str = Field(min_length=1, max_length=20_000)
    supporting_observations_json: list[dict[str, Any]] | dict[str, Any] = Field(
        default_factory=list
    )
    contradicting_observations_json: list[dict[str, Any]] | dict[str, Any] = Field(
        default_factory=list
    )
    confidence_label: ReactionMechanisticConfidenceLabel = "speculative"
    status: ReactionMechanisticHypothesisStatus = "proposed"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "hypothesis", mode="before")
    @classmethod
    def _trim_hypothesis_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionMechanisticHypothesisUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=240)
    hypothesis: str | None = Field(default=None, max_length=20_000)
    supporting_observations_json: list[dict[str, Any]] | dict[str, Any] | None = None
    contradicting_observations_json: list[dict[str, Any]] | dict[str, Any] | None = None
    confidence_label: ReactionMechanisticConfidenceLabel | None = None
    status: ReactionMechanisticHypothesisStatus | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("title", "hypothesis", mode="before")
    @classmethod
    def _trim_hypothesis_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionMechanisticHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    title: str
    hypothesis: str
    supporting_observations_json: list[dict[str, Any]] | dict[str, Any] = Field(
        default_factory=list
    )
    contradicting_observations_json: list[dict[str, Any]] | dict[str, Any] = Field(
        default_factory=list
    )
    confidence_label: ReactionMechanisticConfidenceLabel
    status: ReactionMechanisticHypothesisStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionConditionCritiqueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisor_run_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionConditionCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    recommendation_id: int | None = None
    advisor_run_id: int | None = None
    condition_summary_json: dict[str, Any] = Field(default_factory=dict)
    mechanistic_rationale: str
    practicality_assessment: str
    cost_assessment: str
    safety_assessment: str
    risk_flags_json: list[dict[str, Any]] = Field(default_factory=list)
    suggested_controls_json: list[dict[str, Any]] = Field(default_factory=list)
    suggested_alternatives_json: list[dict[str, Any]] = Field(default_factory=list)
    recommendation: ReactionConditionCritiqueRecommendation
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    risk_flags: list[dict[str, Any]] = Field(default_factory=list)
    suggested_controls: list[dict[str, Any]] = Field(default_factory=list)
    suggested_alternatives: list[dict[str, Any]] = Field(default_factory=list)


class ReactionLiteraturePriorCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ReactionLiteraturePriorSourceType = "user_note"
    title: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=20_000)
    citation: str | None = Field(default=None, max_length=2_000)
    relevance_tags_json: list[str] | dict[str, Any] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "summary", "citation", mode="before")
    @classmethod
    def _trim_literature_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionLiteraturePrior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    source_type: ReactionLiteraturePriorSourceType
    title: str
    summary: str
    citation: str | None = None
    relevance_tags_json: list[str] | dict[str, Any] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionOptimizationDebateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bo_run_id: int | None = None
    advisor_run_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionOptimizationDebate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    bo_run_id: int | None = None
    advisor_run_id: int | None = None
    bo_summary_json: dict[str, Any] = Field(default_factory=dict)
    advisor_summary_json: dict[str, Any] = Field(default_factory=dict)
    agreements_json: list[dict[str, Any]] = Field(default_factory=list)
    disagreements_json: list[dict[str, Any]] = Field(default_factory=list)
    final_review_recommendation: str
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    agreements: list[dict[str, Any]] = Field(default_factory=list)
    disagreements: list[dict[str, Any]] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionAdvisorReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str | None = Field(default=None, max_length=200)
    decision: str = Field(default="reviewed", max_length=80)
    rationale: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "decision", "rationale", mode="before")
    @classmethod
    def _trim_advisor_review_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


ReactionExecutionBatchStatus = Literal[
    "draft",
    "planned",
    "running",
    "completed",
    "failed",
    "canceled",
    "partially_completed",
]
ReactionExecutionItemStatus = Literal[
    "planned",
    "running",
    "completed",
    "failed",
    "skipped",
    "canceled",
]
ReactionExecutionEventType = Literal[
    "planned",
    "started",
    "completed",
    "failed",
    "skipped",
    "analytical_result_added",
    "outcome_extracted",
    "outcome_confirmed",
    "note",
]
ReactionAnalyticalResultType = Literal[
    "nmr",
    "lcms",
    "hrms",
    "msms",
    "hplc",
    "uplc",
    "qnmr",
    "other",
]
ReactionOutcomeExtractionStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
]
ReactionOutcomeExtractionMethod = Literal[
    "manual",
    "lcms_area",
    "nmr_purity",
    "unified_spectracheck",
    "rule_based",
]
ReactionOutcomeConfidenceLabel = Literal["low", "medium", "high", "requires_review"]
ReactionOptimizationCycleStatus = Literal[
    "draft",
    "running",
    "completed",
    "requires_review",
    "failed",
]
ReactionCycleDecision = Literal[
    "continue_optimization",
    "pause",
    "stop_success",
    "stop_insufficient_progress",
    "revise_design_space",
    "revise_objective",
    "requires_review",
]


class ReactionExecutionBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_code: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=240)
    status: ReactionExecutionBatchStatus = "draft"
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    created_by: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("batch_code", "title", "created_by", mode="before")
    @classmethod
    def _trim_execution_batch_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExecutionBatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_code: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=240)
    status: ReactionExecutionBatchStatus | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    created_by: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] | None = None

    @field_validator("batch_code", "title", "created_by", mode="before")
    @classmethod
    def _trim_execution_batch_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExecutionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    batch_code: str
    title: str | None = None
    status: ReactionExecutionBatchStatus
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionExecutionItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: int | None = None
    experiment_id: int | None = None
    item_code: str = Field(min_length=1, max_length=120)
    status: ReactionExecutionItemStatus = "planned"
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    checklist_json: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    operator_name: str | None = Field(default=None, max_length=200)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("item_code", "operator_name", "failure_reason", mode="before")
    @classmethod
    def _trim_execution_item_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExecutionItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: int | None = None
    experiment_id: int | None = None
    item_code: str | None = Field(default=None, max_length=120)
    status: ReactionExecutionItemStatus | None = None
    conditions_json: dict[str, Any] | None = None
    checklist_json: list[dict[str, Any]] | dict[str, Any] | None = None
    operator_name: str | None = Field(default=None, max_length=200)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] | None = None

    @field_validator("item_code", "operator_name", "failure_reason", mode="before")
    @classmethod
    def _trim_execution_item_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExecutionStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_name: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=20_000)
    failure_reason: str | None = Field(default=None, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("operator_name", "message", "failure_reason", mode="before")
    @classmethod
    def _trim_execution_status_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionExecutionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    execution_batch_id: int
    reaction_project_id: int
    recommendation_id: int | None = None
    experiment_id: int | None = None
    item_code: str
    status: ReactionExecutionItemStatus
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    checklist_json: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)
    operator_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    execution_item_id: int | None = None
    execution_batch_id: int | None = None
    event_type: ReactionExecutionEventType
    message: str
    actor: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionAnalyticalResultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spectracheck_session_id: int | None = None
    file_id: int | None = None
    artifact_id: int | None = None
    result_type: ReactionAnalyticalResultType = "other"
    summary_json: dict[str, Any] = Field(default_factory=dict)
    qc_status: str | None = Field(default=None, max_length=100)
    source_hash: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("qc_status", "source_hash", mode="before")
    @classmethod
    def _trim_analytical_result_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionAnalyticalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    execution_item_id: int
    spectracheck_session_id: int | None = None
    file_id: int | None = None
    artifact_id: int | None = None
    result_type: ReactionAnalyticalResultType
    summary_json: dict[str, Any] = Field(default_factory=dict)
    qc_status: str | None = None
    source_hash: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionOutcomeExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_method: ReactionOutcomeExtractionMethod = "rule_based"
    analytical_result_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionOutcomeExtractionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    execution_item_id: int
    status: ReactionOutcomeExtractionStatus
    extraction_method: ReactionOutcomeExtractionMethod
    proposed_outcome_json: dict[str, Any] = Field(default_factory=dict)
    confidence_label: ReactionOutcomeConfidenceLabel
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionOutcomeConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extraction_run_id: int | None = None
    confirmed_outcome_json: dict[str, Any] | None = None
    reviewer_name: str | None = Field(default=None, max_length=200)
    rationale: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "rationale", mode="before")
    @classmethod
    def _trim_outcome_confirm_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionRecommendationConvertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_code: str | None = Field(default=None, max_length=120)
    execution_batch_id: int | None = None
    item_code: str | None = Field(default=None, max_length=120)
    reviewer_name: str | None = Field(default=None, max_length=200)
    rationale: str = Field(min_length=1, max_length=20_000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("experiment_code", "item_code", "reviewer_name", "rationale", mode="before")
    @classmethod
    def _trim_convert_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionRecommendationConvertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: int
    reaction_project_id: int
    experiment: ReactionExperiment
    execution_item: ReactionExecutionItem | None = None
    event: ReactionExecutionEvent | None = None
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionOptimizationCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle_number: int | None = Field(default=None, ge=1)
    status: ReactionOptimizationCycleStatus = "draft"
    bo_run_id: int | None = None
    advisor_run_id: int | None = None
    recommendation_batch_id: int | None = None
    execution_batch_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionOptimizationCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    cycle_number: int
    status: ReactionOptimizationCycleStatus
    input_experiment_count: int
    new_experiment_count: int
    bo_run_id: int | None = None
    advisor_run_id: int | None = None
    recommendation_batch_id: int | None = None
    execution_batch_id: int | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ReactionCycleDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReactionCycleDecision
    rationale: str = Field(min_length=1, max_length=20_000)
    reviewer_name: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("rationale", "reviewer_name", mode="before")
    @classmethod
    def _trim_cycle_decision_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class ReactionCycleDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    optimization_cycle_id: int
    decision: ReactionCycleDecision
    rationale: str
    reviewer_name: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


class ReactionExperimentSpectraCheckLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionExperimentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: int
    linked_spectracheck_session_id: int | None = None
    evidence_records: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True


QualityTargetType = Literal["file", "artifact", "evidence", "session"]
QualitySeverity = Literal["info", "warning", "error", "critical"]
QualityModality = Literal[
    "nmr_1h_processed",
    "nmr_13c_processed",
    "raw_fid_nmr",
    "dept_apt",
    "nmr_2d",
    "hrms",
    "msms",
    "lcms_ms1",
    "lcms_ms2",
    "lcms_feature_table",
    "lcms_consensus",
    "report",
    "unknown",
]
QualityQCStatus = Literal[
    "qc_pass",
    "qc_warning",
    "qc_fail",
    "requires_human_review",
    "not_assessed",
]
QualityReadinessStatus = Literal[
    "ready_for_unified_evidence",
    "usable_with_warnings",
    "blocked_until_review",
    "not_ready",
]
QualityOverrideDecision = Literal["allow_with_warning", "block", "needs_reprocessing"]


class QualityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    target_type: QualityTargetType
    target_id: int
    severity: QualitySeverity
    code: str
    title: str
    message: str
    recommendation: str | None = None
    layer: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class QualityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    target_type: QualityTargetType
    target_id: int
    modality: QualityModality
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    qc_status: QualityQCStatus
    readiness_status: QualityReadinessStatus
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    findings_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    recommended_actions_json: list[str] = Field(default_factory=list)
    human_review_required: bool
    override_status: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class QualityAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modality: QualityModality | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class QualityFindingReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=10_000)
    decision: str = Field(default="reviewed", min_length=1, max_length=100)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "reason", "decision", mode="before")
    @classmethod
    def _trim_finding_review_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class QualityOverrideCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_name: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=10_000)
    decision: QualityOverrideDecision
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer_name", "reason", mode="before")
    @classmethod
    def _trim_override_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class QualityOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assessment_id: int
    reviewer_name: str | None = None
    reason: str
    decision: QualityOverrideDecision
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


WorkflowTemplateCategory = Literal["nmr", "ms", "lcms", "full_spectracheck", "report"]
WorkflowRunStatus = Literal[
    "draft",
    "queued",
    "running",
    "succeeded",
    "failed",
    "canceled",
    "requires_review",
]
WorkflowStepType = Literal[
    "upload",
    "job",
    "quality_control",
    "evidence_queue",
    "unified_evidence",
    "report",
    "review_gate",
    "manual",
]
WorkflowStepStatus = Literal[
    "pending", "queued", "running", "succeeded", "failed", "skipped", "blocked"
]


class WorkflowTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    category: WorkflowTemplateCategory
    version: str = Field(default="1.0", min_length=1, max_length=32)
    is_builtin: bool = False
    steps_json: list[dict[str, Any]] = Field(default_factory=list)
    required_inputs_json: list[str] = Field(default_factory=list)
    optional_inputs_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "slug", "description", "version", mode="before")
    @classmethod
    def _trim_template_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class WorkflowTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    category: WorkflowTemplateCategory | None = None
    version: str | None = Field(default=None, min_length=1, max_length=32)
    steps_json: list[dict[str, Any]] | None = None
    required_inputs_json: list[str] | None = None
    optional_inputs_json: list[str] | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("name", "description", "version", mode="before")
    @classmethod
    def _trim_template_update_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class WorkflowTemplateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    description: str
    category: WorkflowTemplateCategory
    version: str
    is_builtin: bool
    steps_json: list[dict[str, Any]] = Field(default_factory=list)
    required_inputs_json: list[str] = Field(default_factory=list)
    optional_inputs_json: list[str] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class WorkflowRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: int | None = None
    template_slug: str | None = Field(default=None, max_length=120)
    session_id: int | None = Field(default=None, ge=1)
    project_id: int | None = Field(default=None, ge=1)
    sample_id: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    inputs_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    method_id: int | None = Field(default=None, ge=1)
    model_version_id: int | None = Field(default=None, ge=1)
    scoring_profile_id: int | None = Field(default=None, ge=1)
    threshold_profile_id: int | None = Field(default=None, ge=1)

    @field_validator("template_slug", "sample_id", "name", mode="before")
    @classmethod
    def _trim_run_create_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class WorkflowRunStepRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow_run_id: int
    step_id: str
    step_name: str
    step_type: WorkflowStepType
    status: WorkflowStepStatus
    job_id: int | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow_run_id: int
    step_id: str | None = None
    event_type: str
    message: str
    progress_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow_run_id: int
    step_id: str | None = None
    artifact_id: int | None = None
    evidence_id: int | None = None
    title: str
    artifact_type: str
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    template_id: int | None = None
    session_id: int | None = None
    project_id: int | None = None
    sample_id: str | None = None
    name: str
    status: WorkflowRunStatus
    progress_percent: float = Field(ge=0.0, le=100.0)
    current_step_id: str | None = None
    current_step: str | None = None
    inputs_json: dict[str, Any] = Field(default_factory=dict)
    outputs_json: dict[str, Any] | None = None
    outputs: dict[str, Any] | None = None
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    steps: list[WorkflowRunStepRecord] = Field(default_factory=list)
    events: list[WorkflowRunEventRecord] = Field(default_factory=list)
    artifacts: list[WorkflowRunArtifactRecord] = Field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    user_id: int | None = None
    job_name: str | None = None
    uploaded_filename: str | None = None
    status: JobStatus
    total_items: int
    completed_items: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    backend_job_id: str | None = None
    queue_name: str | None = None
    review_required: bool = True
    method_id: int | None = None
    model_version_id: int | None = None
    scoring_profile_id: int | None = None
    threshold_profile_id: int | None = None
    review_completion_rate: float = 0.0


class AsyncJobAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobRecord
    accepted: bool = True
    detail: str = "Job accepted and queued for background processing."
    queue_backend: Literal["rq", "fastapi-background"]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=512)


class UserLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=512)


class UserSignUp(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str | None = Field(default=None, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=512)
    password_confirm: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "password_confirm",
            "passwordConfirm",
            "password-confirm",
            "confirm_password",
        ),
        max_length=512,
    )

    @field_validator("name", mode="before")
    @classmethod
    def _optional_trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @model_validator(mode="after")
    def _passwords_match(self) -> UserSignUp:
        if self.password_confirm is not None and self.password_confirm != self.password:
            raise ValueError("Password confirmation does not match password.")
        return self


class UserSignIn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: EmailStr
    password: str = Field(min_length=8, max_length=512)
    remember_me: bool = Field(
        default=False,
        validation_alias=AliasChoices("remember_me", "rememberMe"),
    )


class UserPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool
    is_verified: bool
    created_at: datetime
    verified_at: datetime | None = None


class AccessTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserPublic


class AuthPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str | None = None
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime | None = None
    user: UserPublic
    requires_email_verification: bool = False
    detail: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str


class EmailActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=8, max_length=512)


class TokenActionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    token: str | None = None
    expires_at: datetime | None = None


class EmailOutboxRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    to_email: EmailStr
    subject: str
    body: str
    purpose: ActionTokenPurpose | None = None


class QueueWorkerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["rq", "fastapi-background"]
    redis_configured: bool
    queue_name: str
    detail: str


class ReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=4000)
    final_label: str | None = Field(default=None, max_length=100)
    hours_saved_estimate: float | None = Field(default=None, ge=0.0, le=100.0)


class ReviewDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    analysis_id: int
    reviewer_user_id: int
    action: ReviewAction
    previous_status: ReviewStatus
    new_status: ReviewStatus
    comment: str | None = None
    previous_label: str | None = None
    final_label: str | None = None
    created_at: datetime


class ReviewQueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: StoredAnalysisRecord
    evidence_notes: list[str] = Field(default_factory=list)
    recommended_action: ReviewStatus | None = None


class AIEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    module: AIEvidenceModule
    entity_type: str
    entity_id: int
    status: AIEvidenceStatus
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_level: AIEvidenceRiskLevel = "unknown"
    summary: str
    reviewer_id: int | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    created_at: datetime
    updated_at: datetime


class AIEvidenceReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AIEvidenceReviewStatus
    review_comment: str | None = Field(default=None, max_length=4000)

    @field_validator("review_comment", mode="before")
    @classmethod
    def _sanitize_review_comment(cls, value: str | None) -> str | None:
        text = sanitize_optional_plain_text(value)
        if text is not None and _PLAIN_TEXT_TAG_RE.search(text):
            raise ValueError("review_comment must be plain text.")
        return text


class AIEvidenceReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item: AIEvidenceItem
    audit_event_id: int
    updated_status: AIEvidenceStatus
    reviewed_at: datetime
    reviewer_id: int | None = None
    reviewer_display_name: str | None = None


class AuditEventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    created_at: datetime
    event_type: str
    message: str
    tenant_id: int | None = None
    action: str | None = None
    module: str | None = None
    actor_user_id: int | None = None
    actor_email: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    reason: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NMR2DEvidenceReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    report_url: str
    experiment_type: str
    peak_count: int = 0
    matched_correlations: int = 0
    suspicious_correlations: int = 0
    evidence_score: float = Field(ge=0.0, le=1.0)
    cosy_connectivity_notes: list[str] = Field(default_factory=list)
    hsqc_hmqc_direct_attachment_notes: list[str] = Field(default_factory=list)
    hmbc_long_range_notes: list[str] = Field(default_factory=list)
    missing_extra_correlation_notes: list[str] = Field(default_factory=list)
    dept_apt_experiment_type: str | None = None
    dept_apt_typed_peak_count: int = 0
    dept_apt_type_summary: dict[str, int] = Field(default_factory=dict)
    dept_apt_matched_carbon13_count: int = 0
    dept_apt_consistency_score: float | None = Field(default=None, ge=0.0, le=1.0)
    dept_apt_apt_convention_warning: str | None = None
    hsqc_hmqc_dept_apt_supported_correlations: int = 0
    hsqc_hmqc_dept_apt_conflicting_correlations: int = 0
    hmbc_dept_apt_contextual_correlations: int = 0
    human_review_status: ReviewStatus = "pending_review"
    score_components: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AnalysisEvidenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: FullStoredAnalysisRecord
    structure: StructureSummary
    parsed_nmr_text: str
    parsed_peaks: list[Peak] = Field(default_factory=list)
    spectrum_derived_matched_peaks: list[Peak] = Field(default_factory=list)
    unmatched_peaks: list[Peak] = Field(default_factory=list)
    impurity_candidates: list[str] = Field(default_factory=list)
    confidence_notes: list[str] = Field(default_factory=list)
    review_decisions: list[ReviewDecisionRecord] = Field(default_factory=list)
    audit_events: list[AuditEventRecord] = Field(default_factory=list)
    audit_metadata: dict[str, Any] = Field(default_factory=dict)
    nmr2d_evidence: list[NMR2DEvidenceReportSection] = Field(default_factory=list)
    time_saved_estimate: float = 0.0


class StoredReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    analysis_id: int
    user_id: int | None = None
    created_at: datetime
    version: int = 1
    title: str
    report: AnalysisEvidenceReport


class SampleDetailRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample: ProjectSampleRecord
    latest_analysis: StoredAnalysisRecord | None = None
    notes: list[str] = Field(default_factory=list)
    reports_count: int = 0


class SampleTimelineRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample: ProjectSampleRecord
    analysis_ids: list[int] = Field(default_factory=list)
    review_decisions: list[ReviewDecisionRecord] = Field(default_factory=list)
    audit_events: list[AuditEventRecord] = Field(default_factory=list)


class SampleReportsRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample: ProjectSampleRecord
    reports: list[StoredReportRecord] = Field(default_factory=list)


class ProjectDashboardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectRecord
    sample_count: int = 0
    analysis_count: int = 0
    approved_reviews: int = 0
    rejected_reviews: int = 0
    pending_review: int = 0
    solvent_distribution: dict[str, int] = Field(default_factory=dict)
    hours_saved_estimate: float = 0.0
    likely_impurity_flags: int = 0
    latest_activity: list[AuditEventRecord] = Field(default_factory=list)


class SampleAnalysisComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: int
    created_at: datetime
    label: DiagnosticLabel
    final_label: str | None = None
    proton_count_delta: int = 0
    confidence: float
    impurity_flags: int = 0
    reviewer_outcome: ReviewStatus
    peak_count: int = 0
    peak_count_change: int = 0
    time_saved: float = 0.0


class SampleAnalysisComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample: ProjectSampleRecord
    basis: Literal["sample_id", "smiles", "none"]
    items: list[SampleAnalysisComparisonItem] = Field(default_factory=list)


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    value: float
    unit: str | None = None
    detail: str | None = None


class MetricsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_analyses: int
    total_jobs: int
    pending_review: int
    approved_reviews: int
    rejected_reviews: int
    overrides: int
    validation_failures: int
    likely_impurity_flags: int
    hours_saved_estimate: float
    automation_rate: float = Field(ge=0.0, le=1.0)
    cards: list[MetricCard] = Field(default_factory=list)


class AdminUserRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    email: EmailStr
    is_active: bool
    is_admin: bool
    is_verified: bool
    created_at: datetime
    analyses_count: int = 0
    jobs_count: int = 0


class AdminSystemSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: int
    admins: int
    active_users: int
    analyses: int
    jobs: int
    pending_review: int
    audit_events: int
    queue_backend: str
    redis_configured: bool


ConnectorType = Literal[
    "instrument_watch_folder",
    "object_storage",
    "eln",
    "lims",
    "sdms",
    "chromatography_data_system",
    "regulatory_document_system",
    "webhook",
    "generic_rest",
    "other",
]
ConnectorTargetProgram = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
]
ConnectorRegistryStatus = Literal["draft", "active", "disabled", "error"]
ConnectorCredentialType = Literal[
    "api_key",
    "oauth",
    "basic_auth",
    "token",
    "service_account",
    "none",
]
ConnectorCredentialStatus = Literal["active", "revoked", "expired", "missing"]
ConnectorHealthStatus = Literal["ok", "warning", "error", "unknown"]
InstrumentTargetRoute = Literal[
    "processed_nmr",
    "raw_fid",
    "nmr2d",
    "dept_apt",
    "msms",
    "ms_raw",
    "lcms",
    "lcms_raw",
    "spectrum_file",
    "regulatory_source",
    "reaction_outcome",
    "other",
]
InstrumentWatchFolderStatus = Literal["active", "paused", "error"]
IngestionRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "partial",
    "requires_review",
]
FileNormalizationSourceFormat = Literal[
    "bruker_zip",
    "agilent_varian_zip",
    "jcamp_dx",
    "csv",
    "tsv",
    "txt",
    "mzml",
    "mzxml",
    "sdf",
    "pdf",
    "docx",
    "unknown",
]
FileNormalizationTargetFormat = Literal[
    "moltrace_spectrum_json",
    "moltrace_lcms_json",
    "moltrace_regulatory_source_json",
    "moltrace_reaction_table_json",
    "unchanged",
    "unsupported",
]
FileNormalizationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "unsupported",
    "requires_review",
]
ExternalObjectType = Literal[
    "project",
    "sample",
    "experiment",
    "batch",
    "report",
    "document",
    "result",
    "file",
    "action_item",
    "other",
]
MolTraceResourceType = Literal[
    "project",
    "sample",
    "spectracheck_session",
    "regulatory_dossier",
    "reaction_project",
    "reaction_experiment",
    "compound",
    "batch",
    "report",
    "file",
    "artifact",
    "action_item",
    "other",
]
ExternalRelationType = Literal[
    "source_of",
    "exported_to",
    "linked_to",
    "synchronized_with",
    "derived_from",
    "evidence_for",
    "other",
]
MappingTemplateSourceType = Literal[
    "eln_experiment",
    "lims_sample",
    "instrument_file",
    "regulatory_document",
    "reaction_table",
    "ctd_package",
    "other",
]
MappingTemplateTargetType = Literal[
    "spectracheck_session",
    "regulatory_dossier",
    "reaction_experiment",
    "compound_batch",
    "file_record",
    "action_item",
    "other",
]
MappingTemplateStatus = Literal["draft", "active", "archived"]
OutboundSyncStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
WebhookSubscriptionStatus = Literal["active", "disabled", "error"]
RegulatorySubmissionPackageType = Literal[
    "ctd_module3",
    "impurity_report",
    "qnmr_validation",
    "ai_governance",
    "readiness_bundle",
    "other",
]
RegulatorySubmissionPackageStatus = Literal[
    "draft",
    "ready_for_review",
    "exported",
    "failed",
]


class ConnectorRegistryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=240)
    connector_type: ConnectorType
    target_program: ConnectorTargetProgram
    status: ConnectorRegistryStatus = "draft"
    config_schema_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConnectorRegistryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_key: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, min_length=1, max_length=240)
    connector_type: ConnectorType | None = None
    target_program: ConnectorTargetProgram | None = None
    status: ConnectorRegistryStatus | None = None
    config_schema_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class ConnectorRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_key: str
    display_name: str
    connector_type: ConnectorType
    target_program: ConnectorTargetProgram
    status: ConnectorRegistryStatus
    config_schema_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConnectorCredentialReferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential_type: ConnectorCredentialType
    secret_ref: str | None = Field(default=None, max_length=1000)
    status: ConnectorCredentialStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConnectorCredentialReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int
    credential_type: ConnectorCredentialType
    secret_ref: str | None = None
    status: ConnectorCredentialStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealthCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConnectorHealthStatus | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    message: str | None = Field(default=None, max_length=1000)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealthCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int
    status: ConnectorHealthStatus
    latency_ms: int | None = None
    message: str | None = None
    checked_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InstrumentWatchFolderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    folder_path: str = Field(min_length=1)
    file_patterns_json: list[str] = Field(default_factory=lambda: ["*"], max_length=100)
    recursive: bool = False
    target_program: Literal["spectracheck", "regulatory_hub", "reaction_optimization"]
    target_route: InstrumentTargetRoute
    status: InstrumentWatchFolderStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InstrumentWatchFolderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    folder_path: str | None = Field(default=None, min_length=1)
    file_patterns_json: list[str] | None = Field(default=None, max_length=100)
    recursive: bool | None = None
    target_program: Literal["spectracheck", "regulatory_hub", "reaction_optimization"] | None = None
    target_route: InstrumentTargetRoute | None = None
    status: InstrumentWatchFolderStatus | None = None
    metadata_json: dict[str, Any] | None = None


class InstrumentWatchFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int | None = None
    folder_path: str
    file_patterns_json: list[str] = Field(default_factory=list)
    recursive: bool
    target_program: Literal["spectracheck", "regulatory_hub", "reaction_optimization"]
    target_route: InstrumentTargetRoute
    status: InstrumentWatchFolderStatus
    last_scan_at: datetime | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InstrumentWatchFolderScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IngestionFileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_base64: str | None = None
    content_text: str | None = None
    content_type: str | None = Field(default=None, max_length=100)
    file_kind: ManagedFileKind = "other"
    source_path: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_content(self) -> IngestionFileInput:
        if self.content_base64 is None and self.content_text is None:
            raise ValueError("Either content_base64 or content_text is required.")
        return self


class IngestionRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    watch_folder_id: int | None = Field(default=None, ge=1)
    source_system: str | None = Field(default=None, max_length=120)
    source_path: str | None = None
    status: IngestionRunStatus = "queued"
    files_json: list[IngestionFileInput] = Field(default_factory=list, max_length=500)
    force: bool = False
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IngestionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int | None = None
    watch_folder_id: int | None = None
    source_system: str | None = None
    source_path: str | None = None
    status: IngestionRunStatus
    discovered_count: int = Field(ge=0)
    ingested_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FileNormalizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_format: FileNormalizationSourceFormat | None = None
    target_format: FileNormalizationTargetFormat | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FileNormalizationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    file_id: int
    source_format: FileNormalizationSourceFormat
    target_format: FileNormalizationTargetFormat
    status: FileNormalizationStatus
    output_artifact_id: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExternalSystemRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int = Field(ge=1)
    external_system: str = Field(min_length=1, max_length=160)
    external_object_type: ExternalObjectType
    external_object_id: str = Field(min_length=1, max_length=240)
    external_url: str | None = None
    title: str | None = Field(default=None, max_length=300)
    status: str | None = Field(default=None, max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExternalSystemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int
    external_system: str
    external_object_type: ExternalObjectType
    external_object_id: str
    external_url: str | None = None
    title: str | None = None
    status: str | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExternalObjectLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_record_id: int = Field(ge=1)
    moltrace_resource_type: MolTraceResourceType
    moltrace_resource_id: int = Field(ge=1)
    relation_type: ExternalRelationType
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExternalObjectLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    external_record_id: int
    moltrace_resource_type: MolTraceResourceType
    moltrace_resource_id: int
    relation_type: ExternalRelationType
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MappingTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=240)
    source_type: MappingTemplateSourceType
    target_type: MappingTemplateTargetType
    field_map_json: dict[str, Any] = Field(default_factory=dict)
    status: MappingTemplateStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MappingTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    source_type: MappingTemplateSourceType | None = None
    target_type: MappingTemplateTargetType | None = None
    field_map_json: dict[str, Any] | None = None
    status: MappingTemplateStatus | None = None
    metadata_json: dict[str, Any] | None = None


class MappingTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int | None = None
    name: str
    source_type: MappingTemplateSourceType
    target_type: MappingTemplateTargetType
    field_map_json: dict[str, Any] = Field(default_factory=dict)
    status: MappingTemplateStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OutboundSyncJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int = Field(ge=1)
    target_system: str = Field(min_length=1, max_length=160)
    source_resource_type: str = Field(min_length=1, max_length=64)
    source_resource_id: int = Field(ge=1)
    payload_summary_json: dict[str, Any] = Field(default_factory=dict)
    status: OutboundSyncStatus = "requires_review"
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class OutboundSyncJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int
    target_system: str
    source_resource_type: str
    source_resource_id: int
    payload_summary_json: dict[str, Any] = Field(default_factory=dict)
    status: OutboundSyncStatus
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    created_at: datetime
    finished_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WebhookSubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=240)
    event_types_json: list[str] = Field(default_factory=list, max_length=100)
    target_url: str | None = Field(default=None, exclude=True)
    target_url_hash: str | None = Field(default=None, min_length=64, max_length=64)
    status: WebhookSubscriptionStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_webhook_target(self) -> WebhookSubscriptionCreate:
        if self.target_url is None and self.target_url_hash is None:
            raise ValueError("Either target_url or target_url_hash is required.")
        return self


class WebhookSubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    event_types_json: list[str] | None = Field(default=None, max_length=100)
    target_url: str | None = Field(default=None, exclude=True)
    target_url_hash: str | None = Field(default=None, min_length=64, max_length=64)
    status: WebhookSubscriptionStatus | None = None
    metadata_json: dict[str, Any] | None = None


class WebhookSubscription(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    connector_id: int | None = None
    name: str
    event_types_json: list[str] = Field(default_factory=list)
    target_url_hash: str
    status: WebhookSubscriptionStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatorySubmissionPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: int | None = Field(default=None, ge=1)
    package_type: RegulatorySubmissionPackageType = "ctd_module3"
    status: RegulatorySubmissionPackageStatus = "ready_for_review"
    file_ids_json: list[int] = Field(default_factory=list)
    artifact_ids_json: list[int] = Field(default_factory=list)
    source_citations_json: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatorySubmissionPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dossier_id: int | None = None
    report_id: int | None = None
    package_type: RegulatorySubmissionPackageType
    status: RegulatorySubmissionPackageStatus
    file_ids_json: list[int] = Field(default_factory=list)
    artifact_ids_json: list[int] = Field(default_factory=list)
    package_manifest_json: dict[str, Any] = Field(default_factory=dict)
    package_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SpectraCheckImportFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    file_id: int = Field(ge=1)
    spectracheck_session_id: int | None = Field(default=None, ge=1)
    route: InstrumentTargetRoute = "processed_nmr"
    external_record_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RegulatoryImportSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    file_id: int = Field(ge=1)
    dossier_id: int | None = Field(default=None, ge=1)
    external_record_id: int | None = Field(default=None, ge=1)
    source_citation_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionExperimentTableImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int | None = Field(default=None, ge=1)
    file_id: int = Field(ge=1)
    reaction_project_id: int | None = Field(default=None, ge=1)
    external_record_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionApprovedExperimentsExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: int = Field(ge=1)
    target_system: str = Field(min_length=1, max_length=160)
    experiment_ids_json: list[int] = Field(default_factory=list)
    payload_summary_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class IntegrationImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["imported", "requires_review"]
    review_required: bool
    file_id: int | None = None
    ingestion_run_id: int | None = None
    normalization_run_id: int | None = None
    external_record_id: int | None = None
    external_link_id: int | None = None
    sync_job_id: int | None = None
    warnings_json: list[str] = Field(default_factory=list)
    notes_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


ValidationProjectScope = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "full_platform",
]
ValidationType = Literal[
    "initial_validation",
    "change_validation",
    "periodic_review",
    "release_validation",
    "supplier_assessment",
]
ValidationProjectStatus = Literal[
    "draft",
    "in_progress",
    "ready_for_qa_review",
    "approved",
    "rejected",
    "archived",
]
ValidationModule = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "system",
    "mobile",
    "ai_ml",
    "connectors",
]
ValidationCriticality = Literal["low", "medium", "high", "critical"]
GxPImpact = Literal["none", "indirect", "direct", "unknown"]
SpecificationStatus = Literal["draft", "approved", "retired"]
ValidationTargetType = Literal[
    "requirement",
    "function",
    "module",
    "workflow",
    "connector",
    "ai_model",
    "report",
    "mobile",
    "system",
]
ValidationRiskScale = Literal["low", "medium", "high", "critical"]
ValidationProbability = Literal["low", "medium", "high", "unknown"]
ValidationDetectability = Literal["low", "medium", "high", "unknown"]
ValidationTestingRigor = Literal[
    "scripted",
    "unscripted",
    "exploratory",
    "automated",
    "supplier_evidence",
]
ValidationRiskStatus = Literal["open", "mitigated", "accepted", "rejected"]
ValidationProtocolType = Literal[
    "installation",
    "operational",
    "performance",
    "regression",
    "security",
    "data_integrity",
    "electronic_signature",
    "ai_model",
    "connector",
    "mobile",
]
ValidationProtocolStatus = Literal["draft", "approved", "executed", "failed", "archived"]
ValidationTestCaseStatus = Literal["draft", "approved", "executed", "retired"]
ValidationExecutionStatus = Literal["pass", "fail", "blocked", "not_run", "requires_review"]
TraceabilityStatus = Literal["draft", "complete", "gaps_identified", "approved"]
SignatureMeaning = Literal[
    "reviewed",
    "approved",
    "rejected",
    "authored",
    "verified",
    "released",
    "locked",
    "override",
    "other",
]
ControlledRecordType = Literal[
    "report",
    "validation_protocol",
    "validation_result",
    "regulatory_dossier",
    "ctd_bundle",
    "ai_model_card",
    "workflow_template",
    "sop",
    "release_record",
    "other",
]
ControlledRecordStatus = Literal[
    "draft",
    "in_review",
    "approved",
    "locked",
    "archived",
    "superseded",
]
RetentionPolicyStatus = Literal["draft", "active", "retired"]
DataIntegrityScope = Literal[
    "system",
    "project",
    "spectracheck_session",
    "regulatory_dossier",
    "reaction_project",
    "report",
    "connector",
    "ai_model",
    "mobile",
]
DataIntegrityStatus = Literal["pass", "warning", "fail", "requires_review"]
InspectionPackageScope = Literal[
    "project",
    "dossier",
    "report",
    "validation_project",
    "full_platform",
]
InspectionPackageStatus = Literal["draft", "ready_for_review", "approved", "exported", "failed"]
SystemReleaseType = Literal[
    "frontend",
    "backend",
    "full_platform",
    "model_update",
    "connector_update",
    "regulatory_rule_update",
]
SystemReleaseApprovalStatus = Literal["draft", "ready_for_qa", "approved", "rejected", "released"]
DeviationSeverity = Literal["low", "medium", "high", "critical"]
DeviationSourceType = Literal[
    "validation_test",
    "production_issue",
    "data_integrity",
    "audit",
    "report",
    "ai_model",
    "connector",
    "other",
]
DeviationStatus = Literal["open", "investigation", "resolved", "closed", "rejected"]
CAPAStatus = Literal["open", "in_progress", "effectiveness_check", "closed", "canceled"]


class ValidationProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    scope: ValidationProjectScope
    validation_type: ValidationType
    status: ValidationProjectStatus = "draft"
    intended_use: str = Field(min_length=1)
    regulated_context: str | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    qa_reviewer_name: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    scope: ValidationProjectScope | None = None
    validation_type: ValidationType | None = None
    status: ValidationProjectStatus | None = None
    intended_use: str | None = Field(default=None, min_length=1)
    regulated_context: str | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    qa_reviewer_name: str | None = Field(default=None, max_length=200)
    metadata_json: dict[str, Any] | None = None


class ValidationProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    scope: ValidationProjectScope
    validation_type: ValidationType
    status: ValidationProjectStatus
    intended_use: str
    regulated_context: str | None = None
    owner_name: str | None = None
    qa_reviewer_name: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class UserRequirementSpecificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_code: str = Field(min_length=1, max_length=100)
    module: ValidationModule
    requirement_text: str = Field(min_length=1)
    criticality: ValidationCriticality
    gxp_impact: GxPImpact
    status: SpecificationStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class UserRequirementSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_project_id: int
    requirement_code: str
    module: ValidationModule
    requirement_text: str
    criticality: ValidationCriticality
    gxp_impact: GxPImpact
    status: SpecificationStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FunctionalSpecificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: int | None = Field(default=None, ge=1)
    function_code: str = Field(min_length=1, max_length=100)
    function_name: str = Field(min_length=1, max_length=240)
    function_description: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    module: ValidationModule
    status: SpecificationStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FunctionalSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_project_id: int
    requirement_id: int | None = None
    function_code: str
    function_name: str
    function_description: str
    expected_behavior: str
    module: ValidationModule
    status: SpecificationStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationRiskAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: ValidationTargetType
    target_id: int | None = Field(default=None, ge=1)
    risk_description: str = Field(min_length=1)
    severity: ValidationRiskScale
    probability: ValidationProbability
    detectability: ValidationDetectability
    risk_priority: int | None = Field(default=None, ge=1)
    mitigation: str = Field(min_length=1)
    testing_rigor: ValidationTestingRigor
    status: ValidationRiskStatus = "open"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationRiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_project_id: int
    target_type: ValidationTargetType
    target_id: int | None = None
    risk_description: str
    severity: ValidationRiskScale
    probability: ValidationProbability
    detectability: ValidationDetectability
    risk_priority: int | None = None
    mitigation: str
    testing_rigor: ValidationTestingRigor
    status: ValidationRiskStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestProtocolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    module: ValidationModule
    protocol_type: ValidationProtocolType
    status: ValidationProtocolStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_project_id: int
    protocol_code: str
    title: str
    module: ValidationModule
    protocol_type: ValidationProtocolType
    status: ValidationProtocolStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_case_code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    preconditions: str = Field(min_length=1)
    steps_json: list[dict[str, Any]] = Field(default_factory=list)
    expected_results: str = Field(min_length=1)
    linked_requirement_ids_json: list[int] = Field(default_factory=list)
    linked_risk_ids_json: list[int] = Field(default_factory=list)
    status: ValidationTestCaseStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    protocol_id: int
    test_case_code: str
    title: str
    preconditions: str
    steps_json: list[dict[str, Any]] = Field(default_factory=list)
    expected_results: str
    linked_requirement_ids_json: list[int] = Field(default_factory=list)
    linked_risk_ids_json: list[int] = Field(default_factory=list)
    status: ValidationTestCaseStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executed_by: str | None = Field(default=None, max_length=200)
    execution_status: ValidationExecutionStatus
    actual_results: str = Field(min_length=1)
    evidence_file_ids_json: list[int] = Field(default_factory=list)
    evidence_artifact_ids_json: list[int] = Field(default_factory=list)
    deviation_id: int | None = Field(default=None, ge=1)
    create_deviation_on_fail: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ValidationTestExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    test_case_id: int
    executed_by: str | None = None
    execution_status: ValidationExecutionStatus
    actual_results: str
    evidence_file_ids_json: list[int] = Field(default_factory=list)
    evidence_artifact_ids_json: list[int] = Field(default_factory=list)
    deviation_id: int | None = None
    executed_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TraceabilityMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    validation_project_id: int
    matrix_json: dict[str, Any] = Field(default_factory=dict)
    coverage_summary_json: dict[str, Any] = Field(default_factory=dict)
    missing_coverage_json: list[dict[str, Any]] = Field(default_factory=list)
    status: TraceabilityStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ElectronicSignatureRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signer_name: str = Field(min_length=1, max_length=200)
    signer_email: str | None = Field(default=None, max_length=255)
    signature_meaning: SignatureMeaning
    target_type: str = Field(min_length=1, max_length=100)
    target_id: int = Field(ge=1)
    reason: str = Field(min_length=1)
    authentication_method: str | None = Field(default=None, max_length=120)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ElectronicSignatureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    signer_name: str
    signer_email: str | None = None
    signature_meaning: SignatureMeaning
    target_type: str
    target_id: int
    reason: str
    signed_at: datetime
    authentication_method: str | None = None
    signature_hash: str = Field(min_length=64, max_length=64)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ControlledRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: ControlledRecordType
    resource_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=300)
    version: str = Field(default="1", min_length=1, max_length=64)
    status: ControlledRecordStatus = "draft"
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    content_json: dict[str, Any] | None = Field(default=None, exclude=True)
    retention_policy_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ControlledRecordNewVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    version: str | None = Field(default=None, min_length=1, max_length=64)
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    content_json: dict[str, Any] | None = Field(default=None, exclude=True)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ControlledRecordLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locked_by: str = Field(min_length=1, max_length=200)
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    reason: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ControlledRecordArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ControlledRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    record_type: ControlledRecordType
    resource_id: int | None = None
    title: str
    version: str
    status: ControlledRecordStatus
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    locked_at: datetime | None = None
    locked_by: str | None = None
    retention_policy_id: int | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RecordRetentionPolicyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=240)
    record_type: ControlledRecordType
    retention_period_years: int | None = Field(default=None, ge=0)
    archive_strategy: str = Field(min_length=1)
    legal_hold: bool = False
    status: RetentionPolicyStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class RecordRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    record_type: ControlledRecordType
    retention_period_years: int | None = None
    archive_strategy: str
    legal_hold: bool
    status: RetentionPolicyStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DataIntegrityAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: DataIntegrityScope
    scope_id: int | None = Field(default=None, ge=1)
    assessment_status: DataIntegrityStatus | None = None
    attributable_status: DataIntegrityStatus = "requires_review"
    legible_status: DataIntegrityStatus = "requires_review"
    contemporaneous_status: DataIntegrityStatus = "requires_review"
    original_status: DataIntegrityStatus = "requires_review"
    accurate_status: DataIntegrityStatus = "requires_review"
    complete_status: DataIntegrityStatus = "requires_review"
    consistent_status: DataIntegrityStatus = "requires_review"
    enduring_status: DataIntegrityStatus = "requires_review"
    available_status: DataIntegrityStatus = "requires_review"
    findings_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DataIntegrityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scope: DataIntegrityScope
    scope_id: int | None = None
    assessment_status: DataIntegrityStatus
    attributable_status: DataIntegrityStatus
    legible_status: DataIntegrityStatus
    contemporaneous_status: DataIntegrityStatus
    original_status: DataIntegrityStatus
    accurate_status: DataIntegrityStatus
    complete_status: DataIntegrityStatus
    consistent_status: DataIntegrityStatus
    enduring_status: DataIntegrityStatus
    available_status: DataIntegrityStatus
    findings_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InspectionReadinessPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    scope: InspectionPackageScope
    scope_id: int | None = Field(default=None, ge=1)
    package_status: InspectionPackageStatus = "ready_for_review"
    included_record_ids_json: list[int] = Field(default_factory=list)
    included_signature_ids_json: list[int] = Field(default_factory=list)
    included_audit_event_ids_json: list[int] = Field(default_factory=list)
    included_validation_project_ids_json: list[int] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class InspectionReadinessPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    scope: InspectionPackageScope
    scope_id: int | None = None
    package_status: InspectionPackageStatus
    included_record_ids_json: list[int] = Field(default_factory=list)
    included_signature_ids_json: list[int] = Field(default_factory=list)
    included_audit_event_ids_json: list[int] = Field(default_factory=list)
    included_validation_project_ids_json: list[int] = Field(default_factory=list)
    package_manifest_json: dict[str, Any] = Field(default_factory=dict)
    package_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SystemReleaseRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_version: str = Field(min_length=1, max_length=120)
    release_type: SystemReleaseType
    change_summary: str = Field(min_length=1)
    validation_project_id: int | None = Field(default=None, ge=1)
    test_summary_json: dict[str, Any] = Field(default_factory=dict)
    risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    approval_status: SystemReleaseApprovalStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SystemReleaseApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signer_name: str = Field(min_length=1, max_length=200)
    signer_email: str | None = Field(default=None, max_length=255)
    reason: str = Field(min_length=1)
    authentication_method: str | None = Field(default=None, max_length=120)
    signature_meaning: Literal["approved", "released"] = "approved"
    release: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SystemReleaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    release_version: str
    release_type: SystemReleaseType
    change_summary: str
    validation_project_id: int | None = None
    test_summary_json: dict[str, Any] = Field(default_factory=dict)
    risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    approval_status: SystemReleaseApprovalStatus
    created_at: datetime
    released_at: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeviationRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deviation_code: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    severity: DeviationSeverity
    source_type: DeviationSourceType
    source_id: int | None = Field(default=None, ge=1)
    status: DeviationStatus = "open"
    root_cause: str | None = None
    resolution: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DeviationRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    severity: DeviationSeverity | None = None
    status: DeviationStatus | None = None
    root_cause: str | None = None
    resolution: str | None = None
    metadata_json: dict[str, Any] | None = None


class DeviationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    deviation_code: str
    title: str
    description: str
    severity: DeviationSeverity
    source_type: DeviationSourceType
    source_id: int | None = None
    status: DeviationStatus
    root_cause: str | None = None
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CAPARecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capa_code: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    source_deviation_id: int | None = Field(default=None, ge=1)
    corrective_action: str = Field(min_length=1)
    preventive_action: str = Field(min_length=1)
    owner: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    status: CAPAStatus = "open"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CAPARecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    source_deviation_id: int | None = Field(default=None, ge=1)
    corrective_action: str | None = Field(default=None, min_length=1)
    preventive_action: str | None = Field(default=None, min_length=1)
    owner: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    status: CAPAStatus | None = None
    metadata_json: dict[str, Any] | None = None


class CAPARecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    capa_code: str
    title: str
    description: str
    source_deviation_id: int | None = None
    corrective_action: str
    preventive_action: str
    owner: str | None = None
    due_date: datetime | None = None
    status: CAPAStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


TenantType = Literal[
    "internal",
    "pilot",
    "customer",
    "sandbox",
    "demo",
    "regulated_customer",
]
TenantStatus = Literal["active", "suspended", "archived", "onboarding", "trial"]
TenantEnvironmentType = Literal["dev", "sandbox", "validation", "production", "demo"]
TenantEnvironmentStatus = Literal["active", "disabled", "archived"]
SaaSProgram = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "validation_center",
    "connectors",
    "ml_ai",
    "mobile",
    "admin",
    "cross_module",
]
SubscriptionPlanStatus = Literal["active", "deprecated", "archived"]
FeatureFlagStatus = Literal["active", "disabled", "archived"]
PilotProgramStatus = Literal["planned", "active", "completed", "paused", "failed", "archived"]
OnboardingProjectStatus = Literal[
    "not_started",
    "in_progress",
    "blocked",
    "ready_for_go_live",
    "completed",
    "archived",
]
ImplementationStage = Literal[
    "discovery",
    "security_review",
    "data_setup",
    "spectracheck_rollout",
    "regulatory_rollout",
    "reaction_rollout",
    "validation",
    "go_live",
    "renewal_review",
]
ImplementationTaskType = Literal[
    "security",
    "data_ingestion",
    "connector_setup",
    "spectracheck_configuration",
    "regulatory_configuration",
    "reaction_configuration",
    "validation",
    "training",
    "mobile_setup",
    "roi",
    "procurement",
    "other",
]
ImplementationTaskProgram = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "system",
]
ImplementationTaskStatus = Literal["open", "in_progress", "blocked", "completed", "dismissed"]
TenantIsolationMode = Literal[
    "shared_database_tenant_scoped",
    "dedicated_schema",
    "dedicated_database",
    "dedicated_deployment",
]
TenantProfileStatus = Literal["draft", "active", "requires_review"]
TenantValidationProfileStatus = Literal[
    "draft",
    "in_progress",
    "ready_for_review",
    "approved_internal",
    "not_required",
]
CustomerSuccessStatus = Literal["healthy", "watch", "at_risk", "unknown"]
ProcurementPackageType = Literal[
    "security_review",
    "validation_readiness",
    "ai_governance",
    "data_integrity",
    "roi",
    "full_procurement",
]
ProcurementPackageStatus = Literal["draft", "ready_for_review", "exported", "failed"]
TenantAuditExportScope = Literal[
    "all",
    "security",
    "validation",
    "regulatory",
    "spectracheck",
    "reaction",
    "ai_ml",
    "connectors",
]
TenantAuditExportStatus = Literal["queued", "succeeded", "failed"]


class TenantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=240)
    tenant_type: TenantType
    status: TenantStatus = "onboarding"
    primary_contact_email: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_key: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = Field(default=None, min_length=1, max_length=240)
    tenant_type: TenantType | None = None
    status: TenantStatus | None = None
    primary_contact_email: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] | None = None


class Tenant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_key: str
    display_name: str
    tenant_type: TenantType
    status: TenantStatus
    primary_contact_email: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantEnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_type: TenantEnvironmentType
    base_url: str | None = Field(default=None, max_length=500)
    status: TenantEnvironmentStatus = "active"
    data_retention_policy_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantEnvironmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_type: TenantEnvironmentType | None = None
    base_url: str | None = Field(default=None, max_length=500)
    status: TenantEnvironmentStatus | None = None
    data_retention_policy_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] | None = None


class TenantEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    environment_type: TenantEnvironmentType
    base_url: str | None = None
    status: TenantEnvironmentStatus
    data_retention_policy_id: int | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SubscriptionPlanCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    default_entitlements_json: dict[str, Any] = Field(default_factory=dict)
    status: SubscriptionPlanStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SubscriptionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    plan_key: str
    display_name: str
    description: str
    default_entitlements_json: dict[str, Any] = Field(default_factory=dict)
    status: SubscriptionPlanStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantEntitlementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: int | None = Field(default=None, ge=1)
    feature_key: str = Field(min_length=1, max_length=160)
    program: SaaSProgram
    enabled: bool = True
    limit_json: dict[str, Any] = Field(default_factory=dict)
    effective_start: datetime | None = None
    effective_end: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantEntitlementUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: int | None = Field(default=None, ge=1)
    feature_key: str | None = Field(default=None, min_length=1, max_length=160)
    program: SaaSProgram | None = None
    enabled: bool | None = None
    limit_json: dict[str, Any] | None = None
    effective_start: datetime | None = None
    effective_end: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class TenantEntitlement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    plan_id: int | None = None
    feature_key: str
    program: SaaSProgram
    enabled: bool
    limit_json: dict[str, Any] = Field(default_factory=dict)
    effective_start: datetime | None = None
    effective_end: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1)
    program: SaaSProgram
    default_enabled: bool = False
    rollout_rules_json: dict[str, Any] = Field(default_factory=dict)
    status: FeatureFlagStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_key: str | None = Field(default=None, min_length=1, max_length=160)
    display_name: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, min_length=1)
    program: SaaSProgram | None = None
    default_enabled: bool | None = None
    rollout_rules_json: dict[str, Any] | None = None
    status: FeatureFlagStatus | None = None
    metadata_json: dict[str, Any] | None = None


class FeatureFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    flag_key: str
    display_name: str
    description: str
    program: SaaSProgram
    default_enabled: bool
    rollout_rules_json: dict[str, Any] = Field(default_factory=dict)
    status: FeatureFlagStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotProgramCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1)
    status: PilotProgramStatus = "planned"
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_programs_json: list[str] = Field(default_factory=list)
    success_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    risks_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotProgramUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    objective: str | None = Field(default=None, min_length=1)
    status: PilotProgramStatus | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_programs_json: list[str] | None = None
    success_criteria_json: list[dict[str, Any]] | None = None
    risks_json: list[dict[str, Any]] | None = None
    notes_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class PilotProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    title: str
    objective: str
    status: PilotProgramStatus
    start_date: datetime | None = None
    end_date: datetime | None = None
    target_programs_json: list[str] = Field(default_factory=list)
    success_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    risks_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerOnboardingProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pilot_program_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=300)
    status: OnboardingProjectStatus = "not_started"
    owner_name: str | None = Field(default=None, max_length=200)
    customer_contact: str | None = Field(default=None, max_length=255)
    implementation_stage: ImplementationStage = "discovery"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerOnboardingProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pilot_program_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: OnboardingProjectStatus | None = None
    owner_name: str | None = Field(default=None, max_length=200)
    customer_contact: str | None = Field(default=None, max_length=255)
    implementation_stage: ImplementationStage | None = None
    metadata_json: dict[str, Any] | None = None


class CustomerOnboardingProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    pilot_program_id: int | None = None
    title: str
    status: OnboardingProjectStatus
    owner_name: str | None = None
    customer_contact: str | None = None
    implementation_stage: ImplementationStage
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ImplementationTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    task_type: ImplementationTaskType
    program: ImplementationTaskProgram
    status: ImplementationTaskStatus = "open"
    owner: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ImplementationTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    task_type: ImplementationTaskType | None = None
    program: ImplementationTaskProgram | None = None
    status: ImplementationTaskStatus | None = None
    owner: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class ImplementationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    onboarding_project_id: int
    title: str
    description: str | None = None
    task_type: ImplementationTaskType
    program: ImplementationTaskProgram
    status: ImplementationTaskStatus
    owner: str | None = None
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantDataBoundaryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isolation_mode: TenantIsolationMode
    encryption_profile: str | None = Field(default=None, max_length=160)
    storage_prefix: str | None = Field(default=None, max_length=300)
    allowed_regions_json: list[str] = Field(default_factory=list)
    data_residency_notes: str | None = None
    status: TenantProfileStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantDataBoundaryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    isolation_mode: TenantIsolationMode | None = None
    encryption_profile: str | None = Field(default=None, max_length=160)
    storage_prefix: str | None = Field(default=None, max_length=300)
    allowed_regions_json: list[str] | None = None
    data_residency_notes: str | None = None
    status: TenantProfileStatus | None = None
    metadata_json: dict[str, Any] | None = None


class TenantDataBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    isolation_mode: TenantIsolationMode
    encryption_profile: str | None = None
    storage_prefix: str | None = None
    allowed_regions_json: list[str] = Field(default_factory=list)
    data_residency_notes: str | None = None
    status: TenantProfileStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantSecurityProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sso_enabled: bool = False
    mfa_required: bool = False
    allowed_domains_json: list[str] = Field(default_factory=list)
    session_timeout_minutes: int | None = Field(default=None, ge=1)
    ip_allowlist_json: list[str] = Field(default_factory=list)
    security_frameworks_json: list[str] = Field(default_factory=list)
    risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    status: TenantProfileStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantSecurityProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sso_enabled: bool | None = None
    mfa_required: bool | None = None
    allowed_domains_json: list[str] | None = None
    session_timeout_minutes: int | None = Field(default=None, ge=1)
    ip_allowlist_json: list[str] | None = None
    security_frameworks_json: list[str] | None = None
    risk_summary_json: dict[str, Any] | None = None
    status: TenantProfileStatus | None = None
    metadata_json: dict[str, Any] | None = None


class TenantSecurityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    sso_enabled: bool
    mfa_required: bool
    allowed_domains_json: list[str] = Field(default_factory=list)
    session_timeout_minutes: int | None = None
    ip_allowlist_json: list[str] = Field(default_factory=list)
    security_frameworks_json: list[str] = Field(default_factory=list)
    risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    status: TenantProfileStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantValidationProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_required: bool = False
    validation_project_ids_json: list[int] = Field(default_factory=list)
    controlled_record_policy: str | None = None
    esignature_required: bool = False
    data_integrity_assessment_ids_json: list[int] = Field(default_factory=list)
    inspection_package_ids_json: list[int] = Field(default_factory=list)
    status: TenantValidationProfileStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantValidationProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_required: bool | None = None
    validation_project_ids_json: list[int] | None = None
    controlled_record_policy: str | None = None
    esignature_required: bool | None = None
    data_integrity_assessment_ids_json: list[int] | None = None
    inspection_package_ids_json: list[int] | None = None
    status: TenantValidationProfileStatus | None = None
    metadata_json: dict[str, Any] | None = None


class TenantValidationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    validation_required: bool
    validation_project_ids_json: list[int] = Field(default_factory=list)
    controlled_record_policy: str | None = None
    esignature_required: bool
    data_integrity_assessment_ids_json: list[int] = Field(default_factory=list)
    inspection_package_ids_json: list[int] = Field(default_factory=list)
    status: TenantValidationProfileStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerSuccessHealthScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    score: float | None = None
    status: CustomerSuccessStatus
    usage_summary_json: dict[str, Any] = Field(default_factory=dict)
    onboarding_summary_json: dict[str, Any] = Field(default_factory=dict)
    support_summary_json: dict[str, Any] = Field(default_factory=dict)
    roi_summary_json: dict[str, Any] = Field(default_factory=dict)
    blockers_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    period_start: datetime
    period_end: datetime
    spectracheck_usage_json: dict[str, Any] = Field(default_factory=dict)
    regulatory_usage_json: dict[str, Any] = Field(default_factory=dict)
    reaction_usage_json: dict[str, Any] = Field(default_factory=dict)
    reports_generated: int
    actions_completed: int
    hours_saved: float | None = None
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantRoiSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    period_start: datetime
    period_end: datetime
    total_hours_saved: float
    tasks_automated: int
    reports_generated: int
    regulatory_actions_created: int
    reaction_recommendations_approved: int
    renewal_summary_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProcurementEvidencePackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    package_type: ProcurementPackageType
    status: ProcurementPackageStatus = "ready_for_review"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ProcurementEvidencePackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    title: str
    package_type: ProcurementPackageType
    status: ProcurementPackageStatus
    package_json: dict[str, Any] = Field(default_factory=dict)
    package_html: str | None = None
    package_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantAuditExportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_scope: TenantAuditExportScope = "all"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantAuditExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    export_scope: TenantAuditExportScope
    status: TenantAuditExportStatus
    export_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TenantModuleReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int
    product_order: list[str] = Field(default_factory=list)
    modules: list[dict[str, Any]] = Field(default_factory=list)
    entitlement_summary_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[str] = Field(default_factory=list)


class TenantGoLiveReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int
    status: str
    onboarding_readiness: dict[str, Any] = Field(default_factory=dict)
    validation_readiness: dict[str, Any] = Field(default_factory=dict)
    security_profile: dict[str, Any] = Field(default_factory=dict)
    data_boundary: dict[str, Any] = Field(default_factory=dict)
    blockers_json: list[dict[str, Any]] = Field(default_factory=list)
    product_order: list[str] = Field(default_factory=list)


GoldenDatasetType = Literal[
    "spectracheck",
    "regulatory",
    "reaction_optimization",
    "cross_module",
    "mobile",
    "validation",
    "connector",
    "ai_ml",
]
GoldenDatasetSourceType = Literal[
    "internal_demo",
    "curated_literature",
    "synthetic_demo",
    "customer_pilot",
    "benchmark",
    "other",
]
GoldenDatasetStatus = Literal["draft", "ready_for_review", "approved_demo", "archived"]
GoldenScenarioType = Literal[
    "spectracheck_structure_evidence",
    "impurity_threshold_trigger",
    "residual_solvent_qnmr",
    "nitrosamine_watch",
    "regulatory_to_reaction_constraint",
    "full_product_workflow",
    "connector_import",
    "mobile_review",
    "validation_readiness",
]
GoldenScenarioStatus = Literal["draft", "ready_for_review", "approved", "archived"]
GoldenWorkflowCaseStatus = Literal["draft", "active", "archived"]
GoldenTargetModule = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "mobile",
    "validation",
]
ExpectedOutputType = Literal[
    "evidence_item",
    "regulatory_action_item",
    "reaction_constraint",
    "report_bundle",
    "ct_dossier_section",
    "review_task",
    "qc_warning",
    "mobile_summary",
    "validation_record",
    "roi_summary",
    "other",
]
PilotRunStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "requires_review",
    "accepted",
    "rejected",
]
PilotRunStepStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "requires_review",
]
ScenarioValidationStatus = Literal["pass", "fail", "warning", "not_assessed", "requires_review"]
CustomerAcceptanceScope = Literal[
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "full_platform",
]
CustomerAcceptanceProtocolStatus = Literal[
    "draft",
    "ready_for_review",
    "active",
    "completed",
    "archived",
]
CustomerAcceptanceTestStatus = Literal["not_run", "pass", "fail", "blocked", "requires_review"]
PilotSuccessMetricStatus = Literal["met", "not_met", "warning", "not_assessed"]
PilotReadinessStatus = Literal[
    "not_ready",
    "partially_ready",
    "ready_for_pilot",
    "ready_for_customer_review",
    "blocked",
]
PilotSignoffDecision = Literal["accepted", "accepted_with_limitations", "rejected", "deferred"]
DemoTenantSeedType = Literal[
    "spectracheck_demo",
    "regulatory_demo",
    "reaction_demo",
    "full_product_demo",
    "mobile_demo",
    "validation_demo",
]
DemoTenantSeedStatus = Literal["queued", "running", "succeeded", "failed", "requires_review"]
PilotEvidenceBundleStatus = Literal["draft", "ready_for_review", "exported", "failed"]


class GoldenDatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    dataset_type: GoldenDatasetType
    source_type: GoldenDatasetSourceType
    status: GoldenDatasetStatus = "draft"
    source_references_json: list[dict[str, Any]] = Field(default_factory=list)
    file_ids_json: list[int] = Field(default_factory=list)
    artifact_ids_json: list[int] = Field(default_factory=list)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GoldenDatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_key: str | None = Field(default=None, min_length=1, max_length=160)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    dataset_type: GoldenDatasetType | None = None
    source_type: GoldenDatasetSourceType | None = None
    status: GoldenDatasetStatus | None = None
    source_references_json: list[dict[str, Any]] | None = None
    file_ids_json: list[int] | None = None
    artifact_ids_json: list[int] | None = None
    warnings_json: list[dict[str, Any]] | None = None
    notes_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None


class GoldenDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    dataset_key: str
    title: str
    description: str
    dataset_type: GoldenDatasetType
    source_type: GoldenDatasetSourceType
    status: GoldenDatasetStatus
    source_references_json: list[dict[str, Any]] = Field(default_factory=list)
    file_ids_json: list[int] = Field(default_factory=list)
    artifact_ids_json: list[int] = Field(default_factory=list)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GoldenPilotScenarioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    scenario_type: GoldenScenarioType
    program_sequence_json: list[str] = Field(default_factory=list)
    dataset_ids_json: list[int] = Field(default_factory=list)
    required_inputs_json: dict[str, Any] = Field(default_factory=dict)
    expected_outputs_json: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    status: GoldenScenarioStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GoldenPilotScenarioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_key: str | None = Field(default=None, min_length=1, max_length=160)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, min_length=1)
    scenario_type: GoldenScenarioType | None = None
    program_sequence_json: list[str] | None = None
    dataset_ids_json: list[int] | None = None
    required_inputs_json: dict[str, Any] | None = None
    expected_outputs_json: dict[str, Any] | None = None
    acceptance_criteria_json: list[dict[str, Any]] | None = None
    status: GoldenScenarioStatus | None = None
    metadata_json: dict[str, Any] | None = None


class GoldenPilotScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scenario_key: str
    title: str
    description: str
    scenario_type: GoldenScenarioType
    program_sequence_json: list[str] = Field(default_factory=list)
    dataset_ids_json: list[int] = Field(default_factory=list)
    required_inputs_json: dict[str, Any] = Field(default_factory=dict)
    expected_outputs_json: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    status: GoldenScenarioStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GoldenWorkflowCaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    input_payload_json: dict[str, Any] = Field(default_factory=dict)
    expected_step_order_json: list[str] = Field(default_factory=list)
    expected_resource_links_json: list[dict[str, Any]] = Field(default_factory=list)
    expected_warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    status: GoldenWorkflowCaseStatus = "active"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class GoldenWorkflowCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scenario_id: int
    case_key: str
    title: str
    input_payload_json: dict[str, Any] = Field(default_factory=dict)
    expected_step_order_json: list[str] = Field(default_factory=list)
    expected_resource_links_json: list[dict[str, Any]] = Field(default_factory=list)
    expected_warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    status: GoldenWorkflowCaseStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExpectedOutputContractCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_key: str = Field(min_length=1, max_length=160)
    target_module: GoldenTargetModule
    expected_output_type: ExpectedOutputType
    required_fields_json: list[str] = Field(default_factory=list)
    forbidden_fields_json: list[str] = Field(default_factory=list)
    expected_statuses_json: list[str] = Field(default_factory=list)
    tolerance_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ExpectedOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scenario_id: int
    step_key: str
    target_module: GoldenTargetModule
    expected_output_type: ExpectedOutputType
    required_fields_json: list[str] = Field(default_factory=list)
    forbidden_fields_json: list[str] = Field(default_factory=list)
    expected_statuses_json: list[str] = Field(default_factory=list)
    tolerance_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DemoTenantSeedCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int = Field(ge=1)
    seed_type: DemoTenantSeedType = "full_product_demo"
    use_customer_data: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class DemoTenantSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int
    scenario_id: int | None = None
    seed_type: DemoTenantSeedType
    status: DemoTenantSeedStatus
    created_resource_ids_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    project_id: int | None = Field(default=None, ge=1)
    sample_id: int | None = Field(default=None, ge=1)
    run_label: str = Field(default="Golden scenario run", min_length=1, max_length=300)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    scenario_id: int
    tenant_id: int | None = None
    project_id: int | None = None
    sample_id: int | None = None
    run_label: str
    status: PilotRunStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary_json: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotRunStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pilot_run_id: int
    step_key: str
    module: GoldenTargetModule
    status: PilotRunStepStatus
    input_summary_json: dict[str, Any] = Field(default_factory=dict)
    output_summary_json: dict[str, Any] = Field(default_factory=dict)
    linked_resource_type: str | None = None
    linked_resource_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    notes_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotRunDetail(PilotRun):
    steps: list[PilotRunStep] = Field(default_factory=list)


class ScenarioValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pilot_run_id: int
    scenario_id: int
    contract_id: int | None = None
    validation_status: ScenarioValidationStatus
    expected_json: dict[str, Any] = Field(default_factory=dict)
    actual_json: dict[str, Any] = Field(default_factory=dict)
    differences_json: dict[str, Any] = Field(default_factory=dict)
    score: float | None = None
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerAcceptanceProtocolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    pilot_program_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=300)
    scope: CustomerAcceptanceScope
    scenario_ids_json: list[int] = Field(default_factory=list)
    acceptance_tests_json: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    status: CustomerAcceptanceProtocolStatus = "draft"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerAcceptanceProtocolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    pilot_program_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    scope: CustomerAcceptanceScope | None = None
    scenario_ids_json: list[int] | None = None
    acceptance_tests_json: list[dict[str, Any]] | None = None
    success_criteria_json: list[dict[str, Any]] | None = None
    status: CustomerAcceptanceProtocolStatus | None = None
    metadata_json: dict[str, Any] | None = None


class CustomerAcceptanceProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int | None = None
    pilot_program_id: int | None = None
    title: str
    scope: CustomerAcceptanceScope
    scenario_ids_json: list[int] = Field(default_factory=list)
    acceptance_tests_json: list[dict[str, Any]] = Field(default_factory=list)
    success_criteria_json: list[dict[str, Any]] = Field(default_factory=list)
    status: CustomerAcceptanceProtocolStatus
    created_at: datetime
    updated_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerAcceptanceTestExecute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CustomerAcceptanceTestStatus = "pass"
    executed_by: str | None = Field(default=None, max_length=200)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class CustomerAcceptanceTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    protocol_id: int
    test_key: str
    title: str
    description: str
    scenario_id: int | None = None
    expected_result: str
    status: CustomerAcceptanceTestStatus
    executed_by: str | None = None
    executed_at: datetime | None = None
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotSuccessMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pilot_run_id: int | None = None
    tenant_id: int | None = None
    metric_key: str
    metric_name: str
    metric_value: float | None = None
    metric_unit: str | None = None
    target_value: float | None = None
    status: PilotSuccessMetricStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotReadinessAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    pilot_program_id: int | None = Field(default=None, ge=1)
    onboarding_project_id: int | None = Field(default=None, ge=1)
    readiness_status: PilotReadinessStatus | None = None
    spectracheck_readiness_json: dict[str, Any] = Field(default_factory=dict)
    regulatory_readiness_json: dict[str, Any] = Field(default_factory=dict)
    reaction_readiness_json: dict[str, Any] = Field(default_factory=dict)
    connector_readiness_json: dict[str, Any] = Field(default_factory=dict)
    validation_readiness_json: dict[str, Any] = Field(default_factory=dict)
    mobile_readiness_json: dict[str, Any] = Field(default_factory=dict)
    security_readiness_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotReadinessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int | None = None
    pilot_program_id: int | None = None
    onboarding_project_id: int | None = None
    readiness_status: PilotReadinessStatus
    spectracheck_readiness_json: dict[str, Any] = Field(default_factory=dict)
    regulatory_readiness_json: dict[str, Any] = Field(default_factory=dict)
    reaction_readiness_json: dict[str, Any] = Field(default_factory=dict)
    connector_readiness_json: dict[str, Any] = Field(default_factory=dict)
    validation_readiness_json: dict[str, Any] = Field(default_factory=dict)
    mobile_readiness_json: dict[str, Any] = Field(default_factory=dict)
    security_readiness_json: dict[str, Any] = Field(default_factory=dict)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotSignoffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    pilot_run_id: int | None = Field(default=None, ge=1)
    protocol_id: int | None = Field(default=None, ge=1)
    signer_name: str = Field(min_length=1, max_length=200)
    signer_email: str | None = Field(default=None, max_length=255)
    decision: PilotSignoffDecision
    rationale: str = Field(min_length=1)
    signature_record_id: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotSignoffRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tenant_id: int | None = None
    pilot_run_id: int | None = None
    protocol_id: int | None = None
    signer_name: str
    signer_email: str | None = None
    decision: PilotSignoffDecision
    rationale: str
    signed_at: datetime
    signature_record_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotEvidenceBundleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    status: PilotEvidenceBundleStatus = "ready_for_review"
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pilot_run_id: int
    title: str
    included_resource_ids_json: dict[str, Any] = Field(default_factory=dict)
    package_json: dict[str, Any] = Field(default_factory=dict)
    package_html: str | None = None
    package_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    status: PilotEvidenceBundleStatus
    created_at: datetime
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class PilotCustomerDashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int
    product_order: list[str] = Field(default_factory=list)
    latest_readiness: dict[str, Any] = Field(default_factory=dict)
    pilot_runs: list[dict[str, Any]] = Field(default_factory=list)
    acceptance_protocols: list[dict[str, Any]] = Field(default_factory=list)
    signoffs: list[dict[str, Any]] = Field(default_factory=list)
    warnings_json: list[dict[str, Any]] = Field(default_factory=list)
