from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NMR2DExperimentType(str, Enum):
    COSY = "COSY"
    HSQC = "HSQC"
    HMQC = "HMQC"
    HMBC = "HMBC"
    UNKNOWN = "UNKNOWN"


NMR2DExperiment = NMR2DExperimentType
NMR2DNucleus = Literal["1H", "13C", "UNKNOWN"]


def _experiment_value(experiment: NMR2DExperimentType | str | None) -> str:
    if isinstance(experiment, NMR2DExperimentType):
        return experiment.value
    return str(experiment or "UNKNOWN").upper()


def _expected_f1_nucleus(experiment: NMR2DExperimentType | str | None) -> NMR2DNucleus:
    return "1H" if _experiment_value(experiment) == "COSY" else "13C"


def _shift_region(ppm: float | None, nucleus: str | None) -> str | None:
    if ppm is None:
        return None
    if nucleus == "13C":
        if ppm < 0 or ppm > 230:
            return "outside_13c_range"
        if ppm < 50:
            return "alkyl"
        if ppm < 90:
            return "heteroatom_substituted"
        if ppm < 110:
            return "alkyne_or_acetal"
        if ppm < 160:
            return "alkene_aromatic"
        return "carbonyl"
    if nucleus == "1H":
        if ppm < -0.5 or ppm > 16:
            return "outside_1h_range"
        if ppm < 3:
            return "aliphatic"
        if ppm < 5:
            return "heteroatom_or_water"
        if ppm < 6.5:
            return "alkene_anomeric"
        if ppm < 9:
            return "aromatic"
        return "aldehyde_acid_or_exchangeable"
    return None


def _near_any(value: float | None, targets: tuple[float, ...], tolerance: float) -> bool:
    return value is not None and any(abs(value - target) <= tolerance for target in targets)


def _looks_like_solvent_artifact(f2_ppm: float | None, f1_ppm: float | None, f2_nucleus: str, f1_nucleus: str) -> bool:
    proton_solvents = (7.26, 4.79, 3.31, 2.50, 1.94, 1.56, 1.50)
    carbon_solvents = (77.16, 49.0, 39.52, 128.06, 118.26)
    f2_hit = _near_any(f2_ppm, proton_solvents, 0.04) if f2_nucleus == "1H" else _near_any(f2_ppm, carbon_solvents, 0.3)
    f1_hit = _near_any(f1_ppm, proton_solvents, 0.04) if f1_nucleus == "1H" else _near_any(f1_ppm, carbon_solvents, 0.3)
    return bool(f1_hit or f2_hit)


class NMR2DPeak(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    experiment: NMR2DExperimentType = NMR2DExperimentType.UNKNOWN
    f2_ppm: float = Field(ge=-20.0, le=260.0)
    f1_ppm: float = Field(ge=-20.0, le=260.0)
    intensity: float | None = None
    volume: float | None = None
    assignment: str | None = Field(default=None, max_length=250)
    source_row: int | None = Field(default=None, ge=1)
    f2_nucleus: NMR2DNucleus = "1H"
    f1_nucleus: NMR2DNucleus | None = None
    f2_region: str | None = None
    f1_region: str | None = None
    is_diagonal: bool = False
    is_solvent_artifact: bool = False
    is_suspicious: bool = False
    warnings: list[str] = Field(default_factory=list)

    proton1_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    proton2_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    carbon_ppm: float | None = Field(default=None, ge=-20.0, le=260.0)
    linked_proton_ppm: float | None = Field(default=None, ge=-5.0, le=20.0)
    linked_carbon_ppm: float | None = Field(default=None, ge=-20.0, le=260.0)
    evidence_label: str = "review"
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def derive_peak_annotations(self) -> "NMR2DPeak":
        experiment = _experiment_value(self.experiment)
        if self.f1_nucleus is None:
            self.f1_nucleus = _expected_f1_nucleus(experiment)
        if self.f2_region is None:
            self.f2_region = _shift_region(self.f2_ppm, self.f2_nucleus)
        if self.f1_region is None:
            self.f1_region = _shift_region(self.f1_ppm, self.f1_nucleus)
        if experiment == "COSY" and abs(self.f1_ppm - self.f2_ppm) <= 0.025:
            self.is_diagonal = True
        if _looks_like_solvent_artifact(self.f2_ppm, self.f1_ppm, self.f2_nucleus, self.f1_nucleus or "UNKNOWN"):
            self.is_solvent_artifact = True
        warning_set = list(dict.fromkeys(self.warnings))
        if self.is_diagonal and "Near-diagonal COSY peak; review whether this is a diagonal artifact." not in warning_set:
            warning_set.append("Near-diagonal COSY peak; review whether this is a diagonal artifact.")
        if self.is_solvent_artifact and "Peak overlaps a common solvent/artifact shift; verify before assignment." not in warning_set:
            warning_set.append("Peak overlaps a common solvent/artifact shift; verify before assignment.")
        if self.f1_region and self.f1_region.startswith("outside_"):
            warning_set.append("F1 chemical shift is outside the usual nucleus range.")
        if self.f2_region and self.f2_region.startswith("outside_"):
            warning_set.append("F2 chemical shift is outside the usual nucleus range.")
        self.warnings = list(dict.fromkeys(warning_set))
        self.is_suspicious = bool(self.is_suspicious or self.is_diagonal or self.is_solvent_artifact or self.warnings)
        return self


class NMR2DContourPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    f1_ppm: float
    f2_ppm: float
    intensity: float


class NMR2DPreviewReport(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    filename: str
    experiment_detected: NMR2DExperimentType = NMR2DExperimentType.UNKNOWN
    peak_count: int = 0
    peaks: list[NMR2DPeak] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    source_mode: Literal[
        "processed_peak_table",
        "processed_contour_table",
        "processed_matrix_preview",
        "raw_2d_stub",
    ] = "processed_peak_table"
    experiments: list[NMR2DExperimentType] = Field(default_factory=list)
    contour_preview: list[NMR2DContourPoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def derive_preview_experiment(self) -> "NMR2DPreviewReport":
        if not self.experiments and self.experiment_detected != NMR2DExperimentType.UNKNOWN.value:
            self.experiments = [self.experiment_detected]  # type: ignore[list-item]
        if self.experiments and self.experiment_detected == NMR2DExperimentType.UNKNOWN.value:
            self.experiment_detected = self.experiments[0]
        return self


class NMR2DPreview(NMR2DPreviewReport):
    pass


class NMR2DAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    experiment_type: NMR2DExperimentType | None = None
    proton_nmr_text: str | None = None
    carbon13_text: str | None = None
    smiles: str | None = None
    solvent: str | None = None
    sample_id: str | None = None


class NMR2DCorrelationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_type: str
    observed_f2_ppm: float
    observed_f1_ppm: float
    matched_1h_peak: float | None = None
    matched_13c_peak: float | None = None
    plausibility_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class NMR2DAnalyzeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview: NMR2DPreviewReport = Field(default_factory=lambda: NMR2DPreviewReport(filename="unknown"))
    evidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    correlation_summary: dict[str, Any] = Field(default_factory=dict)
    suspicious_peak_count: int = 0
    matched_correlation_count: int = 0
    missing_reference_count: int = 0
    extra_correlation_count: int = 0
    correlations: list[NMR2DCorrelationEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NMR2DAnalysisReport(NMR2DAnalyzeResult):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    sample_id: str | None = None
    run_id: int | None = None
    smiles: str
    solvent: str | None = None
    experiments: list[NMR2DExperimentType] = Field(default_factory=list)
    peak_count: int = 0
    linked_1d_peak_count: int = 0
    correlation_score: float = Field(ge=0.0, le=1.0)
    structure_consistency_score: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    label: Literal["supportive", "review", "weak", "invalid_input"]
    peaks: list[NMR2DPeak] = Field(default_factory=list)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)


class NMR2DRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    id: int
    created_at: datetime
    user_id: int | None = None
    sample_pk: int | None = None
    filename: str
    experiment_detected: NMR2DExperimentType = NMR2DExperimentType.UNKNOWN
    peak_count: int = 0
    evidence_score: float = Field(ge=0.0, le=1.0)
    suspicious_peak_count: int = 0
    review_status: str = "pending_review"
    metadata: dict[str, Any] = Field(default_factory=dict)

    analysis_id: int | None = None
    sample_id: str | None = None
    experiments: list[NMR2DExperimentType] = Field(default_factory=list)
    overall_score: float = Field(ge=0.0, le=1.0)
    report: NMR2DAnalysisReport
