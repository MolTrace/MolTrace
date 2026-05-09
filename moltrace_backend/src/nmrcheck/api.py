from __future__ import annotations

import csv
import hashlib
import hmac
import importlib.util
import io
import json
import logging
import re
import uuid
import zipfile
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path as ApiPath,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import ai_evidence_store as ai_evidence_store
from . import ai_inference_store as ai_store
from . import analytics_store as analytics_store
from . import collaboration_store as collab_store
from . import compound_registry_store as compound_store
from . import golden_pilot_store as golden_pilot_store
from . import interoperability_store as interop_store
from . import knowledge_flywheel_store as knowledge_store
from . import method_registry_store as method_store
from . import mobile_store as mobile_store
from . import ml_model_factory_store as ml_store
from . import operations_store as ops_store
from . import orchestration_store as orch_store
from . import product_orchestration_store as product_store
from . import quality_control_store as qc_store
from . import reaction_advisor as reaction_advisor
from . import reaction_bo as reaction_bo
from . import reaction_execution as reaction_execution
from . import reaction_store as reaction_store
from . import regulatory_compliance_store as compliance_store
from . import regulatory_intelligence as regulatory_store
from . import regulatory_surveillance_store as surveillance_store
from . import spectracheck_store as sc_store
from . import tenant_saas_store as tenant_store
from . import validation_center_store as validation_store
from . import workflow_store as wf_store
from .adduct_inference import AdductInferenceError, infer_adducts_and_isotopes
from .analysis import analyze_inputs, validate_inputs
from .baseline import normalize_baseline_mode
from .candidate import compare_candidates, parse_candidate_text
from .candidate_predicted import (
    PREDICTED_NMR_MATCH_LIMITATIONS,
    match_candidates_with_predicted_nmr,
)
from .carbon13 import (
    Carbon13ParseError,
    analyze_carbon13,
    analyze_carbon13_text,
    carbon13_peaks_from_shift_values,
    parse_carbon13_processed_spectrum,
    parse_carbon13_table,
    parse_carbon13_text,
    refine_carbon13_peaks_with_context,
)
from .chemistry import structure_summary_from_smiles
from .database import (
    audit_event,
    authenticate_user,
    build_evidence_report,
    build_fid_run_report,
    build_project_dashboard,
    compare_sample_analyses,
    consume_user_action_token,
    create_job,
    create_project,
    create_project_sample,
    create_report_from_analysis,
    create_session_factory,
    create_user,
    create_user_action_token,
    create_user_session,
    export_history_csv,
    export_job_csv,
    export_job_json,
    get_admin_system_summary,
    get_analysis_by_id,
    get_fid_run_by_id,
    get_full_analysis_by_id,
    get_job_by_id,
    get_metrics_summary,
    get_project_by_id,
    get_raw_archive_by_id_or_sha,
    get_report_by_id,
    get_sample_detail,
    get_sample_timeline,
    get_user_by_token,
    init_db,
    link_project_sample_analysis,
    list_admin_users,
    list_audit_events,
    list_email_outbox,
    list_fid_run_review_decisions,
    list_fid_runs,
    list_fid_runs_for_raw_archive,
    list_job_analyses,
    list_jobs,
    list_project_samples,
    list_projects,
    list_recent_analyses,
    list_review_decisions,
    list_review_queue,
    list_sample_analyses,
    list_sample_reports,
    mark_user_verified,
    queue_email,
    revoke_all_user_tokens,
    revoke_token,
    save_analysis,
    save_fid_run,
    save_raw_archive_preview,
    set_job_backend_id,
    set_user_admin_status,
    set_user_password,
    submit_fid_run_review_decision,
    submit_review_decision,
)
from .dept import DeptAptParseError, analyze_dept_apt_preview, parse_dept_apt_table
from .exceptions import StructureParseError
from .export_raw_package import export_raw_fid_analysis_package
from .fid import (
    FIDProcessingError,
    available_fid_presets,
    fid_settings_from_preset,
    normalize_phase_mode,
    process_bruker_1d_zip,
)
from .fragmentation_tree import MSMSFragmentationTreeError, build_msms_fragmentation_tree
from .hrms import HRMSError, match_hrms_candidates, search_formulas_by_hrms
from .lcms_confidence_bridge import (
    LCMSConfidenceBridgeError,
    score_lcms_candidates_against_consensus,
)
from .lcms_consensus import LCMSFeatureFamilyConsensusError, score_lcms_feature_family_consensus
from .lcms_features import LCMSFeatureDetectionError, detect_lcms_features
from .lcms_grouping import LCMSFeatureGroupingError, group_lcms_features
from .lcms_import import LCMSImportError, import_lcms_bridge
from .models import (
    AccessTokenResponse,
    ActiveLearningCandidate,
    ActiveLearningCandidateCreate,
    ActiveLearningCandidateUpdate,
    AdminSystemSummary,
    AdminUserRecord,
    AIEvidenceItem,
    AIEvidenceModule,
    AIEvidenceReviewRequest,
    AIEvidenceReviewResponse,
    AIEvidenceStatus,
    AIGovernanceRecord,
    AIGovernanceRecordCreate,
    AIModelMonitoringSummary,
    AIServiceRegistry,
    AIServiceRegistryCreate,
    AIServiceRegistryUpdate,
    AnalysisEvidenceReport,
    AnalysisInputs,
    AnalysisJobCreate,
    AnalysisJobRecord,
    AnalysisReport,
    AnalysisValidationInputs,
    AnalyticalMethodValidationProfile,
    AnalyticalMethodValidationProfileCreate,
    AnalyticsSummary,
    ApprovalRecord,
    ApprovalRecordCreate,
    ArtifactRecord,
    AsyncJobAccepted,
    AuditEventRecord,
    AuthPageResponse,
    AutomationTaskDefinition,
    AutomationTaskDefinitionCreate,
    AutomationTaskDefinitionUpdate,
    BatchAnalysisInputs,
    BatchAnalysisReport,
    BatchRegulatoryAssessment,
    BatchRegulatoryAssessmentCreate,
    BenchmarkDataset,
    BenchmarkDatasetCandidate,
    BenchmarkDatasetCandidateCreate,
    BenchmarkDatasetCandidateUpdate,
    BenchmarkDatasetCreate,
    CAPARecord,
    CAPARecordCreate,
    CAPARecordUpdate,
    CalibrationAssessment,
    CalibrationAssessmentCreate,
    CanaryDeploymentCreate,
    CanaryDeploymentRecord,
    CanaryReviewRequest,
    CandidateComparisonRequest,
    CandidateComparisonResult,
    CandidateInput,
    CandidatePredictedNMRMatchEvidenceRequest,
    CandidatePredictedNMRMatchRequest,
    CandidatePredictedNMRMatchResult,
    Carbon13AnalysisReport,
    Carbon13Inputs,
    Carbon13UploadPreview,
    CompoundAlias,
    CompoundAliasCreate,
    CompoundBatch,
    CompoundBatchCreate,
    CompoundBatchUpdate,
    CompoundEntity,
    CompoundEntityCreate,
    CompoundEntityUpdate,
    CompoundEvidenceLink,
    CompoundEvidenceLinkCreate,
    CompoundRegistryLinkRequest,
    CompoundRegistryLinkResponse,
    CompoundRegistrySearchRequest,
    CompoundRegistrySearchResult,
    CompoundRelationship,
    CompoundRelationshipCreate,
    CompoundStructureRecord,
    CompoundStructureRecordCreate,
    ComplianceDrivenOptimizationObjective,
    ComplianceDrivenOptimizationObjectiveCreate,
    ConnectorCredentialReference,
    ConnectorCredentialReferenceCreate,
    ConnectorHealthCheck,
    ConnectorHealthCheckRequest,
    ConnectorRegistry,
    ConnectorRegistryCreate,
    ConnectorRegistryUpdate,
    ControlledRecord,
    ControlledRecordArchiveRequest,
    ControlledRecordCreate,
    ControlledRecordLockRequest,
    ControlledRecordNewVersionRequest,
    CrossModuleActionItem,
    CrossModuleActionItemCreate,
    CrossModuleActionItemUpdate,
    CrossModuleBridgeReviewRequest,
    CrossModuleCommandCenterSummary,
    CrossModuleWorkflowTemplate,
    CrossModuleWorkflowTemplateCreate,
    CTDModule3ReportBundle,
    CTDModule3ReportBundleCreate,
    CustomerOnboardingProject,
    CustomerOnboardingProjectCreate,
    CustomerOnboardingProjectUpdate,
    CustomerAcceptanceProtocol,
    CustomerAcceptanceProtocolCreate,
    CustomerAcceptanceProtocolUpdate,
    CustomerAcceptanceTest,
    CustomerAcceptanceTestExecute,
    CustomerSuccessHealthScore,
    DatasetVersion,
    DatasetVersionCreate,
    DatasetVersionUpdate,
    DataIntegrityAssessment,
    DataIntegrityAssessmentCreate,
    DebugBundle,
    DebugBundleCreate,
    DependencyCheck,
    DeploymentCandidate,
    DeploymentCandidateApprovalRequest,
    DeploymentCandidateCreate,
    DeploymentCandidateRejectRequest,
    DeploymentCandidateResponse,
    DeptAptAnalyzeResult,
    DeptAptPreviewReport,
    DeviationRecord,
    DeviationRecordCreate,
    DeviationRecordUpdate,
    DriftAlert,
    ElectronicSignatureRecord,
    ElectronicSignatureRecordCreate,
    EmailActionRequest,
    EmailOutboxRecord,
    EnvironmentCheckResponse,
    ErrorAnalysisSlice,
    ErrorAnalysisSliceCreate,
    EvidenceCommentCreate,
    EvidenceCommentRecord,
    EvidenceCommentUpdate,
    EvidenceInputProvenance,
    ExtractedAnalyticalRecord,
    ExtractedReactionRecord,
    ExtractedRegulatoryRecord,
    ExternalObjectLink,
    ExternalObjectLinkCreate,
    ExternalSystemRecord,
    ExternalSystemRecordCreate,
    FeatureFlag,
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeaturePipeline,
    FeaturePipelineCreate,
    FeatureRecord,
    FeatureRecordCreate,
    FIDPreviewReport,
    FIDProcessingPreset,
    FIDProcessingSettings,
    FIDProcessResult,
    FIDRunRecord,
    FIDRunReport,
    FIDRunReviewCreate,
    FIDRunReviewDecisionRecord,
    FileRecord,
    FileNormalizationRequest,
    FileNormalizationRun,
    FunctionalSpecification,
    FunctionalSpecificationCreate,
    DemoTenantSeed,
    DemoTenantSeedCreate,
    ExpectedOutputContract,
    ExpectedOutputContractCreate,
    FullStoredAnalysisRecord,
    GoldenDataset,
    GoldenDatasetCreate,
    GoldenDatasetUpdate,
    GoldenPilotScenario,
    GoldenPilotScenarioCreate,
    GoldenPilotScenarioUpdate,
    GoldenWorkflowCase,
    GoldenWorkflowCaseCreate,
    HRMSCandidateMatchRequest,
    HRMSCandidateMatchResult,
    HRMSFormulaSearchRequest,
    HRMSFormulaSearchResult,
    ImpurityRiskRegister,
    ImpurityRiskRegisterCreate,
    InferenceExplanation,
    InferenceExplanationCreate,
    ImplementationTask,
    ImplementationTaskCreate,
    ImplementationTaskUpdate,
    IngestionRun,
    IngestionRunCreate,
    InstrumentWatchFolder,
    InstrumentWatchFolderCreate,
    InstrumentWatchFolderScanRequest,
    InstrumentWatchFolderUpdate,
    IntegrationImportResponse,
    InspectionReadinessPackage,
    InspectionReadinessPackageCreate,
    JobEventRecord,
    JobRecord,
    JurisdictionalRequirementMap,
    JurisdictionalRequirementMapCreate,
    KnowledgeExtractionRun,
    KnowledgeExtractionRunCreate,
    KnowledgeGraphLink,
    KnowledgeGraphLinkCreate,
    KnowledgeRecordReviewRequest,
    KnowledgeRecordReviewResult,
    KnowledgeReviewTask,
    KnowledgeReviewTaskCreate,
    KnowledgeReviewTaskUpdate,
    KnowledgeSearchResult,
    KnowledgeSource,
    KnowledgeSourceCreate,
    KnowledgeSourceFile,
    KnowledgeSourceUpdate,
    LCMSConsensusCandidateBridgeRequest,
    LCMSConsensusCandidateBridgeResult,
    LCMSFeatureDetectionRequest,
    LCMSFeatureDetectionResult,
    LCMSFeatureFamilyConsensusRequest,
    LCMSFeatureFamilyConsensusResult,
    LCMSFeatureGroupingRequest,
    LCMSFeatureGroupingResult,
    LCMSFeatureGroupingRunInput,
    LCMSImportBridgeRequest,
    LCMSImportBridgeResult,
    LCMSLibraryDereplicationResult,
    ManagedFileKind,
    MappingTemplate,
    MappingTemplateCreate,
    MappingTemplateUpdate,
    MessageResponse,
    MethodComparisonRun,
    MethodComparisonRunCreate,
    MobileActionDraft,
    MobileActionDraftCreate,
    MobileActionDraftPatch,
    MobileActionQueueResponse,
    MobileCommandCenterResponse,
    MobileConfigResponse,
    MobileDashboardResponse,
    MobileDeviceSession,
    MobileDeviceSessionCreate,
    MobileDeviceSessionPatch,
    MobileJobsSummary,
    MobileNotification,
    MobileNotificationCreate,
    MobileNotificationPatch,
    MobileOfflineSafeSummary,
    MobilePushSubscription,
    MobilePushSubscriptionCreate,
    MobileReportPreview,
    MobileResourceSummary,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileViewPreferencePatch,
    MethodRegistryEntry,
    MethodRegistryEntryCreate,
    MethodRegistryEntryUpdate,
    MetricsSummary,
    MLEvaluationRun,
    MLEvaluationRunCreate,
    MLEvaluationRunResponse,
    MLModelHealthSummary,
    MLTaskDefinition,
    MLTaskDefinitionCreate,
    MLTrainingRun,
    MLTrainingRunCreate,
    MLTrainingRunResponse,
    ModelArtifact,
    ModelCard,
    ModelCardCreate,
    ModelCardUpdate,
    ModelHealthSummary,
    ModelImprovementQueueItem,
    ModelImprovementQueueItemCreate,
    ModelImprovementQueueItemUpdate,
    ModelMonitoringEvent,
    ModelMonitoringEventCreate,
    ModelRoutingDecision,
    ModelRoutingDecisionCreate,
    ModelVersion,
    ModelVersionCreate,
    ModelVersionUpdate,
    MS1AdductInferenceRequest,
    MS1AdductInferenceResult,
    MSMSAnnotationRequest,
    MSMSAnnotationResult,
    MSMSFragmentationTreeRequest,
    MSMSFragmentationTreeResult,
    ModulePriorityMap,
    ModulePriorityMapPatch,
    NitrosamineWatchRequest,
    NMRProcessedAnalyzeResponse,
    NMRProcessedPreviewResponse,
    NMRRawFIDPreviewResponse,
    NMRRawFIDProcessResponse,
    OperationalMetric,
    OrganizationCreate,
    OrganizationRecord,
    OutboundSyncJob,
    OutboundSyncJobCreate,
    OutOfDomainAssessment,
    OutOfDomainAssessmentCreate,
    PasswordResetConfirm,
    PilotCustomerDashboard,
    PilotEvidenceBundle,
    PilotEvidenceBundleCreate,
    PilotProgram,
    PilotProgramCreate,
    PilotProgramUpdate,
    PilotReadinessAssessment,
    PilotReadinessAssessmentCreate,
    PilotRun,
    PilotRunCreate,
    PilotRunDetail,
    PilotSignoffCreate,
    PilotSignoffRecord,
    PredictedNMRReport,
    PredictionAuditEntry,
    PredictionFeedbackCreate,
    PredictionFeedbackResponse,
    PredictionRequest,
    PredictionResponse,
    PredictionReviewRequest,
    PredictionRun,
    PredictionServiceConfig,
    PredictionServiceConfigCreate,
    ProductProgramOrderPatch,
    ProductProgramRegistry,
    ProcurementEvidencePackage,
    ProcurementEvidencePackageCreate,
    ProjectCreate,
    ProjectDashboardRecord,
    ProjectPermissionCreate,
    ProjectPermissionRecord,
    ProjectPermissionUpdate,
    ProjectRecord,
    ProjectSampleAnalysisLink,
    ProjectSampleCreate,
    ProjectSampleRecord,
    ProtonEvidenceReport,
    QNMRComplianceProfile,
    QNMRComplianceProfileCreate,
    QualityAssessment,
    QualityAssessmentRequest,
    QualityFinding,
    QualityFindingReviewRequest,
    QualityOverrideCreate,
    QueueWorkerStatus,
    RawArchiveExportManifest,
    RawArchiveRecord,
    RecordRetentionPolicy,
    RecordRetentionPolicyCreate,
    ReactionAdvisorReviewRequest,
    ReactionAnalyticalResult,
    ReactionAnalyticalResultCreate,
    ReactionBayesianOptimizationRun,
    ReactionBayesianOptimizationRunRequest,
    ReactionConditionCritique,
    ReactionConditionCritiqueRequest,
    ReactionCostProfile,
    ReactionCostProfileCreate,
    ReactionCostProfileUpdate,
    ReactionCycleDecisionCreate,
    ReactionCycleDecisionRecord,
    ReactionDesignSpace,
    ReactionDesignSpaceCreate,
    ReactionDesignSpaceUpdate,
    ReactionExecutionBatch,
    ReactionExecutionBatchCreate,
    ReactionExecutionBatchUpdate,
    ReactionExecutionItem,
    ReactionExecutionItemCreate,
    ReactionExecutionItemUpdate,
    ReactionExecutionStatusUpdate,
    ReactionApprovedExperimentsExportRequest,
    ReactionExperiment,
    ReactionExperimentCreate,
    ReactionExperimentEvidence,
    ReactionExperimentSpectraCheckLink,
    ReactionExperimentTableImportRequest,
    ReactionExperimentUpdate,
    ReactionLiteraturePrior,
    ReactionLiteraturePriorCreate,
    ReactionMechanisticHypothesis,
    ReactionMechanisticHypothesisCreate,
    ReactionMechanisticHypothesisUpdate,
    ReactionObjectiveProfile,
    ReactionObjectiveProfileCreate,
    ReactionObjectiveProfileUpdate,
    ReactionOptimizationAdvisorRun,
    ReactionOptimizationAdvisorRunRequest,
    ReactionOptimizationBenchmarkRequest,
    ReactionOptimizationBenchmarkRun,
    ReactionOptimizationCycle,
    ReactionOptimizationCycleCreate,
    ReactionOptimizationDebate,
    ReactionOptimizationDebateRequest,
    ReactionOptimizationRun,
    ReactionOptimizationRunRequest,
    ReactionOutcomeConfirmRequest,
    ReactionOutcomeExtractionRequest,
    ReactionOutcomeExtractionRun,
    ReactionProject,
    ReactionProjectCreate,
    ReactionProjectUpdate,
    ReactionRecommendation,
    ReactionRecommendationBatch,
    ReactionRecommendationBatchCreate,
    ReactionRecommendationConvertRequest,
    ReactionRecommendationConvertResponse,
    ReactionRecommendationCreate,
    ReactionRecommendationReview,
    ReactionSafetyConstraintProfile,
    ReactionSafetyConstraintProfileCreate,
    ReactionSafetyConstraintProfileUpdate,
    ReactionVariable,
    ReactionVariableCreate,
    ReactionVariableUpdate,
    RegulatoryActionItem,
    RegulatoryActionItemCreate,
    RegulatoryActionItemUpdate,
    RegulatoryAnswer,
    RegulatoryChangeEvent,
    RegulatoryChangeReviewRequest,
    RegulatoryCitation,
    RegulatoryConstraintSet,
    RegulatoryConstraintSetCreate,
    RegulatoryConstraintSetUpdate,
    RegulatoryDossier,
    RegulatoryDossierChangeImpact,
    RegulatoryDossierCreate,
    RegulatoryDossierUpdate,
    RegulatoryEvidenceLink,
    RegulatoryEvidenceLinkCreate,
    RegulatoryImpactAssessment,
    RegulatoryImpactAssessmentCreate,
    RegulatoryImpactNotification,
    RegulatoryImpactNotificationUpdate,
    RegulatoryImportSourceRequest,
    RegulatoryJurisdiction,
    RegulatoryJurisdictionCreate,
    RegulatoryQuery,
    RegulatoryQueryCreate,
    RegulatoryReadinessReport,
    RegulatoryReadinessReportRequest,
    RegulatoryRequirement,
    RegulatoryRequirementCreate,
    RegulatoryRequirementUpdate,
    RegulatoryReviewDecision,
    RegulatoryReviewDecisionCreate,
    RegulatoryRiskAssessment,
    RegulatoryRiskAssessmentRequest,
    RegulatoryRuleSet,
    RegulatoryRuleSetCreate,
    RegulatoryRuleUpdateProposal,
    RegulatoryRuleUpdateProposalCreate,
    RegulatoryRuleUpdateProposalReviewRequest,
    RegulatorySourceDocument,
    RegulatorySourceSearchRequest,
    RegulatorySourceSearchResult,
    RegulatorySourceStatus,
    RegulatorySourceType,
    RegulatorySourceVersion,
    RegulatorySourceVersionCompareRequest,
    RegulatorySourceVersionCompareResponse,
    RegulatorySourceWatcher,
    RegulatorySourceWatcherCreate,
    RegulatorySourceWatcherUpdate,
    RegulatorySurveillanceRun,
    RegulatorySurveillanceRunCreate,
    RegulatorySubmissionPackage,
    RegulatorySubmissionPackageCreate,
    RegulatoryToReactionBridge,
    RegulatoryToReactionBridgeCreate,
    RenewalValueReport,
    RenewalValueReportCreate,
    ReportLock,
    ReportLockRequest,
    ReportReleaseRequest,
    ResidualSolventAssessmentRequest,
    ReviewDecisionCreate,
    ReviewDecisionRecord,
    ReviewQueueItem,
    ReviewTaskCreate,
    ReviewTaskRecord,
    ReviewTaskUpdate,
    RoiSnapshot,
    SampleAliquot,
    SampleAliquotCreate,
    SampleAnalysisComparison,
    SampleDetailRecord,
    SampleReportsRecord,
    SampleTimelineRecord,
    ScientificKnowledgeGraph,
    ScientificKnowledgeGraphEdge,
    ScientificKnowledgeGraphEdgeCreate,
    ScoringProfile,
    ScoringProfileCreate,
    ScoringProfileUpdate,
    ScenarioValidationResult,
    SecureShareLinkCreate,
    SecureShareLinkRecord,
    SecurityEvent,
    SecurityEventCreate,
    SecuritySummary,
    SessionFileLinkCreate,
    SessionFileLinkRecord,
    SessionReviewerCreate,
    SessionReviewerRecord,
    SessionReviewerUpdate,
    ShadowEvaluationRun,
    ShadowEvaluationRunCreate,
    SpectroscopyToRegulatoryBridge,
    SpectroscopyToRegulatoryBridgeCreate,
    SpectraCheckImportFileRequest,
    SpectraCheckAuditEventRecord,
    SpectraCheckEvidenceCreate,
    SpectraCheckEvidenceRecord,
    SpectraCheckEvidenceUpdate,
    SpectraCheckProjectCreate,
    SpectraCheckProjectRecord,
    SpectraCheckProjectUpdate,
    SpectraCheckReportCreate,
    SpectraCheckReportRecord,
    SpectraCheckReviewCreate,
    SpectraCheckReviewDecisionRecord,
    SpectraCheckSampleCreate,
    SpectraCheckSampleRecord,
    SpectraCheckSampleUpdate,
    SpectraCheckSessionCreate,
    SpectraCheckSessionRecord,
    SpectraCheckSessionUpdate,
    SpectraCheckUnifiedEvidenceRecord,
    SpectraCheckUnifiedEvidenceSave,
    SpectralSimilarityRequest,
    SpectralSimilarityResult,
    SpectrumAnalyzeResult,
    SpectrumPreviewReport,
    StoredAnalysisRecord,
    StoredReportRecord,
    StructureElucidationReportRequest,
    StructureElucidationReportResult,
    SubscriptionPlan,
    SubscriptionPlanCreate,
    SystemReleaseApproveRequest,
    SystemReleaseRecord,
    SystemReleaseRecordCreate,
    SystemHealthResponse,
    SystemStatusResponse,
    TeamMemberCreate,
    TeamMemberRecord,
    TeamMemberUpdate,
    Tenant,
    TenantAuditExport,
    TenantAuditExportCreate,
    TenantCreate,
    TenantDataBoundary,
    TenantDataBoundaryCreate,
    TenantDataBoundaryUpdate,
    TenantEntitlement,
    TenantEntitlementCreate,
    TenantEntitlementUpdate,
    TenantEnvironment,
    TenantEnvironmentCreate,
    TenantEnvironmentUpdate,
    TenantGoLiveReadiness,
    TenantModuleReadiness,
    TenantRoiSnapshot,
    TenantSecurityProfile,
    TenantSecurityProfileCreate,
    TenantSecurityProfileUpdate,
    TenantUpdate,
    TenantUsageSummary,
    TenantValidationProfile,
    TenantValidationProfileCreate,
    TenantValidationProfileUpdate,
    ThresholdProfile,
    ThresholdProfileCreate,
    ThresholdProfileUpdate,
    TokenActionPreview,
    TraceabilityMatrix,
    TrainingDatasetCandidate,
    TrainingDatasetCandidateCreate,
    TrainingDatasetCandidateUpdate,
    UnifiedCandidateConfidenceRequest,
    UnifiedCandidateConfidenceResult,
    UnifiedEvidenceBundleConfidenceResult,
    UnifiedEvidenceBundleRequest,
    UsageEvent,
    UsageEventCreate,
    UserRequirementSpecification,
    UserRequirementSpecificationCreate,
    UserCreate,
    UserFeedbackEvent,
    UserFeedbackEventCreate,
    UserLogin,
    UserPublic,
    UserSignIn,
    UserSignUp,
    ValidationReport,
    ValidationProject,
    ValidationProjectCreate,
    ValidationProjectUpdate,
    ValidationRiskAssessment,
    ValidationRiskAssessmentCreate,
    ValidationRun,
    ValidationRunCreate,
    ValidationTestCase,
    ValidationTestCaseCreate,
    ValidationTestExecution,
    ValidationTestExecutionCreate,
    ValidationTestProtocol,
    ValidationTestProtocolCreate,
    VisualizationArtifact,
    VisualizationNormalizeRequest,
    WebhookSubscription,
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
    WorkflowAnalyticsSummary,
    WorkflowRunArtifactRecord,
    WorkflowRunCreate,
    WorkflowRunEventRecord,
    WorkflowRunRecord,
    WorkflowRunStepRecord,
    WorkflowTemplateCreate,
    WorkflowTemplateRecord,
    WorkflowTemplateUpdate,
)
from .msms import MSMSError, annotate_msms
from .nmr2d import NMR2DParseError, analyze_nmr2d_preview, parse_nmr2d_upload
from .nmr_prediction import predict_nmr_from_smiles
from .proton import analyze_proton_evidence
from .queueing import enqueue_job_processing
from .raw_vault import (
    RAW_ARCHIVE_HASH_MISMATCH_MESSAGE,
    RawVaultError,
    build_raw_upload_provenance,
    load_raw_archive_bytes,
    verify_raw_archive_integrity,
    verify_stored_raw_upload,
)
from .regulatory_report import StructureElucidationReportError, compose_structure_elucidation_report
from .settings import Settings, get_settings, validate_startup_settings
from .spectral_similarity import (
    combine_similarity_layers,
    score_nmr2d_similarity,
    score_similarity_request,
)
from .spectrum import SpectrumParseError, parse_processed_spectrum
from .unified_confidence import (
    UnifiedConfidenceError,
    build_unified_candidate_confidence,
    build_unified_candidate_confidence_from_bundle,
)
from .upload import UploadParseError, parse_batch_upload
from .visualization import normalize_artifact_record, normalize_visualization_request

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)
logger = logging.getLogger(__name__)

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"
DATA_MODE_HEADER = "X-MolTrace-Data-Mode"
GENERATED_AT_HEADER = "X-MolTrace-Generated-At"
UNAVAILABLE_WARNING = "Service temporarily unavailable"
INTERNAL_ERROR_DETAIL = "Internal server error."
PUBLIC_AUTH_REQUIRED_DETAIL = (
    "Sign in to continue. If you already signed in, your session may have expired."
)
PUBLIC_ACCESS_DENIED_DETAIL = "You do not have access to perform this action."
PUBLIC_REQUEST_FAILED_DETAIL = "Request could not be completed. Please try again."

_ERROR_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|bearer|password|passwd|secret|credential|private[_-]?key|service[_-]?account)",
    re.IGNORECASE,
)
_ERROR_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|credential|private[_-]?key)\b\s*[:=]\s*([^\s,;}\]]+)"
)
_ERROR_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_ERROR_DB_URL_RE = re.compile(
    r"(?i)\b(?:postgres(?:ql)?(?:\+\w+)?|mysql(?:\+\w+)?|mariadb(?:\+\w+)?|mssql(?:\+\w+)?|oracle(?:\+\w+)?|sqlite)://[^\s'\"<>]+"
)
_ERROR_SIGNED_URL_RE = re.compile(
    r"(?i)https?://[^\s'\"<>]*(?:x-amz-signature|signature=|sig=|access_token=|token=)[^\s'\"<>]*"
)
_ERROR_PATH_RE = re.compile(
    r"(?:(?:/(?:Users|private|tmp|var|home|app|workspace|opt|srv|mnt|Volumes)"
    r"(?:/[A-Za-z0-9._ -]+)+)|[A-Za-z]:\\[^\s'\"<>]+)"
)
_ERROR_STACK_RE = re.compile(r"(?i)(traceback \(most recent call last\)|\n\s*file \"[^\"]+\")")
_ERROR_INTERNAL_DETAIL_RE = re.compile(
    r"(?i)(backend\s+requires\s+authentication|for\s+local\s+development|"
    r"disable\s+backend\s+auth|disable_auth|disable_backend_auth|todo:|"
    r"authorization\s*:\s*bearer|bearer\s*<\s*token\s*>|bearer\s+token|"
    r"x-api-key|api[_\s-]?key|raw\s+prompt|system\s+prompt|developer\s+prompt|"
    r"chain[_\s-]?of[_\s-]?thought|\bcot\b|reasoning[_\s-]?trace|"
    r"credential\s*[:=]|secret\s*[:=]|password\s*[:=]|"
    r"private[_\s-]?key|service[_\s-]?account)"
)


@dataclass(frozen=True)
class AccessContext:
    user: UserPublic | None = None
    system_api_key: bool = False
    raw_token: str | None = None

    @property
    def user_id(self) -> int | None:
        return self.user.id if self.user is not None else None


@dataclass(frozen=True)
class AppStateView:
    session_factory: sessionmaker[Session]
    api_key: str | None
    settings: Settings


def _state(request: Request) -> AppStateView:
    return AppStateView(
        session_factory=request.app.state.session_factory,
        api_key=request.app.state.api_key,
        settings=request.app.state.settings,
    )


def _stream_text(text: str) -> Iterator[bytes]:
    yield text.encode("utf-8")


def _parse_optional_json_object(raw: str | None, *, field_name: str) -> dict[str, Any]:
    if raw is None or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object.")
    return parsed


def _orchestration_storage_root(request: Request) -> Path:
    database_url = _state(request).settings.database_url
    if database_url.startswith("sqlite:///"):
        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path and raw_path != ":memory:":
            db_path = Path(raw_path).expanduser()
            if not db_path.is_absolute():
                db_path = Path.cwd() / db_path
            return db_path.resolve().parent / "storage"
    return Path("storage").resolve()


def _stream_file_path(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            yield chunk


def _raw_fid_upload_provenance(
    request: Request,
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    user_id: int | None = None,
) -> dict[str, object]:
    try:
        provenance = build_raw_upload_provenance(
            filename=filename,
            content=content,
            storage_dir=_state(request).settings.raw_data_vault_dir,
            max_bytes=_state(request).settings.raw_archive_max_bytes,
            max_files=_state(request).settings.raw_archive_max_files,
            allowed_extensions=_state(request).settings.raw_archive_allowed_extensions,
            immutable=_state(request).settings.raw_archive_immutable,
        )
    except RawVaultError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Raw FID vault rejected the upload: {exc}",
        ) from exc
    if provenance.get("storage_path"):
        raw_archive = save_raw_archive_preview(
            _state(request).session_factory,
            provenance=provenance,
            user_id=user_id,
            content_type=content_type,
        )
        provenance = dict(provenance)
        provenance["raw_archive_db_id"] = raw_archive.archive.id
        provenance["raw_archive_record"] = raw_archive.archive.model_dump(mode="json")
        provenance["raw_archive_db_already_stored"] = raw_archive.already_stored
    else:
        provenance = dict(provenance)
        warnings = list(provenance.get("warnings") or [])
        warnings.append(
            "Raw archive was inspected without immutable vault storage; no database vault record was created."
        )
        provenance["warnings"] = warnings
    return provenance


def _metadata_only_raw_fid_provenance(
    request: Request,
    *,
    filename: str,
    content: bytes,
) -> dict[str, object]:
    try:
        provenance = build_raw_upload_provenance(
            filename=filename,
            content=content,
            storage_dir=None,
            max_bytes=_state(request).settings.raw_archive_max_bytes,
            max_files=_state(request).settings.raw_archive_max_files,
            allowed_extensions=_state(request).settings.raw_archive_allowed_extensions,
        )
    except RawVaultError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Raw FID preview rejected the upload: {exc}",
        ) from exc
    warnings = list(provenance.get("warnings") or [])
    warnings.append(
        "Legacy /fid/preview inspected this archive without permanent raw-vault storage. "
        "Use POST /raw-fid/upload followed by POST /raw-fid/{archive_id}/process for auditable processing."
    )
    provenance["warnings"] = warnings
    provenance["legacy_endpoint"] = "/fid/preview"
    provenance["recommended_workflow"] = (
        "POST /raw-fid/upload then POST /raw-fid/{archive_id}/process"
    )
    return provenance


def _raw_fid_archive_provenance_from_record(archive: RawArchiveRecord) -> dict[str, object]:
    provenance: dict[str, object] = {
        "raw_archive_id": archive.sha256,
        "raw_archive_db_id": archive.id,
        "raw_archive_record": archive.model_dump(mode="json"),
        "original_filename": archive.filename,
        "filename": archive.filename,
        "safe_filename": Path(archive.filename).name,
        "sha256": archive.sha256,
        "byte_size": archive.byte_size,
        "storage_path": archive.storage_path,
        "storage_backend": "local_raw_vault",
        "storage_status": "stored",
        "raw_data_immutable": archive.immutable,
        "raw_bytes_embedded_in_metadata": False,
        "vendor_detected": archive.vendor_detected,
        "dataset_root": archive.dataset_root,
        "required_files_present": archive.required_files_present,
        "files_found": list(archive.files_found),
        "acquisition_metadata": dict(archive.acquisition_metadata),
        "warnings": list(archive.warnings),
        "vault_record": True,
    }
    return provenance


def _raw_fid_user_scope_for_context(context: AccessContext) -> int | None:
    return _user_scope_for_context(context)


def _get_visible_raw_archive(
    request: Request, archive_id: str, context: AccessContext
) -> RawArchiveRecord:
    user_id = _raw_fid_user_scope_for_context(context)
    archive = get_raw_archive_by_id_or_sha(
        _state(request).session_factory,
        archive_id=archive_id,
        user_id=user_id,
    )
    if archive is None:
        raise HTTPException(status_code=404, detail="Raw FID archive not found.")
    return archive


def _raw_archive_integrity(archive: RawArchiveRecord) -> dict[str, object]:
    report = verify_raw_archive_integrity(archive)
    return {
        "available": report.exists,
        "sha256_verified": report.sha256_verified,
        "byte_size_matches": report.byte_size_matches,
        "byte_size": report.actual_byte_size,
        "expected_byte_size": report.expected_byte_size,
        "actual_sha256": report.actual_sha256,
        "expected_sha256": report.expected_sha256,
        "ok": report.ok,
        "warning": report.warning,
        **({"error": report.warning} if report.warning else {}),
    }


def _load_raw_archive_bytes_or_conflict(archive: RawArchiveRecord) -> bytes:
    try:
        return load_raw_archive_bytes(_raw_fid_archive_provenance_from_record(archive))
    except RawVaultError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


def _load_raw_archive_bytes_for_request(
    request: Request,
    *,
    context: AccessContext,
    archive: RawArchiveRecord,
    action: str,
) -> bytes:
    try:
        raw_bytes = load_raw_archive_bytes(
            _raw_fid_archive_provenance_from_record(archive),
            require_hash_verification=_state(
                request
            ).settings.raw_archive_require_hash_verification,
        )
    except RawVaultError as exc:
        is_hash_mismatch = str(exc) == RAW_ARCHIVE_HASH_MISMATCH_MESSAGE
        _audit_raw_fid_event(
            request,
            context=context,
            archive=archive,
            event_type="raw_fid.integrity_failure",
            message=RAW_ARCHIVE_HASH_MISMATCH_MESSAGE
            if is_hash_mismatch
            else "Raw FID archive integrity verification failed.",
            extra={"action": action, "error": str(exc)},
        )
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.hash_verified",
        message="Raw FID archive SHA-256 hash verified.",
        extra={"action": action, "byte_size": len(raw_bytes)},
    )
    return raw_bytes


def _upload_http_400(exc: Exception, *, operation: str) -> HTTPException:
    if isinstance(exc, PydanticValidationError):
        messages: list[str] = []
        for error in exc.errors()[:3]:
            loc = ".".join(str(item) for item in error.get("loc", ())) or "value"
            messages.append(f"{loc}: {error.get('msg', 'invalid value')}")
        detail = f"{operation} produced data outside the accepted upload range. " + "; ".join(
            messages
        )
    else:
        detail = str(exc) or f"{operation} failed."
    return HTTPException(status_code=400, detail=detail)


def _manual_carbon13_peaks_from_json(raw: str | None, *, solvent: str | None) -> list | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Carbon13ParseError("Reviewed ¹³C peak list must be valid JSON.") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("peaks")
    if not isinstance(parsed, list):
        raise Carbon13ParseError(
            "Reviewed ¹³C peak list must be a JSON list or an object with a peaks list."
        )
    shifts: list[float | tuple[float, float | None]] = []
    for item in parsed:
        if isinstance(item, dict):
            raw_shift = (
                item.get("shift_ppm") or item.get("ppm") or item.get("shift") or item.get("delta")
            )
            raw_intensity = item.get("intensity") or item.get("height") or item.get("area")
        elif isinstance(item, (list, tuple)) and item:
            raw_shift = item[0]
            raw_intensity = item[1] if len(item) > 1 else None
        else:
            raw_shift = item
            raw_intensity = None
        try:
            shift = float(str(raw_shift).strip())
        except (TypeError, ValueError):
            continue
        intensity: float | None = None
        if raw_intensity is not None:
            try:
                intensity = float(str(raw_intensity).strip())
            except (TypeError, ValueError):
                intensity = None
        shifts.append((shift, intensity))
    if not shifts:
        raise Carbon13ParseError("Reviewed ¹³C peak list did not contain any valid shifts.")
    return carbon13_peaks_from_shift_values(shifts, solvent=solvent)


def _maybe_record_email(
    request: Request, *, to_email: str, subject: str, body: str, purpose: str | None = None
) -> None:
    state = _state(request)
    if state.settings.email_backend == "console":
        print(
            json.dumps(
                {"to": to_email, "subject": subject, "body": body, "purpose": purpose}, indent=2
            )
        )
        return
    queue_email(
        state.session_factory, to_email=to_email, subject=subject, body=body, purpose=purpose
    )


def _build_absolute_url(base_url: str, path_and_query: str) -> str:
    return f"{base_url.rstrip('/')}{path_and_query}"


def _pretty_nmr_label_text(text: str | None) -> str:
    return str(text or "").replace("13C", "¹³C").replace("1H", "¹H")


def _render_evidence_report_html(report: AnalysisEvidenceReport) -> str:
    analysis = report.analysis
    structure = report.structure
    peaks = report.parsed_peaks
    review_decisions = report.review_decisions
    audit_events = report.audit_events
    notes = report.confidence_notes
    impurity_candidates = report.impurity_candidates
    peak_rows = "".join(
        f"<tr><td>{html_escape(str(peak.shift_ppm))}</td><td>{html_escape(peak.multiplicity)}</td><td>{html_escape(', '.join(str(v) for v in peak.j_values_hz) or '—')}</td><td>{html_escape(str(peak.integration_h))}</td></tr>"
        for peak in peaks
    )
    notes_html = (
        "".join(f"<li>{html_escape(note)}</li>" for note in notes) or "<li>No notes recorded.</li>"
    )
    impurity_html = (
        "".join(f"<li>{html_escape(note)}</li>" for note in impurity_candidates)
        or "<li>No likely impurity candidates were preserved in this stored record.</li>"
    )
    decisions_html = (
        "".join(
            f"<tr><td>{html_escape(decision.action)}</td><td>{html_escape(decision.new_status)}</td><td>{html_escape(decision.comment or '—')}</td><td>{html_escape(decision.created_at.isoformat())}</td></tr>"
            for decision in review_decisions
        )
        or "<tr><td colspan='4'>No reviewer decisions recorded.</td></tr>"
    )
    audit_html = (
        "".join(
            f"<tr><td>{html_escape(event.event_type)}</td><td>{html_escape(event.message)}</td><td>{html_escape(event.created_at.isoformat())}</td></tr>"
            for event in audit_events
        )
        or "<tr><td colspan='3'>No audit events recorded.</td></tr>"
    )
    evidence_confidence_score = 0.0
    evidence_confidence_score += 0.25 if structure.formula else 0.0
    evidence_confidence_score += 0.25 if peaks else 0.0
    evidence_confidence_score += 0.2 if analysis.review_status == "approved" else 0.1
    evidence_confidence_score += min(float(analysis.confidence or 0), 1.0) * 0.3
    evidence_confidence_score = round(min(evidence_confidence_score, 1.0), 2)
    raw_fid_processing = report.audit_metadata.get("raw_fid_processing")
    fid_processing_html = ""
    if isinstance(raw_fid_processing, dict):
        processing_params = raw_fid_processing.get("processing_parameters")
        acquisition_params = raw_fid_processing.get("acquisition_parameters")
        files_found = raw_fid_processing.get("raw_dataset_files_found")
        extracted_peaks = raw_fid_processing.get("extracted_peak_list")
        qa_diagnostics = raw_fid_processing.get("qa_diagnostics")
        fid_rows = [
            ("Vendor format", raw_fid_processing.get("vendor_format_detected")),
            ("Processing preset", raw_fid_processing.get("selected_preset")),
            ("Nucleus", raw_fid_processing.get("nucleus")),
            ("Solvent", raw_fid_processing.get("solvent")),
            ("Reference ppm", raw_fid_processing.get("reference_ppm")),
            (
                "Raw dataset files found",
                json.dumps(files_found, sort_keys=True) if isinstance(files_found, dict) else None,
            ),
            (
                "Digital-filter correction",
                raw_fid_processing.get("digital_filter_correction_status"),
            ),
            ("Group delay correction", raw_fid_processing.get("group_delay_correction_applied")),
            ("Automatic phasing", raw_fid_processing.get("automatic_phase_correction")),
            (
                "Automatic baseline correction",
                raw_fid_processing.get("automatic_baseline_correction"),
            ),
            (
                "FID QA diagnostics",
                json.dumps(qa_diagnostics, sort_keys=True)
                if isinstance(qa_diagnostics, dict)
                else None,
            ),
            ("Reviewer signoff required", raw_fid_processing.get("reviewer_signoff_required")),
            ("Human review status", raw_fid_processing.get("human_review_status")),
            (
                "Extracted peaks",
                len(extracted_peaks) if isinstance(extracted_peaks, list) else None,
            ),
            (
                "Processing parameters",
                json.dumps(processing_params, sort_keys=True)
                if isinstance(processing_params, dict)
                else None,
            ),
            (
                "Acquisition parameters",
                json.dumps(acquisition_params, sort_keys=True)
                if isinstance(acquisition_params, dict)
                else None,
            ),
        ]
        fid_body = "".join(
            f"<tr><td>{html_escape(label)}</td><td>{html_escape(str(value if value is not None else '—'))}</td></tr>"
            for label, value in fid_rows
        )
        fid_processing_html = f"""
      <section class="card">
        <h2 style="margin-top:0;">Raw FID processing assumptions</h2>
        <table>
          <tbody>{fid_body}</tbody>
        </table>
      </section>"""
    nmr2d_sections = report.nmr2d_evidence
    nmr2d_evidence_html = ""
    if nmr2d_sections:
        nmr2d_cards: list[str] = []
        for section in nmr2d_sections:
            score_components = json.dumps(section.score_components, sort_keys=True)
            warnings = "; ".join(section.warnings) or "—"
            cosy_notes = "; ".join(section.cosy_connectivity_notes) or "—"
            direct_notes = "; ".join(section.hsqc_hmqc_direct_attachment_notes) or "—"
            hmbc_notes = "; ".join(section.hmbc_long_range_notes) or "—"
            missing_extra_notes = "; ".join(section.missing_extra_correlation_notes) or "—"
            dept_type_summary = json.dumps(section.dept_apt_type_summary, sort_keys=True)
            nmr2d_cards.append(
                f"""
        <div class="card">
          <h3 style="margin-top:0;">Run #{html_escape(str(section.run_id))} · {html_escape(section.experiment_type)}</h3>
          <div class="grid">
            <div class="metric"><div class="label">Experiment type</div><div class="value">{html_escape(section.experiment_type)}</div></div>
            <div class="metric"><div class="label">Peak count</div><div class="value">{html_escape(str(section.peak_count))}</div></div>
            <div class="metric"><div class="label">Matched correlations</div><div class="value">{html_escape(str(section.matched_correlations))}</div></div>
            <div class="metric"><div class="label">Suspicious correlations</div><div class="value">{html_escape(str(section.suspicious_correlations))}</div></div>
            <div class="metric"><div class="label">Evidence score</div><div class="value">{html_escape(str(section.evidence_score))}</div></div>
            <div class="metric"><div class="label">Human review status</div><div class="value">{html_escape(section.human_review_status)}</div></div>
            <div class="metric"><div class="label">DEPT/APT experiment</div><div class="value">{html_escape(section.dept_apt_experiment_type or "—")}</div></div>
            <div class="metric"><div class="label">Typed DEPT/APT peaks</div><div class="value">{html_escape(str(section.dept_apt_typed_peak_count))}</div></div>
            <div class="metric"><div class="label">Matched 13C count</div><div class="value">{html_escape(str(section.dept_apt_matched_carbon13_count))}</div></div>
            <div class="metric"><div class="label">DEPT/APT score</div><div class="value">{html_escape(str(section.dept_apt_consistency_score if section.dept_apt_consistency_score is not None else "—"))}</div></div>
            <div class="metric"><div class="label">HSQC/HMQC DEPT support</div><div class="value">{html_escape(str(section.hsqc_hmqc_dept_apt_supported_correlations))}</div></div>
            <div class="metric"><div class="label">HSQC/HMQC DEPT conflicts</div><div class="value">{html_escape(str(section.hsqc_hmqc_dept_apt_conflicting_correlations))}</div></div>
            <div class="metric"><div class="label">HMBC DEPT context</div><div class="value">{html_escape(str(section.hmbc_dept_apt_contextual_correlations))}</div></div>
          </div>
          <table style="margin-top:.85rem;">
            <tbody>
              <tr><td>COSY connectivity notes</td><td>{html_escape(cosy_notes)}</td></tr>
              <tr><td>HSQC/HMQC direct attachment notes</td><td>{html_escape(direct_notes)}</td></tr>
              <tr><td>HMBC long-range notes</td><td>{html_escape(hmbc_notes)}</td></tr>
              <tr><td>Missing/extra correlation notes</td><td>{html_escape(missing_extra_notes)}</td></tr>
              <tr><td>DEPT/APT type summary</td><td><code>{html_escape(dept_type_summary)}</code></td></tr>
              <tr><td>APT convention warning</td><td>{html_escape(section.dept_apt_apt_convention_warning or "—")}</td></tr>
              <tr><td>Warnings</td><td>{html_escape(warnings)}</td></tr>
              <tr><td>Score components</td><td><code>{html_escape(score_components)}</code></td></tr>
              <tr><td>2D evidence link</td><td>{html_escape(section.report_url)}</td></tr>
            </tbody>
          </table>
        </div>"""
            )
        nmr2d_evidence_html = f"""
      <section class="card">
        <h2 style="margin-top:0;">2D NMR Evidence</h2>
        <p>2D NMR evidence is supportive connectivity evidence and requires human review.</p>
      </section>
      {"".join(nmr2d_cards)}"""
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NMRCheck Evidence Report #{analysis.id}</title>
    <style>
      body {{ font-family: Inter, Arial, sans-serif; margin: 0; background: #f6f8fc; color: #172033; }}
      main {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem; }}
      .hero {{ background: linear-gradient(135deg,#173a9a 0%,#2855d9 70%,#6a88ff 100%); color: white; border-radius: 22px; padding: 1.25rem 1.4rem; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .8rem; margin-top: 1rem; }}
      .card {{ background: white; border: 1px solid #dce2ee; border-radius: 16px; padding: 1rem; margin-top: 1rem; }}
      .metric {{ border: 1px solid #dce2ee; border-radius: 14px; padding: .8rem; background: #fff; }}
      .label {{ color: #5d6b82; font-size: .82rem; text-transform: uppercase; }}
      .value {{ margin-top: .35rem; font-size: 1.1rem; font-weight: 700; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ text-align: left; padding: .6rem .55rem; border-bottom: 1px solid #dce2ee; }}
      th {{ background: #f5f7fc; color: #5d6b82; }}
      code, pre {{ background: #0e1528; color: #d8e0ff; border-radius: 12px; padding: .8rem; display: block; overflow: auto; }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1 style="margin:0 0 .35rem;">Evidence Report</h1>
        <p style="margin:.2rem 0 0;">Analysis #{analysis.id} · {html_escape(analysis.sample_id or "Unlabeled sample")} · {html_escape(analysis.label)}</p>
      </section>
      <section class="grid">
        <div class="metric"><div class="label">Sample ID</div><div class="value">{html_escape(analysis.sample_id or "—")}</div></div>
        <div class="metric"><div class="label">Solvent</div><div class="value">{html_escape(analysis.solvent or "—")}</div></div>
        <div class="metric"><div class="label">Review status</div><div class="value">{html_escape(analysis.review_status)}</div></div>
        <div class="metric"><div class="label">Confidence</div><div class="value">{html_escape(str(analysis.confidence))}</div></div>
        <div class="metric"><div class="label">Time saved</div><div class="value">{html_escape(str(report.time_saved_estimate))} h</div></div>
        <div class="metric"><div class="label">Formula</div><div class="value">{html_escape(structure.formula)}</div></div>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Parsed ¹H NMR text</h2>
        <pre>{html_escape(_pretty_nmr_label_text(report.parsed_nmr_text))}</pre>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Structure summary</h2>
        <div class="grid">
          <div class="metric"><div class="label">Molecular weight</div><div class="value">{html_escape(str(structure.molecular_weight))}</div></div>
          <div class="metric"><div class="label">Total H</div><div class="value">{html_escape(str(structure.total_hydrogens))}</div></div>
          <div class="metric"><div class="label">Non-labile H</div><div class="value">{html_escape(str(structure.non_labile_hydrogens))}</div></div>
          <div class="metric"><div class="label">Aromatic H</div><div class="value">{html_escape(str(structure.aromatic_protons))}</div></div>
          <div class="metric"><div class="label">Aliphatic H</div><div class="value">{html_escape(str(structure.aliphatic_protons))}</div></div>
        </div>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Evidence confidence</h2>
        <div class="grid">
          <div class="metric"><div class="label">Confidence score</div><div class="value">{html_escape(str(evidence_confidence_score))}</div></div>
          <div class="metric"><div class="label">Structure parsed</div><div class="value">{html_escape("yes" if structure.formula else "no")}</div></div>
          <div class="metric"><div class="label">NMR evidence parsed</div><div class="value">{html_escape("yes" if peaks else "no")}</div></div>
          <div class="metric"><div class="label">Review status</div><div class="value">{html_escape(analysis.review_status)}</div></div>
          <div class="metric"><div class="label">Reviewer decisions</div><div class="value">{html_escape(str(len(review_decisions)))}</div></div>
        </div>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Matched peak list</h2>
        <table>
          <thead><tr><th>Shift (ppm)</th><th>Multiplicity</th><th>Coupling Constant (Hz)</th><th>Integration</th></tr></thead>
          <tbody>{peak_rows or "<tr><td colspan='4'>No peaks available.</td></tr>"}</tbody>
        </table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Confidence notes</h2>
        <ul>{notes_html}</ul>
      </section>
      {nmr2d_evidence_html}
      {fid_processing_html}
      <section class="card">
        <h2 style="margin-top:0;">Unmatched / impurity candidates</h2>
        <ul>{impurity_html}</ul>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Reviewer decisions</h2>
        <table>
          <thead><tr><th>Action</th><th>Status</th><th>Comment</th><th>Created</th></tr></thead>
          <tbody>{decisions_html}</tbody>
        </table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Audit trail</h2>
        <table>
          <thead><tr><th>Event</th><th>Message</th><th>Created</th></tr></thead>
          <tbody>{audit_html}</tbody>
        </table>
      </section>
    </main>
  </body>
</html>"""


def _render_fid_run_report_html(report: FIDRunReport) -> str:
    run = report.run
    metadata = run.processing_metadata
    qa = report.qa_diagnostics
    decision_rows = (
        "".join(
            f"<tr><td>{html_escape(decision.action)}</td><td>{html_escape(decision.previous_status)}</td><td>{html_escape(decision.new_status)}</td><td>{html_escape(decision.comment or '—')}</td><td>{html_escape(decision.created_at.isoformat())}</td></tr>"
            for decision in report.review_decisions
        )
        or "<tr><td colspan='5'>No FID-run reviewer decisions recorded.</td></tr>"
    )
    peak_rows = (
        "".join(
            f"<tr><td>{html_escape(str(peak.shift_ppm))}</td><td>{html_escape(peak.multiplicity)}</td><td>{html_escape(', '.join(str(v) for v in peak.j_values_hz) or '—')}</td><td>{html_escape(str(peak.integration_h))}</td></tr>"
            for peak in report.inferred_peak_list
        )
        or "<tr><td colspan='4'>No peaks inferred.</td></tr>"
    )
    provenance_rows = "".join(
        f"<tr><td>{html_escape(str(key))}</td><td>{html_escape(json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value))}</td></tr>"
        for key, value in report.raw_fid_provenance.items()
    )
    assumption_rows = "".join(
        f"<tr><td>{html_escape(str(key))}</td><td>{html_escape(json.dumps(value, sort_keys=True) if isinstance(value, dict) else str(value))}</td></tr>"
        for key, value in report.processing_assumptions.items()
    )
    qa_rows = "".join(
        f"<tr><td>{html_escape(label)}</td><td>{html_escape(str(value))}</td></tr>"
        for label, value in [
            ("Quality label", qa.quality_label),
            ("Quality score", qa.quality_score),
            ("Dynamic range", qa.dynamic_range),
            ("Noise estimate", qa.noise_estimate),
            ("Baseline offset ratio", qa.baseline_offset_ratio),
            ("Clipping proxy", qa.saturation_clipping_proxy),
            ("Point count", qa.point_count),
            ("Warnings", "; ".join(qa.warnings) or "—"),
        ]
    )
    reference_selection = json.dumps(metadata.reference_peak_selection, sort_keys=True)
    fid_evidence_confidence = round(
        min(
            1.0,
            float(qa.quality_score or 0) * 0.55
            + (0.2 if report.inferred_peak_list else 0.0)
            + (0.15 if run.review_status == "approved" else 0.05)
            + min(len(report.review_decisions), 2) * 0.05,
        ),
        2,
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>NMRCheck FID Run Report #{run.id}</title>
    <style>
      body {{ font-family: Inter, Arial, sans-serif; margin: 0; background: #f6f8fc; color: #172033; }}
      main {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem; }}
      .hero {{ background: #173a9a; color: white; border-radius: 18px; padding: 1.2rem 1.4rem; }}
      .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .8rem; margin-top: 1rem; }}
      .card {{ background: white; border: 1px solid #dce2ee; border-radius: 12px; padding: 1rem; margin-top: 1rem; }}
      .metric {{ border: 1px solid #dce2ee; border-radius: 10px; padding: .8rem; background: #fff; }}
      .label {{ color: #5d6b82; font-size: .82rem; text-transform: uppercase; }}
      .value {{ margin-top: .35rem; font-size: 1.1rem; font-weight: 700; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ text-align: left; padding: .6rem .55rem; border-bottom: 1px solid #dce2ee; vertical-align: top; }}
      th {{ background: #f5f7fc; color: #5d6b82; }}
      pre {{ background: #0e1528; color: #d8e0ff; border-radius: 10px; padding: .8rem; overflow: auto; }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero">
        <h1 style="margin:0 0 .35rem;">FID Run Evidence Report</h1>
        <p style="margin:.2rem 0 0;">Run #{run.id} · {html_escape(run.sample_id or "Unlabeled sample")} · {html_escape(run.review_status)}</p>
      </section>
      <section class="grid">
        <div class="metric"><div class="label">Preset</div><div class="value">{html_escape(run.selected_preset)}</div></div>
        <div class="metric"><div class="label">Quality</div><div class="value">{html_escape(run.quality_label)}</div></div>
        <div class="metric"><div class="label">Review status</div><div class="value">{html_escape(run.review_status)}</div></div>
        <div class="metric"><div class="label">Reviewer</div><div class="value">{html_escape(str(run.reviewer_user_id or "—"))}</div></div>
        <div class="metric"><div class="label">Reviewed</div><div class="value">{html_escape(run.reviewed_at.isoformat() if run.reviewed_at else "—")}</div></div>
        <div class="metric"><div class="label">Decisions</div><div class="value">{html_escape(str(len(report.review_decisions)))}</div></div>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Reviewer comment</h2>
        <p>{html_escape(run.reviewer_comment or "No reviewer comment recorded.")}</p>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Evidence confidence</h2>
        <div class="grid">
          <div class="metric"><div class="label">Confidence score</div><div class="value">{html_escape(str(fid_evidence_confidence))}</div></div>
          <div class="metric"><div class="label">Peak evidence</div><div class="value">{html_escape(str(len(report.inferred_peak_list)))}</div></div>
          <div class="metric"><div class="label">QA score</div><div class="value">{html_escape(str(qa.quality_score))}</div></div>
          <div class="metric"><div class="label">Review status</div><div class="value">{html_escape(run.review_status)}</div></div>
          <div class="metric"><div class="label">Reviewer decisions</div><div class="value">{html_escape(str(len(report.review_decisions)))}</div></div>
        </div>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Raw FID provenance</h2>
        <table><tbody>{provenance_rows}</tbody></table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Processing assumptions</h2>
        <table><tbody>{assumption_rows}<tr><td>Single reference peak</td><td>{html_escape(reference_selection)}</td></tr></tbody></table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">QA diagnostics</h2>
        <table><tbody>{qa_rows}</tbody></table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Inferred peak list</h2>
        <table>
          <thead><tr><th>Shift (ppm)</th><th>Multiplicity</th><th>Coupling Constant (Hz)</th><th>Integration</th></tr></thead>
          <tbody>{peak_rows}</tbody>
        </table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Reviewer decisions</h2>
        <table>
          <thead><tr><th>Action</th><th>Previous</th><th>New</th><th>Comment</th><th>Created</th></tr></thead>
          <tbody>{decision_rows}</tbody>
        </table>
      </section>
      <section class="card">
        <h2 style="margin-top:0;">Generated ¹H NMR text</h2>
        <pre>{html_escape(_pretty_nmr_label_text(run.preview.inferred_nmr_text or "No generated peak text."))}</pre>
      </section>
    </main>
  </body>
</html>"""


def _build_fid_run_package(report: FIDRunReport) -> tuple[bytes, bool]:
    metadata = report.run.processing_metadata
    provenance = dict(metadata.raw_upload_provenance)
    original_available = verify_stored_raw_upload(provenance)
    manifest = RawArchiveExportManifest(
        exported_at=datetime.now(UTC),
        raw_archive=provenance.get("raw_archive_record"),
        raw_archive_id=provenance.get("raw_archive_id"),
        sha256=provenance.get("sha256"),
        original_filename=provenance.get("original_filename") or provenance.get("filename"),
        storage_backend=provenance.get("storage_backend"),
        include_original_archive=original_available,
        sha256_verified=original_available,
        files=["analysis.json", "processing_metadata.json", "raw_upload_provenance.json"],
        warnings=list(provenance.get("warnings") or []),
    )
    buffer = io.BytesIO()
    original_included = False
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "analysis.json",
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        )
        archive.writestr(
            "processing_metadata.json",
            json.dumps(metadata.model_dump(mode="json"), indent=2, sort_keys=True),
        )
        archive.writestr(
            "raw_upload_provenance.json",
            json.dumps(provenance, indent=2, sort_keys=True),
        )
        archive.writestr(
            "raw_archive_export_manifest.json",
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        )
        archive.writestr(
            "README.txt",
            "\n".join(
                [
                    "NMRCheck raw FID evidence package",
                    "",
                    "The original raw FID archive is content-addressed by SHA-256.",
                    "Processing, phase correction, baseline correction, peak picking, and review decisions are derivative metadata.",
                    "The application does not overwrite the uploaded raw binary archive.",
                    "",
                    f"Raw SHA-256: {provenance.get('sha256') or 'not recorded'}",
                    f"Original included: {'yes' if original_available else 'no'}",
                ]
            ),
        )
        if original_available:
            path = Path(str(provenance["storage_path"])).expanduser()
            safe_name = str(provenance.get("safe_filename") or path.name)
            archive.write(path, f"original/{safe_name}")
            original_included = True
        else:
            archive.writestr(
                "original/RAW_UPLOAD_NOT_EMBEDDED.txt",
                "The original archive was not available in local immutable storage for this export. "
                "Use raw_upload_provenance.json to verify the expected SHA-256 and object key.",
            )
    return (buffer.getvalue(), original_included)


def _build_raw_archive_export_package(
    archive: RawArchiveRecord,
    *,
    latest_report: FIDRunReport | None,
    audit_trail: list[AuditEventRecord] | None = None,
    original_archive_bytes: bytes | None = None,
    original_archive_error: str | None = None,
) -> tuple[bytes, bool]:
    warnings = list(archive.warnings)
    if original_archive_error:
        warnings.append(original_archive_error)
    if original_archive_bytes is None and original_archive_error is None:
        try:
            original_archive_bytes = _load_raw_archive_bytes_or_conflict(archive)
        except HTTPException as exc:
            warnings.append(str(exc.detail))
    original_included = original_archive_bytes is not None
    run = latest_report.run if latest_report is not None else None
    analysis_payload = (
        latest_report.model_dump(mode="json")
        if latest_report is not None
        else {
            "raw_archive_id": archive.sha256,
            "message": "No derived FID processing run is available for this raw archive yet.",
        }
    )
    payload, _manifest = export_raw_fid_analysis_package(
        raw_archive=archive,
        original_archive_bytes=original_archive_bytes,
        original_filename=archive.filename,
        analysis=analysis_payload,
        processing_recipe=run.processing_recipe if run is not None else {},
        acquisition_metadata=archive.acquisition_metadata,
        peak_list=run.processing_metadata.extracted_peak_list if run is not None else [],
        spectrum_preview=run.preview if run is not None else {},
        evidence_report=latest_report
        or {
            "raw_archive": archive.model_dump(mode="json"),
            "processing_run_available": False,
        },
        audit_trail=audit_trail or [],
        warnings=warnings,
    )
    return payload, original_included


def _raw_archive_audit_trail(
    request: Request,
    *,
    context: AccessContext,
    archive: RawArchiveRecord,
    limit: int = 500,
) -> list[AuditEventRecord]:
    actor_user_id = _raw_fid_user_scope_for_context(context)
    events = list_audit_events(
        _state(request).session_factory,
        limit=limit,
        actor_user_id=actor_user_id,
    )
    return [
        event
        for event in events
        if event.metadata.get("raw_archive_id") == archive.sha256
        or event.metadata.get("sha256") == archive.sha256
        or event.metadata.get("raw_archive_db_id") == archive.id
    ]


async def get_optional_access_context(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    bearer_token: str | None = Depends(oauth2_scheme),
    access_token: str | None = Query(default=None, alias="access_token"),
) -> AccessContext | None:
    state = _state(request)
    if state.settings.local_auth_disabled:
        return AccessContext(system_api_key=True)
    if x_api_key is not None:
        if state.api_key and hmac.compare_digest(x_api_key, state.api_key):
            return AccessContext(system_api_key=True)
        raise HTTPException(status_code=401, detail=PUBLIC_AUTH_REQUIRED_DETAIL)
    token_value = bearer_token or access_token
    if token_value:
        user = get_user_by_token(state.session_factory, token_value)
        if user is None:
            raise HTTPException(status_code=401, detail=PUBLIC_AUTH_REQUIRED_DETAIL)
        return AccessContext(user=user, raw_token=token_value)
    return None


async def require_access_context(
    context: AccessContext | None = Depends(get_optional_access_context),
) -> AccessContext:
    if context is None:
        raise HTTPException(status_code=401, detail=PUBLIC_AUTH_REQUIRED_DETAIL)
    return context


async def require_authenticated_user(
    context: AccessContext = Depends(require_access_context),
) -> UserPublic:
    if context.user is None:
        raise HTTPException(status_code=403, detail=PUBLIC_ACCESS_DENIED_DETAIL)
    return context.user


def _estimate_hours_saved(settings: Settings, *, parsed_peak_count: int) -> float:
    baseline_minutes = settings.default_analysis_minutes_saved
    if parsed_peak_count <= 0:
        return round(settings.default_validation_minutes_saved / 60.0, 2)
    scaled = baseline_minutes + min(parsed_peak_count, 12) * 0.25
    return round(scaled / 60.0, 2)


def _spectrum_structure_targets(smiles: str | None) -> tuple[int | None, int | None]:
    if smiles is None:
        return (None, None)
    candidate = smiles.strip()
    if not candidate:
        return (None, None)
    try:
        summary = structure_summary_from_smiles(candidate)
    except StructureParseError:
        return (None, None)
    return (summary.total_hydrogens, summary.non_labile_hydrogens)


def _validation_detail(errors: list[str]) -> str | list[str]:
    if not errors:
        return "Invalid analysis input."
    if len(errors) == 1:
        return errors[0]
    return errors


def _ensure_analysis_inputs_valid(payload: AnalysisInputs) -> ValidationReport:
    validation = validate_inputs(payload)
    if validation.errors or not validation.analysis_ready:
        errors = validation.errors or [
            "SMILES and ¹H NMR text must both validate and correspond before analysis."
        ]
        raise HTTPException(status_code=400, detail=_validation_detail(errors))
    return validation


def _ensure_batch_inputs_valid(items: list[AnalysisInputs]) -> None:
    failures: list[dict[str, object]] = []
    for index, item in enumerate(items):
        validation = validate_inputs(item)
        if validation.errors or not validation.analysis_ready:
            failures.append(
                {
                    "item_index": index,
                    "sample_id": item.sample_id,
                    "errors": validation.errors
                    or [
                        "SMILES and ¹H NMR text must both validate and correspond before analysis."
                    ],
                }
            )
    if failures:
        raise HTTPException(status_code=400, detail=failures)


def _audit_from_context(
    request: Request,
    *,
    context: AccessContext | None,
    event_type: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    actor_user_id = context.user.id if context and context.user else None
    actor_email = context.user.email if context and context.user else None
    audit_event(
        _state(request).session_factory,
        event_type=event_type,
        message=message,
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )


def _collaboration_actor(
    request: Request, context: AccessContext
) -> collab_store.CollaborationActor:
    return collab_store.CollaborationActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        is_admin=bool(context.user and context.user.is_admin),
        is_system=context.system_api_key,
        permissive=_state(request).settings.local_auth_disabled,
    )


def _raise_collaboration_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, collab_store.CollaborationPermissionError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, collab_store.CollaborationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _method_registry_actor(context: AccessContext) -> method_store.RegistryActor:
    return method_store.RegistryActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_method_registry_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, method_store.MethodRegistryError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _operations_actor(context: AccessContext) -> ops_store.OperationsActor:
    return ops_store.OperationsActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _analytics_actor(context: AccessContext) -> analytics_store.AnalyticsActor:
    return analytics_store.AnalyticsActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_analytics_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, analytics_store.AnalyticsError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _reaction_actor(context: AccessContext) -> reaction_store.ReactionActor:
    return reaction_store.ReactionActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_reaction_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, reaction_store.ReactionError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _regulatory_actor(context: AccessContext) -> regulatory_store.RegulatoryActor:
    return regulatory_store.RegulatoryActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_regulatory_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, regulatory_store.RegulatoryError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _compliance_actor(context: AccessContext) -> compliance_store.RegulatoryComplianceActor:
    return compliance_store.RegulatoryComplianceActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_compliance_http_error(exc: Exception) -> None:
    if isinstance(exc, compliance_store.RegulatoryComplianceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, compliance_store.RegulatoryComplianceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _surveillance_actor(context: AccessContext) -> surveillance_store.RegulatorySurveillanceActor:
    return surveillance_store.RegulatorySurveillanceActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_surveillance_http_error(exc: Exception) -> None:
    if isinstance(exc, surveillance_store.RegulatorySurveillanceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, surveillance_store.RegulatorySurveillanceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _knowledge_actor(context: AccessContext) -> knowledge_store.KnowledgeFlywheelActor:
    return knowledge_store.KnowledgeFlywheelActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_knowledge_http_error(exc: Exception) -> None:
    if isinstance(exc, knowledge_store.KnowledgeFlywheelNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, knowledge_store.KnowledgeFlywheelError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _ml_actor(context: AccessContext) -> ml_store.MLModelFactoryActor:
    return ml_store.MLModelFactoryActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_ml_http_error(exc: Exception) -> None:
    if isinstance(exc, ml_store.MLModelFactoryNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ml_store.MLModelFactoryError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _ai_actor(context: AccessContext) -> ai_store.AIInferenceActor:
    return ai_store.AIInferenceActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _ai_evidence_actor(context: AccessContext) -> ai_evidence_store.AIEvidenceActor:
    if context.user is None:
        raise HTTPException(status_code=403, detail=PUBLIC_ACCESS_DENIED_DETAIL)
    return ai_evidence_store.AIEvidenceActor(
        user_id=context.user.id,
        email=context.user.email,
    )


def _raise_ai_evidence_http_error(exc: Exception) -> None:
    if isinstance(exc, ai_evidence_store.AIEvidenceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ai_evidence_store.AIEvidenceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _raise_ai_http_error(exc: Exception) -> None:
    if isinstance(exc, ai_store.AIInferenceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ai_store.AIInferenceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _product_actor(context: AccessContext) -> product_store.ProductOrchestrationActor:
    return product_store.ProductOrchestrationActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_product_http_error(exc: Exception) -> None:
    if isinstance(exc, product_store.ProductOrchestrationNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, product_store.ProductOrchestrationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _mobile_actor(context: AccessContext) -> mobile_store.MobileActor:
    return mobile_store.MobileActor(
        user_id=context.user_id,
        email=context.user.email if context.user is not None else None,
        system_api_key=context.system_api_key,
    )


def _raise_mobile_http_error(exc: Exception) -> None:
    if isinstance(exc, mobile_store.MobileExperienceNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, mobile_store.MobileExperienceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _raise_compound_registry_http_error(exc: Exception) -> None:
    if isinstance(exc, compound_store.CompoundRegistryNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, compound_store.CompoundRegistryError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def _openapi_available(request: Request) -> bool:
    try:
        request.app.openapi()
        return True
    except Exception:
        return False


def _app_uptime_seconds(request: Request) -> float | None:
    started_at = getattr(request.app.state, "started_at", None)
    if not isinstance(started_at, datetime):
        return None
    return round((datetime.now(UTC) - started_at).total_seconds(), 3)


def _generated_at_iso() -> str:
    return datetime.now(UTC).isoformat()


def _correlation_id_from_request(request: Request) -> str:
    incoming = request.headers.get(CORRELATION_ID_HEADER) or request.headers.get(
        REQUEST_ID_HEADER
    )
    if incoming:
        cleaned = incoming.strip()
        if 0 < len(cleaned) <= 128 and re.fullmatch(r"[A-Za-z0-9._:-]+", cleaned):
            return cleaned
    return uuid.uuid4().hex


def _request_correlation_id(request: Request) -> str:
    existing = getattr(request.state, "correlation_id", None)
    if isinstance(existing, str) and existing:
        return existing
    correlation_id = _correlation_id_from_request(request)
    request.state.correlation_id = correlation_id
    return correlation_id


def _stable_unavailable_payload(request: Request | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "detail": UNAVAILABLE_WARNING,
        "data_mode": "unavailable",
        "warnings": [UNAVAILABLE_WARNING],
        "generated_at": _generated_at_iso(),
    }
    if request is not None:
        payload["correlation_id"] = _request_correlation_id(request)
    return payload


def _redact_secret_assignment(match: re.Match[str]) -> str:
    key = match.group(1)
    value = match.group(2)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", value) and value.startswith(
        ("forbidden_", "invalid_", "missing_", "required_", "unsupported_")
    ):
        return match.group(0)
    return f"{key}=[redacted]"


def _redact_public_error_text(value: str) -> str:
    text = str(value)
    if _ERROR_STACK_RE.search(text):
        return INTERNAL_ERROR_DETAIL
    if _ERROR_INTERNAL_DETAIL_RE.search(text):
        return PUBLIC_REQUEST_FAILED_DETAIL
    text = _ERROR_SIGNED_URL_RE.sub("[redacted signed URL]", text)
    text = _ERROR_DB_URL_RE.sub("[redacted database URL]", text)
    text = _ERROR_BEARER_RE.sub("Bearer [redacted]", text)
    text = _ERROR_SECRET_ASSIGNMENT_RE.sub(_redact_secret_assignment, text)
    text = _ERROR_PATH_RE.sub("[redacted path]", text)
    return text


def _sanitize_public_error_detail(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_public_error_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, list):
        return [_sanitize_public_error_detail(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_public_error_detail(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str == "input" or _ERROR_SECRET_KEY_RE.search(key_str):
                sanitized[key_str] = "[redacted]"
            else:
                sanitized[key_str] = _sanitize_public_error_detail(item)
        return sanitized
    return _redact_public_error_text(str(value))


def _safe_http_exception_detail(status_code: int, detail: Any) -> Any:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return PUBLIC_AUTH_REQUIRED_DETAIL
    if status_code == status.HTTP_403_FORBIDDEN:
        return PUBLIC_ACCESS_DENIED_DETAIL
    return _sanitize_public_error_detail(detail)


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    safe_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        safe: dict[str, Any] = {
            "type": _sanitize_public_error_detail(error.get("type")),
            "loc": _sanitize_public_error_detail(error.get("loc")),
            "msg": _sanitize_public_error_detail(error.get("msg")),
        }
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            safe["ctx"] = _sanitize_public_error_detail(ctx)
        safe_errors.append(safe)
    return safe_errors


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _raw_fid_audit_metadata(
    archive: RawArchiveRecord,
    context: AccessContext,
    *,
    processing_run_id: int | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "raw_archive_id": archive.sha256,
        "raw_archive_db_id": archive.id,
        "sha256": archive.sha256,
        "user_id": context.user_id,
        "filename": archive.filename,
        "vendor_detected": archive.vendor_detected,
        "processing_run_id": processing_run_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if extra:
        metadata.update(extra)
    return metadata


def _audit_raw_fid_event(
    request: Request,
    *,
    context: AccessContext,
    archive: RawArchiveRecord,
    event_type: str,
    message: str,
    entity_type: str = "raw_archive",
    entity_id: int | None = None,
    processing_run_id: int | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    _audit_from_context(
        request,
        context=context,
        event_type=event_type,
        message=message,
        entity_type=entity_type,
        entity_id=archive.id if entity_id is None else entity_id,
        metadata=_raw_fid_audit_metadata(
            archive,
            context,
            processing_run_id=processing_run_id,
            extra=extra,
        ),
    )


def _user_scope_for_context(context: AccessContext) -> int | None:
    if context.system_api_key:
        return None
    if context.user is not None and context.user.is_admin:
        return None
    return context.user_id


def _health_response(request: Request | None = None) -> dict[str, object]:
    checks: dict[str, str] = {"app": "ok"}
    if request is not None:
        try:
            with _state(request).session_factory() as session:
                session.execute(select(1))
            checks["database"] = "ok"
        except Exception:
            logger.exception(
                "Health check database probe failed",
                extra={"correlation_id": _request_correlation_id(request)},
            )
            checks["database"] = "error"
    status_value = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": status_value, "checks": checks}


def health() -> dict[str, object]:
    return _health_response()


@router.get("/health")
def health_route(request: Request) -> dict[str, object]:
    return _health_response(request)


async def require_admin(
    context: AccessContext = Depends(require_access_context),
) -> AccessContext:
    if context.system_api_key:
        return context
    if context.user is None or not context.user.is_admin:
        raise HTTPException(status_code=403, detail=PUBLIC_ACCESS_DENIED_DETAIL)
    return context


@router.get("/queue/status", response_model=QueueWorkerStatus)
def queue_status(request: Request) -> QueueWorkerStatus:
    state = _state(request)
    return QueueWorkerStatus(
        backend="rq" if state.settings.redis_url else "fastapi-background",
        redis_configured=state.settings.redis_url is not None,
        queue_name=state.settings.queue_name,
        detail="RQ will be used when REDIS_URL is configured; otherwise FastAPI background tasks are used.",
    )


@router.get("/system/health", response_model=SystemHealthResponse)
def system_health_route(request: Request) -> SystemHealthResponse:
    state = _state(request)
    return ops_store.system_health(
        state.session_factory,
        settings=state.settings,
        uptime_seconds=_app_uptime_seconds(request),
        local_auth_disabled=state.settings.local_auth_disabled,
    )


@router.get(
    "/system/status",
    response_model=SystemStatusResponse,
    dependencies=[Depends(require_access_context)],
)
def system_status_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SystemStatusResponse:
    state = _state(request)
    return ops_store.system_status(
        state.session_factory,
        settings=state.settings,
        storage_root=_orchestration_storage_root(request),
        openapi_available=_openapi_available(request),
        local_auth_disabled=state.settings.local_auth_disabled,
    )


@router.get("/system/version")
def system_version_route(request: Request) -> dict[str, Any]:
    settings = _state(request).settings
    return {
        "backend_version": settings.release_version,
        "api_version": settings.release_version,
        "environment": settings.app_env,
        "timestamp": datetime.now(UTC).isoformat(),
        "notes": ["Version metadata does not indicate scientific validation status."],
    }


@router.get(
    "/system/dependencies",
    response_model=list[DependencyCheck],
    dependencies=[Depends(require_access_context)],
)
def system_dependencies_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[DependencyCheck]:
    state = _state(request)
    return ops_store.dependencies(
        state.session_factory,
        settings=state.settings,
        storage_root=_orchestration_storage_root(request),
        openapi_available=_openapi_available(request),
    )


@router.get(
    "/system/environment-check",
    response_model=EnvironmentCheckResponse,
    dependencies=[Depends(require_admin)],
)
def system_environment_check_route(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> EnvironmentCheckResponse:
    state = _state(request)
    return ops_store.environment_check(
        state.settings,
        local_auth_disabled=state.settings.local_auth_disabled,
    )


@router.get(
    "/system/metrics",
    response_model=list[OperationalMetric],
    dependencies=[Depends(require_access_context)],
)
def system_metrics_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[OperationalMetric]:
    return ops_store.operational_metrics(_state(request).session_factory)


@router.get("/system/jobs/summary", dependencies=[Depends(require_access_context)])
def system_jobs_summary_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> dict[str, Any]:
    return ops_store.jobs_summary(_state(request).session_factory)


@router.get("/system/storage/summary", dependencies=[Depends(require_access_context)])
def system_storage_summary_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> dict[str, Any]:
    return ops_store.storage_summary(
        _state(request).session_factory,
        storage_root=_orchestration_storage_root(request),
    )


@router.get(
    "/security/events",
    response_model=list[SecurityEvent],
    dependencies=[Depends(require_admin)],
)
def list_security_events_route(
    request: Request,
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_admin),
) -> list[SecurityEvent]:
    return ops_store.list_security_events(
        _state(request).session_factory,
        event_type=event_type,
        severity=severity,
        actor_email=actor_email,
        limit=limit,
    )


@router.post(
    "/security/events",
    response_model=SecurityEvent,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_security_event_route(
    payload: SecurityEventCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SecurityEvent:
    return ops_store.create_security_event(
        _state(request).session_factory,
        payload,
        actor=_operations_actor(context),
        request_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get(
    "/security/summary",
    response_model=SecuritySummary,
    dependencies=[Depends(require_admin)],
)
def security_summary_route(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> SecuritySummary:
    return ops_store.security_summary(_state(request).session_factory)


@router.get(
    "/admin/audit/search",
    response_model=list[AuditEventRecord],
    dependencies=[Depends(require_admin)],
)
def admin_audit_search_route(
    request: Request,
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    actor_email: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_admin),
) -> list[AuditEventRecord]:
    return ops_store.search_audit_events(
        _state(request).session_factory,
        actor=_operations_actor(context),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_email=actor_email,
        q=q,
        limit=limit,
    )


@router.post(
    "/admin/debug-bundles",
    response_model=DebugBundle,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_debug_bundle_route(
    payload: DebugBundleCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> DebugBundle:
    return ops_store.create_debug_bundle(
        _state(request).session_factory,
        payload,
        actor=_operations_actor(context),
        settings=_state(request).settings,
        storage_root=_orchestration_storage_root(request),
        openapi_available=_openapi_available(request),
    )


@router.get(
    "/admin/debug-bundles/{bundle_id}",
    response_model=DebugBundle,
    dependencies=[Depends(require_admin)],
)
def get_debug_bundle_route(
    bundle_id: int,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> DebugBundle:
    record = ops_store.get_debug_bundle(_state(request).session_factory, bundle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Debug bundle not found.")
    return record


@router.get(
    "/admin/debug-bundles/{bundle_id}/download",
    dependencies=[Depends(require_admin)],
)
def download_debug_bundle_route(
    bundle_id: int,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> StreamingResponse:
    record_and_content = ops_store.get_debug_bundle_content(
        _state(request).session_factory, bundle_id
    )
    if record_and_content is None:
        raise HTTPException(status_code=404, detail="Debug bundle not found.")
    record, content = record_and_content
    filename = f"debug-bundle-{record.id}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/analytics/events",
    response_model=UsageEvent,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_usage_event_route(
    payload: UsageEventCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UsageEvent:
    try:
        return analytics_store.create_usage_event(
            _state(request).session_factory,
            payload,
            actor=_analytics_actor(context),
        )
    except Exception as exc:
        _raise_analytics_http_error(exc)
        raise


@router.get(
    "/analytics/events",
    response_model=list[UsageEvent],
    dependencies=[Depends(require_admin)],
)
def list_usage_events_route(
    request: Request,
    event_type: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    session_id: int | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_admin),
) -> list[UsageEvent]:
    return analytics_store.list_usage_events(
        _state(request).session_factory,
        event_type=event_type,
        project_id=project_id,
        session_id=session_id,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    dependencies=[Depends(require_admin)],
)
def analytics_summary_route(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> AnalyticsSummary:
    return analytics_store.analytics_summary(_state(request).session_factory)


@router.get(
    "/analytics/roi",
    response_model=RoiSnapshot,
    dependencies=[Depends(require_admin)],
)
def analytics_roi_route(
    request: Request,
    scope: Literal["global", "project", "session", "user"] = Query(default="global"),
    scope_id: str | None = Query(default=None),
    period_start: datetime | None = Query(default=None),
    period_end: datetime | None = Query(default=None),
    context: AccessContext = Depends(require_admin),
) -> RoiSnapshot:
    return analytics_store.roi_snapshot(
        _state(request).session_factory,
        scope=scope,
        scope_id=scope_id,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/analytics/automation-tasks",
    response_model=list[AutomationTaskDefinition],
    dependencies=[Depends(require_access_context)],
)
def list_automation_tasks_route(
    request: Request,
    category: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    context: AccessContext = Depends(require_access_context),
) -> list[AutomationTaskDefinition]:
    return analytics_store.list_automation_tasks(
        _state(request).session_factory,
        category=category,
        enabled=enabled,
    )


@router.post(
    "/analytics/automation-tasks",
    response_model=AutomationTaskDefinition,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_automation_task_route(
    payload: AutomationTaskDefinitionCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> AutomationTaskDefinition:
    try:
        return analytics_store.create_automation_task(
            _state(request).session_factory,
            payload,
            actor=_analytics_actor(context),
        )
    except Exception as exc:
        _raise_analytics_http_error(exc)
        raise


@router.patch(
    "/analytics/automation-tasks/{task_id}",
    response_model=AutomationTaskDefinition,
    dependencies=[Depends(require_admin)],
)
def update_automation_task_route(
    task_id: int,
    payload: AutomationTaskDefinitionUpdate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> AutomationTaskDefinition:
    try:
        record = analytics_store.update_automation_task(
            _state(request).session_factory,
            task_id,
            payload,
            actor=_analytics_actor(context),
        )
    except Exception as exc:
        _raise_analytics_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Automation task not found.")
    return record


@router.get(
    "/analytics/projects/{project_id}/roi",
    response_model=RoiSnapshot,
    dependencies=[Depends(require_admin)],
)
def project_roi_route(
    project_id: int,
    request: Request,
    period_start: datetime | None = Query(default=None),
    period_end: datetime | None = Query(default=None),
    context: AccessContext = Depends(require_admin),
) -> RoiSnapshot:
    return analytics_store.roi_snapshot(
        _state(request).session_factory,
        scope="project",
        scope_id=str(project_id),
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/analytics/sessions/{session_id}/roi",
    response_model=RoiSnapshot,
    dependencies=[Depends(require_admin)],
)
def session_roi_route(
    session_id: int,
    request: Request,
    period_start: datetime | None = Query(default=None),
    period_end: datetime | None = Query(default=None),
    context: AccessContext = Depends(require_admin),
) -> RoiSnapshot:
    return analytics_store.roi_snapshot(
        _state(request).session_factory,
        scope="session",
        scope_id=str(session_id),
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/analytics/workflows/summary",
    response_model=WorkflowAnalyticsSummary,
    dependencies=[Depends(require_admin)],
)
def analytics_workflows_summary_route(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> WorkflowAnalyticsSummary:
    return analytics_store.workflow_summary(_state(request).session_factory)


@router.post(
    "/analytics/feedback",
    response_model=UserFeedbackEvent,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_feedback_route(
    payload: UserFeedbackEventCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UserFeedbackEvent:
    return analytics_store.create_feedback(
        _state(request).session_factory,
        payload,
        actor=_analytics_actor(context),
    )


@router.get(
    "/analytics/feedback",
    response_model=list[UserFeedbackEvent],
    dependencies=[Depends(require_admin)],
)
def list_feedback_route(
    request: Request,
    feedback_type: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    session_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_admin),
) -> list[UserFeedbackEvent]:
    return analytics_store.list_feedback(
        _state(request).session_factory,
        feedback_type=feedback_type,
        project_id=project_id,
        session_id=session_id,
        limit=limit,
    )


@router.post(
    "/analytics/renewal-report",
    response_model=RenewalValueReport,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_renewal_report_route(
    payload: RenewalValueReportCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> RenewalValueReport:
    return analytics_store.create_renewal_report(
        _state(request).session_factory,
        payload,
        actor=_analytics_actor(context),
    )


@router.get(
    "/analytics/renewal-report/{report_id}",
    response_model=RenewalValueReport,
    dependencies=[Depends(require_admin)],
)
def get_renewal_report_route(
    report_id: int,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> RenewalValueReport:
    record = analytics_store.get_renewal_report(_state(request).session_factory, report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Renewal value report not found.")
    return record


@router.post(
    "/reaction-projects",
    response_model=ReactionProject,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_project_route(
    payload: ReactionProjectCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionProject:
    return reaction_store.create_project(
        _state(request).session_factory,
        payload,
        actor=_reaction_actor(context),
    )


@router.get(
    "/reaction-projects",
    response_model=list[ReactionProject],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_projects_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionProject]:
    return reaction_store.list_projects(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/reaction-projects/{reaction_project_id}",
    response_model=ReactionProject,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_project_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionProject:
    record = reaction_store.get_project(_state(request).session_factory, reaction_project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction project not found.")
    return record


@router.patch(
    "/reaction-projects/{reaction_project_id}",
    response_model=ReactionProject,
    dependencies=[Depends(require_access_context)],
)
def update_reaction_project_route(
    reaction_project_id: int,
    payload: ReactionProjectUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionProject:
    try:
        record = reaction_store.update_project(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction project not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/design-space",
    response_model=ReactionDesignSpace,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_design_space_route(
    reaction_project_id: int,
    payload: ReactionDesignSpaceCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionDesignSpace:
    try:
        return reaction_bo.create_design_space(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/design-space",
    response_model=ReactionDesignSpace,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_design_space_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionDesignSpace:
    try:
        record = reaction_bo.get_design_space(_state(request).session_factory, reaction_project_id)
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction design space not found.")
    return record


@router.patch(
    "/reaction-projects/{reaction_project_id}/design-space",
    response_model=ReactionDesignSpace,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_design_space_route(
    reaction_project_id: int,
    payload: ReactionDesignSpaceUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionDesignSpace:
    try:
        record = reaction_bo.patch_design_space(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction design space not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/objective-profile",
    response_model=ReactionObjectiveProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_objective_profile_route(
    reaction_project_id: int,
    payload: ReactionObjectiveProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionObjectiveProfile:
    try:
        return reaction_bo.create_objective_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/objective-profile",
    response_model=ReactionObjectiveProfile,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_objective_profile_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionObjectiveProfile:
    try:
        record = reaction_bo.get_objective_profile(
            _state(request).session_factory, reaction_project_id
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction objective profile not found.")
    return record


@router.patch(
    "/reaction-projects/{reaction_project_id}/objective-profile",
    response_model=ReactionObjectiveProfile,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_objective_profile_route(
    reaction_project_id: int,
    payload: ReactionObjectiveProfileUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionObjectiveProfile:
    try:
        record = reaction_bo.patch_objective_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction objective profile not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/cost-profile",
    response_model=ReactionCostProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_cost_profile_route(
    reaction_project_id: int,
    payload: ReactionCostProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionCostProfile:
    try:
        return reaction_bo.create_cost_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/cost-profile",
    response_model=ReactionCostProfile,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_cost_profile_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionCostProfile:
    try:
        record = reaction_bo.get_cost_profile(_state(request).session_factory, reaction_project_id)
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction cost profile not found.")
    return record


@router.patch(
    "/reaction-projects/{reaction_project_id}/cost-profile",
    response_model=ReactionCostProfile,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_cost_profile_route(
    reaction_project_id: int,
    payload: ReactionCostProfileUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionCostProfile:
    try:
        record = reaction_bo.patch_cost_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction cost profile not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/safety-profile",
    response_model=ReactionSafetyConstraintProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_safety_profile_route(
    reaction_project_id: int,
    payload: ReactionSafetyConstraintProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionSafetyConstraintProfile:
    try:
        return reaction_bo.create_safety_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/safety-profile",
    response_model=ReactionSafetyConstraintProfile,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_safety_profile_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionSafetyConstraintProfile:
    try:
        record = reaction_bo.get_safety_profile(
            _state(request).session_factory, reaction_project_id
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction safety profile not found.")
    return record


@router.patch(
    "/reaction-projects/{reaction_project_id}/safety-profile",
    response_model=ReactionSafetyConstraintProfile,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_safety_profile_route(
    reaction_project_id: int,
    payload: ReactionSafetyConstraintProfileUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionSafetyConstraintProfile:
    try:
        record = reaction_bo.patch_safety_profile(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction safety profile not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/variables",
    response_model=ReactionVariable,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_variable_route(
    reaction_project_id: int,
    payload: ReactionVariableCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionVariable:
    try:
        return reaction_store.create_variable(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/variables",
    response_model=list[ReactionVariable],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_variables_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionVariable]:
    try:
        return reaction_store.list_variables(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.patch(
    "/reaction-variables/{variable_id}",
    response_model=ReactionVariable,
    dependencies=[Depends(require_access_context)],
)
def update_reaction_variable_route(
    variable_id: int,
    payload: ReactionVariableUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionVariable:
    try:
        record = reaction_store.update_variable(
            _state(request).session_factory,
            variable_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction variable not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/experiments",
    response_model=ReactionExperiment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_experiment_route(
    reaction_project_id: int,
    payload: ReactionExperimentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperiment:
    try:
        return reaction_store.create_experiment(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/experiments",
    response_model=list[ReactionExperiment],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_experiments_route(
    reaction_project_id: int,
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionExperiment]:
    try:
        return reaction_store.list_experiments(
            _state(request).session_factory,
            reaction_project_id,
            status=status_filter,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-experiments/{experiment_id}",
    response_model=ReactionExperiment,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_experiment_route(
    experiment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperiment:
    record = reaction_store.get_experiment(_state(request).session_factory, experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction experiment not found.")
    return record


@router.patch(
    "/reaction-experiments/{experiment_id}",
    response_model=ReactionExperiment,
    dependencies=[Depends(require_access_context)],
)
def update_reaction_experiment_route(
    experiment_id: int,
    payload: ReactionExperimentUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperiment:
    try:
        record = reaction_store.update_experiment(
            _state(request).session_factory,
            experiment_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction experiment not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/optimization/run",
    response_model=ReactionOptimizationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_reaction_optimization_route(
    reaction_project_id: int,
    payload: ReactionOptimizationRunRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationRun:
    try:
        return reaction_store.run_optimization(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/optimization/runs",
    response_model=list[ReactionOptimizationRun],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_optimization_runs_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionOptimizationRun]:
    try:
        return reaction_store.list_optimization_runs(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-optimization-runs/{run_id}",
    response_model=ReactionOptimizationRun,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_optimization_run_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationRun:
    record = reaction_store.get_optimization_run(_state(request).session_factory, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction optimization run not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/optimization/bo/run",
    response_model=ReactionBayesianOptimizationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_reaction_bayesian_optimization_route(
    reaction_project_id: int,
    payload: ReactionBayesianOptimizationRunRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionBayesianOptimizationRun:
    try:
        return reaction_bo.run_bayesian_optimization(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/optimization/bo/runs",
    response_model=list[ReactionBayesianOptimizationRun],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_bayesian_optimization_runs_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionBayesianOptimizationRun]:
    try:
        return reaction_bo.list_bayesian_optimization_runs(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-optimization/bo-runs/{bo_run_id}",
    response_model=ReactionBayesianOptimizationRun,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_bayesian_optimization_run_route(
    bo_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionBayesianOptimizationRun:
    record = reaction_bo.get_bayesian_optimization_run(
        _state(request).session_factory,
        bo_run_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction Bayesian optimization run not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/advisor/run",
    response_model=ReactionOptimizationAdvisorRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_reaction_optimization_advisor_route(
    reaction_project_id: int,
    payload: ReactionOptimizationAdvisorRunRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationAdvisorRun:
    try:
        return reaction_advisor.run_advisor(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/advisor/runs",
    response_model=list[ReactionOptimizationAdvisorRun],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_optimization_advisor_runs_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionOptimizationAdvisorRun]:
    try:
        return reaction_advisor.list_advisor_runs(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-advisor-runs/{advisor_run_id}",
    response_model=ReactionOptimizationAdvisorRun,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_optimization_advisor_run_route(
    advisor_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationAdvisorRun:
    record = reaction_advisor.get_advisor_run(_state(request).session_factory, advisor_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction advisor run not found.")
    return record


@router.post(
    "/reaction-advisor-runs/{advisor_run_id}/review",
    response_model=ReactionOptimizationAdvisorRun,
    dependencies=[Depends(require_access_context)],
)
def review_reaction_optimization_advisor_run_route(
    advisor_run_id: int,
    payload: ReactionAdvisorReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationAdvisorRun:
    record = reaction_advisor.review_advisor_run(
        _state(request).session_factory,
        advisor_run_id,
        payload,
        actor=_reaction_actor(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction advisor run not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/recommendations",
    response_model=ReactionRecommendation,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_recommendation_route(
    reaction_project_id: int,
    payload: ReactionRecommendationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendation:
    try:
        return reaction_store.create_recommendation(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/recommendations",
    response_model=list[ReactionRecommendation],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_recommendations_route(
    reaction_project_id: int,
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionRecommendation]:
    try:
        return reaction_store.list_recommendations(
            _state(request).session_factory,
            reaction_project_id,
            status=status_filter,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.post(
    "/reaction-recommendations/{recommendation_id}/advisor/critique",
    response_model=ReactionConditionCritique,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_recommendation_advisor_critique_route(
    recommendation_id: int,
    payload: ReactionConditionCritiqueRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionConditionCritique:
    try:
        record = reaction_advisor.create_recommendation_critique(
            _state(request).session_factory,
            recommendation_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation not found.")
    return record


@router.get(
    "/reaction-recommendations/{recommendation_id}/advisor/critique",
    response_model=ReactionConditionCritique,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_recommendation_advisor_critique_route(
    recommendation_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionConditionCritique:
    record = reaction_advisor.get_recommendation_critique(
        _state(request).session_factory,
        recommendation_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation critique not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/recommendation-batches",
    response_model=ReactionRecommendationBatch,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_recommendation_batch_route(
    reaction_project_id: int,
    payload: ReactionRecommendationBatchCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendationBatch:
    try:
        return reaction_bo.create_recommendation_batch(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/recommendation-batches",
    response_model=list[ReactionRecommendationBatch],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_recommendation_batches_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionRecommendationBatch]:
    try:
        return reaction_bo.list_recommendation_batches(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-recommendation-batches/{batch_id}",
    response_model=ReactionRecommendationBatch,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_recommendation_batch_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendationBatch:
    record = reaction_bo.get_recommendation_batch(_state(request).session_factory, batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation batch not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/mechanistic-hypotheses",
    response_model=ReactionMechanisticHypothesis,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_mechanistic_hypothesis_route(
    reaction_project_id: int,
    payload: ReactionMechanisticHypothesisCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionMechanisticHypothesis:
    try:
        return reaction_advisor.create_hypothesis(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/mechanistic-hypotheses",
    response_model=list[ReactionMechanisticHypothesis],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_mechanistic_hypotheses_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionMechanisticHypothesis]:
    try:
        return reaction_advisor.list_hypotheses(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.patch(
    "/reaction-mechanistic-hypotheses/{hypothesis_id}",
    response_model=ReactionMechanisticHypothesis,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_mechanistic_hypothesis_route(
    hypothesis_id: int,
    payload: ReactionMechanisticHypothesisUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionMechanisticHypothesis:
    record = reaction_advisor.patch_hypothesis(
        _state(request).session_factory,
        hypothesis_id,
        payload,
        actor=_reaction_actor(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction mechanistic hypothesis not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/literature-priors",
    response_model=ReactionLiteraturePrior,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_literature_prior_route(
    reaction_project_id: int,
    payload: ReactionLiteraturePriorCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionLiteraturePrior:
    try:
        return reaction_advisor.create_literature_prior(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/literature-priors",
    response_model=list[ReactionLiteraturePrior],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_literature_priors_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionLiteraturePrior]:
    try:
        return reaction_advisor.list_literature_priors(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.post(
    "/reaction-projects/{reaction_project_id}/advisor/compare-bo-llm",
    response_model=ReactionOptimizationDebate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def compare_reaction_bo_and_advisor_route(
    reaction_project_id: int,
    payload: ReactionOptimizationDebateRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationDebate:
    try:
        return reaction_advisor.compare_bo_advisor(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/advisor/comparisons",
    response_model=list[ReactionOptimizationDebate],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_bo_advisor_comparisons_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionOptimizationDebate]:
    try:
        return reaction_advisor.list_comparisons(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.post(
    "/reaction-recommendations/{recommendation_id}/approve",
    response_model=ReactionRecommendation,
    dependencies=[Depends(require_access_context)],
)
def approve_reaction_recommendation_route(
    recommendation_id: int,
    payload: ReactionRecommendationReview,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendation:
    try:
        record = reaction_store.approve_recommendation(
            _state(request).session_factory,
            recommendation_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation not found.")
    return record


@router.post(
    "/reaction-recommendations/{recommendation_id}/reject",
    response_model=ReactionRecommendation,
    dependencies=[Depends(require_access_context)],
)
def reject_reaction_recommendation_route(
    recommendation_id: int,
    payload: ReactionRecommendationReview,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendation:
    try:
        record = reaction_store.reject_recommendation(
            _state(request).session_factory,
            recommendation_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/execution-batches",
    response_model=ReactionExecutionBatch,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_execution_batch_route(
    reaction_project_id: int,
    payload: ReactionExecutionBatchCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionBatch:
    try:
        return reaction_execution.create_execution_batch(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/execution-batches",
    response_model=list[ReactionExecutionBatch],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_execution_batches_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionExecutionBatch]:
    try:
        return reaction_execution.list_execution_batches(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-execution-batches/{batch_id}",
    response_model=ReactionExecutionBatch,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_execution_batch_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionBatch:
    record = reaction_execution.get_execution_batch(_state(request).session_factory, batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution batch not found.")
    return record


@router.patch(
    "/reaction-execution-batches/{batch_id}",
    response_model=ReactionExecutionBatch,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_execution_batch_route(
    batch_id: int,
    payload: ReactionExecutionBatchUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionBatch:
    try:
        record = reaction_execution.patch_execution_batch(
            _state(request).session_factory,
            batch_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution batch not found.")
    return record


@router.post(
    "/reaction-execution-batches/{batch_id}/items",
    response_model=ReactionExecutionItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_execution_item_route(
    batch_id: int,
    payload: ReactionExecutionItemCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionItem:
    try:
        return reaction_execution.create_execution_item(
            _state(request).session_factory,
            batch_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-execution-batches/{batch_id}/items",
    response_model=list[ReactionExecutionItem],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_execution_items_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionExecutionItem]:
    try:
        return reaction_execution.list_execution_items(_state(request).session_factory, batch_id)
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.patch(
    "/reaction-execution-items/{item_id}",
    response_model=ReactionExecutionItem,
    dependencies=[Depends(require_access_context)],
)
def patch_reaction_execution_item_route(
    item_id: int,
    payload: ReactionExecutionItemUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionItem:
    try:
        record = reaction_execution.patch_execution_item(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.post(
    "/reaction-recommendations/{recommendation_id}/convert-to-experiment",
    response_model=ReactionRecommendationConvertResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def convert_reaction_recommendation_to_experiment_route(
    recommendation_id: int,
    payload: ReactionRecommendationConvertRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionRecommendationConvertResponse:
    try:
        record = reaction_execution.convert_recommendation_to_experiment(
            _state(request).session_factory,
            recommendation_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction recommendation not found.")
    return record


@router.post(
    "/reaction-execution-items/{item_id}/mark-running",
    response_model=ReactionExecutionItem,
    dependencies=[Depends(require_access_context)],
)
def mark_reaction_execution_item_running_route(
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionItem:
    try:
        record = reaction_execution.mark_execution_item_running(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.post(
    "/reaction-execution-items/{item_id}/mark-completed",
    response_model=ReactionExecutionItem,
    dependencies=[Depends(require_access_context)],
)
def mark_reaction_execution_item_completed_route(
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionItem:
    try:
        record = reaction_execution.mark_execution_item_completed(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.post(
    "/reaction-execution-items/{item_id}/mark-failed",
    response_model=ReactionExecutionItem,
    dependencies=[Depends(require_access_context)],
)
def mark_reaction_execution_item_failed_route(
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExecutionItem:
    try:
        record = reaction_execution.mark_execution_item_failed(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.post(
    "/reaction-execution-items/{item_id}/analytical-results",
    response_model=ReactionAnalyticalResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def add_reaction_execution_item_analytical_result_route(
    item_id: int,
    payload: ReactionAnalyticalResultCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionAnalyticalResult:
    try:
        record = reaction_execution.add_analytical_result(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.get(
    "/reaction-execution-items/{item_id}/analytical-results",
    response_model=list[ReactionAnalyticalResult],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_execution_item_analytical_results_route(
    item_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionAnalyticalResult]:
    try:
        return reaction_execution.list_analytical_results(_state(request).session_factory, item_id)
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.post(
    "/reaction-execution-items/{item_id}/extract-outcome",
    response_model=ReactionOutcomeExtractionRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def extract_reaction_execution_item_outcome_route(
    item_id: int,
    payload: ReactionOutcomeExtractionRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOutcomeExtractionRun:
    try:
        record = reaction_execution.extract_outcome(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.get(
    "/reaction-outcome-extraction-runs/{extraction_run_id}",
    response_model=ReactionOutcomeExtractionRun,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_outcome_extraction_run_route(
    extraction_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOutcomeExtractionRun:
    record = reaction_execution.get_extraction_run(
        _state(request).session_factory, extraction_run_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction outcome extraction run not found.")
    return record


@router.post(
    "/reaction-execution-items/{item_id}/confirm-outcome",
    response_model=ReactionExperiment,
    dependencies=[Depends(require_access_context)],
)
def confirm_reaction_execution_item_outcome_route(
    item_id: int,
    payload: ReactionOutcomeConfirmRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperiment:
    try:
        record = reaction_execution.confirm_outcome(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction execution item not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/optimization-cycles",
    response_model=ReactionOptimizationCycle,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_optimization_cycle_route(
    reaction_project_id: int,
    payload: ReactionOptimizationCycleCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationCycle:
    try:
        return reaction_execution.create_optimization_cycle(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/optimization-cycles",
    response_model=list[ReactionOptimizationCycle],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_optimization_cycles_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionOptimizationCycle]:
    try:
        return reaction_execution.list_optimization_cycles(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-optimization-cycles/{cycle_id}",
    response_model=ReactionOptimizationCycle,
    dependencies=[Depends(require_access_context)],
)
def get_reaction_optimization_cycle_route(
    cycle_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationCycle:
    record = reaction_execution.get_optimization_cycle(_state(request).session_factory, cycle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction optimization cycle not found.")
    return record


@router.post(
    "/reaction-optimization-cycles/{cycle_id}/decision",
    response_model=ReactionCycleDecisionRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_optimization_cycle_decision_route(
    cycle_id: int,
    payload: ReactionCycleDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionCycleDecisionRecord:
    try:
        record = reaction_execution.create_cycle_decision(
            _state(request).session_factory,
            cycle_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction optimization cycle not found.")
    return record


@router.post(
    "/reaction-experiments/{experiment_id}/link-spectracheck-session",
    response_model=ReactionExperiment,
    dependencies=[Depends(require_access_context)],
)
def link_reaction_experiment_spectracheck_route(
    experiment_id: int,
    payload: ReactionExperimentSpectraCheckLink,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperiment:
    try:
        record = reaction_store.link_spectracheck_session(
            _state(request).session_factory,
            experiment_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction experiment not found.")
    return record


@router.get(
    "/reaction-experiments/{experiment_id}/evidence",
    response_model=ReactionExperimentEvidence,
    dependencies=[Depends(require_access_context)],
)
def reaction_experiment_evidence_route(
    experiment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionExperimentEvidence:
    record = reaction_store.experiment_evidence(_state(request).session_factory, experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Reaction experiment not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/optimization/benchmark",
    response_model=ReactionOptimizationBenchmarkRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_reaction_optimization_benchmark_route(
    reaction_project_id: int,
    payload: ReactionOptimizationBenchmarkRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReactionOptimizationBenchmarkRun:
    try:
        return reaction_bo.run_benchmark(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_reaction_actor(context),
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/optimization/benchmark-runs",
    response_model=list[ReactionOptimizationBenchmarkRun],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_optimization_benchmark_runs_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReactionOptimizationBenchmarkRun]:
    try:
        return reaction_bo.list_benchmark_runs(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_reaction_http_error(exc)
        raise


def _queue_verification_email(request: Request, *, email: str) -> bool:
    state = _state(request)
    token_pair = create_user_action_token(
        state.session_factory,
        email=email,
        purpose="verify_email",
        ttl_minutes=state.settings.email_verification_ttl_minutes,
    )
    if token_pair is None:
        return False
    token, _expires_at = token_pair
    verification_link = _build_absolute_url(
        state.settings.base_url,
        f"/auth/verify-email?token={token}",
    )
    _maybe_record_email(
        request,
        to_email=email,
        subject="Verify your NMRCheck account",
        body=f"Use this link to verify your account: {verification_link}",
        purpose="verify_email",
    )
    return True


def _issue_auth_page_session(
    request: Request,
    *,
    user: UserPublic,
    detail: str,
    requires_email_verification: bool = False,
) -> AuthPageResponse:
    token, expires_at = create_user_session(
        _state(request).session_factory,
        user_id=user.id,
        ttl_minutes=_state(request).settings.access_token_ttl_minutes,
    )
    return AuthPageResponse(
        access_token=token,
        expires_at=expires_at,
        user=user,
        requires_email_verification=requires_email_verification,
        detail=detail,
    )


@router.post("/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request) -> UserPublic:
    state = _state(request)
    try:
        user = create_user(
            state.session_factory,
            email=payload.email,
            password=payload.password,
            is_verified=not state.settings.require_verified_email,
            is_admin=state.settings.is_admin_email(payload.email),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if state.settings.require_verified_email:
        _queue_verification_email(request, email=payload.email)
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="auth.register",
        message="User registered.",
        entity_type="user",
        entity_id=user.id,
    )
    return user


@router.post("/auth/sign-up", response_model=AuthPageResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: UserSignUp, request: Request) -> AuthPageResponse:
    state = _state(request)
    try:
        user = create_user(
            state.session_factory,
            email=payload.email,
            password=payload.password,
            is_verified=not state.settings.require_verified_email,
            is_admin=state.settings.is_admin_email(payload.email),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    verification_queued = False
    if state.settings.require_verified_email:
        verification_queued = _queue_verification_email(request, email=payload.email)
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="auth.sign_up",
        message="User signed up from frontend auth page.",
        entity_type="user",
        entity_id=user.id,
        metadata={
            "name_supplied": bool(payload.name),
            "verification_queued": verification_queued,
        },
    )
    if state.settings.require_verified_email:
        return AuthPageResponse(
            access_token=None,
            expires_at=None,
            user=user,
            requires_email_verification=True,
            detail="Account created. Verify your email before signing in.",
        )
    return _issue_auth_page_session(
        request,
        user=user,
        detail="Account created and signed in.",
    )


@router.post("/auth/login", response_model=AccessTokenResponse)
def login_json(payload: UserLogin, request: Request) -> AccessTokenResponse:
    state = _state(request)
    user = authenticate_user(
        state.session_factory,
        email=payload.email,
        password=payload.password,
        require_verified=state.settings.require_verified_email,
    )
    if user is None:
        raise HTTPException(
            status_code=401, detail="Incorrect email or password, or email not verified."
        )
    if state.settings.is_admin_email(user.email) and not user.is_admin:
        user = set_user_admin_status(state.session_factory, user_id=user.id, is_admin=True)
    token, expires_at = create_user_session(
        state.session_factory,
        user_id=user.id,
        ttl_minutes=state.settings.access_token_ttl_minutes,
    )
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="auth.login",
        message="User logged in.",
        entity_type="user",
        entity_id=user.id,
    )
    return AccessTokenResponse(access_token=token, expires_at=expires_at, user=user)


@router.post("/auth/sign-in", response_model=AuthPageResponse)
def sign_in(payload: UserSignIn, request: Request) -> AuthPageResponse:
    state = _state(request)
    user = authenticate_user(
        state.session_factory,
        email=payload.email,
        password=payload.password,
        require_verified=state.settings.require_verified_email,
    )
    if user is None:
        raise HTTPException(
            status_code=401, detail="Incorrect email or password, or email not verified."
        )
    if state.settings.is_admin_email(user.email) and not user.is_admin:
        user = set_user_admin_status(state.session_factory, user_id=user.id, is_admin=True)
    response = _issue_auth_page_session(
        request,
        user=user,
        detail="Signed in.",
    )
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="auth.sign_in",
        message="User signed in from frontend auth page.",
        entity_type="user",
        entity_id=user.id,
        metadata={"remember_me": payload.remember_me},
    )
    return response


@router.post("/auth/token", response_model=AccessTokenResponse)
def login_form(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends()
) -> AccessTokenResponse:
    state = _state(request)
    user = authenticate_user(
        state.session_factory,
        email=form_data.username,
        password=form_data.password,
        require_verified=state.settings.require_verified_email,
    )
    if user is None:
        raise HTTPException(
            status_code=401, detail="Incorrect username or password, or email not verified."
        )
    if state.settings.is_admin_email(user.email) and not user.is_admin:
        user = set_user_admin_status(state.session_factory, user_id=user.id, is_admin=True)
    token, expires_at = create_user_session(
        state.session_factory,
        user_id=user.id,
        ttl_minutes=state.settings.access_token_ttl_minutes,
    )
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="auth.login",
        message="User logged in via OAuth2 form.",
        entity_type="user",
        entity_id=user.id,
    )
    return AccessTokenResponse(access_token=token, expires_at=expires_at, user=user)


@router.get("/auth/me", response_model=UserPublic)
def auth_me(user: UserPublic = Depends(require_authenticated_user)) -> UserPublic:
    return user


@router.post("/auth/logout", response_model=MessageResponse)
def auth_logout(
    request: Request, context: AccessContext = Depends(require_access_context)
) -> MessageResponse:
    if context.raw_token is not None:
        revoke_token(_state(request).session_factory, context.raw_token)
    return MessageResponse(detail="Logged out.")


@router.post("/auth/request-email-verification", response_model=TokenActionPreview)
def request_email_verification(payload: EmailActionRequest, request: Request) -> TokenActionPreview:
    state = _state(request)
    token_pair = create_user_action_token(
        state.session_factory,
        email=payload.email,
        purpose="verify_email",
        ttl_minutes=state.settings.email_verification_ttl_minutes,
    )
    if token_pair is None:
        return TokenActionPreview(
            detail="If the account exists, a verification email has been queued."
        )
    token, expires_at = token_pair
    verification_link = _build_absolute_url(
        state.settings.base_url, f"/auth/verify-email?token={token}"
    )
    _maybe_record_email(
        request,
        to_email=payload.email,
        subject="Verify your NMRCheck account",
        body=f"Use this link to verify your account: {verification_link}",
        purpose="verify_email",
    )
    preview_token = token if state.settings.app_env != "production" else None
    return TokenActionPreview(
        detail="If the account exists, a verification email has been queued.",
        token=preview_token,
        expires_at=expires_at,
    )


@router.get("/auth/verify-email", response_model=MessageResponse)
def verify_email(token: str, request: Request) -> MessageResponse:
    user = consume_user_action_token(
        _state(request).session_factory, token=token, purpose="verify_email"
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Verification token is invalid or expired.")
    mark_user_verified(_state(request).session_factory, user_id=user.id)
    return MessageResponse(detail="Email verified successfully.")


@router.post("/auth/request-password-reset", response_model=TokenActionPreview)
def request_password_reset(payload: EmailActionRequest, request: Request) -> TokenActionPreview:
    state = _state(request)
    token_pair = create_user_action_token(
        state.session_factory,
        email=payload.email,
        purpose="reset_password",
        ttl_minutes=state.settings.password_reset_ttl_minutes,
    )
    if token_pair is None:
        return TokenActionPreview(
            detail="If the account exists, a password reset email has been queued."
        )
    token, expires_at = token_pair
    reset_link = _build_absolute_url(state.settings.base_url, f"/reset-password?token={token}")
    _maybe_record_email(
        request,
        to_email=payload.email,
        subject="Reset your NMRCheck password",
        body=f"Use this link to reset your password: {reset_link}",
        purpose="reset_password",
    )
    preview_token = token if state.settings.app_env != "production" else None
    return TokenActionPreview(
        detail="If the account exists, a password reset email has been queued.",
        token=preview_token,
        expires_at=expires_at,
    )


@router.post("/auth/reset-password", response_model=MessageResponse)
def reset_password(payload: PasswordResetConfirm, request: Request) -> MessageResponse:
    state = _state(request)
    user = consume_user_action_token(
        state.session_factory, token=payload.token, purpose="reset_password"
    )
    if user is None:
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired.")
    set_user_password(state.session_factory, user_id=user.id, new_password=payload.new_password)
    revoke_all_user_tokens(state.session_factory, user.id)
    return MessageResponse(detail="Password reset successful. Existing sessions have been revoked.")


@router.get(
    "/auth/outbox",
    response_model=list[EmailOutboxRecord],
    dependencies=[Depends(require_access_context)],
)
def auth_outbox(
    request: Request, limit: int = Query(default=20, ge=1, le=200)
) -> list[EmailOutboxRecord]:
    state = _state(request)
    if state.settings.app_env == "production":
        raise HTTPException(status_code=404, detail="Not found.")
    return list_email_outbox(state.session_factory, limit=limit)


@router.post(
    "/analyze/validate",
    response_model=ValidationReport,
    dependencies=[Depends(require_access_context)],
)
def validate(payload: AnalysisValidationInputs) -> ValidationReport:
    return validate_inputs(payload)


@router.post(
    "/analyze", response_model=AnalysisReport, dependencies=[Depends(require_access_context)]
)
def analyze(
    payload: AnalysisInputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AnalysisReport:
    _ensure_analysis_inputs_valid(payload)
    report = analyze_inputs(payload)
    hours_saved = _estimate_hours_saved(
        _state(request).settings, parsed_peak_count=report.parsed_peak_count
    )
    analysis_id = save_analysis(
        _state(request).session_factory,
        report,
        payload,
        user_id=context.user_id,
        hours_saved_estimate=hours_saved,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="analysis.run",
        message="Single analysis completed.",
        entity_type="analysis",
        entity_id=analysis_id,
        metadata={"hours_saved_estimate": hours_saved},
    )
    return report


@router.post(
    "/analyze/batch",
    response_model=BatchAnalysisReport,
    dependencies=[Depends(require_access_context)],
)
def analyze_batch(
    payload: BatchAnalysisInputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BatchAnalysisReport:
    _ensure_batch_inputs_valid(payload.items)
    reports: list[AnalysisReport] = []
    session_factory = _state(request).session_factory
    for item in payload.items:
        report = analyze_inputs(item)
        save_analysis(
            session_factory,
            report,
            item,
            user_id=context.user_id,
            hours_saved_estimate=_estimate_hours_saved(
                _state(request).settings, parsed_peak_count=report.parsed_peak_count
            ),
        )
        reports.append(report)
    _audit_from_context(
        request,
        context=context,
        event_type="analysis.batch",
        message="Batch analysis completed.",
        metadata={"items": len(reports)},
    )
    return BatchAnalysisReport(items=reports, total_items=len(reports))


@router.post(
    "/analyze/upload",
    response_model=BatchAnalysisReport,
    dependencies=[Depends(require_access_context)],
)
async def analyze_upload(
    request: Request,
    file: UploadFile = File(...),
    context: AccessContext = Depends(require_access_context),
) -> BatchAnalysisReport:
    content = await file.read()
    filename = file.filename or "batch.json"
    try:
        payload = parse_batch_upload(filename=filename, content=content)
    except UploadParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ensure_batch_inputs_valid(payload.items)
    session_factory = _state(request).session_factory
    reports: list[AnalysisReport] = []
    for item in payload.items:
        report = analyze_inputs(item)
        save_analysis(
            session_factory,
            report,
            item,
            user_id=context.user_id,
            hours_saved_estimate=_estimate_hours_saved(
                _state(request).settings, parsed_peak_count=report.parsed_peak_count
            ),
        )
        reports.append(report)
    return BatchAnalysisReport(items=reports, total_items=len(reports))


@router.post(
    "/spectrum/preview",
    response_model=SpectrumPreviewReport,
    dependencies=[Depends(require_access_context)],
)
async def spectrum_preview(
    request: Request,
    file: UploadFile = File(...),
    smiles: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    frequency_mhz: float | None = Form(default=None),
    reference_ppm: float | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=False),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    processed_baseline_correction: str = Form(default="none"),
    processed_baseline_order: int = Form(default=3),
    context: AccessContext = Depends(require_access_context),
) -> SpectrumPreviewReport:
    filename = file.filename or "spectrum.dat"
    content = await file.read()
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    display_mode_value = _unwrap_form_default(display_mode)
    vertical_gain_value = _coerce_optional_form_float(vertical_gain, default=1.0)
    debug_preview_value = _coerce_optional_form_bool(debug_preview, default=False)
    try:
        preview = parse_processed_spectrum(
            filename=filename,
            content=content,
            solvent=solvent,
            frequency_mhz=frequency_mhz,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            peak_sensitivity=peak_sensitivity,
            mask_solvent_regions=mask_solvent_regions,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            display_mode=display_mode_value,
            vertical_gain=vertical_gain_value,
            debug_preview=debug_preview_value,
            processed_baseline_correction=_unwrap_form_default(processed_baseline_correction),
            processed_baseline_order=int(_unwrap_form_default(processed_baseline_order) or 3),
        )
    except (SpectrumParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Processed spectrum preview") from exc
    _audit_from_context(
        request,
        context=context,
        event_type="spectrum.preview",
        message="Processed spectrum preview generated.",
        metadata={
            "filename": filename,
            "format": preview.format_detected,
            "mode": preview.source_mode,
            "peak_sensitivity": peak_sensitivity,
            "mask_solvent_regions": mask_solvent_regions,
            "display_mode": display_mode_value,
            "debug_preview": debug_preview_value,
            "reference_text_supplied": bool(reference_nmr_text and reference_nmr_text.strip()),
        },
    )
    return preview


@router.post(
    "/spectrum/analyze",
    response_model=SpectrumAnalyzeResult,
    dependencies=[Depends(require_access_context)],
)
async def spectrum_analyze(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    frequency_mhz: float | None = Form(default=None),
    reference_ppm: float | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    manual_nmr_text: str | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=False),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    processed_baseline_correction: str = Form(default="none"),
    processed_baseline_order: int = Form(default=3),
    context: AccessContext = Depends(require_access_context),
) -> SpectrumAnalyzeResult:
    filename = file.filename or "spectrum.dat"
    content = await file.read()
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    display_mode_value = _unwrap_form_default(display_mode)
    vertical_gain_value = _coerce_optional_form_float(vertical_gain, default=1.0)
    debug_preview_value = _coerce_optional_form_bool(debug_preview, default=False)
    try:
        preview = parse_processed_spectrum(
            filename=filename,
            content=content,
            solvent=solvent,
            frequency_mhz=frequency_mhz,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            peak_sensitivity=peak_sensitivity,
            mask_solvent_regions=mask_solvent_regions,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            display_mode=display_mode_value,
            vertical_gain=vertical_gain_value,
            debug_preview=debug_preview_value,
            processed_baseline_correction=_unwrap_form_default(processed_baseline_correction),
            processed_baseline_order=int(_unwrap_form_default(processed_baseline_order) or 3),
        )
    except (SpectrumParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Processed spectrum analysis") from exc

    reviewed_nmr_text = (
        manual_nmr_text.strip()
        if manual_nmr_text is not None and manual_nmr_text.strip()
        else preview.inferred_nmr_text
    )
    if not reviewed_nmr_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Raw FID processing did not infer any peaks; review FID QA diagnostics before processing.",
        )
    generated_inputs = AnalysisInputs(
        sample_id=sample_id,
        smiles=smiles,
        nmr_text=reviewed_nmr_text,
        solvent=solvent,
    )
    _ensure_analysis_inputs_valid(generated_inputs)
    report = analyze_inputs(generated_inputs)
    combined_notes = list(report.notes)
    if reviewed_nmr_text != preview.inferred_nmr_text:
        combined_notes.insert(
            0,
            "Reviewer-adjusted peak acceptance/exclusion decisions were used for the final processed-spectrum analysis.",
        )
    for warning in preview.warnings:
        if warning not in combined_notes:
            combined_notes.append(warning)
    report = report.model_copy(update={"notes": combined_notes})
    hours_saved = _estimate_hours_saved(
        _state(request).settings, parsed_peak_count=report.parsed_peak_count
    )
    analysis_id = save_analysis(
        _state(request).session_factory,
        report,
        generated_inputs,
        user_id=context.user_id,
        hours_saved_estimate=hours_saved,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="spectrum.analyze",
        message="Processed spectrum analyzed through inferred peak list.",
        entity_type="analysis",
        entity_id=analysis_id,
        metadata={
            "filename": filename,
            "format": preview.format_detected,
            "mode": preview.source_mode,
            "hours_saved_estimate": hours_saved,
            "peak_sensitivity": peak_sensitivity,
            "mask_solvent_regions": mask_solvent_regions,
            "reference_text_supplied": bool(reference_nmr_text and reference_nmr_text.strip()),
            "manual_nmr_text_supplied": reviewed_nmr_text != preview.inferred_nmr_text,
        },
    )
    return SpectrumAnalyzeResult(
        preview=preview, generated_inputs=generated_inputs, analysis=report
    )


def _unwrap_form_default(value: Any) -> Any:
    return getattr(value, "default", value)


def _coerce_optional_form_bool(value: Any, *, default: bool) -> bool:
    value = _unwrap_form_default(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_optional_form_float(value: Any, *, default: float) -> float:
    value = _unwrap_form_default(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_display_mode(value: Any) -> str:
    value = _unwrap_form_default(value)
    normalized = str(value or "real").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"weak_peak_magnifier", "weak_peak_magnifier_view"}:
        return "magnifier"
    return normalized if normalized in {"real", "magnifier"} else "real"


_TEXT_NUMERIC_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _processed_parser_upload(
    *,
    filename: str,
    content: bytes,
) -> tuple[str, bytes, list[str], dict[str, Any]]:
    name = filename or "processed_spectrum.dat"
    lowered = name.lower()
    if not lowered.endswith(".txt"):
        return (name, content, [], {})

    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    sample = "\n".join(text.splitlines()[:10])
    notes = [
        "TXT processed spectrum upload was normalized for the existing processed-spectrum parser."
    ]
    metadata: dict[str, Any] = {"txt_upload_normalized": True}
    if any(delimiter in sample for delimiter in (",", "\t", ";")):
        metadata["txt_interpretation"] = "delimited_table"
        return (f"{Path(name).stem or 'processed_spectrum'}.csv", content, notes, metadata)

    pairs: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("#", "//")):
            continue
        values = _TEXT_NUMERIC_RE.findall(stripped)
        if len(values) >= 2:
            pairs.append((values[0], values[1]))
    if not pairs:
        raise SpectrumParseError("TXT processed spectrum did not contain numeric x/y pairs.")

    csv_text = "ppm,intensity\n" + "\n".join(f"{x},{y}" for x, y in pairs)
    metadata.update(
        {
            "txt_interpretation": "whitespace_numeric_pairs",
            "numeric_pair_count": len(pairs),
        }
    )
    return (
        f"{Path(name).stem or 'processed_spectrum'}.csv",
        csv_text.encode("utf-8"),
        notes,
        metadata,
    )


def _xy_from_spectrum_points(points: list[Any]) -> tuple[list[float], list[float]]:
    x_values: list[float] = []
    y_values: list[float] = []
    for point in points:
        if isinstance(point, dict):
            x = point.get("shift_ppm", point.get("x"))
            y = point.get("intensity", point.get("y"))
        else:
            x = getattr(point, "shift_ppm", None)
            y = getattr(point, "intensity", None)
        try:
            x_values.append(float(x))
            y_values.append(float(y))
        except (TypeError, ValueError):
            continue
    return (x_values, y_values)


def _reversed_x_axis(x_values: list[float]) -> bool:
    return len(x_values) < 2 or x_values[0] > x_values[-1]


def _model_dicts(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _carbon13_preview_points(preview: Carbon13UploadPreview) -> tuple[list[float], list[float]]:
    points = preview.metadata.get("preview_points")
    if isinstance(points, list) and points:
        return _xy_from_spectrum_points(points)
    x_values: list[float] = []
    y_values: list[float] = []
    for peak in preview.peaks:
        x_values.append(float(peak.shift_ppm))
        y_values.append(float(peak.intensity if peak.intensity is not None else 1.0))
    return (x_values, y_values)


def _solvent_warnings_from_processed(
    *,
    nucleus: str,
    warnings: list[str],
    peaks: list[dict[str, Any]],
) -> list[str]:
    selected = [
        warning
        for warning in warnings
        if "solvent" in warning.lower() or "water" in warning.lower()
    ]
    if nucleus == "13C":
        count = sum(1 for peak in peaks if peak.get("is_likely_solvent"))
        if count:
            selected.append(f"{count} inferred 13C peak(s) overlap known solvent-carbon regions.")
    return list(dict.fromkeys(selected))


def _impurity_warnings_from_processed(
    *,
    nucleus: str,
    warnings: list[str],
    peaks: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[str]:
    selected = [warning for warning in warnings if "impurity" in warning.lower()]
    if nucleus == "1H":
        candidates = metadata.get("impurity_candidates")
        if isinstance(candidates, list) and candidates:
            selected.append(
                f"{len(candidates)} 1H peak(s) were flagged as possible impurity candidates."
            )
    if nucleus == "13C":
        count = sum(1 for peak in peaks if peak.get("is_likely_impurity"))
        if count:
            selected.append(
                f"{count} inferred 13C peak(s) overlap embedded impurity-reference shifts."
            )
    return list(dict.fromkeys(selected))


def _comparison_score(comparison: Any | None) -> float | None:
    if comparison is None:
        return None
    matched = float(getattr(comparison, "matched_count", 0) or 0)
    total = (
        matched
        + float(getattr(comparison, "missing_count", 0) or 0)
        + float(getattr(comparison, "extra_count", 0) or 0)
    )
    if total <= 0:
        return None
    return round(max(0.0, min(1.0, matched / total)), 4)


def _candidate_summary_from_text(
    *,
    candidates_text: str | None,
    sample_id: str | None,
    solvent: str | None,
    proton_nmr_text: str | None,
    carbon13_text: str | None,
) -> tuple[float | None, list[str], dict[str, Any], list[str]]:
    if not candidates_text or not candidates_text.strip():
        return (None, [], {}, [])
    try:
        candidates = parse_candidate_text(candidates_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = compare_candidates(
        CandidateComparisonRequest(
            sample_id=sample_id,
            solvent=solvent,
            candidates=candidates,
            proton_nmr_text=proton_nmr_text,
            carbon13_text=carbon13_text,
        )
    )
    best = result.best_candidate
    summary = [
        f"Candidate comparison ranked {result.candidate_count} candidate(s).",
        "Candidate comparison is evidence ranking, not structure confirmation.",
    ]
    if best is not None:
        summary.insert(
            1,
            f"Best-ranked candidate: {best.name or best.smiles} with score {best.total_score:.3f}.",
        )
    metadata = {"candidate_comparison": result.model_dump(mode="json")}
    warnings = list(result.warnings)
    return (best.total_score if best is not None else None, summary, metadata, warnings)


def _carbon13_text_from_peaks(peaks: list[dict[str, Any]]) -> str:
    shifts = [peak.get("shift_ppm") for peak in peaks]
    formatted = [f"{float(shift):.3f}" for shift in shifts if shift is not None]
    return "13C NMR δ " + ", ".join(formatted) if formatted else ""


def _vendor_expectation_warnings(*, requested_vendor: str, vendor_detected: str) -> list[str]:
    if requested_vendor == "auto":
        return []
    normalized_detected = vendor_detected.strip().lower()
    if requested_vendor == "bruker" and "bruker" in normalized_detected:
        return []
    if requested_vendor == "agilent_varian" and (
        "varian" in normalized_detected or "agilent" in normalized_detected
    ):
        return []
    return [
        f"Requested vendor '{requested_vendor}' did not match detected vendor "
        f"'{vendor_detected or 'unknown'}'; auto-detected metadata was preserved for review."
    ]


def _raw_fid_file_inventory(provenance: dict[str, Any]) -> dict[str, Any]:
    files = list(provenance.get("files_found") or [])
    return {
        "files": files,
        "file_count": int(provenance.get("file_count") or len(files)),
        "dataset_root": provenance.get("dataset_root"),
        "required_files_present": bool(provenance.get("required_files_present")),
    }


def _processing_parameters_payload(preview: FIDPreviewReport) -> dict[str, Any]:
    metadata = preview.processing_metadata
    return {
        "processing_parameters": metadata.processing_parameters,
        "processing_recipe": metadata.processing_recipe.model_dump(mode="json"),
        "phase_settings": metadata.phase_settings,
        "baseline_correction": metadata.baseline_correction,
        "digital_filter_correction_status": metadata.digital_filter_correction_status,
        "group_delay_correction_applied": metadata.group_delay_correction_applied,
        "automatic_phase_correction": metadata.automatic_phase_correction,
        "automatic_baseline_correction": metadata.automatic_baseline_correction,
    }


def _fid_settings_from_form(
    *,
    selected_preset: str | None,
    processing_preset: str | None,
    zero_fill_factor: int | None,
    line_broadening_hz: float | None,
    apodization_mode: str = "exponential",
    apply_group_delay: bool,
    auto_phase: bool,
    auto_baseline: bool,
    phase_mode: str,
    phase_p0: float,
    phase_p1: float,
    baseline_correction: str,
    baseline_order: int,
    baseline_lock: bool | None,
    peak_sensitivity: float | None,
    mask_solvent_regions: bool,
    display_mode: str = "real",
    vertical_gain: float = 1.0,
    debug_preview: bool = False,
) -> FIDProcessingSettings:
    display_mode = _coerce_display_mode(display_mode)
    apply_group_delay = _coerce_optional_form_bool(apply_group_delay, default=True)
    auto_phase = _coerce_optional_form_bool(auto_phase, default=True)
    auto_baseline = _coerce_optional_form_bool(auto_baseline, default=True)
    mask_solvent_regions = _coerce_optional_form_bool(mask_solvent_regions, default=True)
    phase_mode = normalize_phase_mode(_unwrap_form_default(phase_mode))
    apodization_mode = _unwrap_form_default(apodization_mode) or "exponential"
    phase_p0 = _coerce_optional_form_float(phase_p0, default=0.0)
    phase_p1 = _coerce_optional_form_float(phase_p1, default=0.0)
    baseline_correction = normalize_baseline_mode(_unwrap_form_default(baseline_correction))
    try:
        baseline_order = max(1, min(8, int(_unwrap_form_default(baseline_order))))
    except (TypeError, ValueError):
        baseline_order = 3
    vertical_gain = _coerce_optional_form_float(vertical_gain, default=1.0)
    debug_preview = _coerce_optional_form_bool(debug_preview, default=False)
    processing_preset = _unwrap_form_default(processing_preset)
    baseline_lock = _unwrap_form_default(baseline_lock)
    effective_preset = processing_preset or selected_preset
    baseline_lock_visual_only = (
        _coerce_optional_form_bool(baseline_lock, default=True)
        if baseline_lock is not None
        else True
    )
    return fid_settings_from_preset(
        selected_preset=effective_preset,
        zero_fill_factor=zero_fill_factor,
        apodization_mode=apodization_mode,
        line_broadening_hz=line_broadening_hz,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock_visual_only=baseline_lock_visual_only,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )


def _fid_processing_notes(preview: FIDPreviewReport, *, manual_review_used: bool) -> list[str]:
    metadata = preview.processing_metadata
    peak_text = ", ".join(
        f"{peak.shift_ppm:.2f} ppm/{peak.integration_h:g}H"
        for peak in metadata.extracted_peak_list[:12]
    )
    files_found = ", ".join(
        f"{name}={'yes' if present else 'no'}"
        for name, present in sorted(metadata.raw_dataset_files_found.items())
    )
    notes = [
        f"Raw FID beta source detected as {metadata.vendor_format_detected}.",
        f"FID processing preset: {metadata.selected_preset}.",
        f"Raw dataset files found: {files_found or 'not recorded'}.",
        f"FID processing parameters: zero_fill_factor={metadata.processing_parameters.get('zero_fill_factor')}, line_broadening_hz={metadata.processing_parameters.get('line_broadening_hz')}.",
        f"FID QA result: {metadata.qa_diagnostics.quality_label} ({metadata.qa_diagnostics.quality_score:g}).",
        f"Group delay correction applied: {'yes' if metadata.group_delay_correction_applied else 'no'}.",
        f"Automatic phasing: {'yes' if metadata.automatic_phase_correction else 'no'}; automatic baseline correction: {'yes' if metadata.automatic_baseline_correction else 'no'}.",
        f"Reference ppm used: {metadata.reference_ppm if metadata.reference_ppm is not None else 'not supplied'}.",
        f"Solvent context used for FID processing: {metadata.solvent or 'not supplied'}.",
        f"Raw FID extracted peak list: {peak_text or 'no peaks inferred'}.",
        f"Human review status: {metadata.human_review_status}.",
        "Human reviewer signoff is required because raw FID processing can change spectrum appearance.",
    ]
    if manual_review_used:
        notes.insert(
            0,
            "Reviewer-adjusted peak acceptance/exclusion decisions were used for the final raw FID-derived analysis.",
        )
    for warning in preview.warnings:
        if warning not in notes:
            notes.append(warning)
    return notes


@router.post(
    "/nmr/processed/preview",
    response_model=NMRProcessedPreviewResponse,
    dependencies=[Depends(require_access_context)],
)
async def nmr_processed_preview_route(
    request: Request,
    file: UploadFile = File(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: Literal["1H", "13C"] = Form(default="1H"),
    spectrometer_frequency_mhz: float | None = Form(default=None),
    nmr_text: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> NMRProcessedPreviewResponse:
    filename = file.filename or "processed_spectrum.dat"
    content = await file.read()
    try:
        parser_filename, parser_content, parser_notes, parser_metadata = _processed_parser_upload(
            filename=filename,
            content=content,
        )
        if nucleus == "1H":
            preview = parse_processed_spectrum(
                filename=parser_filename,
                content=parser_content,
                solvent=solvent,
                frequency_mhz=spectrometer_frequency_mhz,
                reference_nmr_text=nmr_text,
                mask_solvent_regions=False,
                display_mode="real",
                vertical_gain=1.0,
            )
            x_values, y_values = _xy_from_spectrum_points(preview.preview_points)
            metadata = {
                **preview.metadata,
                **parser_metadata,
                "format_detected": preview.format_detected,
                "source_mode": preview.source_mode,
                "legacy_route_wrapped": "/spectrum/preview",
                "spectrometer_frequency_mhz": spectrometer_frequency_mhz,
                "nmr_text_supplied": bool(nmr_text and nmr_text.strip()),
            }
            warnings = list(preview.warnings)
        else:
            carbon_preview = parse_carbon13_processed_spectrum(
                parser_filename,
                parser_content,
                solvent=solvent,
                mask_solvent_regions=False,
                display_mode="real",
                vertical_gain=1.0,
            )
            x_values, y_values = _carbon13_preview_points(carbon_preview)
            metadata = {
                **carbon_preview.metadata,
                **parser_metadata,
                "format_detected": carbon_preview.metadata.get("format"),
                "source_mode": carbon_preview.source_mode,
                "legacy_route_wrapped": "/carbon13/spectrum/preview",
                "spectrometer_frequency_mhz": spectrometer_frequency_mhz,
                "nmr_text_supplied": bool(nmr_text and nmr_text.strip()),
            }
            warnings = list(carbon_preview.warnings)
            preview = None
    except (SpectrumParseError, Carbon13ParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="NMR processed spectrum preview") from exc

    point_count = int(
        metadata.get("point_count")
        or (preview.point_count if nucleus == "1H" and preview is not None else len(x_values))
    )
    notes = [
        *parser_notes,
        "Preview arrays are display-ready and may be downsampled; point_count reports "
        "the parsed source size when available.",
        "Processed-spectrum evidence is a review aid and does not confirm structure by itself.",
    ]
    _audit_from_context(
        request,
        context=context,
        event_type="nmr.processed.preview",
        message="Frontend-facing NMR processed spectrum preview generated.",
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "nucleus": nucleus,
            "point_count": point_count,
        },
    )
    return NMRProcessedPreviewResponse(
        sample_id=sample_id,
        nucleus=nucleus,
        filename=filename,
        point_count=point_count,
        x=x_values,
        y=y_values,
        x_label="ppm",
        y_label="intensity",
        reversed_x_axis=_reversed_x_axis(x_values),
        warnings=warnings,
        notes=notes,
        metadata=metadata,
    )


@router.post(
    "/nmr/processed/analyze",
    response_model=NMRProcessedAnalyzeResponse,
    dependencies=[Depends(require_access_context)],
)
async def nmr_processed_analyze_route(
    request: Request,
    file: UploadFile = File(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: Literal["1H", "13C"] = Form(default="1H"),
    spectrometer_frequency_mhz: float | None = Form(default=None),
    nmr_text: str | None = Form(default=None),
    candidates_text: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> NMRProcessedAnalyzeResponse:
    filename = file.filename or "processed_spectrum.dat"
    content = await file.read()
    candidate_score: float | None = None
    candidate_summary: list[str] = []
    candidate_metadata: dict[str, Any] = {}
    candidate_warnings: list[str] = []
    comparison_score: float | None = None
    try:
        parser_filename, parser_content, parser_notes, parser_metadata = _processed_parser_upload(
            filename=filename,
            content=content,
        )
        if nucleus == "1H":
            preview = parse_processed_spectrum(
                filename=parser_filename,
                content=parser_content,
                solvent=solvent,
                frequency_mhz=spectrometer_frequency_mhz,
                reference_nmr_text=nmr_text,
                mask_solvent_regions=bool(solvent),
                display_mode="real",
                vertical_gain=1.0,
            )
            peaks = _model_dicts(preview.inferred_peaks)
            metadata = {
                **preview.metadata,
                **parser_metadata,
                "format_detected": preview.format_detected,
                "source_mode": preview.source_mode,
                "legacy_route_wrapped": "/spectrum/analyze",
                "spectrometer_frequency_mhz": spectrometer_frequency_mhz,
                "nmr_text_supplied": bool(nmr_text and nmr_text.strip()),
            }
            comparison_score = _comparison_score(preview.comparison)
            (
                candidate_score,
                candidate_summary,
                candidate_metadata,
                candidate_warnings,
            ) = _candidate_summary_from_text(
                candidates_text=candidates_text,
                sample_id=sample_id,
                solvent=solvent,
                proton_nmr_text=(
                    nmr_text.strip() if nmr_text and nmr_text.strip() else preview.inferred_nmr_text
                ),
                carbon13_text=None,
            )
            warnings = [*preview.warnings, *candidate_warnings]
            point_count = preview.point_count
        else:
            carbon_preview = parse_carbon13_processed_spectrum(
                parser_filename,
                parser_content,
                solvent=solvent,
                mask_solvent_regions=bool(solvent),
                display_mode="real",
                vertical_gain=1.0,
            )
            peaks = _model_dicts(carbon_preview.peaks)
            generated_carbon13_text = _carbon13_text_from_peaks(peaks)
            metadata = {
                **carbon_preview.metadata,
                **parser_metadata,
                "format_detected": carbon_preview.metadata.get("format"),
                "source_mode": carbon_preview.source_mode,
                "legacy_route_wrapped": "/carbon13/spectrum/analyze",
                "spectrometer_frequency_mhz": spectrometer_frequency_mhz,
                "nmr_text_supplied": bool(nmr_text and nmr_text.strip()),
                "generated_carbon13_text": generated_carbon13_text,
            }
            if nmr_text and nmr_text.strip():
                try:
                    reference_peaks = parse_carbon13_text(nmr_text, solvent=solvent)
                    matched = sum(
                        1
                        for reference_peak in reference_peaks
                        if any(
                            abs(float(reference_peak.shift_ppm) - float(peak["shift_ppm"])) <= 0.35
                            for peak in peaks
                        )
                    )
                    denominator = max(len(reference_peaks), len(peaks), 1)
                    comparison_score = round(matched / denominator, 4)
                    metadata["carbon13_text_comparison"] = {
                        "reference_peak_count": len(reference_peaks),
                        "matched_peak_count": matched,
                    }
                except Carbon13ParseError as exc:
                    metadata["carbon13_text_comparison_error"] = str(exc)
            (
                candidate_score,
                candidate_summary,
                candidate_metadata,
                candidate_warnings,
            ) = _candidate_summary_from_text(
                candidates_text=candidates_text,
                sample_id=sample_id,
                solvent=solvent,
                proton_nmr_text=None,
                carbon13_text=(
                    nmr_text.strip() if nmr_text and nmr_text.strip() else generated_carbon13_text
                ),
            )
            warnings = [*carbon_preview.warnings, *candidate_warnings]
            point_count = int(carbon_preview.metadata.get("point_count") or len(peaks))
    except (SpectrumParseError, Carbon13ParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="NMR processed spectrum analysis") from exc

    metadata.update(candidate_metadata)
    solvent_warnings = _solvent_warnings_from_processed(
        nucleus=nucleus,
        warnings=warnings,
        peaks=peaks,
    )
    impurity_warnings = _impurity_warnings_from_processed(
        nucleus=nucleus,
        warnings=warnings,
        peaks=peaks,
        metadata=metadata,
    )
    score = candidate_score if candidate_score is not None else comparison_score
    evidence_summary = [
        f"Parsed {point_count} spectrum point(s) and returned {len(peaks)} inferred peak(s).",
        *candidate_summary,
        "Human review is required before using processed-spectrum evidence for final "
        "interpretation.",
    ]
    if nmr_text and nmr_text.strip():
        evidence_summary.insert(
            1,
            "Supplied NMR text was used as comparison context where supported by the parser.",
        )
    notes = [
        *parser_notes,
        "Peak picking uses the existing NMRCheck heuristic parser and should be reviewed "
        "for weak or overlapped signals.",
        "This endpoint reports evidence summaries only; it does not overclaim structure "
        "confirmation.",
    ]
    _audit_from_context(
        request,
        context=context,
        event_type="nmr.processed.analyze",
        message="Frontend-facing NMR processed spectrum analysis generated.",
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "nucleus": nucleus,
            "point_count": point_count,
            "peak_count": len(peaks),
            "candidate_text_supplied": bool(candidates_text and candidates_text.strip()),
        },
    )
    return NMRProcessedAnalyzeResponse(
        sample_id=sample_id,
        nucleus=nucleus,
        filename=filename,
        point_count=point_count,
        peak_count=len(peaks),
        peaks=peaks,
        solvent_warnings=solvent_warnings,
        impurity_warnings=impurity_warnings,
        analysis_score=score,
        evidence_summary=evidence_summary,
        warnings=list(dict.fromkeys(warnings)),
        notes=notes,
        metadata=metadata,
    )


@router.post(
    "/nmr/raw-fid/preview",
    response_model=NMRRawFIDPreviewResponse,
    dependencies=[Depends(require_access_context)],
)
async def nmr_raw_fid_preview_route(
    request: Request,
    file: UploadFile = File(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: Literal["1H", "13C"] = Form(default="1H"),
    vendor: Literal["auto", "bruker", "agilent_varian"] = Form(default="auto"),
    context: AccessContext = Depends(require_access_context),
) -> NMRRawFIDPreviewResponse:
    filename = file.filename or "raw_fid_archive.zip"
    content = await file.read()
    provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    raw_sha256 = str(provenance.get("sha256") or hashlib.sha256(content).hexdigest())
    vendor_detected = str(provenance.get("vendor_detected") or "unknown")
    warnings = [
        *list(provenance.get("warnings") or []),
        *_vendor_expectation_warnings(requested_vendor=vendor, vendor_detected=vendor_detected),
    ]
    notes = [
        "Raw archive was hashed, safely inspected, and stored as immutable source data.",
        "No Fourier transform, phasing, baseline correction, or peak picking was run by "
        "this preview endpoint.",
        "Human review remains required for raw FID-derived evidence.",
    ]
    metadata = {
        "raw_archive_id": provenance.get("raw_archive_id") or raw_sha256,
        "raw_archive_db_id": provenance.get("raw_archive_db_id"),
        "storage_backend": provenance.get("storage_backend"),
        "storage_status": provenance.get("storage_status"),
        "raw_data_immutable": provenance.get("raw_data_immutable", True),
        "raw_bytes_returned": False,
        "requested_vendor": vendor,
        "legacy_route_wrapped": "/raw-fid/upload",
    }
    _audit_from_context(
        request,
        context=context,
        event_type="nmr.raw_fid.preview",
        message="Frontend-facing raw FID archive metadata preview generated.",
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "raw_sha256": raw_sha256,
            "vendor_detected": vendor_detected,
            "nucleus": nucleus,
        },
    )
    return NMRRawFIDPreviewResponse(
        sample_id=sample_id,
        filename=filename,
        raw_sha256=raw_sha256,
        vendor_detected=vendor_detected,
        nucleus=nucleus,
        solvent=solvent,
        acquisition_parameters=dict(provenance.get("acquisition_metadata") or {}),
        file_inventory=_raw_fid_file_inventory(provenance),
        warnings=warnings,
        notes=notes,
        metadata=metadata,
    )


@router.post(
    "/nmr/raw-fid/process",
    response_model=NMRRawFIDProcessResponse,
    dependencies=[Depends(require_access_context)],
)
async def nmr_raw_fid_process_route(
    request: Request,
    file: UploadFile = File(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: Literal["1H", "13C"] = Form(default="1H"),
    vendor: Literal["auto", "bruker", "agilent_varian"] = Form(default="auto"),
    processing_preset: str | None = Form(default="balanced"),
    preserve_raw: bool = Form(default=True),
    context: AccessContext = Depends(require_access_context),
) -> NMRRawFIDProcessResponse:
    filename = file.filename or "raw_fid_archive.zip"
    content = await file.read()
    raw_upload_provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    raw_upload_provenance = dict(raw_upload_provenance)
    extra_warnings = _vendor_expectation_warnings(
        requested_vendor=vendor,
        vendor_detected=str(raw_upload_provenance.get("vendor_detected") or "unknown"),
    )
    if not _coerce_optional_form_bool(preserve_raw, default=True):
        extra_warnings.append(
            "preserve_raw=false was ignored; raw FID uploads are always preserved as "
            "immutable vault records."
        )
    provenance_warnings = list(raw_upload_provenance.get("warnings") or [])
    provenance_warnings.extend(
        warning for warning in extra_warnings if warning not in provenance_warnings
    )
    raw_upload_provenance["warnings"] = provenance_warnings
    raw_upload_provenance["frontend_endpoint"] = "/nmr/raw-fid/process"
    raw_upload_provenance["raw_data_immutable"] = True

    settings = _fid_settings_from_form(
        selected_preset=processing_preset or "balanced",
        processing_preset=processing_preset,
        zero_fill_factor=None,
        line_broadening_hz=None,
        apodization_mode="exponential",
        apply_group_delay=True,
        auto_phase=True,
        auto_baseline=True,
        phase_mode="auto",
        phase_p0=0.0,
        phase_p1=0.0,
        baseline_correction="bernstein",
        baseline_order=3,
        baseline_lock=None,
        peak_sensitivity=None,
        mask_solvent_regions=True,
        display_mode="real",
        vertical_gain=1.0,
        debug_preview=False,
    )
    try:
        preview = process_bruker_1d_zip(
            filename=filename,
            content=content,
            solvent=solvent,
            nucleus=nucleus,
            settings=settings,
            raw_upload_provenance=raw_upload_provenance,
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="NMR raw FID processing") from exc

    fid_run = save_fid_run(
        _state(request).session_factory,
        preview,
        user_id=context.user_id,
        analysis_id=None,
        sample_id=sample_id,
    )
    preview = fid_run.preview
    x_values, y_values = _xy_from_spectrum_points(preview.preview_points)
    raw_sha256 = str(raw_upload_provenance.get("sha256") or hashlib.sha256(content).hexdigest())
    processing_parameters = _processing_parameters_payload(preview)
    notes = [
        "Raw archive was preserved as immutable source data before processing.",
        "Processing used a temporary derived workspace and did not overwrite raw vendor files.",
        "Phase and baseline correction details are reported in processing_parameters.",
        "Human reviewer signoff is required before final report use.",
    ]
    metadata = {
        **preview.metadata,
        "fid_run_id": preview.fid_run_id,
        "raw_archive_id": raw_upload_provenance.get("raw_archive_id") or raw_sha256,
        "raw_archive_db_id": raw_upload_provenance.get("raw_archive_db_id"),
        "requested_vendor": vendor,
        "preserve_raw": True,
        "legacy_route_wrapped": "/fid/process + immutable raw vault processing core",
    }
    _audit_from_context(
        request,
        context=context,
        event_type="nmr.raw_fid.process",
        message="Frontend-facing raw FID archive processed into derived spectrum data.",
        entity_type="fid_run",
        entity_id=fid_run.id,
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "raw_sha256": raw_sha256,
            "vendor_detected": preview.processing_metadata.vendor_format_detected,
            "nucleus": nucleus,
            "processing_preset": settings.selected_preset,
        },
    )
    return NMRRawFIDProcessResponse(
        sample_id=sample_id,
        filename=filename,
        raw_sha256=raw_sha256,
        vendor_detected=preview.processing_metadata.vendor_format_detected,
        nucleus=nucleus,
        processing_preset=settings.selected_preset,
        processing_parameters=processing_parameters,
        point_count=preview.point_count,
        x=x_values,
        y=y_values,
        x_label="ppm",
        y_label="intensity",
        reversed_x_axis=_reversed_x_axis(x_values),
        warnings=list(dict.fromkeys([*preview.warnings, *extra_warnings])),
        notes=notes,
        metadata=metadata,
    )


@router.get("/fid/presets", response_model=list[FIDProcessingPreset])
def fid_presets() -> list[FIDProcessingPreset]:
    return available_fid_presets()


@router.post(
    "/raw-fid/upload",
    response_model=RawArchiveRecord,
    dependencies=[Depends(require_access_context)],
)
async def raw_fid_upload(
    request: Request,
    file: UploadFile = File(...),
    context: AccessContext = Depends(require_access_context),
) -> RawArchiveRecord:
    filename = file.filename or "raw_fid_archive.zip"
    content = await file.read()
    provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    record_payload = provenance.get("raw_archive_record")
    if not isinstance(record_payload, dict):
        raise HTTPException(status_code=500, detail="Raw FID vault storage is not configured.")
    archive = RawArchiveRecord.model_validate(record_payload)
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.uploaded",
        message="Raw FID archive uploaded to immutable vault.",
        extra={
            "byte_size": archive.byte_size,
            "content_type": file.content_type,
        },
    )
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.hash_verified",
        message="Raw FID archive SHA-256 hash verified after upload.",
        extra={"action": "upload", "byte_size": archive.byte_size},
    )
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.metadata_extracted",
        message="Raw FID acquisition metadata extracted from immutable upload.",
        extra={
            "dataset_root": archive.dataset_root,
            "required_files_present": archive.required_files_present,
            "acquisition_metadata_keys": sorted(archive.acquisition_metadata.keys()),
        },
    )
    return archive


@router.get("/raw-fid/{archive_id}", dependencies=[Depends(require_access_context)])
def raw_fid_archive_detail(
    archive_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> dict[str, object]:
    archive = _get_visible_raw_archive(request, archive_id, context)
    integrity = _raw_archive_integrity(archive)
    if integrity.get("sha256_verified"):
        _audit_raw_fid_event(
            request,
            context=context,
            archive=archive,
            event_type="raw_fid.hash_verified",
            message="Raw FID archive SHA-256 hash verified during metadata lookup.",
            extra={"action": "metadata_lookup"},
        )
    else:
        _audit_raw_fid_event(
            request,
            context=context,
            archive=archive,
            event_type="raw_fid.integrity_failure",
            message="Raw FID archive integrity check failed during metadata lookup.",
            extra={"action": "metadata_lookup", "error": str(integrity.get("error") or "unknown")},
        )
    return {
        "archive": archive.model_dump(mode="json"),
        "integrity": integrity,
        "raw_bytes_returned": False,
    }


@router.get("/raw-fid/{archive_id}/download", dependencies=[Depends(require_access_context)])
def raw_fid_archive_download(
    archive_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    archive = _get_visible_raw_archive(request, archive_id, context)
    raw_bytes = _load_raw_archive_bytes_for_request(
        request,
        context=context,
        archive=archive,
        action="download",
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{Path(archive.filename).name or "raw_fid_archive"}"'
    }
    return StreamingResponse(
        io.BytesIO(raw_bytes), media_type="application/octet-stream", headers=headers
    )


@router.post(
    "/raw-fid/{archive_id}/preview",
    response_model=FIDPreviewReport,
    dependencies=[Depends(require_access_context)],
)
def raw_fid_archive_preview(
    archive_id: str,
    request: Request,
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: str = Form(default="1H"),
    reference_ppm: float | None = Form(default=None),
    smiles: str | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    save_run: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> FIDPreviewReport:
    archive = _get_visible_raw_archive(request, archive_id, context)
    raw_bytes = _load_raw_archive_bytes_for_request(
        request,
        context=context,
        archive=archive,
        action="preview",
    )
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview = process_bruker_1d_zip(
            filename=archive.filename,
            content=raw_bytes,
            solvent=solvent,
            nucleus=nucleus,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            settings=settings,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            raw_upload_provenance=_raw_fid_archive_provenance_from_record(archive),
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Raw FID vault preview") from exc
    if save_run:
        fid_run = save_fid_run(
            _state(request).session_factory,
            preview,
            user_id=context.user_id,
            analysis_id=None,
            sample_id=sample_id,
        )
        preview = fid_run.preview
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.previewed",
        message="Immutable raw FID archive previewed without modifying the archive.",
        processing_run_id=preview.fid_run_id,
        extra={"save_run": save_run},
    )
    return preview


@router.post(
    "/raw-fid/{archive_id}/process",
    response_model=FIDProcessResult,
    dependencies=[Depends(require_access_context)],
)
def raw_fid_archive_process(
    archive_id: str,
    request: Request,
    smiles: str = Form(...),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: str = Form(default="1H"),
    reference_ppm: float | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    manual_nmr_text: str | None = Form(default=None),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> FIDProcessResult:
    archive = _get_visible_raw_archive(request, archive_id, context)
    raw_bytes = _load_raw_archive_bytes_for_request(
        request,
        context=context,
        archive=archive,
        action="process",
    )
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview = process_bruker_1d_zip(
            filename=archive.filename,
            content=raw_bytes,
            solvent=solvent,
            nucleus=nucleus,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            settings=settings,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            raw_upload_provenance=_raw_fid_archive_provenance_from_record(archive),
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Raw FID vault processing") from exc
    reviewed_nmr_text = (
        manual_nmr_text.strip()
        if manual_nmr_text is not None and manual_nmr_text.strip()
        else preview.inferred_nmr_text
    )
    generated_inputs = AnalysisInputs(
        sample_id=sample_id,
        smiles=smiles,
        nmr_text=reviewed_nmr_text,
        solvent=solvent,
    )
    _ensure_analysis_inputs_valid(generated_inputs)
    report = analyze_inputs(generated_inputs)
    combined_notes = list(report.notes)
    for note in reversed(
        _fid_processing_notes(
            preview, manual_review_used=reviewed_nmr_text != preview.inferred_nmr_text
        )
    ):
        if note not in combined_notes:
            combined_notes.insert(0, note)
    report = report.model_copy(update={"notes": combined_notes})
    hours_saved = _estimate_hours_saved(
        _state(request).settings, parsed_peak_count=report.parsed_peak_count
    )
    analysis_id = save_analysis(
        _state(request).session_factory,
        report,
        generated_inputs,
        user_id=context.user_id,
        hours_saved_estimate=hours_saved,
    )
    fid_run = save_fid_run(
        _state(request).session_factory,
        preview,
        user_id=context.user_id,
        analysis_id=analysis_id,
        sample_id=sample_id,
    )
    preview = fid_run.preview
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.processed",
        message="Immutable raw FID archive processed into an analysis.",
        entity_type="fid_run",
        entity_id=fid_run.id,
        processing_run_id=fid_run.id,
        extra={
            "analysis_id": analysis_id,
            "manual_nmr_text_supplied": reviewed_nmr_text != preview.inferred_nmr_text,
        },
    )
    return FIDProcessResult(preview=preview, generated_inputs=generated_inputs, analysis=report)


@router.get(
    "/raw-fid/{archive_id}/runs",
    response_model=list[FIDRunRecord],
    dependencies=[Depends(require_access_context)],
)
def raw_fid_archive_runs(
    archive_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[FIDRunRecord]:
    archive = _get_visible_raw_archive(request, archive_id, context)
    return list_fid_runs_for_raw_archive(
        _state(request).session_factory,
        raw_archive_id=archive.id,
        raw_sha256=archive.sha256,
        limit=limit,
        user_id=_raw_fid_user_scope_for_context(context),
    )


@router.get("/raw-fid/{archive_id}/export", dependencies=[Depends(require_access_context)])
def raw_fid_archive_export(
    archive_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    archive = _get_visible_raw_archive(request, archive_id, context)
    user_id = _raw_fid_user_scope_for_context(context)
    runs = list_fid_runs_for_raw_archive(
        _state(request).session_factory,
        raw_archive_id=archive.id,
        raw_sha256=archive.sha256,
        limit=1,
        user_id=user_id,
    )
    latest_report = None
    if runs:
        latest_report = build_fid_run_report(
            _state(request).session_factory,
            run_id=runs[0].id,
            user_id=user_id,
        )
    original_archive_bytes = _load_raw_archive_bytes_for_request(
        request,
        context=context,
        archive=archive,
        action="export",
    )
    _audit_raw_fid_event(
        request,
        context=context,
        archive=archive,
        event_type="raw_fid.exported",
        message="Raw FID archive evidence export generated.",
        processing_run_id=runs[0].id if runs else None,
        extra={"latest_run_id": runs[0].id if runs else None},
    )
    audit_trail = _raw_archive_audit_trail(
        request,
        context=context,
        archive=archive,
    )
    payload, original_included = _build_raw_archive_export_package(
        archive,
        latest_report=latest_report,
        audit_trail=audit_trail,
        original_archive_bytes=original_archive_bytes,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="raw-fid-{archive.sha256[:12]}-export.zip"'
    }
    return StreamingResponse(io.BytesIO(payload), media_type="application/zip", headers=headers)


@router.post(
    "/fid/preview", response_model=FIDPreviewReport, dependencies=[Depends(require_access_context)]
)
async def fid_preview(
    request: Request,
    file: UploadFile = File(...),
    sample_id: str | None = Form(default=None),
    workspace_sample_record_id: int | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: str = Form(default="1H"),
    reference_ppm: float | None = Form(default=None),
    smiles: str | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> FIDPreviewReport:
    filename = file.filename or "bruker_dataset.zip"
    content = await file.read()
    raw_upload_provenance = _metadata_only_raw_fid_provenance(
        request,
        filename=filename,
        content=content,
    )
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview = process_bruker_1d_zip(
            filename=filename,
            content=content,
            solvent=solvent,
            nucleus=nucleus,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            settings=settings,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            raw_upload_provenance=raw_upload_provenance,
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Raw FID preview") from exc
    _audit_from_context(
        request,
        context=context,
        event_type="fid.preview.legacy",
        message="Legacy raw FID beta preview generated without permanent vault storage or run creation.",
        metadata={
            "filename": filename,
            "sample_id": sample_id,
            "workspace_sample_record_id": workspace_sample_record_id,
            "reference_text_supplied": bool(reference_nmr_text and reference_nmr_text.strip()),
            "fid_processing": preview.processing_metadata.model_dump(mode="json"),
            "legacy_endpoint": "/fid/preview",
            "recommended_workflow": "POST /raw-fid/upload then POST /raw-fid/{archive_id}/process",
        },
    )
    return preview


@router.post(
    "/fid/process", response_model=FIDProcessResult, dependencies=[Depends(require_access_context)]
)
async def fid_process(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    sample_id: str | None = Form(default=None),
    workspace_project_id: int | None = Form(default=None),
    workspace_sample_record_id: int | None = Form(default=None),
    solvent: str | None = Form(default=None),
    nucleus: str = Form(default="1H"),
    reference_ppm: float | None = Form(default=None),
    reference_nmr_text: str | None = Form(default=None),
    manual_nmr_text: str | None = Form(default=None),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> FIDProcessResult:
    filename = file.filename or "bruker_dataset.zip"
    content = await file.read()
    raw_upload_provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    raw_upload_provenance = dict(raw_upload_provenance)
    legacy_warnings = list(raw_upload_provenance.get("warnings") or [])
    legacy_warnings.append(
        "Legacy /fid/process stored this upload in the immutable raw vault before processing. "
        "Prefer POST /raw-fid/upload followed by POST /raw-fid/{archive_id}/process for explicit provenance."
    )
    raw_upload_provenance["warnings"] = legacy_warnings
    raw_upload_provenance["legacy_endpoint"] = "/fid/process"
    raw_upload_provenance["recommended_workflow"] = (
        "POST /raw-fid/upload then POST /raw-fid/{archive_id}/process"
    )
    expected_total_h, expected_non_labile_h = _spectrum_structure_targets(smiles)
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview = process_bruker_1d_zip(
            filename=filename,
            content=content,
            solvent=solvent,
            nucleus=nucleus,
            reference_ppm=reference_ppm,
            reference_nmr_text=reference_nmr_text,
            settings=settings,
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            raw_upload_provenance=raw_upload_provenance,
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="Raw FID analysis") from exc

    resolved_sample_id = sample_id
    if (
        not resolved_sample_id
        and workspace_sample_record_id is not None
        and context.user_id is not None
    ):
        detail = get_sample_detail(
            _state(request).session_factory,
            user_id=context.user_id,
            sample_identity=str(workspace_sample_record_id),
        )
        if detail is not None:
            resolved_sample_id = detail.sample.sample_id
    reviewed_nmr_text = (
        manual_nmr_text.strip()
        if manual_nmr_text is not None and manual_nmr_text.strip()
        else preview.inferred_nmr_text
    )
    generated_inputs = AnalysisInputs(
        sample_id=resolved_sample_id,
        smiles=smiles,
        nmr_text=reviewed_nmr_text,
        solvent=solvent,
    )
    _ensure_analysis_inputs_valid(generated_inputs)
    report = analyze_inputs(generated_inputs)
    combined_notes = list(report.notes)
    for note in reversed(
        _fid_processing_notes(
            preview, manual_review_used=reviewed_nmr_text != preview.inferred_nmr_text
        )
    ):
        if note not in combined_notes:
            combined_notes.insert(0, note)
    report = report.model_copy(update={"notes": combined_notes})
    hours_saved = _estimate_hours_saved(
        _state(request).settings, parsed_peak_count=report.parsed_peak_count
    )
    analysis_id = save_analysis(
        _state(request).session_factory,
        report,
        generated_inputs,
        user_id=context.user_id,
        hours_saved_estimate=hours_saved,
    )
    fid_run = save_fid_run(
        _state(request).session_factory,
        preview,
        user_id=context.user_id,
        analysis_id=analysis_id,
        sample_id=resolved_sample_id,
    )
    preview = fid_run.preview
    if (
        workspace_project_id is not None
        and workspace_sample_record_id is not None
        and context.user_id is not None
    ):
        try:
            link_project_sample_analysis(
                _state(request).session_factory,
                user_id=context.user_id,
                project_id=workspace_project_id,
                sample_record_id=workspace_sample_record_id,
                analysis_id=analysis_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="fid.process",
        message="Raw FID beta processed into an analysis.",
        entity_type="analysis",
        entity_id=analysis_id,
        metadata={
            "filename": filename,
            "sample_id": resolved_sample_id,
            "workspace_project_id": workspace_project_id,
            "workspace_sample_record_id": workspace_sample_record_id,
            "hours_saved_estimate": hours_saved,
            "manual_nmr_text_supplied": reviewed_nmr_text != preview.inferred_nmr_text,
            "reference_text_supplied": bool(reference_nmr_text and reference_nmr_text.strip()),
            "fid_processing": preview.processing_metadata.model_dump(mode="json"),
            "fid_run_id": fid_run.id,
        },
    )
    return FIDProcessResult(preview=preview, generated_inputs=generated_inputs, analysis=report)


def _fid_user_scope_for_context(context: AccessContext) -> int | None:
    return _user_scope_for_context(context)


def _get_visible_fid_run(request: Request, run_id: int, context: AccessContext) -> FIDRunRecord:
    user_id = _fid_user_scope_for_context(context)
    run = get_fid_run_by_id(_state(request).session_factory, run_id=run_id, user_id=user_id)
    if run is None:
        raise HTTPException(status_code=404, detail="FID run not found.")
    return run


@router.get(
    "/fid/runs", response_model=list[FIDRunRecord], dependencies=[Depends(require_access_context)]
)
def fid_runs(
    request: Request,
    context: AccessContext = Depends(require_access_context),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[FIDRunRecord]:
    user_id = _fid_user_scope_for_context(context)
    return list_fid_runs(_state(request).session_factory, limit=limit, user_id=user_id)


@router.get(
    "/fid/runs/{run_id}",
    response_model=FIDRunRecord,
    dependencies=[Depends(require_access_context)],
)
def fid_run_detail(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FIDRunRecord:
    return _get_visible_fid_run(request, run_id, context)


@router.get(
    "/fid/runs/{run_id}/review-decisions",
    response_model=list[FIDRunReviewDecisionRecord],
    dependencies=[Depends(require_access_context)],
)
def fid_run_review_decisions(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[FIDRunReviewDecisionRecord]:
    _get_visible_fid_run(request, run_id, context)
    return list_fid_run_review_decisions(_state(request).session_factory, run_id=run_id, limit=200)


def _submit_fid_run_review(
    *,
    run_id: int,
    payload: FIDRunReviewCreate,
    request: Request,
    context: AccessContext,
    action: str,
) -> FIDRunReviewDecisionRecord:
    try:
        decision = submit_fid_run_review_decision(
            _state(request).session_factory,
            run_id=run_id,
            reviewer_user_id=context.user.id if context.user else 0,
            action=action,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="fid.review",
        message=f"FID run {action} decision submitted.",
        entity_type="fid_run",
        entity_id=run_id,
        metadata={"action": action, "comment_supplied": bool(payload.comment)},
    )
    return decision


@router.post(
    "/fid/runs/{run_id}/review",
    response_model=FIDRunReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def fid_run_review(
    run_id: int,
    payload: FIDRunReviewCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> FIDRunReviewDecisionRecord:
    return _submit_fid_run_review(
        run_id=run_id,
        payload=payload,
        request=request,
        context=context,
        action=payload.action or "review",
    )


@router.post(
    "/fid/runs/{run_id}/approve",
    response_model=FIDRunReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def fid_run_approve(
    run_id: int,
    payload: FIDRunReviewCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> FIDRunReviewDecisionRecord:
    return _submit_fid_run_review(
        run_id=run_id,
        payload=payload,
        request=request,
        context=context,
        action="approve",
    )


@router.post(
    "/fid/runs/{run_id}/reject",
    response_model=FIDRunReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def fid_run_reject(
    run_id: int,
    payload: FIDRunReviewCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> FIDRunReviewDecisionRecord:
    return _submit_fid_run_review(
        run_id=run_id,
        payload=payload,
        request=request,
        context=context,
        action="reject",
    )


@router.post(
    "/fid/runs/{run_id}/request-changes",
    response_model=FIDRunReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def fid_run_request_changes(
    run_id: int,
    payload: FIDRunReviewCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> FIDRunReviewDecisionRecord:
    return _submit_fid_run_review(
        run_id=run_id,
        payload=payload,
        request=request,
        context=context,
        action="request_changes",
    )


@router.get(
    "/fid/runs/{run_id}/report",
    response_model=FIDRunReport,
    dependencies=[Depends(require_access_context)],
)
def fid_run_report(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FIDRunReport:
    user_id = _fid_user_scope_for_context(context)
    report = build_fid_run_report(_state(request).session_factory, run_id=run_id, user_id=user_id)
    if report is None:
        raise HTTPException(status_code=404, detail="FID run report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="fid.report.view_json",
        message="FID run report JSON opened.",
        entity_type="fid_run",
        entity_id=run_id,
    )
    return report


@router.get(
    "/fid/runs/{run_id}/report.html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_context)],
)
def fid_run_report_html(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> HTMLResponse:
    user_id = _fid_user_scope_for_context(context)
    report = build_fid_run_report(_state(request).session_factory, run_id=run_id, user_id=user_id)
    if report is None:
        raise HTTPException(status_code=404, detail="FID run report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="fid.report.view_html",
        message="FID run report HTML opened.",
        entity_type="fid_run",
        entity_id=run_id,
    )
    return HTMLResponse(_render_fid_run_report_html(report))


@router.get(
    "/fid/runs/{run_id}/package",
    dependencies=[Depends(require_access_context)],
)
def fid_run_package(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    user_id = _fid_user_scope_for_context(context)
    report = build_fid_run_report(_state(request).session_factory, run_id=run_id, user_id=user_id)
    if report is None:
        raise HTTPException(status_code=404, detail="FID run report not found.")
    payload, original_included = _build_fid_run_package(report)
    _audit_from_context(
        request,
        context=context,
        event_type="fid.report.package",
        message="FID run evidence package exported.",
        entity_type="fid_run",
        entity_id=run_id,
        metadata={"original_archive_included": original_included},
    )
    headers = {
        "Content-Disposition": f'attachment; filename="fid-run-{run_id}-evidence-package.zip"'
    }
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers=headers,
    )


@router.post(
    "/jobs/submit",
    response_model=AsyncJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_access_context)],
)
def submit_job(
    payload: BatchAnalysisInputs,
    request: Request,
    background_tasks: BackgroundTasks,
    context: AccessContext = Depends(require_access_context),
    job_name: str | None = Query(default=None, min_length=1, max_length=255),
) -> AsyncJobAccepted:
    _ensure_batch_inputs_valid(payload.items)
    state = _state(request)
    job = create_job(
        state.session_factory,
        total_items=len(payload.items),
        job_name=job_name,
        user_id=context.user_id,
        queue_name=state.settings.queue_name,
    )
    enqueue_result = enqueue_job_processing(
        settings=state.settings,
        database_url=state.settings.database_url,
        session_factory=state.session_factory,
        background_tasks=background_tasks,
        job_id=job.id,
        items=payload.items,
        user_id=context.user_id,
    )
    if enqueue_result.backend_job_id is not None:
        set_job_backend_id(
            state.session_factory,
            job.id,
            backend_job_id=enqueue_result.backend_job_id,
            status="queued",
        )
        job = get_job_by_id(state.session_factory, job.id, user_id=context.user_id) or job
    _audit_from_context(
        request,
        context=context,
        event_type="job.submit",
        message="Background job submitted.",
        entity_type="job",
        entity_id=job.id,
        metadata={"items": len(payload.items), "backend": enqueue_result.backend},
    )
    return AsyncJobAccepted(job=job, queue_backend=enqueue_result.backend)


@router.post(
    "/jobs/upload",
    response_model=AsyncJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_access_context)],
)
async def jobs_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_name: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> AsyncJobAccepted:
    content = await file.read()
    filename = file.filename or "batch.json"
    try:
        payload = parse_batch_upload(filename=filename, content=content)
    except UploadParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _ensure_batch_inputs_valid(payload.items)

    state = _state(request)
    job = create_job(
        state.session_factory,
        total_items=len(payload.items),
        job_name=job_name,
        uploaded_filename=filename,
        user_id=context.user_id,
        queue_name=state.settings.queue_name,
    )
    enqueue_result = enqueue_job_processing(
        settings=state.settings,
        database_url=state.settings.database_url,
        session_factory=state.session_factory,
        background_tasks=background_tasks,
        job_id=job.id,
        items=payload.items,
        user_id=context.user_id,
    )
    if enqueue_result.backend_job_id is not None:
        set_job_backend_id(
            state.session_factory,
            job.id,
            backend_job_id=enqueue_result.backend_job_id,
            status="queued",
        )
        job = get_job_by_id(state.session_factory, job.id, user_id=context.user_id) or job
    _audit_from_context(
        request,
        context=context,
        event_type="job.upload",
        message="Upload job submitted.",
        entity_type="job",
        entity_id=job.id,
        metadata={
            "filename": filename,
            "items": len(payload.items),
            "backend": enqueue_result.backend,
        },
    )
    return AsyncJobAccepted(job=job, queue_backend=enqueue_result.backend)


@router.post(
    "/projects",
    response_model=SpectraCheckProjectRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_persistence_project(
    payload: SpectraCheckProjectCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckProjectRecord:
    try:
        record = sc_store.create_spectracheck_project(
            _state(request).session_factory,
            payload,
            owner_id=context.user_id,
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="spectracheck.project.create",
        message="SpectraCheck persistence project created.",
        entity_type="spectracheck_project",
        entity_id=record.id,
        metadata={"name": record.name, "status": record.status},
    )
    return record


@router.get(
    "/projects",
    response_model=list[SpectraCheckProjectRecord],
    dependencies=[Depends(require_access_context)],
)
def list_persistence_projects(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckProjectRecord]:
    return sc_store.list_spectracheck_projects(
        _state(request).session_factory,
        owner_scope_id=_user_scope_for_context(context),
        limit=limit,
    )


@router.get(
    "/projects/{project_id}",
    response_model=SpectraCheckProjectRecord,
    dependencies=[Depends(require_access_context)],
)
def get_persistence_project(
    project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckProjectRecord:
    record = sc_store.get_spectracheck_project(
        _state(request).session_factory,
        project_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return record


@router.patch(
    "/projects/{project_id}",
    response_model=SpectraCheckProjectRecord,
    dependencies=[Depends(require_access_context)],
)
def update_persistence_project(
    project_id: int,
    payload: SpectraCheckProjectUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckProjectRecord:
    try:
        record = sc_store.update_spectracheck_project(
            _state(request).session_factory,
            project_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="spectracheck.project.update",
        message="SpectraCheck persistence project updated.",
        entity_type="spectracheck_project",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/projects/{project_id}/samples",
    response_model=SpectraCheckSampleRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_persistence_sample(
    project_id: int,
    payload: SpectraCheckSampleCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckSampleRecord:
    try:
        record = sc_store.create_spectracheck_sample(
            _state(request).session_factory,
            project_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="spectracheck.sample.create",
        message="SpectraCheck persistence sample created.",
        entity_type="spectracheck_sample",
        entity_id=record.id,
        metadata={"project_id": project_id, "sample_id": record.sample_id},
    )
    return record


@router.get(
    "/projects/{project_id}/samples",
    response_model=list[SpectraCheckSampleRecord],
    dependencies=[Depends(require_access_context)],
)
def list_persistence_samples(
    project_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckSampleRecord]:
    try:
        return sc_store.list_spectracheck_samples(
            _state(request).session_factory,
            project_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc


@router.patch(
    "/samples/{sample_id}",
    response_model=SpectraCheckSampleRecord,
    dependencies=[Depends(require_access_context)],
)
def update_persistence_sample(
    sample_id: str,
    payload: SpectraCheckSampleUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckSampleRecord:
    try:
        record = sc_store.update_spectracheck_sample(
            _state(request).session_factory,
            sample_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="spectracheck.sample.update",
        message="SpectraCheck persistence sample updated.",
        entity_type="spectracheck_sample",
        entity_id=record.id,
        metadata={
            "updated_fields": sorted(payload.model_fields_set),
            "sample_id": record.sample_id,
        },
    )
    return record


@router.post(
    "/spectracheck/sessions",
    response_model=SpectraCheckSessionRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_spectracheck_session_route(
    payload: SpectraCheckSessionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckSessionRecord:
    try:
        return sc_store.create_spectracheck_session(
            _state(request).session_factory,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions",
    response_model=list[SpectraCheckSessionRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_sessions_route(
    request: Request,
    project_id: int | None = Query(default=None, ge=1),
    sample_pk: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckSessionRecord]:
    return sc_store.list_spectracheck_sessions(
        _state(request).session_factory,
        owner_scope_id=_user_scope_for_context(context),
        project_id=project_id,
        sample_pk=sample_pk,
        limit=limit,
    )


@router.get(
    "/spectracheck/sessions/{session_id}",
    response_model=SpectraCheckSessionRecord,
    dependencies=[Depends(require_access_context)],
)
def get_spectracheck_session_route(
    session_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckSessionRecord:
    record = sc_store.get_spectracheck_session(
        _state(request).session_factory,
        session_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="SpectraCheck session not found.")
    return record


@router.patch(
    "/spectracheck/sessions/{session_id}",
    response_model=SpectraCheckSessionRecord,
    dependencies=[Depends(require_access_context)],
)
def update_spectracheck_session_route(
    session_id: int,
    payload: SpectraCheckSessionUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckSessionRecord:
    try:
        record = sc_store.update_spectracheck_session(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="SpectraCheck session not found.")
    return record


@router.delete(
    "/spectracheck/sessions/{session_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_access_context)],
)
def delete_spectracheck_session_route(
    session_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MessageResponse:
    deleted = sc_store.archive_spectracheck_session(
        _state(request).session_factory,
        session_id,
        owner_scope_id=_user_scope_for_context(context),
        actor_id=context.user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="SpectraCheck session not found.")
    return MessageResponse(detail="SpectraCheck session archived.")


@router.post(
    "/spectracheck/sessions/{session_id}/evidence",
    response_model=SpectraCheckEvidenceRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_spectracheck_evidence_route(
    session_id: int,
    payload: SpectraCheckEvidenceCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckEvidenceRecord:
    try:
        return sc_store.create_spectracheck_evidence(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/evidence",
    response_model=list[SpectraCheckEvidenceRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_evidence_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckEvidenceRecord]:
    try:
        return sc_store.list_spectracheck_evidence(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/spectracheck/sessions/{session_id}/evidence/{evidence_id}",
    response_model=SpectraCheckEvidenceRecord,
    dependencies=[Depends(require_access_context)],
)
def update_spectracheck_evidence_route(
    session_id: int,
    evidence_id: int,
    payload: SpectraCheckEvidenceUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckEvidenceRecord:
    try:
        record = sc_store.update_spectracheck_evidence(
            _state(request).session_factory,
            session_id,
            evidence_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    return record


@router.delete(
    "/spectracheck/sessions/{session_id}/evidence/{evidence_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_access_context)],
)
def delete_spectracheck_evidence_route(
    session_id: int,
    evidence_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MessageResponse:
    deleted = sc_store.delete_spectracheck_evidence(
        _state(request).session_factory,
        session_id,
        evidence_id,
        owner_scope_id=_user_scope_for_context(context),
        actor_id=context.user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Evidence record not found.")
    return MessageResponse(detail="Evidence record deleted.")


@router.post(
    "/spectracheck/sessions/{session_id}/unified-evidence",
    response_model=SpectraCheckUnifiedEvidenceRecord,
    dependencies=[Depends(require_access_context)],
)
def save_spectracheck_unified_evidence_route(
    session_id: int,
    payload: SpectraCheckUnifiedEvidenceSave,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckUnifiedEvidenceRecord:
    try:
        record = sc_store.save_spectracheck_unified_evidence(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="SpectraCheck session not found.")
    return record


@router.get(
    "/spectracheck/sessions/{session_id}/unified-evidence",
    response_model=SpectraCheckUnifiedEvidenceRecord,
    dependencies=[Depends(require_access_context)],
)
def get_spectracheck_unified_evidence_route(
    session_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckUnifiedEvidenceRecord:
    record = sc_store.get_spectracheck_unified_evidence(
        _state(request).session_factory,
        session_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="SpectraCheck session not found.")
    return record


@router.post(
    "/spectracheck/sessions/{session_id}/review",
    response_model=SpectraCheckReviewDecisionRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_spectracheck_review_route(
    session_id: int,
    payload: SpectraCheckReviewCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckReviewDecisionRecord:
    try:
        return sc_store.create_spectracheck_review(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/review",
    response_model=list[SpectraCheckReviewDecisionRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_reviews_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckReviewDecisionRecord]:
    try:
        return sc_store.list_spectracheck_reviews(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/audit",
    response_model=list[SpectraCheckAuditEventRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_audit_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckAuditEventRecord]:
    try:
        return sc_store.list_spectracheck_audit_events(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/spectracheck/sessions/{session_id}/reports",
    response_model=SpectraCheckReportRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_spectracheck_report_route(
    session_id: int,
    payload: SpectraCheckReportCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectraCheckReportRecord:
    try:
        return sc_store.create_spectracheck_report(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except sc_store.SpectraCheckPersistenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/reports",
    response_model=list[SpectraCheckReportRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_reports_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectraCheckReportRecord]:
    try:
        return sc_store.list_spectracheck_reports(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/files/upload",
    response_model=FileRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
async def upload_managed_file_route(
    request: Request,
    file: UploadFile = File(...),
    file_kind: ManagedFileKind = Form(default="other"),
    metadata_json: str | None = Form(default=None),
    provenance_metadata_json: str | None = Form(default=None),
    provenance_metadata: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> FileRecord:
    metadata = _parse_optional_json_object(metadata_json, field_name="metadata_json")
    provenance_aliases: dict[str, Any] = {}
    provenance_aliases.update(
        _parse_optional_json_object(
            provenance_metadata_json,
            field_name="provenance_metadata_json",
        )
    )
    provenance_aliases.update(
        _parse_optional_json_object(
            provenance_metadata,
            field_name="provenance_metadata",
        )
    )
    if provenance_aliases:
        existing_provenance = metadata.get("provenance_metadata")
        metadata["provenance_metadata"] = {
            **(existing_provenance if isinstance(existing_provenance, dict) else {}),
            **provenance_aliases,
        }
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file cannot be empty.")
    try:
        record = orch_store.upload_file_record(
            _state(request).session_factory,
            original_filename=file.filename or "upload.bin",
            content_type=file.content_type,
            content=content,
            file_kind=file_kind,
            metadata_json=metadata,
            storage_root=_orchestration_storage_root(request),
        )
    except orch_store.OrchestrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="managed_file.upload",
        message="Managed file uploaded to immutable local storage.",
        entity_type="managed_file",
        entity_id=record.id,
        metadata={
            "sha256": record.sha256,
            "file_kind": record.file_kind,
            "file_size_bytes": record.file_size_bytes,
        },
    )
    return record


@router.get(
    "/files", response_model=list[FileRecord], dependencies=[Depends(require_access_context)]
)
def list_managed_files_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    file_kind: str | None = Query(default=None),
    context: AccessContext = Depends(require_access_context),
) -> list[FileRecord]:
    return orch_store.list_file_records(
        _state(request).session_factory, limit=limit, file_kind=file_kind
    )


@router.get(
    "/files/{file_id}", response_model=FileRecord, dependencies=[Depends(require_access_context)]
)
def get_managed_file_route(
    file_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FileRecord:
    record = orch_store.get_file_record(_state(request).session_factory, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Managed file not found.")
    return record


@router.get("/files/{file_id}/download", dependencies=[Depends(require_access_context)])
def download_managed_file_route(
    file_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    try:
        download = orch_store.get_file_download(
            _state(request).session_factory,
            file_id,
            storage_root=_orchestration_storage_root(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if download is None:
        raise HTTPException(status_code=404, detail="Managed file not found.")
    record, path = download
    headers = {"Content-Disposition": f'attachment; filename="{record.original_filename}"'}
    return StreamingResponse(
        _stream_file_path(path),
        media_type=record.content_type or "application/octet-stream",
        headers=headers,
    )


@router.delete(
    "/files/{file_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_access_context)],
)
def delete_managed_file_route(
    file_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MessageResponse:
    deleted = orch_store.delete_file_record(_state(request).session_factory, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Managed file not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="managed_file.delete",
        message="Managed file record deleted; stored bytes remain immutable where already written.",
        entity_type="managed_file",
        entity_id=file_id,
    )
    return MessageResponse(
        detail="Managed file record deleted; immutable stored bytes were not overwritten."
    )


def _raise_interoperability_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, interop_store.InteroperabilityError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _raise_validation_center_http_error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, validation_store.ControlledRecordLockedError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, validation_store.ValidationCenterError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _raise_tenant_saas_http_error(exc: Exception) -> None:
    if isinstance(exc, tenant_store.TenantIsolationError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, tenant_store.TenantNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, tenant_store.TenantSaaSError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _raise_golden_pilot_http_error(exc: Exception) -> None:
    if isinstance(exc, golden_pilot_store.GoldenPilotNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, golden_pilot_store.GoldenPilotError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _is_internal_super_admin(context: AccessContext) -> bool:
    return bool(context.system_api_key or (context.user and context.user.is_admin))


def _require_tenant_scope_header(
    *,
    context: AccessContext,
    requested_tenant_id: int | None,
    actual_tenant_id: int,
) -> None:
    if _is_internal_super_admin(context):
        return
    if requested_tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="Tenant-scoped access requires an x-tenant-id header.",
        )
    try:
        tenant_store.ensure_tenant_scope(requested_tenant_id, actual_tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)


@router.get(
    "/connectors",
    response_model=list[ConnectorRegistry],
    dependencies=[Depends(require_access_context)],
)
def list_connectors_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    target_program: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ConnectorRegistry]:
    return interop_store.list_connectors(
        _state(request).session_factory,
        status_filter=status_filter,
        target_program=target_program,
        limit=limit,
    )


@router.post(
    "/connectors",
    response_model=ConnectorRegistry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_connector_route(
    payload: ConnectorRegistryCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ConnectorRegistry:
    try:
        record = interop_store.create_connector(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="connector.create",
        message="Connector registry entry created.",
        entity_type="connector",
        entity_id=record.id,
        metadata={"connector_key": record.connector_key, "target_program": record.target_program},
    )
    return record


@router.get(
    "/connectors/{connector_id}",
    response_model=ConnectorRegistry,
    dependencies=[Depends(require_access_context)],
)
def get_connector_route(
    connector_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ConnectorRegistry:
    record = interop_store.get_connector(_state(request).session_factory, connector_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Connector not found.")
    return record


@router.patch(
    "/connectors/{connector_id}",
    response_model=ConnectorRegistry,
    dependencies=[Depends(require_access_context)],
)
def update_connector_route(
    connector_id: int,
    payload: ConnectorRegistryUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ConnectorRegistry:
    try:
        record = interop_store.update_connector(
            _state(request).session_factory,
            connector_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Connector not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="connector.update",
        message="Connector registry entry updated.",
        entity_type="connector",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/connectors/{connector_id}/health-check",
    response_model=ConnectorHealthCheck,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_connector_health_check_route(
    connector_id: int,
    request: Request,
    payload: ConnectorHealthCheckRequest | None = None,
    context: AccessContext = Depends(require_access_context),
) -> ConnectorHealthCheck:
    try:
        record = interop_store.create_connector_health_check(
            _state(request).session_factory,
            connector_id,
            payload or ConnectorHealthCheckRequest(),
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="connector.health_check",
        message="Connector health check recorded without exposing credentials.",
        entity_type="connector",
        entity_id=connector_id,
        metadata={"health_check_id": record.id, "status": record.status},
    )
    return record


@router.get(
    "/connectors/{connector_id}/health-checks",
    response_model=list[ConnectorHealthCheck],
    dependencies=[Depends(require_access_context)],
)
def list_connector_health_checks_route(
    connector_id: int,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ConnectorHealthCheck]:
    try:
        return interop_store.list_connector_health_checks(
            _state(request).session_factory,
            connector_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise


@router.post(
    "/connectors/{connector_id}/credentials",
    response_model=ConnectorCredentialReference,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_connector_credential_route(
    connector_id: int,
    payload: ConnectorCredentialReferenceCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ConnectorCredentialReference:
    try:
        record = interop_store.create_connector_credential(
            _state(request).session_factory,
            connector_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="connector.credential_reference.create",
        message="Connector credential reference created; no raw credential value was returned.",
        entity_type="connector",
        entity_id=connector_id,
        metadata={"credential_reference_id": record.id, "credential_type": record.credential_type},
    )
    return record


@router.get(
    "/connectors/{connector_id}/credentials",
    response_model=list[ConnectorCredentialReference],
    dependencies=[Depends(require_access_context)],
)
def list_connector_credentials_route(
    connector_id: int,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ConnectorCredentialReference]:
    try:
        return interop_store.list_connector_credentials(
            _state(request).session_factory,
            connector_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise


@router.post(
    "/instrument-watch-folders",
    response_model=InstrumentWatchFolder,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_instrument_watch_folder_route(
    payload: InstrumentWatchFolderCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InstrumentWatchFolder:
    try:
        record = interop_store.create_watch_folder(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="instrument_watch_folder.create",
        message="Instrument watch folder created.",
        entity_type="instrument_watch_folder",
        entity_id=record.id,
        metadata={"target_program": record.target_program, "target_route": record.target_route},
    )
    return record


@router.get(
    "/instrument-watch-folders",
    response_model=list[InstrumentWatchFolder],
    dependencies=[Depends(require_access_context)],
)
def list_instrument_watch_folders_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[InstrumentWatchFolder]:
    return interop_store.list_watch_folders(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/instrument-watch-folders/{watch_folder_id}",
    response_model=InstrumentWatchFolder,
    dependencies=[Depends(require_access_context)],
)
def get_instrument_watch_folder_route(
    watch_folder_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InstrumentWatchFolder:
    record = interop_store.get_watch_folder(_state(request).session_factory, watch_folder_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Instrument watch folder not found.")
    return record


@router.patch(
    "/instrument-watch-folders/{watch_folder_id}",
    response_model=InstrumentWatchFolder,
    dependencies=[Depends(require_access_context)],
)
def update_instrument_watch_folder_route(
    watch_folder_id: int,
    payload: InstrumentWatchFolderUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InstrumentWatchFolder:
    try:
        record = interop_store.update_watch_folder(
            _state(request).session_factory,
            watch_folder_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Instrument watch folder not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="instrument_watch_folder.update",
        message="Instrument watch folder updated.",
        entity_type="instrument_watch_folder",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/instrument-watch-folders/{watch_folder_id}/scan",
    response_model=IngestionRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def scan_instrument_watch_folder_route(
    watch_folder_id: int,
    payload: InstrumentWatchFolderScanRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IngestionRun:
    try:
        record = interop_store.scan_watch_folder(
            _state(request).session_factory,
            watch_folder_id,
            payload,
            storage_root=_orchestration_storage_root(request),
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="instrument_watch_folder.scan",
        message="Instrument watch folder scan recorded.",
        entity_type="ingestion_run",
        entity_id=record.id,
        metadata={
            "watch_folder_id": watch_folder_id,
            "ingested_count": record.ingested_count,
            "skipped_count": record.skipped_count,
            "failed_count": record.failed_count,
        },
    )
    return record


@router.post(
    "/ingestion-runs",
    response_model=IngestionRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ingestion_run_route(
    payload: IngestionRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IngestionRun:
    try:
        record = interop_store.create_ingestion_run(
            _state(request).session_factory,
            payload,
            storage_root=_orchestration_storage_root(request),
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="ingestion_run.create",
        message="Ingestion run recorded with source hashes.",
        entity_type="ingestion_run",
        entity_id=record.id,
        metadata={
            "status": record.status,
            "ingested_count": record.ingested_count,
            "skipped_count": record.skipped_count,
            "failed_count": record.failed_count,
        },
    )
    return record


@router.get(
    "/ingestion-runs",
    response_model=list[IngestionRun],
    dependencies=[Depends(require_access_context)],
)
def list_ingestion_runs_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[IngestionRun]:
    return interop_store.list_ingestion_runs(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/ingestion-runs/{ingestion_run_id}",
    response_model=IngestionRun,
    dependencies=[Depends(require_access_context)],
)
def get_ingestion_run_route(
    ingestion_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IngestionRun:
    record = interop_store.get_ingestion_run(_state(request).session_factory, ingestion_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found.")
    return record


@router.post(
    "/files/{file_id}/normalize",
    response_model=FileNormalizationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def normalize_file_route(
    file_id: int,
    payload: FileNormalizationRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FileNormalizationRun:
    try:
        record = interop_store.normalize_file(
            _state(request).session_factory,
            file_id,
            payload,
            storage_root=_orchestration_storage_root(request),
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="file_normalization.create",
        message="File normalization run created a normalized artifact or warning.",
        entity_type="file_normalization_run",
        entity_id=record.id,
        metadata={
            "file_id": file_id,
            "source_format": record.source_format,
            "target_format": record.target_format,
            "status": record.status,
            "output_artifact_id": record.output_artifact_id,
        },
    )
    return record


@router.get(
    "/files/{file_id}/normalization-runs",
    response_model=list[FileNormalizationRun],
    dependencies=[Depends(require_access_context)],
)
def list_file_normalization_runs_route(
    file_id: int,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[FileNormalizationRun]:
    return interop_store.list_normalization_runs_for_file(
        _state(request).session_factory,
        file_id,
        limit=limit,
    )


@router.get(
    "/normalization-runs/{normalization_run_id}",
    response_model=FileNormalizationRun,
    dependencies=[Depends(require_access_context)],
)
def get_normalization_run_route(
    normalization_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FileNormalizationRun:
    record = interop_store.get_normalization_run(
        _state(request).session_factory,
        normalization_run_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Normalization run not found.")
    return record


@router.post(
    "/external-records",
    response_model=ExternalSystemRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_external_record_route(
    payload: ExternalSystemRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ExternalSystemRecord:
    try:
        record = interop_store.create_external_record(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="external_record.create",
        message="External system record created.",
        entity_type="external_record",
        entity_id=record.id,
        metadata={"external_system": record.external_system, "external_object_type": record.external_object_type},
    )
    return record


@router.get(
    "/external-records",
    response_model=list[ExternalSystemRecord],
    dependencies=[Depends(require_access_context)],
)
def list_external_records_route(
    request: Request,
    connector_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ExternalSystemRecord]:
    return interop_store.list_external_records(
        _state(request).session_factory,
        connector_id=connector_id,
        limit=limit,
    )


@router.get(
    "/external-records/{external_record_id}",
    response_model=ExternalSystemRecord,
    dependencies=[Depends(require_access_context)],
)
def get_external_record_route(
    external_record_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ExternalSystemRecord:
    record = interop_store.get_external_record(
        _state(request).session_factory,
        external_record_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="External system record not found.")
    return record


@router.post(
    "/external-object-links",
    response_model=ExternalObjectLink,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_external_object_link_route(
    payload: ExternalObjectLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ExternalObjectLink:
    try:
        record = interop_store.create_external_object_link(
            _state(request).session_factory,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="external_object_link.create",
        message="External object link created.",
        entity_type="external_object_link",
        entity_id=record.id,
        metadata={
            "external_record_id": record.external_record_id,
            "moltrace_resource_type": record.moltrace_resource_type,
            "relation_type": record.relation_type,
        },
    )
    return record


@router.get(
    "/external-object-links",
    response_model=list[ExternalObjectLink],
    dependencies=[Depends(require_access_context)],
)
def list_external_object_links_route(
    request: Request,
    external_record_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ExternalObjectLink]:
    return interop_store.list_external_object_links(
        _state(request).session_factory,
        external_record_id=external_record_id,
        limit=limit,
    )


@router.post(
    "/mapping-templates",
    response_model=MappingTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_mapping_template_route(
    payload: MappingTemplateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MappingTemplate:
    try:
        record = interop_store.create_mapping_template(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="mapping_template.create",
        message="Mapping template created.",
        entity_type="mapping_template",
        entity_id=record.id,
        metadata={"source_type": record.source_type, "target_type": record.target_type},
    )
    return record


@router.get(
    "/mapping-templates",
    response_model=list[MappingTemplate],
    dependencies=[Depends(require_access_context)],
)
def list_mapping_templates_route(
    request: Request,
    connector_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[MappingTemplate]:
    return interop_store.list_mapping_templates(
        _state(request).session_factory,
        connector_id=connector_id,
        limit=limit,
    )


@router.get(
    "/mapping-templates/{template_id}",
    response_model=MappingTemplate,
    dependencies=[Depends(require_access_context)],
)
def get_mapping_template_route(
    template_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MappingTemplate:
    record = interop_store.get_mapping_template(_state(request).session_factory, template_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Mapping template not found.")
    return record


@router.patch(
    "/mapping-templates/{template_id}",
    response_model=MappingTemplate,
    dependencies=[Depends(require_access_context)],
)
def update_mapping_template_route(
    template_id: int,
    payload: MappingTemplateUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MappingTemplate:
    try:
        record = interop_store.update_mapping_template(
            _state(request).session_factory,
            template_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Mapping template not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="mapping_template.update",
        message="Mapping template updated.",
        entity_type="mapping_template",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/outbound-sync-jobs",
    response_model=OutboundSyncJob,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_outbound_sync_job_route(
    payload: OutboundSyncJobCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OutboundSyncJob:
    try:
        record = interop_store.create_outbound_sync_job(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="outbound_sync_job.create",
        message="Outbound sync job created for review.",
        entity_type="outbound_sync_job",
        entity_id=record.id,
        metadata={"target_system": record.target_system, "status": record.status},
    )
    return record


@router.get(
    "/outbound-sync-jobs",
    response_model=list[OutboundSyncJob],
    dependencies=[Depends(require_access_context)],
)
def list_outbound_sync_jobs_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[OutboundSyncJob]:
    return interop_store.list_outbound_sync_jobs(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/outbound-sync-jobs/{sync_job_id}",
    response_model=OutboundSyncJob,
    dependencies=[Depends(require_access_context)],
)
def get_outbound_sync_job_route(
    sync_job_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OutboundSyncJob:
    record = interop_store.get_outbound_sync_job(_state(request).session_factory, sync_job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Outbound sync job not found.")
    return record


@router.post(
    "/webhooks/subscriptions",
    response_model=WebhookSubscription,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_webhook_subscription_route(
    payload: WebhookSubscriptionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WebhookSubscription:
    try:
        record = interop_store.create_webhook_subscription(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="webhook_subscription.create",
        message="Webhook subscription created with hashed target URL.",
        entity_type="webhook_subscription",
        entity_id=record.id,
        metadata={"event_types_json": record.event_types_json, "status": record.status},
    )
    return record


@router.get(
    "/webhooks/subscriptions",
    response_model=list[WebhookSubscription],
    dependencies=[Depends(require_access_context)],
)
def list_webhook_subscriptions_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[WebhookSubscription]:
    return interop_store.list_webhook_subscriptions(
        _state(request).session_factory,
        limit=limit,
    )


@router.patch(
    "/webhooks/subscriptions/{subscription_id}",
    response_model=WebhookSubscription,
    dependencies=[Depends(require_access_context)],
)
def update_webhook_subscription_route(
    subscription_id: int,
    payload: WebhookSubscriptionUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WebhookSubscription:
    try:
        record = interop_store.update_webhook_subscription(
            _state(request).session_factory,
            subscription_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Webhook subscription not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="webhook_subscription.update",
        message="Webhook subscription updated.",
        entity_type="webhook_subscription",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/submission-package",
    response_model=RegulatorySubmissionPackage,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_submission_package_route(
    dossier_id: int,
    payload: RegulatorySubmissionPackageCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySubmissionPackage:
    try:
        record = interop_store.create_submission_package(
            _state(request).session_factory,
            dossier_id,
            payload,
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="regulatory_submission_package.create",
        message="Regulatory export package created for review.",
        entity_type="regulatory_submission_package",
        entity_id=record.id,
        metadata={"dossier_id": dossier_id, "package_type": record.package_type, "status": record.status},
    )
    return record


@router.get(
    "/regulatory/dossiers/{dossier_id}/submission-package",
    response_model=list[RegulatorySubmissionPackage],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_submission_packages_for_dossier_route(
    dossier_id: int,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatorySubmissionPackage]:
    return interop_store.list_submission_packages_for_dossier(
        _state(request).session_factory,
        dossier_id,
        limit=limit,
    )


@router.get(
    "/regulatory/submission-packages/{package_id}",
    response_model=RegulatorySubmissionPackage,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_submission_package_route(
    package_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySubmissionPackage:
    record = interop_store.get_submission_package(_state(request).session_factory, package_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory submission package not found.")
    return record


@router.post(
    "/integrations/spectracheck/import-file",
    response_model=IntegrationImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def import_spectracheck_file_route(
    payload: SpectraCheckImportFileRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IntegrationImportResponse:
    try:
        record = interop_store.import_spectracheck_file(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="integration.spectracheck.import_file",
        message="SpectraCheck file import recorded.",
        entity_type="ingestion_run",
        entity_id=record.ingestion_run_id,
        metadata={"file_id": record.file_id, "review_required": record.review_required},
    )
    return record


@router.post(
    "/integrations/regulatory/import-source",
    response_model=IntegrationImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def import_regulatory_source_route(
    payload: RegulatoryImportSourceRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IntegrationImportResponse:
    try:
        record = interop_store.import_regulatory_source(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="integration.regulatory.import_source",
        message="Regulatory source imported with citation metadata.",
        entity_type="ingestion_run",
        entity_id=record.ingestion_run_id,
        metadata={"file_id": record.file_id, "review_required": record.review_required},
    )
    return record


@router.post(
    "/integrations/reactions/import-experiment-table",
    response_model=IntegrationImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def import_reaction_experiment_table_route(
    payload: ReactionExperimentTableImportRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IntegrationImportResponse:
    try:
        record = interop_store.import_reaction_experiment_table(
            _state(request).session_factory,
            payload,
            storage_root=_orchestration_storage_root(request),
        )
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="integration.reactions.import_experiment_table",
        message="Reaction experiment table imported as a normalized artifact; review required.",
        entity_type="file_normalization_run",
        entity_id=record.normalization_run_id,
        metadata={"file_id": record.file_id, "review_required": record.review_required},
    )
    return record


@router.post(
    "/integrations/reactions/export-approved-experiments",
    response_model=IntegrationImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def export_reaction_experiments_route(
    payload: ReactionApprovedExperimentsExportRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> IntegrationImportResponse:
    try:
        record = interop_store.export_reaction_experiments(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_interoperability_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="integration.reactions.export_experiments",
        message="Reaction experiment export package created for review.",
        entity_type="outbound_sync_job",
        entity_id=record.sync_job_id,
        metadata={"sync_job_id": record.sync_job_id, "review_required": record.review_required},
    )
    return record


@router.post(
    "/validation-center/projects",
    response_model=ValidationProject,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_validation_project_route(
    payload: ValidationProjectCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationProject:
    try:
        record = validation_store.create_validation_project(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_project.create",
        message="Validation project created for Part 11 readiness and Annex 11 readiness.",
        entity_type="validation_project",
        entity_id=record.id,
        metadata={"scope": record.scope, "validation_type": record.validation_type},
    )
    return record


@router.get(
    "/validation-center/projects",
    response_model=list[ValidationProject],
    dependencies=[Depends(require_access_context)],
)
def list_validation_projects_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationProject]:
    return validation_store.list_validation_projects(
        _state(request).session_factory,
        status_filter=status_filter,
        scope=scope,
        limit=limit,
    )


@router.get(
    "/validation-center/projects/{validation_project_id}",
    response_model=ValidationProject,
    dependencies=[Depends(require_access_context)],
)
def get_validation_project_route(
    validation_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationProject:
    record = validation_store.get_validation_project(
        _state(request).session_factory,
        validation_project_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Validation project not found.")
    return record


@router.patch(
    "/validation-center/projects/{validation_project_id}",
    response_model=ValidationProject,
    dependencies=[Depends(require_access_context)],
)
def update_validation_project_route(
    validation_project_id: int,
    payload: ValidationProjectUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationProject:
    try:
        record = validation_store.update_validation_project(
            _state(request).session_factory,
            validation_project_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Validation project not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="validation_project.update",
        message="Validation project updated.",
        entity_type="validation_project",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/validation-center/projects/{validation_project_id}/urs",
    response_model=UserRequirementSpecification,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_urs_route(
    validation_project_id: int,
    payload: UserRequirementSpecificationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UserRequirementSpecification:
    try:
        record = validation_store.create_urs(
            _state(request).session_factory,
            validation_project_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_urs.create",
        message="User requirement specification created.",
        entity_type="user_requirement_specification",
        entity_id=record.id,
        metadata={"validation_project_id": validation_project_id, "module": record.module},
    )
    return record


@router.get(
    "/validation-center/projects/{validation_project_id}/urs",
    response_model=list[UserRequirementSpecification],
    dependencies=[Depends(require_access_context)],
)
def list_urs_route(
    validation_project_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[UserRequirementSpecification]:
    try:
        return validation_store.list_urs(
            _state(request).session_factory,
            validation_project_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise


@router.post(
    "/validation-center/projects/{validation_project_id}/functional-specs",
    response_model=FunctionalSpecification,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_functional_spec_route(
    validation_project_id: int,
    payload: FunctionalSpecificationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FunctionalSpecification:
    try:
        record = validation_store.create_functional_spec(
            _state(request).session_factory,
            validation_project_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_functional_spec.create",
        message="Functional specification created.",
        entity_type="functional_specification",
        entity_id=record.id,
        metadata={"validation_project_id": validation_project_id, "module": record.module},
    )
    return record


@router.get(
    "/validation-center/projects/{validation_project_id}/functional-specs",
    response_model=list[FunctionalSpecification],
    dependencies=[Depends(require_access_context)],
)
def list_functional_specs_route(
    validation_project_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[FunctionalSpecification]:
    try:
        return validation_store.list_functional_specs(
            _state(request).session_factory,
            validation_project_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise


@router.post(
    "/validation-center/projects/{validation_project_id}/risk-assessment",
    response_model=ValidationRiskAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_validation_risk_assessment_route(
    validation_project_id: int,
    payload: ValidationRiskAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationRiskAssessment:
    try:
        record = validation_store.create_risk_assessment(
            _state(request).session_factory,
            validation_project_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_risk_assessment.create",
        message="Validation risk assessment created.",
        entity_type="validation_risk_assessment",
        entity_id=record.id,
        metadata={"validation_project_id": validation_project_id, "risk_priority": record.risk_priority},
    )
    return record


@router.get(
    "/validation-center/projects/{validation_project_id}/risk-assessment",
    response_model=list[ValidationRiskAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_validation_risk_assessments_route(
    validation_project_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationRiskAssessment]:
    try:
        return validation_store.list_risk_assessments(
            _state(request).session_factory,
            validation_project_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise


@router.post(
    "/validation-center/projects/{validation_project_id}/test-protocols",
    response_model=ValidationTestProtocol,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_validation_test_protocol_route(
    validation_project_id: int,
    payload: ValidationTestProtocolCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationTestProtocol:
    try:
        record = validation_store.create_test_protocol(
            _state(request).session_factory,
            validation_project_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_test_protocol.create",
        message="Validation test protocol created.",
        entity_type="validation_test_protocol",
        entity_id=record.id,
        metadata={"validation_project_id": validation_project_id, "protocol_type": record.protocol_type},
    )
    return record


@router.get(
    "/validation-center/projects/{validation_project_id}/test-protocols",
    response_model=list[ValidationTestProtocol],
    dependencies=[Depends(require_access_context)],
)
def list_validation_test_protocols_route(
    validation_project_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationTestProtocol]:
    try:
        return validation_store.list_test_protocols(
            _state(request).session_factory,
            validation_project_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise


@router.get(
    "/validation-center/test-protocols/{protocol_id}",
    response_model=ValidationTestProtocol,
    dependencies=[Depends(require_access_context)],
)
def get_validation_test_protocol_route(
    protocol_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationTestProtocol:
    record = validation_store.get_test_protocol(_state(request).session_factory, protocol_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Validation test protocol not found.")
    return record


@router.post(
    "/validation-center/test-protocols/{protocol_id}/test-cases",
    response_model=ValidationTestCase,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_validation_test_case_route(
    protocol_id: int,
    payload: ValidationTestCaseCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationTestCase:
    try:
        record = validation_store.create_test_case(
            _state(request).session_factory,
            protocol_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_test_case.create",
        message="Validation test case created.",
        entity_type="validation_test_case",
        entity_id=record.id,
        metadata={"protocol_id": protocol_id, "test_case_code": record.test_case_code},
    )
    return record


@router.get(
    "/validation-center/test-protocols/{protocol_id}/test-cases",
    response_model=list[ValidationTestCase],
    dependencies=[Depends(require_access_context)],
)
def list_validation_test_cases_route(
    protocol_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationTestCase]:
    try:
        return validation_store.list_test_cases(
            _state(request).session_factory,
            protocol_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise


@router.post(
    "/validation-center/test-cases/{test_case_id}/execute",
    response_model=ValidationTestExecution,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def execute_validation_test_case_route(
    test_case_id: int,
    payload: ValidationTestExecutionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationTestExecution:
    try:
        record = validation_store.execute_test_case(
            _state(request).session_factory,
            test_case_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="validation_test_execution.create",
        message="Validation test execution recorded.",
        entity_type="validation_test_execution",
        entity_id=record.id,
        metadata={
            "test_case_id": test_case_id,
            "execution_status": record.execution_status,
            "deviation_id": record.deviation_id,
        },
    )
    return record


@router.get(
    "/validation-center/test-executions",
    response_model=list[ValidationTestExecution],
    dependencies=[Depends(require_access_context)],
)
def list_validation_test_executions_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationTestExecution]:
    return validation_store.list_test_executions(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/validation-center/test-executions/{execution_id}",
    response_model=ValidationTestExecution,
    dependencies=[Depends(require_access_context)],
)
def get_validation_test_execution_route(
    execution_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationTestExecution:
    record = validation_store.get_test_execution(_state(request).session_factory, execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Validation test execution not found.")
    return record


@router.get(
    "/validation-center/projects/{validation_project_id}/traceability",
    response_model=TraceabilityMatrix,
    dependencies=[Depends(require_access_context)],
)
def get_traceability_matrix_route(
    validation_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TraceabilityMatrix:
    try:
        record = validation_store.get_latest_traceability(
            _state(request).session_factory,
            validation_project_id,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Traceability matrix not found.")
    return record


@router.post(
    "/validation-center/projects/{validation_project_id}/traceability/generate",
    response_model=TraceabilityMatrix,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def generate_traceability_matrix_route(
    validation_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TraceabilityMatrix:
    try:
        record = validation_store.generate_traceability(
            _state(request).session_factory,
            validation_project_id,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="traceability_matrix.generate",
        message="Traceability matrix generated.",
        entity_type="traceability_matrix",
        entity_id=record.id,
        metadata={
            "validation_project_id": validation_project_id,
            "status": record.status,
            "missing_coverage_count": len(record.missing_coverage_json),
        },
    )
    return record


@router.post(
    "/esignatures/records",
    response_model=ElectronicSignatureRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_esignature_record_route(
    payload: ElectronicSignatureRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ElectronicSignatureRecord:
    try:
        record = validation_store.create_signature(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="esignature.create",
        message="E-signature record created with server timestamp and signature hash.",
        entity_type="electronic_signature",
        entity_id=record.id,
        metadata={
            "target_type": record.target_type,
            "target_id": record.target_id,
            "signature_meaning": record.signature_meaning,
        },
    )
    return record


@router.get(
    "/esignatures/records",
    response_model=list[ElectronicSignatureRecord],
    dependencies=[Depends(require_access_context)],
)
def list_esignature_records_route(
    request: Request,
    target_type: str | None = Query(default=None),
    target_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ElectronicSignatureRecord]:
    return validation_store.list_signatures(
        _state(request).session_factory,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )


@router.get(
    "/esignatures/records/{signature_id}",
    response_model=ElectronicSignatureRecord,
    dependencies=[Depends(require_access_context)],
)
def get_esignature_record_route(
    signature_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ElectronicSignatureRecord:
    record = validation_store.get_signature(_state(request).session_factory, signature_id)
    if record is None:
        raise HTTPException(status_code=404, detail="E-signature record not found.")
    return record


@router.post(
    "/controlled-records",
    response_model=ControlledRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_controlled_record_route(
    payload: ControlledRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ControlledRecord:
    try:
        record = validation_store.create_controlled_record(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="controlled_record.create",
        message="Controlled record created.",
        entity_type="controlled_record",
        entity_id=record.id,
        metadata={"record_type": record.record_type, "status": record.status},
    )
    return record


@router.get(
    "/controlled-records",
    response_model=list[ControlledRecord],
    dependencies=[Depends(require_access_context)],
)
def list_controlled_records_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    record_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ControlledRecord]:
    return validation_store.list_controlled_records(
        _state(request).session_factory,
        status_filter=status_filter,
        record_type=record_type,
        limit=limit,
    )


@router.get(
    "/controlled-records/{record_id}",
    response_model=ControlledRecord,
    dependencies=[Depends(require_access_context)],
)
def get_controlled_record_route(
    record_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ControlledRecord:
    record = validation_store.get_controlled_record(_state(request).session_factory, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Controlled record not found.")
    return record


@router.post(
    "/controlled-records/{record_id}/new-version",
    response_model=ControlledRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_controlled_record_new_version_route(
    record_id: int,
    payload: ControlledRecordNewVersionRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ControlledRecord:
    try:
        record = validation_store.create_controlled_record_version(
            _state(request).session_factory,
            record_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="controlled_record.new_version",
        message="New controlled record version created.",
        entity_type="controlled_record",
        entity_id=record.id,
        metadata={"previous_record_id": record_id, "version": record.version},
    )
    return record


@router.post(
    "/controlled-records/{record_id}/lock",
    response_model=ControlledRecord,
    dependencies=[Depends(require_access_context)],
)
def lock_controlled_record_route(
    record_id: int,
    payload: ControlledRecordLockRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ControlledRecord:
    try:
        record = validation_store.lock_controlled_record(
            _state(request).session_factory,
            record_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="controlled_record.lock",
        message="Controlled record locked.",
        entity_type="controlled_record",
        entity_id=record.id,
        metadata={"locked_by": record.locked_by, "content_hash": record.content_hash},
    )
    return record


@router.post(
    "/controlled-records/{record_id}/archive",
    response_model=ControlledRecord,
    dependencies=[Depends(require_access_context)],
)
def archive_controlled_record_route(
    record_id: int,
    payload: ControlledRecordArchiveRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ControlledRecord:
    try:
        record = validation_store.archive_controlled_record(
            _state(request).session_factory,
            record_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="controlled_record.archive",
        message="Controlled record archived.",
        entity_type="controlled_record",
        entity_id=record.id,
        metadata={"status": record.status},
    )
    return record


@router.post(
    "/record-retention-policies",
    response_model=RecordRetentionPolicy,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_record_retention_policy_route(
    payload: RecordRetentionPolicyCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RecordRetentionPolicy:
    try:
        record = validation_store.create_retention_policy(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="record_retention_policy.create",
        message="Record retention policy created.",
        entity_type="record_retention_policy",
        entity_id=record.id,
        metadata={"record_type": record.record_type, "status": record.status},
    )
    return record


@router.get(
    "/record-retention-policies",
    response_model=list[RecordRetentionPolicy],
    dependencies=[Depends(require_access_context)],
)
def list_record_retention_policies_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RecordRetentionPolicy]:
    return validation_store.list_retention_policies(
        _state(request).session_factory,
        limit=limit,
    )


@router.post(
    "/data-integrity/assessments",
    response_model=DataIntegrityAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_data_integrity_assessment_route(
    payload: DataIntegrityAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DataIntegrityAssessment:
    try:
        record = validation_store.create_data_integrity_assessment(
            _state(request).session_factory,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="data_integrity_assessment.create",
        message="Data integrity assessment created.",
        entity_type="data_integrity_assessment",
        entity_id=record.id,
        metadata={"scope": record.scope, "assessment_status": record.assessment_status},
    )
    return record


@router.get(
    "/data-integrity/assessments",
    response_model=list[DataIntegrityAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_data_integrity_assessments_route(
    request: Request,
    scope: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[DataIntegrityAssessment]:
    return validation_store.list_data_integrity_assessments(
        _state(request).session_factory,
        scope=scope,
        limit=limit,
    )


@router.get(
    "/data-integrity/assessments/{assessment_id}",
    response_model=DataIntegrityAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_data_integrity_assessment_route(
    assessment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DataIntegrityAssessment:
    record = validation_store.get_data_integrity_assessment(
        _state(request).session_factory,
        assessment_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Data integrity assessment not found.")
    return record


@router.post(
    "/inspection-packages",
    response_model=InspectionReadinessPackage,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_inspection_package_route(
    payload: InspectionReadinessPackageCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InspectionReadinessPackage:
    try:
        record = validation_store.create_inspection_package(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="inspection_package.create",
        message="Inspection-ready package created.",
        entity_type="inspection_readiness_package",
        entity_id=record.id,
        metadata={"scope": record.scope, "package_sha256": record.package_sha256},
    )
    return record


@router.get(
    "/inspection-packages",
    response_model=list[InspectionReadinessPackage],
    dependencies=[Depends(require_access_context)],
)
def list_inspection_packages_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[InspectionReadinessPackage]:
    return validation_store.list_inspection_packages(
        _state(request).session_factory,
        limit=limit,
    )


@router.get(
    "/inspection-packages/{package_id}",
    response_model=InspectionReadinessPackage,
    dependencies=[Depends(require_access_context)],
)
def get_inspection_package_route(
    package_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InspectionReadinessPackage:
    record = validation_store.get_inspection_package(_state(request).session_factory, package_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection package not found.")
    return record


@router.get(
    "/inspection-packages/{package_id}/download",
    dependencies=[Depends(require_access_context)],
)
def download_inspection_package_route(
    package_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    download = validation_store.get_inspection_package_download(
        _state(request).session_factory,
        package_id,
    )
    if download is None:
        raise HTTPException(status_code=404, detail="Inspection package not found.")
    filename, content = download
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/system-releases",
    response_model=SystemReleaseRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_system_release_route(
    payload: SystemReleaseRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SystemReleaseRecord:
    try:
        record = validation_store.create_system_release(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="system_release.create",
        message="System release record created.",
        entity_type="system_release",
        entity_id=record.id,
        metadata={"release_version": record.release_version, "release_type": record.release_type},
    )
    return record


@router.get(
    "/system-releases",
    response_model=list[SystemReleaseRecord],
    dependencies=[Depends(require_access_context)],
)
def list_system_releases_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SystemReleaseRecord]:
    return validation_store.list_system_releases(_state(request).session_factory, limit=limit)


@router.get(
    "/system-releases/{release_id}",
    response_model=SystemReleaseRecord,
    dependencies=[Depends(require_access_context)],
)
def get_system_release_route(
    release_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SystemReleaseRecord:
    record = validation_store.get_system_release(_state(request).session_factory, release_id)
    if record is None:
        raise HTTPException(status_code=404, detail="System release record not found.")
    return record


@router.post(
    "/system-releases/{release_id}/approve",
    response_model=SystemReleaseRecord,
    dependencies=[Depends(require_access_context)],
)
def approve_system_release_route(
    release_id: int,
    payload: SystemReleaseApproveRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SystemReleaseRecord:
    try:
        record = validation_store.approve_system_release(
            _state(request).session_factory,
            release_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="system_release.approve",
        message="System release approved with e-signature record.",
        entity_type="system_release",
        entity_id=record.id,
        metadata={
            "approval_status": record.approval_status,
            "signature_id": record.metadata_json.get("approval_signature_id"),
        },
    )
    return record


@router.post(
    "/deviations",
    response_model=DeviationRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_deviation_route(
    payload: DeviationRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeviationRecord:
    try:
        record = validation_store.create_deviation(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="deviation.create",
        message="Deviation record created.",
        entity_type="deviation",
        entity_id=record.id,
        metadata={"deviation_code": record.deviation_code, "source_type": record.source_type},
    )
    return record


@router.get(
    "/deviations",
    response_model=list[DeviationRecord],
    dependencies=[Depends(require_access_context)],
)
def list_deviations_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[DeviationRecord]:
    return validation_store.list_deviations(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.patch(
    "/deviations/{deviation_id}",
    response_model=DeviationRecord,
    dependencies=[Depends(require_access_context)],
)
def update_deviation_route(
    deviation_id: int,
    payload: DeviationRecordUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeviationRecord:
    try:
        record = validation_store.update_deviation(
            _state(request).session_factory,
            deviation_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Deviation record not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="deviation.update",
        message="Deviation record updated.",
        entity_type="deviation",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/capa",
    response_model=CAPARecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_capa_route(
    payload: CAPARecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CAPARecord:
    try:
        record = validation_store.create_capa(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="capa.create",
        message="CAPA record created.",
        entity_type="capa",
        entity_id=record.id,
        metadata={"capa_code": record.capa_code, "source_deviation_id": record.source_deviation_id},
    )
    return record


@router.get(
    "/capa",
    response_model=list[CAPARecord],
    dependencies=[Depends(require_access_context)],
)
def list_capa_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[CAPARecord]:
    return validation_store.list_capa(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.patch(
    "/capa/{capa_id}",
    response_model=CAPARecord,
    dependencies=[Depends(require_access_context)],
)
def update_capa_route(
    capa_id: int,
    payload: CAPARecordUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CAPARecord:
    try:
        record = validation_store.update_capa(
            _state(request).session_factory,
            capa_id,
            payload,
        )
    except Exception as exc:
        _raise_validation_center_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="CAPA record not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="capa.update",
        message="CAPA record updated.",
        entity_type="capa",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants",
    response_model=Tenant,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_route(
    payload: TenantCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> Tenant:
    if not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant admin access is required.")
    try:
        record = tenant_store.create_tenant(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant.create",
        message="Tenant isolation record created.",
        entity_type="tenant",
        entity_id=record.id,
        metadata={"tenant_id": record.id, "tenant_type": record.tenant_type, "status": record.status},
    )
    return record


@router.get(
    "/tenants",
    response_model=list[Tenant],
    dependencies=[Depends(require_access_context)],
)
def list_tenants_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[Tenant]:
    if not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Internal super-admin access is required.")
    return tenant_store.list_tenants(
        _state(request).session_factory,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/tenants/{tenant_id}",
    response_model=Tenant,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> Tenant:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    record = tenant_store.get_tenant(_state(request).session_factory, tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return record


@router.patch(
    "/tenants/{tenant_id}",
    response_model=Tenant,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_route(
    tenant_id: int,
    payload: TenantUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> Tenant:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.update_tenant(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="tenant.update",
        message="Tenant isolation record updated.",
        entity_type="tenant",
        entity_id=record.id,
        metadata={"tenant_id": record.id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/environments",
    response_model=TenantEnvironment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_environment_route(
    tenant_id: int,
    payload: TenantEnvironmentCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantEnvironment:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_environment(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_environment.create",
        message="Tenant environment created.",
        entity_type="tenant_environment",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "environment_type": record.environment_type, "status": record.status},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/environments",
    response_model=list[TenantEnvironment],
    dependencies=[Depends(require_access_context)],
)
def list_tenant_environments_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[TenantEnvironment]:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.list_environments(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.patch(
    "/tenant-environments/{environment_id}",
    response_model=TenantEnvironment,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_environment_route(
    environment_id: int,
    payload: TenantEnvironmentUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantEnvironment:
    try:
        record = tenant_store.update_environment(
            _state(request).session_factory,
            environment_id,
            payload,
            requested_tenant_id=x_tenant_id,
            is_internal_super_admin=_is_internal_super_admin(context),
        )
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant environment not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_environment.update",
        message="Tenant environment updated.",
        entity_type="tenant_environment",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/subscription-plans",
    response_model=SubscriptionPlan,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_subscription_plan_route(
    payload: SubscriptionPlanCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SubscriptionPlan:
    if not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant admin access is required.")
    try:
        record = tenant_store.create_subscription_plan(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="subscription_plan.create",
        message="Subscription plan created.",
        entity_type="subscription_plan",
        entity_id=record.id,
        metadata={"plan_key": record.plan_key, "status": record.status},
    )
    return record


@router.get(
    "/subscription-plans",
    response_model=list[SubscriptionPlan],
    dependencies=[Depends(require_access_context)],
)
def list_subscription_plans_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SubscriptionPlan]:
    return tenant_store.list_subscription_plans(_state(request).session_factory, limit=limit)


@router.get(
    "/subscription-plans/{plan_id}",
    response_model=SubscriptionPlan,
    dependencies=[Depends(require_access_context)],
)
def get_subscription_plan_route(
    plan_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SubscriptionPlan:
    record = tenant_store.get_subscription_plan(_state(request).session_factory, plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Subscription plan not found.")
    return record


@router.post(
    "/tenants/{tenant_id}/entitlements",
    response_model=TenantEntitlement,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_entitlement_route(
    tenant_id: int,
    payload: TenantEntitlementCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantEntitlement:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_entitlement(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_entitlement.create",
        message="Tenant entitlement created.",
        entity_type="tenant_entitlement",
        entity_id=record.id,
        metadata={
            "tenant_id": tenant_id,
            "feature_key": record.feature_key,
            "program": record.program,
            "enabled": record.enabled,
        },
    )
    return record


@router.get(
    "/tenants/{tenant_id}/entitlements",
    response_model=list[TenantEntitlement],
    dependencies=[Depends(require_access_context)],
)
def list_tenant_entitlements_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[TenantEntitlement]:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.list_entitlements(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.patch(
    "/tenant-entitlements/{entitlement_id}",
    response_model=TenantEntitlement,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_entitlement_route(
    entitlement_id: int,
    payload: TenantEntitlementUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantEntitlement:
    try:
        record = tenant_store.update_entitlement(
            _state(request).session_factory,
            entitlement_id,
            payload,
            requested_tenant_id=x_tenant_id,
            is_internal_super_admin=_is_internal_super_admin(context),
        )
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant entitlement not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_entitlement.update",
        message="Tenant entitlement updated.",
        entity_type="tenant_entitlement",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/feature-flags",
    response_model=FeatureFlag,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_feature_flag_route(
    payload: FeatureFlagCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeatureFlag:
    if not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant admin access is required.")
    try:
        record = tenant_store.create_feature_flag(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="feature_flag.create",
        message="Feature flag created without changing core program order.",
        entity_type="feature_flag",
        entity_id=record.id,
        metadata={"flag_key": record.flag_key, "program": record.program, "status": record.status},
    )
    return record


@router.get(
    "/feature-flags",
    response_model=list[FeatureFlag],
    dependencies=[Depends(require_access_context)],
)
def list_feature_flags_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[FeatureFlag]:
    return tenant_store.list_feature_flags(_state(request).session_factory, limit=limit)


@router.get(
    "/feature-flags/{flag_id}",
    response_model=FeatureFlag,
    dependencies=[Depends(require_access_context)],
)
def get_feature_flag_route(
    flag_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeatureFlag:
    record = tenant_store.get_feature_flag(_state(request).session_factory, flag_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Feature flag not found.")
    return record


@router.patch(
    "/feature-flags/{flag_id}",
    response_model=FeatureFlag,
    dependencies=[Depends(require_access_context)],
)
def update_feature_flag_route(
    flag_id: int,
    payload: FeatureFlagUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeatureFlag:
    if not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant admin access is required.")
    try:
        record = tenant_store.update_feature_flag(_state(request).session_factory, flag_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Feature flag not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="feature_flag.update",
        message="Feature flag updated without changing core program order.",
        entity_type="feature_flag",
        entity_id=record.id,
        metadata={"flag_key": record.flag_key, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/pilot-programs",
    response_model=PilotProgram,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_pilot_program_route(
    tenant_id: int,
    payload: PilotProgramCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotProgram:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_pilot_program(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_program.create",
        message="Pilot scope created.",
        entity_type="pilot_program",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "status": record.status},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/pilot-programs",
    response_model=list[PilotProgram],
    dependencies=[Depends(require_access_context)],
)
def list_pilot_programs_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[PilotProgram]:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.list_pilot_programs(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/pilot-programs/{pilot_id}",
    response_model=PilotProgram,
    dependencies=[Depends(require_access_context)],
)
def get_pilot_program_route(
    pilot_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotProgram:
    record = tenant_store.get_pilot_program(_state(request).session_factory, pilot_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Pilot program not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    return record


@router.patch(
    "/pilot-programs/{pilot_id}",
    response_model=PilotProgram,
    dependencies=[Depends(require_access_context)],
)
def update_pilot_program_route(
    pilot_id: int,
    payload: PilotProgramUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotProgram:
    try:
        record = tenant_store.update_pilot_program(_state(request).session_factory, pilot_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Pilot program not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_program.update",
        message="Pilot scope updated.",
        entity_type="pilot_program",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/onboarding-projects",
    response_model=CustomerOnboardingProject,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_onboarding_project_route(
    tenant_id: int,
    payload: CustomerOnboardingProjectCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerOnboardingProject:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_onboarding_project(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="onboarding_project.create",
        message="Customer onboarding readiness project created.",
        entity_type="onboarding_project",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "implementation_stage": record.implementation_stage},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/onboarding-projects",
    response_model=list[CustomerOnboardingProject],
    dependencies=[Depends(require_access_context)],
)
def list_onboarding_projects_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[CustomerOnboardingProject]:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.list_onboarding_projects(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/onboarding-projects/{project_id}",
    response_model=CustomerOnboardingProject,
    dependencies=[Depends(require_access_context)],
)
def get_onboarding_project_route(
    project_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerOnboardingProject:
    record = tenant_store.get_onboarding_project(_state(request).session_factory, project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Onboarding project not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    return record


@router.patch(
    "/onboarding-projects/{project_id}",
    response_model=CustomerOnboardingProject,
    dependencies=[Depends(require_access_context)],
)
def update_onboarding_project_route(
    project_id: int,
    payload: CustomerOnboardingProjectUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerOnboardingProject:
    try:
        record = tenant_store.update_onboarding_project(_state(request).session_factory, project_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Onboarding project not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="onboarding_project.update",
        message="Customer onboarding readiness project updated.",
        entity_type="onboarding_project",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/onboarding-projects/{project_id}/tasks",
    response_model=ImplementationTask,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_implementation_task_route(
    project_id: int,
    payload: ImplementationTaskCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> ImplementationTask:
    project = tenant_store.get_onboarding_project(_state(request).session_factory, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Onboarding project not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=project.tenant_id,
    )
    try:
        record = tenant_store.create_implementation_task(
            _state(request).session_factory,
            project_id,
            payload,
        )
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="implementation_task.create",
        message="Implementation task created.",
        entity_type="implementation_task",
        entity_id=record.id,
        metadata={"tenant_id": project.tenant_id, "program": record.program, "status": record.status},
    )
    return record


@router.get(
    "/onboarding-projects/{project_id}/tasks",
    response_model=list[ImplementationTask],
    dependencies=[Depends(require_access_context)],
)
def list_implementation_tasks_route(
    project_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[ImplementationTask]:
    project = tenant_store.get_onboarding_project(_state(request).session_factory, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Onboarding project not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=project.tenant_id,
    )
    try:
        return tenant_store.list_implementation_tasks(_state(request).session_factory, project_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.patch(
    "/implementation-tasks/{task_id}",
    response_model=ImplementationTask,
    dependencies=[Depends(require_access_context)],
)
def update_implementation_task_route(
    task_id: int,
    payload: ImplementationTaskUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> ImplementationTask:
    task_tenant_id = tenant_store.get_implementation_task_tenant_id(
        _state(request).session_factory,
        task_id,
    )
    if task_tenant_id is None:
        raise HTTPException(status_code=404, detail="Implementation task not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=task_tenant_id,
    )
    try:
        record = tenant_store.update_implementation_task(_state(request).session_factory, task_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Implementation task not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="implementation_task.update",
        message="Implementation task updated.",
        entity_type="implementation_task",
        entity_id=record.id,
        metadata={"tenant_id": task_tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/data-boundary",
    response_model=TenantDataBoundary,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_data_boundary_route(
    tenant_id: int,
    payload: TenantDataBoundaryCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantDataBoundary:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_data_boundary(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_data_boundary.create",
        message="Tenant data boundary created.",
        entity_type="tenant_data_boundary",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "isolation_mode": record.isolation_mode, "status": record.status},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/data-boundary",
    response_model=TenantDataBoundary,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_data_boundary_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantDataBoundary:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.get_data_boundary(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant data boundary not found.")
    return record


@router.patch(
    "/tenant-data-boundaries/{boundary_id}",
    response_model=TenantDataBoundary,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_data_boundary_route(
    boundary_id: int,
    payload: TenantDataBoundaryUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantDataBoundary:
    try:
        record = tenant_store.update_data_boundary(_state(request).session_factory, boundary_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant data boundary not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_data_boundary.update",
        message="Tenant data boundary updated.",
        entity_type="tenant_data_boundary",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/security-profile",
    response_model=TenantSecurityProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_security_profile_route(
    tenant_id: int,
    payload: TenantSecurityProfileCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantSecurityProfile:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_security_profile(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_security_profile.create",
        message="Tenant security profile created.",
        entity_type="tenant_security_profile",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "status": record.status, "mfa_required": record.mfa_required},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/security-profile",
    response_model=TenantSecurityProfile,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_security_profile_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantSecurityProfile:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.get_security_profile(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant security profile not found.")
    return record


@router.patch(
    "/tenant-security-profiles/{profile_id}",
    response_model=TenantSecurityProfile,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_security_profile_route(
    profile_id: int,
    payload: TenantSecurityProfileUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantSecurityProfile:
    try:
        record = tenant_store.update_security_profile(_state(request).session_factory, profile_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant security profile not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_security_profile.update",
        message="Tenant security profile updated.",
        entity_type="tenant_security_profile",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/tenants/{tenant_id}/validation-profile",
    response_model=TenantValidationProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_validation_profile_route(
    tenant_id: int,
    payload: TenantValidationProfileCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantValidationProfile:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_validation_profile(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_validation_profile.create",
        message="Tenant validation readiness profile created.",
        entity_type="tenant_validation_profile",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "status": record.status, "validation_required": record.validation_required},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/validation-profile",
    response_model=TenantValidationProfile,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_validation_profile_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantValidationProfile:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.get_validation_profile(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant validation profile not found.")
    return record


@router.patch(
    "/tenant-validation-profiles/{profile_id}",
    response_model=TenantValidationProfile,
    dependencies=[Depends(require_access_context)],
)
def update_tenant_validation_profile_route(
    profile_id: int,
    payload: TenantValidationProfileUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantValidationProfile:
    try:
        record = tenant_store.update_validation_profile(_state(request).session_factory, profile_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant validation profile not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_validation_profile.update",
        message="Tenant validation readiness profile updated.",
        entity_type="tenant_validation_profile",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/usage-summary",
    response_model=TenantUsageSummary,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_usage_summary_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantUsageSummary:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.get_usage_summary(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/tenants/{tenant_id}/roi",
    response_model=TenantRoiSnapshot,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_roi_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantRoiSnapshot:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.get_roi_snapshot(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/tenants/{tenant_id}/health-score",
    response_model=CustomerSuccessHealthScore,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_health_score_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerSuccessHealthScore:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.get_health_score(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.post(
    "/tenants/{tenant_id}/procurement-package",
    response_model=ProcurementEvidencePackage,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_procurement_package_route(
    tenant_id: int,
    payload: ProcurementEvidencePackageCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> ProcurementEvidencePackage:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_procurement_package(
            _state(request).session_factory,
            tenant_id,
            payload,
        )
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="procurement_package.create",
        message="Procurement evidence package created with safe summaries.",
        entity_type="procurement_evidence_package",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "package_type": record.package_type, "package_sha256": record.package_sha256},
    )
    return record


@router.get(
    "/tenants/{tenant_id}/procurement-packages",
    response_model=list[ProcurementEvidencePackage],
    dependencies=[Depends(require_access_context)],
)
def list_tenant_procurement_packages_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[ProcurementEvidencePackage]:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.list_procurement_packages(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/procurement-packages/{package_id}",
    response_model=ProcurementEvidencePackage,
    dependencies=[Depends(require_access_context)],
)
def get_procurement_package_route(
    package_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> ProcurementEvidencePackage:
    record = tenant_store.get_procurement_package(_state(request).session_factory, package_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Procurement evidence package not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    return record


@router.post(
    "/tenants/{tenant_id}/audit-export",
    response_model=TenantAuditExport,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_tenant_audit_export_route(
    tenant_id: int,
    payload: TenantAuditExportCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantAuditExport:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        record = tenant_store.create_audit_export(_state(request).session_factory, tenant_id, payload)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="tenant_audit_export.create",
        message="Tenant audit export created with safe manifest.",
        entity_type="tenant_audit_export",
        entity_id=record.id,
        metadata={"tenant_id": tenant_id, "export_scope": record.export_scope, "export_sha256": record.export_sha256},
    )
    return record


@router.get(
    "/tenant-audit-exports/{export_id}",
    response_model=TenantAuditExport,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_audit_export_route(
    export_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantAuditExport:
    record = tenant_store.get_audit_export(_state(request).session_factory, export_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant audit export not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    return record


@router.get(
    "/tenants/{tenant_id}/module-readiness",
    response_model=TenantModuleReadiness,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_module_readiness_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantModuleReadiness:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.get_module_readiness(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.get(
    "/tenants/{tenant_id}/go-live-readiness",
    response_model=TenantGoLiveReadiness,
    dependencies=[Depends(require_access_context)],
)
def get_tenant_go_live_readiness_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> TenantGoLiveReadiness:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=tenant_id,
    )
    try:
        return tenant_store.get_go_live_readiness(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_tenant_saas_http_error(exc)
        raise


@router.post(
    "/pilot/golden-datasets",
    response_model=GoldenDataset,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_golden_dataset_route(
    payload: GoldenDatasetCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenDataset:
    try:
        record = golden_pilot_store.create_golden_dataset(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="golden_dataset.create",
        message="Golden dataset created as labeled demo/test or customer pilot data.",
        entity_type="golden_dataset",
        entity_id=record.id,
        metadata={"dataset_type": record.dataset_type, "source_type": record.source_type, "status": record.status},
    )
    return record


@router.get(
    "/pilot/golden-datasets",
    response_model=list[GoldenDataset],
    dependencies=[Depends(require_access_context)],
)
def list_golden_datasets_route(
    request: Request,
    dataset_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[GoldenDataset]:
    return golden_pilot_store.list_golden_datasets(
        _state(request).session_factory,
        dataset_type=dataset_type,
        source_type=source_type,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/pilot/golden-datasets/{dataset_id}",
    response_model=GoldenDataset,
    dependencies=[Depends(require_access_context)],
)
def get_golden_dataset_route(
    dataset_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenDataset:
    record = golden_pilot_store.get_golden_dataset(_state(request).session_factory, dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Golden dataset not found.")
    return record


@router.patch(
    "/pilot/golden-datasets/{dataset_id}",
    response_model=GoldenDataset,
    dependencies=[Depends(require_access_context)],
)
def update_golden_dataset_route(
    dataset_id: int,
    payload: GoldenDatasetUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenDataset:
    try:
        record = golden_pilot_store.update_golden_dataset(_state(request).session_factory, dataset_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Golden dataset not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="golden_dataset.update",
        message="Golden dataset updated.",
        entity_type="golden_dataset",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set), "status": record.status},
    )
    return record


@router.post(
    "/pilot/scenarios",
    response_model=GoldenPilotScenario,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_golden_scenario_route(
    payload: GoldenPilotScenarioCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenPilotScenario:
    try:
        record = golden_pilot_store.create_scenario(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="golden_scenario.create",
        message="Golden scenario created with fixed core product order.",
        entity_type="golden_scenario",
        entity_id=record.id,
        metadata={"scenario_type": record.scenario_type, "status": record.status},
    )
    return record


@router.get(
    "/pilot/scenarios",
    response_model=list[GoldenPilotScenario],
    dependencies=[Depends(require_access_context)],
)
def list_golden_scenarios_route(
    request: Request,
    scenario_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[GoldenPilotScenario]:
    return golden_pilot_store.list_scenarios(
        _state(request).session_factory,
        scenario_type=scenario_type,
        status_filter=status_filter,
        limit=limit,
    )


@router.get(
    "/pilot/scenarios/{scenario_id}",
    response_model=GoldenPilotScenario,
    dependencies=[Depends(require_access_context)],
)
def get_golden_scenario_route(
    scenario_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenPilotScenario:
    record = golden_pilot_store.get_scenario(_state(request).session_factory, scenario_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Golden scenario not found.")
    return record


@router.patch(
    "/pilot/scenarios/{scenario_id}",
    response_model=GoldenPilotScenario,
    dependencies=[Depends(require_access_context)],
)
def update_golden_scenario_route(
    scenario_id: int,
    payload: GoldenPilotScenarioUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenPilotScenario:
    try:
        record = golden_pilot_store.update_scenario(_state(request).session_factory, scenario_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Golden scenario not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="golden_scenario.update",
        message="Golden scenario updated.",
        entity_type="golden_scenario",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set), "status": record.status},
    )
    return record


@router.post(
    "/pilot/scenarios/{scenario_id}/workflow-cases",
    response_model=GoldenWorkflowCase,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_golden_workflow_case_route(
    scenario_id: int,
    payload: GoldenWorkflowCaseCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> GoldenWorkflowCase:
    try:
        record = golden_pilot_store.create_workflow_case(_state(request).session_factory, scenario_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="golden_workflow_case.create",
        message="Golden workflow case created.",
        entity_type="golden_workflow_case",
        entity_id=record.id,
        metadata={"scenario_id": scenario_id, "status": record.status},
    )
    return record


@router.get(
    "/pilot/scenarios/{scenario_id}/workflow-cases",
    response_model=list[GoldenWorkflowCase],
    dependencies=[Depends(require_access_context)],
)
def list_golden_workflow_cases_route(
    scenario_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[GoldenWorkflowCase]:
    try:
        return golden_pilot_store.list_workflow_cases(_state(request).session_factory, scenario_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.post(
    "/pilot/scenarios/{scenario_id}/expected-output-contracts",
    response_model=ExpectedOutputContract,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_expected_output_contract_route(
    scenario_id: int,
    payload: ExpectedOutputContractCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ExpectedOutputContract:
    try:
        record = golden_pilot_store.create_expected_output_contract(
            _state(request).session_factory,
            scenario_id,
            payload,
        )
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="expected_output_contract.create",
        message="Expected output contract created.",
        entity_type="expected_output_contract",
        entity_id=record.id,
        metadata={"scenario_id": scenario_id, "target_module": record.target_module},
    )
    return record


@router.get(
    "/pilot/scenarios/{scenario_id}/expected-output-contracts",
    response_model=list[ExpectedOutputContract],
    dependencies=[Depends(require_access_context)],
)
def list_expected_output_contracts_route(
    scenario_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ExpectedOutputContract]:
    try:
        return golden_pilot_store.list_expected_output_contracts(_state(request).session_factory, scenario_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.post(
    "/pilot/scenarios/{scenario_id}/seed-tenant",
    response_model=DemoTenantSeed,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def seed_demo_tenant_route(
    scenario_id: int,
    payload: DemoTenantSeedCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> DemoTenantSeed:
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=payload.tenant_id,
    )
    try:
        record = golden_pilot_store.seed_demo_tenant(_state(request).session_factory, scenario_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="demo_tenant_seed.create",
        message="Demo tenant seed created with safe demo records.",
        entity_type="demo_tenant_seed",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "scenario_id": scenario_id, "status": record.status},
    )
    return record


@router.get(
    "/pilot/demo-seeds/{seed_id}",
    response_model=DemoTenantSeed,
    dependencies=[Depends(require_access_context)],
)
def get_demo_tenant_seed_route(
    seed_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> DemoTenantSeed:
    record = golden_pilot_store.get_demo_seed(_state(request).session_factory, seed_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Demo tenant seed not found.")
    _require_tenant_scope_header(
        context=context,
        requested_tenant_id=x_tenant_id,
        actual_tenant_id=record.tenant_id,
    )
    return record


@router.post(
    "/pilot/scenarios/{scenario_id}/run",
    response_model=PilotRunDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_pilot_scenario_route(
    scenario_id: int,
    payload: PilotRunCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotRunDetail:
    if payload.tenant_id is not None:
        _require_tenant_scope_header(
            context=context,
            requested_tenant_id=x_tenant_id,
            actual_tenant_id=payload.tenant_id,
        )
    try:
        record = golden_pilot_store.run_pilot_scenario(_state(request).session_factory, scenario_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_run.create",
        message="Golden scenario pilot run executed or simulated with safe summaries.",
        entity_type="pilot_run",
        entity_id=record.id,
        metadata={"scenario_id": scenario_id, "tenant_id": record.tenant_id, "status": record.status},
    )
    return record


@router.get(
    "/pilot/runs",
    response_model=list[PilotRun],
    dependencies=[Depends(require_access_context)],
)
def list_pilot_runs_route(
    request: Request,
    tenant_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[PilotRun]:
    if tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=tenant_id)
    elif not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant-scoped access requires a tenant_id filter.")
    return golden_pilot_store.list_pilot_runs(_state(request).session_factory, tenant_id=tenant_id, limit=limit)


@router.get(
    "/pilot/runs/{pilot_run_id}",
    response_model=PilotRunDetail,
    dependencies=[Depends(require_access_context)],
)
def get_pilot_run_route(
    pilot_run_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotRunDetail:
    record = golden_pilot_store.get_pilot_run(_state(request).session_factory, pilot_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Pilot run not found.")
    if record.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=record.tenant_id)
    return record


@router.post(
    "/pilot/runs/{pilot_run_id}/validate",
    response_model=list[ScenarioValidationResult],
    dependencies=[Depends(require_access_context)],
)
def validate_pilot_run_route(
    pilot_run_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[ScenarioValidationResult]:
    run = golden_pilot_store.get_pilot_run(_state(request).session_factory, pilot_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pilot run not found.")
    if run.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=run.tenant_id)
    try:
        records = golden_pilot_store.validate_pilot_run(_state(request).session_factory, pilot_run_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_run.validate",
        message="Pilot run validated against expected output contracts.",
        entity_type="pilot_run",
        entity_id=pilot_run_id,
        metadata={"result_count": len(records)},
    )
    return records


@router.get(
    "/pilot/runs/{pilot_run_id}/validation-results",
    response_model=list[ScenarioValidationResult],
    dependencies=[Depends(require_access_context)],
)
def list_pilot_run_validation_results_route(
    pilot_run_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[ScenarioValidationResult]:
    run = golden_pilot_store.get_pilot_run(_state(request).session_factory, pilot_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pilot run not found.")
    if run.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=run.tenant_id)
    try:
        return golden_pilot_store.list_validation_results(_state(request).session_factory, pilot_run_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.post(
    "/pilot/acceptance-protocols",
    response_model=CustomerAcceptanceProtocol,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_acceptance_protocol_route(
    payload: CustomerAcceptanceProtocolCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerAcceptanceProtocol:
    if payload.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=payload.tenant_id)
    try:
        record = golden_pilot_store.create_acceptance_protocol(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="customer_acceptance_protocol.create",
        message="Customer pilot acceptance protocol created.",
        entity_type="customer_acceptance_protocol",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "scope": record.scope, "status": record.status},
    )
    return record


@router.get(
    "/pilot/acceptance-protocols",
    response_model=list[CustomerAcceptanceProtocol],
    dependencies=[Depends(require_access_context)],
)
def list_acceptance_protocols_route(
    request: Request,
    tenant_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[CustomerAcceptanceProtocol]:
    if tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=tenant_id)
    elif not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant-scoped access requires a tenant_id filter.")
    return golden_pilot_store.list_acceptance_protocols(
        _state(request).session_factory,
        tenant_id=tenant_id,
        limit=limit,
    )


@router.get(
    "/pilot/acceptance-protocols/{protocol_id}",
    response_model=CustomerAcceptanceProtocol,
    dependencies=[Depends(require_access_context)],
)
def get_acceptance_protocol_route(
    protocol_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerAcceptanceProtocol:
    record = golden_pilot_store.get_acceptance_protocol(_state(request).session_factory, protocol_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Customer acceptance protocol not found.")
    if record.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=record.tenant_id)
    return record


@router.patch(
    "/pilot/acceptance-protocols/{protocol_id}",
    response_model=CustomerAcceptanceProtocol,
    dependencies=[Depends(require_access_context)],
)
def update_acceptance_protocol_route(
    protocol_id: int,
    payload: CustomerAcceptanceProtocolUpdate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerAcceptanceProtocol:
    existing = golden_pilot_store.get_acceptance_protocol(_state(request).session_factory, protocol_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Customer acceptance protocol not found.")
    scope_tenant_id = payload.tenant_id or existing.tenant_id
    if scope_tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=scope_tenant_id)
    try:
        record = golden_pilot_store.update_acceptance_protocol(_state(request).session_factory, protocol_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Customer acceptance protocol not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="customer_acceptance_protocol.update",
        message="Customer pilot acceptance protocol updated.",
        entity_type="customer_acceptance_protocol",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/pilot/acceptance-tests/{test_id}/execute",
    response_model=CustomerAcceptanceTest,
    dependencies=[Depends(require_access_context)],
)
def execute_acceptance_test_route(
    test_id: int,
    payload: CustomerAcceptanceTestExecute,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> CustomerAcceptanceTest:
    existing = golden_pilot_store.get_acceptance_test(_state(request).session_factory, test_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Customer acceptance test not found.")
    protocol = golden_pilot_store.get_acceptance_protocol(_state(request).session_factory, existing.protocol_id)
    if protocol is not None and protocol.tenant_id is not None:
        _require_tenant_scope_header(
            context=context,
            requested_tenant_id=x_tenant_id,
            actual_tenant_id=protocol.tenant_id,
        )
    try:
        record = golden_pilot_store.execute_acceptance_test(_state(request).session_factory, test_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Customer acceptance test not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="customer_acceptance_test.execute",
        message="Customer pilot acceptance test executed.",
        entity_type="customer_acceptance_test",
        entity_id=record.id,
        metadata={"protocol_id": record.protocol_id, "status": record.status},
    )
    return record


@router.get(
    "/pilot/acceptance-protocols/{protocol_id}/tests",
    response_model=list[CustomerAcceptanceTest],
    dependencies=[Depends(require_access_context)],
)
def list_acceptance_tests_route(
    protocol_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[CustomerAcceptanceTest]:
    protocol = golden_pilot_store.get_acceptance_protocol(_state(request).session_factory, protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Customer acceptance protocol not found.")
    if protocol.tenant_id is not None:
        _require_tenant_scope_header(
            context=context,
            requested_tenant_id=x_tenant_id,
            actual_tenant_id=protocol.tenant_id,
        )
    try:
        return golden_pilot_store.list_acceptance_tests(_state(request).session_factory, protocol_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.post(
    "/pilot/readiness-assessments",
    response_model=PilotReadinessAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_pilot_readiness_assessment_route(
    payload: PilotReadinessAssessmentCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotReadinessAssessment:
    if payload.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=payload.tenant_id)
    try:
        record = golden_pilot_store.create_readiness_assessment(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_readiness_assessment.create",
        message="Pilot readiness assessment created.",
        entity_type="pilot_readiness_assessment",
        entity_id=record.id,
        metadata={"tenant_id": record.tenant_id, "readiness_status": record.readiness_status},
    )
    return record


@router.get(
    "/pilot/readiness-assessments",
    response_model=list[PilotReadinessAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_pilot_readiness_assessments_route(
    request: Request,
    tenant_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[PilotReadinessAssessment]:
    if tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=tenant_id)
    elif not _is_internal_super_admin(context):
        raise HTTPException(status_code=403, detail="Tenant-scoped access requires a tenant_id filter.")
    return golden_pilot_store.list_readiness_assessments(
        _state(request).session_factory,
        tenant_id=tenant_id,
        limit=limit,
    )


@router.get(
    "/pilot/readiness-assessments/{assessment_id}",
    response_model=PilotReadinessAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_pilot_readiness_assessment_route(
    assessment_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotReadinessAssessment:
    record = golden_pilot_store.get_readiness_assessment(_state(request).session_factory, assessment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Pilot readiness assessment not found.")
    if record.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=record.tenant_id)
    return record


@router.post(
    "/pilot/signoff",
    response_model=PilotSignoffRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_pilot_signoff_route(
    payload: PilotSignoffCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotSignoffRecord:
    if payload.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=payload.tenant_id)
    try:
        record = golden_pilot_store.create_signoff(_state(request).session_factory, payload)
        if record.signature_record_id is None:
            signature = validation_store.create_signature(
                _state(request).session_factory,
                ElectronicSignatureRecordCreate(
                    signer_name=record.signer_name,
                    signer_email=record.signer_email,
                    signature_meaning="reviewed" if record.decision != "rejected" else "rejected",
                    target_type="pilot_signoff",
                    target_id=record.id,
                    reason=record.rationale,
                    authentication_method="server_side_api",
                    metadata_json={
                        "pilot_signoff_decision": record.decision,
                        "pilot_run_id": record.pilot_run_id,
                        "protocol_id": record.protocol_id,
                    },
                ),
            )
            linked = golden_pilot_store.set_signoff_signature_record_id(
                _state(request).session_factory,
                record.id,
                signature.id,
            )
            if linked is not None:
                record = linked
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_signoff.create",
        message="Pilot signoff record created with rationale and e-signature linkage.",
        entity_type="pilot_signoff",
        entity_id=record.id,
        metadata={
            "tenant_id": record.tenant_id,
            "pilot_run_id": record.pilot_run_id,
            "decision": record.decision,
            "signature_record_id": record.signature_record_id,
        },
    )
    return record


@router.get(
    "/pilot/signoff/{signoff_id}",
    response_model=PilotSignoffRecord,
    dependencies=[Depends(require_access_context)],
)
def get_pilot_signoff_route(
    signoff_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotSignoffRecord:
    record = golden_pilot_store.get_signoff(_state(request).session_factory, signoff_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Pilot signoff record not found.")
    if record.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=record.tenant_id)
    return record


@router.post(
    "/pilot/runs/{pilot_run_id}/evidence-bundle",
    response_model=PilotEvidenceBundle,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_pilot_evidence_bundle_route(
    pilot_run_id: int,
    payload: PilotEvidenceBundleCreate,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotEvidenceBundle:
    run = golden_pilot_store.get_pilot_run(_state(request).session_factory, pilot_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pilot run not found.")
    if run.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=run.tenant_id)
    try:
        record = golden_pilot_store.create_evidence_bundle(_state(request).session_factory, pilot_run_id, payload)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="pilot_evidence_bundle.create",
        message="Pilot evidence bundle created with safe summaries and hashes.",
        entity_type="pilot_evidence_bundle",
        entity_id=record.id,
        metadata={"pilot_run_id": pilot_run_id, "package_sha256": record.package_sha256, "status": record.status},
    )
    return record


@router.get(
    "/pilot/runs/{pilot_run_id}/evidence-bundle",
    response_model=list[PilotEvidenceBundle],
    dependencies=[Depends(require_access_context)],
)
def list_pilot_evidence_bundles_route(
    pilot_run_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> list[PilotEvidenceBundle]:
    run = golden_pilot_store.get_pilot_run(_state(request).session_factory, pilot_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Pilot run not found.")
    if run.tenant_id is not None:
        _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=run.tenant_id)
    try:
        return golden_pilot_store.list_evidence_bundles(_state(request).session_factory, pilot_run_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.get(
    "/pilot/customer-dashboard/{tenant_id}",
    response_model=PilotCustomerDashboard,
    dependencies=[Depends(require_access_context)],
)
def get_pilot_customer_dashboard_route(
    tenant_id: int,
    request: Request,
    x_tenant_id: int | None = Header(default=None, alias="x-tenant-id"),
    context: AccessContext = Depends(require_access_context),
) -> PilotCustomerDashboard:
    _require_tenant_scope_header(context=context, requested_tenant_id=x_tenant_id, actual_tenant_id=tenant_id)
    try:
        return golden_pilot_store.get_customer_dashboard(_state(request).session_factory, tenant_id)
    except Exception as exc:
        _raise_golden_pilot_http_error(exc)
        raise


@router.get(
    "/regulatory/jurisdictions",
    response_model=list[RegulatoryJurisdiction],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_jurisdictions_route(
    request: Request,
    include_inactive: bool = Query(default=False),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryJurisdiction]:
    return regulatory_store.list_jurisdictions(
        _state(request).session_factory,
        include_inactive=include_inactive,
    )


@router.post(
    "/regulatory/jurisdictions",
    response_model=RegulatoryJurisdiction,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_jurisdiction_route(
    payload: RegulatoryJurisdictionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryJurisdiction:
    try:
        return regulatory_store.create_jurisdiction(
            _state(request).session_factory,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.post(
    "/regulatory/sources/upload",
    response_model=RegulatorySourceDocument,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
async def upload_regulatory_source_route(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    source_type: RegulatorySourceType = Form(default="other"),
    jurisdiction_id: int | None = Form(default=None),
    source_url: str | None = Form(default=None),
    source_date: str | None = Form(default=None),
    retrieved_at: str | None = Form(default=None),
    version: str | None = Form(default=None),
    file_id: int | None = Form(default=None),
    source_status: RegulatorySourceStatus = Form(default="active", alias="status"),
    metadata_json: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceDocument:
    metadata = _parse_optional_json_object(metadata_json, field_name="metadata_json")
    content = await file.read()
    try:
        return regulatory_store.upload_source_document(
            _state(request).session_factory,
            title=title,
            source_type=source_type,
            jurisdiction_id=jurisdiction_id,
            source_url=source_url,
            source_date=source_date,
            retrieved_at=retrieved_at,
            version=version,
            file_id=file_id,
            filename=file.filename or "source.bin",
            content_type=file.content_type,
            content=content,
            status=source_status,
            metadata_json=metadata,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/sources",
    response_model=list[RegulatorySourceDocument],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_sources_route(
    request: Request,
    jurisdiction_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatorySourceDocument]:
    return regulatory_store.list_sources(
        _state(request).session_factory,
        jurisdiction_id=jurisdiction_id,
        limit=limit,
    )


@router.get(
    "/regulatory/sources/{source_id}",
    response_model=RegulatorySourceDocument,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_source_route(
    source_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceDocument:
    record = regulatory_store.get_source(_state(request).session_factory, source_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory source document not found.")
    return record


@router.get(
    "/regulatory/sources/{source_id}/citations",
    response_model=list[RegulatoryCitation],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_source_citations_route(
    source_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryCitation]:
    try:
        return regulatory_store.list_source_citations(_state(request).session_factory, source_id)
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.post(
    "/regulatory/sources/search",
    response_model=RegulatorySourceSearchResult,
    dependencies=[Depends(require_access_context)],
)
def search_regulatory_sources_route(
    payload: RegulatorySourceSearchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceSearchResult:
    try:
        return regulatory_store.search_sources(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.post(
    "/regulatory/surveillance/sources",
    response_model=RegulatorySourceWatcher,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_source_watcher_route(
    payload: RegulatorySourceWatcherCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceWatcher:
    try:
        return surveillance_store.create_watcher(
            _state(request).session_factory,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/surveillance/sources",
    response_model=list[RegulatorySourceWatcher],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_source_watchers_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    jurisdiction_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatorySourceWatcher]:
    return surveillance_store.list_watchers(
        _state(request).session_factory,
        status=status_filter,
        jurisdiction_id=jurisdiction_id,
        limit=limit,
    )


@router.get(
    "/regulatory/surveillance/sources/{watcher_id}",
    response_model=RegulatorySourceWatcher,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_source_watcher_route(
    watcher_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceWatcher:
    record = surveillance_store.get_watcher(_state(request).session_factory, watcher_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory source watcher not found.")
    return record


@router.patch(
    "/regulatory/surveillance/sources/{watcher_id}",
    response_model=RegulatorySourceWatcher,
    dependencies=[Depends(require_access_context)],
)
def update_regulatory_source_watcher_route(
    watcher_id: int,
    payload: RegulatorySourceWatcherUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceWatcher:
    try:
        record = surveillance_store.update_watcher(
            _state(request).session_factory,
            watcher_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory source watcher not found.")
    return record


@router.post(
    "/regulatory/surveillance/runs",
    response_model=RegulatorySurveillanceRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_surveillance_run_route(
    payload: RegulatorySurveillanceRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySurveillanceRun:
    try:
        return surveillance_store.create_surveillance_run(
            _state(request).session_factory,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/surveillance/runs",
    response_model=list[RegulatorySurveillanceRun],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_surveillance_runs_route(
    request: Request,
    watcher_id: int | None = Query(default=None, ge=1),
    source_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatorySurveillanceRun]:
    return surveillance_store.list_runs(
        _state(request).session_factory,
        watcher_id=watcher_id,
        source_id=source_id,
        limit=limit,
    )


@router.get(
    "/regulatory/surveillance/runs/{run_id}",
    response_model=RegulatorySurveillanceRun,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_surveillance_run_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySurveillanceRun:
    record = surveillance_store.get_run(_state(request).session_factory, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory surveillance run not found.")
    return record


@router.get(
    "/regulatory/sources/{source_id}/versions",
    response_model=list[RegulatorySourceVersion],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_source_versions_route(
    source_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatorySourceVersion]:
    try:
        return surveillance_store.list_source_versions(_state(request).session_factory, source_id)
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/sources/{source_id}/versions/{version_id}",
    response_model=RegulatorySourceVersion,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_source_version_route(
    source_id: int,
    version_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceVersion:
    record = surveillance_store.get_source_version(
        _state(request).session_factory, source_id, version_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory source version not found.")
    return record


@router.post(
    "/regulatory/sources/{source_id}/versions/compare",
    response_model=RegulatorySourceVersionCompareResponse,
    dependencies=[Depends(require_access_context)],
)
def compare_regulatory_source_versions_route(
    source_id: int,
    payload: RegulatorySourceVersionCompareRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatorySourceVersionCompareResponse:
    try:
        return surveillance_store.compare_source_versions(
            _state(request).session_factory, source_id, payload
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/changes",
    response_model=list[RegulatoryChangeEvent],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_changes_route(
    request: Request,
    source_id: int | None = Query(default=None, ge=1),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryChangeEvent]:
    return surveillance_store.list_changes(
        _state(request).session_factory,
        source_id=source_id,
        review_status=review_status,
        limit=limit,
    )


@router.get(
    "/regulatory/changes/{change_id}",
    response_model=RegulatoryChangeEvent,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_change_route(
    change_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryChangeEvent:
    record = surveillance_store.get_change(_state(request).session_factory, change_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory change event not found.")
    return record


@router.post(
    "/regulatory/changes/{change_id}/review",
    response_model=RegulatoryChangeEvent,
    dependencies=[Depends(require_access_context)],
)
def review_regulatory_change_route(
    change_id: int,
    payload: RegulatoryChangeReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryChangeEvent:
    try:
        record = surveillance_store.review_change(
            _state(request).session_factory,
            change_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory change event not found.")
    return record


@router.post(
    "/regulatory/changes/{change_id}/impact-assessment",
    response_model=RegulatoryImpactAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_change_impact_assessment_route(
    change_id: int,
    payload: RegulatoryImpactAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryImpactAssessment:
    try:
        return surveillance_store.create_impact_assessment(
            _state(request).session_factory,
            change_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/changes/{change_id}/impact-assessment",
    response_model=list[RegulatoryImpactAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_change_impact_assessments_route(
    change_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryImpactAssessment]:
    try:
        return surveillance_store.list_impact_assessments(
            _state(request).session_factory, change_id
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.post(
    "/regulatory/changes/{change_id}/rule-update-proposal",
    response_model=RegulatoryRuleUpdateProposal,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_rule_update_proposal_route(
    change_id: int,
    payload: RegulatoryRuleUpdateProposalCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleUpdateProposal:
    try:
        return surveillance_store.create_rule_update_proposal(
            _state(request).session_factory,
            change_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/rule-update-proposals",
    response_model=list[RegulatoryRuleUpdateProposal],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_rule_update_proposals_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    rule_set_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryRuleUpdateProposal]:
    return surveillance_store.list_rule_update_proposals(
        _state(request).session_factory,
        status=status_filter,
        rule_set_id=rule_set_id,
        limit=limit,
    )


@router.get(
    "/regulatory/rule-update-proposals/{proposal_id}",
    response_model=RegulatoryRuleUpdateProposal,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_rule_update_proposal_route(
    proposal_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleUpdateProposal:
    record = surveillance_store.get_rule_update_proposal(
        _state(request).session_factory, proposal_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory rule update proposal not found.")
    return record


@router.post(
    "/regulatory/rule-update-proposals/{proposal_id}/approve",
    response_model=RegulatoryRuleUpdateProposal,
    dependencies=[Depends(require_access_context)],
)
def approve_regulatory_rule_update_proposal_route(
    proposal_id: int,
    payload: RegulatoryRuleUpdateProposalReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleUpdateProposal:
    try:
        record = surveillance_store.approve_rule_update_proposal(
            _state(request).session_factory,
            proposal_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory rule update proposal not found.")
    return record


@router.post(
    "/regulatory/rule-update-proposals/{proposal_id}/reject",
    response_model=RegulatoryRuleUpdateProposal,
    dependencies=[Depends(require_access_context)],
)
def reject_regulatory_rule_update_proposal_route(
    proposal_id: int,
    payload: RegulatoryRuleUpdateProposalReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleUpdateProposal:
    try:
        record = surveillance_store.reject_rule_update_proposal(
            _state(request).session_factory,
            proposal_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory rule update proposal not found.")
    return record


@router.get(
    "/regulatory/dossiers/{dossier_id}/change-impact",
    response_model=RegulatoryDossierChangeImpact,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_dossier_change_impact_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryDossierChangeImpact:
    try:
        return surveillance_store.get_dossier_change_impact(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise


@router.get(
    "/regulatory/notifications",
    response_model=list[RegulatoryImpactNotification],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_notifications_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    dossier_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryImpactNotification]:
    return surveillance_store.list_notifications(
        _state(request).session_factory,
        status=status_filter,
        dossier_id=dossier_id,
        limit=limit,
    )


@router.patch(
    "/regulatory/notifications/{notification_id}",
    response_model=RegulatoryImpactNotification,
    dependencies=[Depends(require_access_context)],
)
def update_regulatory_notification_route(
    notification_id: int,
    payload: RegulatoryImpactNotificationUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryImpactNotification:
    try:
        record = surveillance_store.update_notification(
            _state(request).session_factory,
            notification_id,
            payload,
            actor=_surveillance_actor(context),
        )
    except Exception as exc:
        _raise_surveillance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory impact notification not found.")
    return record


@router.post(
    "/knowledge/sources",
    response_model=KnowledgeSource,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_knowledge_source_route(
    payload: KnowledgeSourceCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeSource:
    try:
        return knowledge_store.create_source(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/sources",
    response_model=list[KnowledgeSource],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_sources_route(
    request: Request,
    source_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[KnowledgeSource]:
    return knowledge_store.list_sources(
        _state(request).session_factory,
        source_type=source_type,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/knowledge/sources/{source_id}",
    response_model=KnowledgeSource,
    dependencies=[Depends(require_access_context)],
)
def get_knowledge_source_route(
    source_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeSource:
    record = knowledge_store.get_source(_state(request).session_factory, source_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found.")
    return record


@router.patch(
    "/knowledge/sources/{source_id}",
    response_model=KnowledgeSource,
    dependencies=[Depends(require_access_context)],
)
def update_knowledge_source_route(
    source_id: int,
    payload: KnowledgeSourceUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeSource:
    try:
        record = knowledge_store.update_source(
            _state(request).session_factory,
            source_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge source not found.")
    return record


@router.post(
    "/knowledge/sources/{source_id}/files",
    response_model=KnowledgeSourceFile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
async def upload_knowledge_source_file_route(
    source_id: int,
    request: Request,
    file: UploadFile = File(...),
    file_id: int | None = Form(default=None),
    metadata_json: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeSourceFile:
    metadata = _parse_optional_json_object(metadata_json, field_name="metadata_json")
    content = await file.read()
    try:
        return knowledge_store.add_source_file(
            _state(request).session_factory,
            source_id,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
            file_id=file_id,
            metadata_json=metadata,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/sources/{source_id}/files",
    response_model=list[KnowledgeSourceFile],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_source_files_route(
    source_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[KnowledgeSourceFile]:
    try:
        return knowledge_store.list_source_files(_state(request).session_factory, source_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.post(
    "/knowledge/extractions/run",
    response_model=KnowledgeExtractionRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def run_knowledge_extraction_route(
    payload: KnowledgeExtractionRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeExtractionRun:
    try:
        return knowledge_store.run_extraction(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/extractions/runs",
    response_model=list[KnowledgeExtractionRun],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_extraction_runs_route(
    request: Request,
    source_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[KnowledgeExtractionRun]:
    return knowledge_store.list_extraction_runs(
        _state(request).session_factory,
        source_id=source_id,
        limit=limit,
    )


@router.get(
    "/knowledge/extractions/runs/{run_id}",
    response_model=KnowledgeExtractionRun,
    dependencies=[Depends(require_access_context)],
)
def get_knowledge_extraction_run_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeExtractionRun:
    record = knowledge_store.get_extraction_run(_state(request).session_factory, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge extraction run not found.")
    return record


@router.get(
    "/knowledge/extractions/{run_id}/reactions",
    response_model=list[ExtractedReactionRecord],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_extracted_reactions_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ExtractedReactionRecord]:
    try:
        return knowledge_store.list_reaction_records(_state(request).session_factory, run_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/extractions/{run_id}/analytical",
    response_model=list[ExtractedAnalyticalRecord],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_extracted_analytical_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ExtractedAnalyticalRecord]:
    try:
        return knowledge_store.list_analytical_records(_state(request).session_factory, run_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/extractions/{run_id}/regulatory",
    response_model=list[ExtractedRegulatoryRecord],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_extracted_regulatory_route(
    run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ExtractedRegulatoryRecord]:
    try:
        return knowledge_store.list_regulatory_records(_state(request).session_factory, run_id)
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.post(
    "/knowledge/review-tasks",
    response_model=KnowledgeReviewTask,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_knowledge_review_task_route(
    payload: KnowledgeReviewTaskCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeReviewTask:
    try:
        return knowledge_store.create_review_task(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/review-tasks",
    response_model=list[KnowledgeReviewTask],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_review_tasks_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    record_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[KnowledgeReviewTask]:
    return knowledge_store.list_review_tasks(
        _state(request).session_factory,
        status=status_filter,
        record_type=record_type,
        limit=limit,
    )


@router.patch(
    "/knowledge/review-tasks/{task_id}",
    response_model=KnowledgeReviewTask,
    dependencies=[Depends(require_access_context)],
)
def update_knowledge_review_task_route(
    task_id: int,
    payload: KnowledgeReviewTaskUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeReviewTask:
    try:
        record = knowledge_store.update_review_task(
            _state(request).session_factory,
            task_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Knowledge review task not found.")
    return record


@router.post(
    "/knowledge/records/{record_id}/approve",
    response_model=KnowledgeRecordReviewResult,
    dependencies=[Depends(require_access_context)],
)
def approve_knowledge_record_route(
    record_id: int,
    payload: KnowledgeRecordReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeRecordReviewResult:
    try:
        return knowledge_store.approve_record(
            _state(request).session_factory,
            record_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.post(
    "/knowledge/records/{record_id}/reject",
    response_model=KnowledgeRecordReviewResult,
    dependencies=[Depends(require_access_context)],
)
def reject_knowledge_record_route(
    record_id: int,
    payload: KnowledgeRecordReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeRecordReviewResult:
    try:
        return knowledge_store.reject_record(
            _state(request).session_factory,
            record_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.post(
    "/knowledge/records/{record_id}/link",
    response_model=KnowledgeGraphLink,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_knowledge_record_route(
    record_id: int,
    payload: KnowledgeGraphLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeGraphLink:
    try:
        return knowledge_store.link_record(
            _state(request).session_factory,
            record_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/search",
    response_model=KnowledgeSearchResult,
    dependencies=[Depends(require_access_context)],
)
def search_knowledge_route(
    request: Request,
    query: str | None = Query(default=None, min_length=1, max_length=500),
    record_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    context: AccessContext = Depends(require_access_context),
) -> KnowledgeSearchResult:
    return knowledge_store.search_knowledge(
        _state(request).session_factory,
        query=query,
        record_type=record_type,
        limit=limit,
    )


@router.post(
    "/knowledge/training-dataset-candidates",
    response_model=TrainingDatasetCandidate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_training_dataset_candidate_route(
    payload: TrainingDatasetCandidateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TrainingDatasetCandidate:
    try:
        return knowledge_store.create_training_candidate(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/training-dataset-candidates",
    response_model=list[TrainingDatasetCandidate],
    dependencies=[Depends(require_access_context)],
)
def list_training_dataset_candidates_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[TrainingDatasetCandidate]:
    return knowledge_store.list_training_candidates(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/knowledge/training-dataset-candidates/{candidate_id}",
    response_model=TrainingDatasetCandidate,
    dependencies=[Depends(require_access_context)],
)
def update_training_dataset_candidate_route(
    candidate_id: int,
    payload: TrainingDatasetCandidateUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TrainingDatasetCandidate:
    try:
        record = knowledge_store.update_training_candidate(
            _state(request).session_factory,
            candidate_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Training dataset candidate not found.")
    return record


@router.post(
    "/knowledge/benchmark-dataset-candidates",
    response_model=BenchmarkDatasetCandidate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_benchmark_dataset_candidate_route(
    payload: BenchmarkDatasetCandidateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BenchmarkDatasetCandidate:
    try:
        return knowledge_store.create_benchmark_candidate(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/benchmark-dataset-candidates",
    response_model=list[BenchmarkDatasetCandidate],
    dependencies=[Depends(require_access_context)],
)
def list_benchmark_dataset_candidates_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[BenchmarkDatasetCandidate]:
    return knowledge_store.list_benchmark_candidates(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/knowledge/benchmark-dataset-candidates/{candidate_id}",
    response_model=BenchmarkDatasetCandidate,
    dependencies=[Depends(require_access_context)],
)
def update_benchmark_dataset_candidate_route(
    candidate_id: int,
    payload: BenchmarkDatasetCandidateUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BenchmarkDatasetCandidate:
    try:
        record = knowledge_store.update_benchmark_candidate(
            _state(request).session_factory,
            candidate_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Benchmark dataset candidate not found.")
    return record


@router.post(
    "/knowledge/model-improvement-queue",
    response_model=ModelImprovementQueueItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_model_improvement_queue_item_route(
    payload: ModelImprovementQueueItemCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelImprovementQueueItem:
    try:
        return knowledge_store.create_model_queue_item(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/model-improvement-queue",
    response_model=list[ModelImprovementQueueItem],
    dependencies=[Depends(require_access_context)],
)
def list_model_improvement_queue_items_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelImprovementQueueItem]:
    return knowledge_store.list_model_queue_items(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/knowledge/model-improvement-queue/{item_id}",
    response_model=ModelImprovementQueueItem,
    dependencies=[Depends(require_access_context)],
)
def update_model_improvement_queue_item_route(
    item_id: int,
    payload: ModelImprovementQueueItemUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelImprovementQueueItem:
    try:
        record = knowledge_store.update_model_queue_item(
            _state(request).session_factory,
            item_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Model improvement queue item not found.")
    return record


@router.post(
    "/knowledge/features",
    response_model=FeatureRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_knowledge_feature_record_route(
    payload: FeatureRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeatureRecord:
    try:
        return knowledge_store.create_feature_record(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/features/{record_type}/{record_id}",
    response_model=list[FeatureRecord],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_feature_records_route(
    record_type: str,
    record_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[FeatureRecord]:
    return knowledge_store.list_feature_records(
        _state(request).session_factory, record_type, record_id
    )


@router.post(
    "/knowledge/dataset-versions",
    response_model=DatasetVersion,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_knowledge_dataset_version_route(
    payload: DatasetVersionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DatasetVersion:
    try:
        return knowledge_store.create_dataset_version(
            _state(request).session_factory,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise


@router.get(
    "/knowledge/dataset-versions",
    response_model=list[DatasetVersion],
    dependencies=[Depends(require_access_context)],
)
def list_knowledge_dataset_versions_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[DatasetVersion]:
    return knowledge_store.list_dataset_versions(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/knowledge/dataset-versions/{dataset_version_id}",
    response_model=DatasetVersion,
    dependencies=[Depends(require_access_context)],
)
def get_knowledge_dataset_version_route(
    dataset_version_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DatasetVersion:
    record = knowledge_store.get_dataset_version(
        _state(request).session_factory, dataset_version_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return record


@router.patch(
    "/knowledge/dataset-versions/{dataset_version_id}",
    response_model=DatasetVersion,
    dependencies=[Depends(require_access_context)],
)
def update_knowledge_dataset_version_route(
    dataset_version_id: int,
    payload: DatasetVersionUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DatasetVersion:
    try:
        record = knowledge_store.update_dataset_version(
            _state(request).session_factory,
            dataset_version_id,
            payload,
            actor=_knowledge_actor(context),
        )
    except Exception as exc:
        _raise_knowledge_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset version not found.")
    return record


@router.get(
    "/ml/tasks",
    response_model=list[MLTaskDefinition],
    dependencies=[Depends(require_access_context)],
)
def list_ml_tasks_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[MLTaskDefinition]:
    return ml_store.list_tasks(_state(request).session_factory, status=status_filter, limit=limit)


@router.post(
    "/ml/tasks",
    response_model=MLTaskDefinition,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_task_route(
    payload: MLTaskDefinitionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLTaskDefinition:
    try:
        return ml_store.create_task(
            _state(request).session_factory, payload, actor=_ml_actor(context)
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.post(
    "/ml/feature-pipelines",
    response_model=FeaturePipeline,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_feature_pipeline_route(
    payload: FeaturePipelineCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeaturePipeline:
    try:
        return ml_store.create_feature_pipeline(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/feature-pipelines",
    response_model=list[FeaturePipeline],
    dependencies=[Depends(require_access_context)],
)
def list_ml_feature_pipelines_route(
    request: Request,
    task_key: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[FeaturePipeline]:
    return ml_store.list_feature_pipelines(
        _state(request).session_factory,
        task_key=task_key,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ml/feature-pipelines/{pipeline_id}",
    response_model=FeaturePipeline,
    dependencies=[Depends(require_access_context)],
)
def get_ml_feature_pipeline_route(
    pipeline_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> FeaturePipeline:
    record = ml_store.get_feature_pipeline(_state(request).session_factory, pipeline_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Feature pipeline not found.")
    return record


@router.post(
    "/ml/training-runs",
    response_model=MLTrainingRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_training_run_route(
    payload: MLTrainingRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLTrainingRunResponse:
    try:
        return ml_store.create_training_run(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/training-runs",
    response_model=list[MLTrainingRun],
    dependencies=[Depends(require_access_context)],
)
def list_ml_training_runs_route(
    request: Request,
    task_key: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[MLTrainingRun]:
    return ml_store.list_training_runs(
        _state(request).session_factory,
        task_key=task_key,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ml/training-runs/{training_run_id}",
    response_model=MLTrainingRunResponse,
    dependencies=[Depends(require_access_context)],
)
def get_ml_training_run_route(
    training_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLTrainingRunResponse:
    record = ml_store.get_training_run(_state(request).session_factory, training_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return record


@router.post(
    "/ml/training-runs/{training_run_id}/cancel",
    response_model=MLTrainingRunResponse,
    dependencies=[Depends(require_access_context)],
)
def cancel_ml_training_run_route(
    training_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLTrainingRunResponse:
    try:
        record = ml_store.cancel_training_run(
            _state(request).session_factory,
            training_run_id,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Training run not found.")
    return record


@router.post(
    "/ml/evaluation-runs",
    response_model=MLEvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_evaluation_run_route(
    payload: MLEvaluationRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLEvaluationRunResponse:
    try:
        return ml_store.create_evaluation_run(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/evaluation-runs",
    response_model=list[MLEvaluationRun],
    dependencies=[Depends(require_access_context)],
)
def list_ml_evaluation_runs_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[MLEvaluationRun]:
    return ml_store.list_evaluation_runs(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ml/evaluation-runs/{evaluation_run_id}",
    response_model=MLEvaluationRunResponse,
    dependencies=[Depends(require_access_context)],
)
def get_ml_evaluation_run_route(
    evaluation_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLEvaluationRunResponse:
    record = ml_store.get_evaluation_run(_state(request).session_factory, evaluation_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return record


@router.get(
    "/ml/model-artifacts",
    response_model=list[ModelArtifact],
    dependencies=[Depends(require_access_context)],
)
def list_ml_model_artifacts_route(
    request: Request,
    task_key: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelArtifact]:
    return ml_store.list_model_artifacts(
        _state(request).session_factory,
        task_key=task_key,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ml/model-artifacts/{model_artifact_id}",
    response_model=ModelArtifact,
    dependencies=[Depends(require_access_context)],
)
def get_ml_model_artifact_route(
    model_artifact_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelArtifact:
    record = ml_store.get_model_artifact(_state(request).session_factory, model_artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model artifact not found.")
    return record


@router.post(
    "/ml/model-cards",
    response_model=ModelCard,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_model_card_route(
    payload: ModelCardCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelCard:
    try:
        return ml_store.create_model_card(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/model-cards",
    response_model=list[ModelCard],
    dependencies=[Depends(require_access_context)],
)
def list_ml_model_cards_route(
    request: Request,
    model_artifact_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelCard]:
    return ml_store.list_model_cards(
        _state(request).session_factory,
        model_artifact_id=model_artifact_id,
        limit=limit,
    )


@router.get(
    "/ml/model-cards/{model_card_id}",
    response_model=ModelCard,
    dependencies=[Depends(require_access_context)],
)
def get_ml_model_card_route(
    model_card_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelCard:
    record = ml_store.get_model_card(_state(request).session_factory, model_card_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model card not found.")
    return record


@router.patch(
    "/ml/model-cards/{model_card_id}",
    response_model=ModelCard,
    dependencies=[Depends(require_access_context)],
)
def update_ml_model_card_route(
    model_card_id: int,
    payload: ModelCardUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelCard:
    try:
        record = ml_store.update_model_card(
            _state(request).session_factory,
            model_card_id,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Model card not found.")
    return record


@router.post(
    "/ml/calibration-assessments",
    response_model=CalibrationAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_calibration_assessment_route(
    payload: CalibrationAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CalibrationAssessment:
    try:
        return ml_store.create_calibration_assessment(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/calibration-assessments",
    response_model=list[CalibrationAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_ml_calibration_assessments_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[CalibrationAssessment]:
    return ml_store.list_calibration_assessments(_state(request).session_factory, limit=limit)


@router.get(
    "/ml/calibration-assessments/{assessment_id}",
    response_model=CalibrationAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_ml_calibration_assessment_route(
    assessment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CalibrationAssessment:
    record = ml_store.get_calibration_assessment(_state(request).session_factory, assessment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Calibration assessment not found.")
    return record


@router.post(
    "/ml/error-analysis",
    response_model=ErrorAnalysisSlice,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_error_analysis_route(
    payload: ErrorAnalysisSliceCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ErrorAnalysisSlice:
    try:
        return ml_store.create_error_analysis(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/error-analysis",
    response_model=list[ErrorAnalysisSlice],
    dependencies=[Depends(require_access_context)],
)
def list_ml_error_analysis_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ErrorAnalysisSlice]:
    return ml_store.list_error_analysis(_state(request).session_factory, limit=limit)


@router.get(
    "/ml/error-analysis/{error_analysis_id}",
    response_model=ErrorAnalysisSlice,
    dependencies=[Depends(require_access_context)],
)
def get_ml_error_analysis_route(
    error_analysis_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ErrorAnalysisSlice:
    record = ml_store.get_error_analysis(_state(request).session_factory, error_analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Error analysis slice not found.")
    return record


@router.post(
    "/ml/ood-assessments",
    response_model=OutOfDomainAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_ood_assessment_route(
    payload: OutOfDomainAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OutOfDomainAssessment:
    try:
        return ml_store.create_ood_assessment(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/ood-assessments",
    response_model=list[OutOfDomainAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_ml_ood_assessments_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[OutOfDomainAssessment]:
    return ml_store.list_ood_assessments(_state(request).session_factory, limit=limit)


@router.get(
    "/ml/ood-assessments/{ood_assessment_id}",
    response_model=OutOfDomainAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_ml_ood_assessment_route(
    ood_assessment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OutOfDomainAssessment:
    record = ml_store.get_ood_assessment(_state(request).session_factory, ood_assessment_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Out-of-domain assessment not found.")
    return record


@router.post(
    "/ml/deployment-candidates",
    response_model=DeploymentCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_deployment_candidate_route(
    payload: DeploymentCandidateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeploymentCandidateResponse:
    try:
        return ml_store.create_deployment_candidate(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/deployment-candidates",
    response_model=list[DeploymentCandidate],
    dependencies=[Depends(require_access_context)],
)
def list_ml_deployment_candidates_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[DeploymentCandidate]:
    return ml_store.list_deployment_candidates(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ml/deployment-candidates/{candidate_id}",
    response_model=DeploymentCandidateResponse,
    dependencies=[Depends(require_access_context)],
)
def get_ml_deployment_candidate_route(
    candidate_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeploymentCandidateResponse:
    record = ml_store.get_deployment_candidate(_state(request).session_factory, candidate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Deployment candidate not found.")
    return record


@router.post(
    "/ml/deployment-candidates/{candidate_id}/approve",
    response_model=DeploymentCandidateResponse,
    dependencies=[Depends(require_access_context)],
)
def approve_ml_deployment_candidate_route(
    candidate_id: int,
    payload: DeploymentCandidateApprovalRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeploymentCandidateResponse:
    try:
        record = ml_store.approve_deployment_candidate(
            _state(request).session_factory,
            candidate_id,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Deployment candidate not found.")
    return record


@router.post(
    "/ml/deployment-candidates/{candidate_id}/reject",
    response_model=DeploymentCandidateResponse,
    dependencies=[Depends(require_access_context)],
)
def reject_ml_deployment_candidate_route(
    candidate_id: int,
    payload: DeploymentCandidateRejectRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DeploymentCandidateResponse:
    try:
        record = ml_store.reject_deployment_candidate(
            _state(request).session_factory,
            candidate_id,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Deployment candidate not found.")
    return record


@router.get(
    "/ml/model-health",
    response_model=MLModelHealthSummary,
    dependencies=[Depends(require_access_context)],
)
def get_ml_model_health_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MLModelHealthSummary:
    return ml_store.model_health(_state(request).session_factory)


@router.post(
    "/ml/prediction-service-configs",
    response_model=PredictionServiceConfig,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ml_prediction_service_config_route(
    payload: PredictionServiceConfigCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> PredictionServiceConfig:
    try:
        return ml_store.create_prediction_service_config(
            _state(request).session_factory,
            payload,
            actor=_ml_actor(context),
        )
    except Exception as exc:
        _raise_ml_http_error(exc)
        raise


@router.get(
    "/ml/prediction-service-configs",
    response_model=list[PredictionServiceConfig],
    dependencies=[Depends(require_access_context)],
)
def list_ml_prediction_service_configs_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[PredictionServiceConfig]:
    return ml_store.list_prediction_service_configs(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/ai/evidence-queue",
    response_model=list[AIEvidenceItem],
    dependencies=[Depends(require_access_context)],
)
def list_ai_evidence_queue_route(
    request: Request,
    module: AIEvidenceModule | None = Query(default=None),
    status_filter: AIEvidenceStatus | None = Query(default=None, alias="status"),
    tenant_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[AIEvidenceItem]:
    try:
        return ai_evidence_store.list_evidence_queue(
            _state(request).session_factory,
            module=module,
            status=status_filter,
            tenant_id=tenant_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_ai_evidence_http_error(exc)
        raise


@router.patch(
    "/ai/evidence-queue/{evidence_id}/review",
    response_model=AIEvidenceReviewResponse,
    dependencies=[Depends(require_access_context)],
)
def review_ai_evidence_queue_item_route(
    payload: AIEvidenceReviewRequest,
    request: Request,
    evidence_id: int = ApiPath(..., ge=1),
    tenant_id: int | None = Query(default=None, ge=1),
    context: AccessContext = Depends(require_access_context),
) -> AIEvidenceReviewResponse:
    try:
        return ai_evidence_store.review_evidence_item(
            _state(request).session_factory,
            evidence_id,
            payload,
            actor=_ai_evidence_actor(context),
            correlation_id=_request_correlation_id(request),
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_ai_evidence_http_error(exc)
        raise


@router.get(
    "/ai/services",
    response_model=list[AIServiceRegistry],
    dependencies=[Depends(require_access_context)],
)
def list_ai_services_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[AIServiceRegistry]:
    return ai_store.list_services(
        _state(request).session_factory, status=status_filter, limit=limit
    )


@router.post(
    "/ai/services",
    response_model=AIServiceRegistry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_service_route(
    payload: AIServiceRegistryCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AIServiceRegistry:
    try:
        return ai_store.create_service(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/services/{service_id}",
    response_model=AIServiceRegistry,
    dependencies=[Depends(require_access_context)],
)
def get_ai_service_route(
    service_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AIServiceRegistry:
    record = ai_store.get_service(_state(request).session_factory, service_id)
    if record is None:
        raise HTTPException(status_code=404, detail="AI service not found.")
    return record


@router.patch(
    "/ai/services/{service_id}",
    response_model=AIServiceRegistry,
    dependencies=[Depends(require_access_context)],
)
def update_ai_service_route(
    service_id: int,
    payload: AIServiceRegistryUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AIServiceRegistry:
    try:
        record = ai_store.update_service(
            _state(request).session_factory,
            service_id,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="AI service not found.")
    return record


@router.post(
    "/ai/predictions",
    response_model=PredictionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_prediction_route(
    payload: PredictionRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> PredictionResponse:
    try:
        return ai_store.create_prediction(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/predictions",
    response_model=list[PredictionRun],
    dependencies=[Depends(require_access_context)],
)
def list_ai_predictions_route(
    request: Request,
    service_key: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[PredictionRun]:
    return ai_store.list_predictions(
        _state(request).session_factory,
        service_key=service_key,
        limit=limit,
    )


@router.get(
    "/ai/predictions/{prediction_id}",
    response_model=PredictionResponse,
    dependencies=[Depends(require_access_context)],
)
def get_ai_prediction_route(
    prediction_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> PredictionResponse:
    record = ai_store.get_prediction(_state(request).session_factory, prediction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prediction run not found.")
    return record


@router.post(
    "/ai/predictions/{prediction_id}/feedback",
    response_model=PredictionFeedbackResponse,
    dependencies=[Depends(require_access_context)],
)
def create_ai_prediction_feedback_route(
    prediction_id: int,
    payload: PredictionFeedbackCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> PredictionFeedbackResponse:
    try:
        return ai_store.create_feedback(
            _state(request).session_factory,
            prediction_id,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.post(
    "/ai/predictions/{prediction_id}/review",
    response_model=PredictionFeedbackResponse,
    dependencies=[Depends(require_access_context)],
)
def review_ai_prediction_route(
    prediction_id: int,
    payload: PredictionReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> PredictionFeedbackResponse:
    try:
        return ai_store.review_prediction(
            _state(request).session_factory,
            prediction_id,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.post(
    "/ai/routing/decide",
    response_model=ModelRoutingDecision,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def decide_ai_routing_route(
    payload: ModelRoutingDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelRoutingDecision:
    try:
        return ai_store.decide_routing(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/routing/decisions",
    response_model=list[ModelRoutingDecision],
    dependencies=[Depends(require_access_context)],
)
def list_ai_routing_decisions_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelRoutingDecision]:
    return ai_store.list_routing_decisions(_state(request).session_factory, limit=limit)


@router.get(
    "/ai/routing/decisions/{decision_id}",
    response_model=ModelRoutingDecision,
    dependencies=[Depends(require_access_context)],
)
def get_ai_routing_decision_route(
    decision_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelRoutingDecision:
    record = ai_store.get_routing_decision(_state(request).session_factory, decision_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model routing decision not found.")
    return record


@router.post(
    "/ai/explanations",
    response_model=InferenceExplanation,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_explanation_route(
    payload: InferenceExplanationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InferenceExplanation:
    try:
        return ai_store.create_explanation(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/explanations/{explanation_id}",
    response_model=InferenceExplanation,
    dependencies=[Depends(require_access_context)],
)
def get_ai_explanation_route(
    explanation_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> InferenceExplanation:
    record = ai_store.get_explanation(_state(request).session_factory, explanation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inference explanation not found.")
    return record


@router.post(
    "/ai/active-learning/candidates",
    response_model=ActiveLearningCandidate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_active_learning_candidate_route(
    payload: ActiveLearningCandidateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ActiveLearningCandidate:
    try:
        return ai_store.create_active_learning_candidate(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/active-learning/candidates",
    response_model=list[ActiveLearningCandidate],
    dependencies=[Depends(require_access_context)],
)
def list_ai_active_learning_candidates_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ActiveLearningCandidate]:
    return ai_store.list_active_learning_candidates(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/ai/active-learning/candidates/{candidate_id}",
    response_model=ActiveLearningCandidate,
    dependencies=[Depends(require_access_context)],
)
def update_ai_active_learning_candidate_route(
    candidate_id: int,
    payload: ActiveLearningCandidateUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ActiveLearningCandidate:
    try:
        record = ai_store.update_active_learning_candidate(
            _state(request).session_factory,
            candidate_id,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Active-learning candidate not found.")
    return record


@router.post(
    "/ai/shadow-evaluations",
    response_model=ShadowEvaluationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_shadow_evaluation_route(
    payload: ShadowEvaluationRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ShadowEvaluationRun:
    try:
        return ai_store.create_shadow_evaluation(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/shadow-evaluations",
    response_model=list[ShadowEvaluationRun],
    dependencies=[Depends(require_access_context)],
)
def list_ai_shadow_evaluations_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ShadowEvaluationRun]:
    return ai_store.list_shadow_evaluations(_state(request).session_factory, limit=limit)


@router.get(
    "/ai/shadow-evaluations/{shadow_run_id}",
    response_model=ShadowEvaluationRun,
    dependencies=[Depends(require_access_context)],
)
def get_ai_shadow_evaluation_route(
    shadow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ShadowEvaluationRun:
    record = ai_store.get_shadow_evaluation(_state(request).session_factory, shadow_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Shadow evaluation run not found.")
    return record


@router.post(
    "/ai/canary-deployments",
    response_model=CanaryDeploymentRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_canary_deployment_route(
    payload: CanaryDeploymentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CanaryDeploymentRecord:
    try:
        return ai_store.create_canary_deployment(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/canary-deployments",
    response_model=list[CanaryDeploymentRecord],
    dependencies=[Depends(require_access_context)],
)
def list_ai_canary_deployments_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[CanaryDeploymentRecord]:
    return ai_store.list_canary_deployments(_state(request).session_factory, limit=limit)


@router.get(
    "/ai/canary-deployments/{canary_id}",
    response_model=CanaryDeploymentRecord,
    dependencies=[Depends(require_access_context)],
)
def get_ai_canary_deployment_route(
    canary_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CanaryDeploymentRecord:
    record = ai_store.get_canary_deployment(_state(request).session_factory, canary_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Canary deployment record not found.")
    return record


@router.post(
    "/ai/canary-deployments/{canary_id}/approve",
    response_model=CanaryDeploymentRecord,
    dependencies=[Depends(require_access_context)],
)
def approve_ai_canary_deployment_route(
    canary_id: int,
    payload: CanaryReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CanaryDeploymentRecord:
    try:
        record = ai_store.review_canary_deployment(
            _state(request).session_factory,
            canary_id,
            payload,
            actor=_ai_actor(context),
            approve=True,
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Canary deployment record not found.")
    return record


@router.post(
    "/ai/canary-deployments/{canary_id}/reject",
    response_model=CanaryDeploymentRecord,
    dependencies=[Depends(require_access_context)],
)
def reject_ai_canary_deployment_route(
    canary_id: int,
    payload: CanaryReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CanaryDeploymentRecord:
    try:
        record = ai_store.review_canary_deployment(
            _state(request).session_factory,
            canary_id,
            payload,
            actor=_ai_actor(context),
            approve=False,
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Canary deployment record not found.")
    return record


@router.get(
    "/ai/model-monitoring",
    response_model=AIModelMonitoringSummary,
    dependencies=[Depends(require_access_context)],
)
def get_ai_model_monitoring_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AIModelMonitoringSummary:
    return ai_store.model_monitoring_summary(_state(request).session_factory)


@router.post(
    "/ai/model-monitoring/events",
    response_model=ModelMonitoringEvent,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ai_model_monitoring_event_route(
    payload: ModelMonitoringEventCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelMonitoringEvent:
    try:
        return ai_store.create_monitoring_event(
            _state(request).session_factory,
            payload,
            actor=_ai_actor(context),
        )
    except Exception as exc:
        _raise_ai_http_error(exc)
        raise


@router.get(
    "/ai/model-monitoring/events",
    response_model=list[ModelMonitoringEvent],
    dependencies=[Depends(require_access_context)],
)
def list_ai_model_monitoring_events_route(
    request: Request,
    service_key: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelMonitoringEvent]:
    return ai_store.list_monitoring_events(
        _state(request).session_factory,
        service_key=service_key,
        limit=limit,
    )


@router.get(
    "/ai/prediction-audit",
    response_model=list[PredictionAuditEntry],
    dependencies=[Depends(require_access_context)],
)
def list_ai_prediction_audit_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[PredictionAuditEntry]:
    return ai_store.prediction_audit(_state(request).session_factory, limit=limit)


@router.get(
    "/mobile/config",
    response_model=MobileConfigResponse,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_config_route(
    request: Request,
    device_session_id: int | None = Query(default=None, ge=1),
    context: AccessContext = Depends(require_access_context),
) -> MobileConfigResponse:
    try:
        return mobile_store.get_config(
            _state(request).session_factory,
            actor=_mobile_actor(context),
            device_session_id=device_session_id,
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.patch(
    "/mobile/config",
    response_model=MobileConfigResponse,
    dependencies=[Depends(require_access_context)],
)
def update_mobile_config_route(
    payload: MobileViewPreferencePatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileConfigResponse:
    try:
        return mobile_store.update_config(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.post(
    "/mobile/device-sessions",
    response_model=MobileDeviceSession,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_mobile_device_session_route(
    payload: MobileDeviceSessionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileDeviceSession:
    try:
        return mobile_store.create_device_session(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/device-sessions",
    response_model=list[MobileDeviceSession],
    dependencies=[Depends(require_access_context)],
)
def list_mobile_device_sessions_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[MobileDeviceSession]:
    return mobile_store.list_device_sessions(
        _state(request).session_factory,
        actor=_mobile_actor(context),
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/mobile/device-sessions/{device_session_id}",
    response_model=MobileDeviceSession,
    dependencies=[Depends(require_access_context)],
)
def update_mobile_device_session_route(
    device_session_id: int,
    payload: MobileDeviceSessionPatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileDeviceSession:
    try:
        return mobile_store.update_device_session(
            _state(request).session_factory,
            device_session_id,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/dashboard",
    response_model=MobileDashboardResponse,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_dashboard_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileDashboardResponse:
    return mobile_store.dashboard_summary(_state(request).session_factory)


@router.get(
    "/mobile/command-center",
    response_model=MobileCommandCenterResponse,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_command_center_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileCommandCenterResponse:
    return mobile_store.command_center_summary(_state(request).session_factory)


@router.get(
    "/mobile/spectracheck/sessions/{session_id}/summary",
    response_model=MobileResourceSummary,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_spectracheck_session_summary_route(
    session_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileResourceSummary:
    try:
        return mobile_store.spectracheck_session_summary(
            _state(request).session_factory,
            session_id,
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/regulatory/dossiers/{dossier_id}/summary",
    response_model=MobileResourceSummary,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_regulatory_dossier_summary_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileResourceSummary:
    try:
        return mobile_store.regulatory_dossier_summary(
            _state(request).session_factory,
            dossier_id,
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/reactions/{reaction_project_id}/summary",
    response_model=MobileResourceSummary,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_reaction_project_summary_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileResourceSummary:
    try:
        return mobile_store.reaction_project_summary(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/action-queue",
    response_model=MobileActionQueueResponse,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_action_queue_route(
    request: Request,
    device_session_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> MobileActionQueueResponse:
    return mobile_store.action_queue(
        _state(request).session_factory,
        actor=_mobile_actor(context),
        device_session_id=device_session_id,
        limit=limit,
    )


@router.post(
    "/mobile/action-drafts",
    response_model=MobileActionDraft,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_mobile_action_draft_route(
    payload: MobileActionDraftCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileActionDraft:
    try:
        return mobile_store.create_action_draft(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/action-drafts",
    response_model=list[MobileActionDraft],
    dependencies=[Depends(require_access_context)],
)
def list_mobile_action_drafts_route(
    request: Request,
    device_session_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[MobileActionDraft]:
    return mobile_store.list_action_drafts(
        _state(request).session_factory,
        actor=_mobile_actor(context),
        device_session_id=device_session_id,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/mobile/action-drafts/{draft_id}",
    response_model=MobileActionDraft,
    dependencies=[Depends(require_access_context)],
)
def update_mobile_action_draft_route(
    draft_id: int,
    payload: MobileActionDraftPatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileActionDraft:
    try:
        return mobile_store.update_action_draft(
            _state(request).session_factory,
            draft_id,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.post(
    "/mobile/sync",
    response_model=MobileSyncResponse,
    dependencies=[Depends(require_access_context)],
)
def sync_mobile_action_drafts_route(
    payload: MobileSyncRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileSyncResponse:
    try:
        return mobile_store.sync_action_drafts(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.post(
    "/mobile/push-subscriptions",
    response_model=MobilePushSubscription,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_mobile_push_subscription_route(
    payload: MobilePushSubscriptionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobilePushSubscription:
    try:
        return mobile_store.create_push_subscription(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.post(
    "/mobile/notifications",
    response_model=MobileNotification,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_mobile_notification_route(
    payload: MobileNotificationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileNotification:
    try:
        return mobile_store.create_notification(
            _state(request).session_factory,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/notifications",
    response_model=list[MobileNotification],
    dependencies=[Depends(require_access_context)],
)
def list_mobile_notifications_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[MobileNotification]:
    return mobile_store.list_notifications(
        _state(request).session_factory,
        actor=_mobile_actor(context),
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/mobile/notifications/{notification_id}",
    response_model=MobileNotification,
    dependencies=[Depends(require_access_context)],
)
def update_mobile_notification_route(
    notification_id: int,
    payload: MobileNotificationPatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileNotification:
    try:
        return mobile_store.update_notification(
            _state(request).session_factory,
            notification_id,
            payload,
            actor=_mobile_actor(context),
        )
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/reports/{report_id}/preview",
    response_model=MobileReportPreview,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_report_preview_route(
    report_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileReportPreview:
    try:
        return mobile_store.report_preview(_state(request).session_factory, report_id)
    except Exception as exc:
        _raise_mobile_http_error(exc)
        raise


@router.get(
    "/mobile/jobs/summary",
    response_model=MobileJobsSummary,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_jobs_summary_route(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    context: AccessContext = Depends(require_access_context),
) -> MobileJobsSummary:
    return mobile_store.jobs_summary(_state(request).session_factory, limit=limit)


@router.get(
    "/mobile/offline-safe-summary",
    response_model=MobileOfflineSafeSummary,
    dependencies=[Depends(require_access_context)],
)
def get_mobile_offline_safe_summary_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MobileOfflineSafeSummary:
    return mobile_store.offline_safe_summary(
        _state(request).session_factory,
        actor=_mobile_actor(context),
    )


@router.get(
    "/product/programs",
    response_model=list[ProductProgramRegistry],
    dependencies=[Depends(require_access_context)],
)
def list_product_programs_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ProductProgramRegistry]:
    return product_store.list_programs(_state(request).session_factory)


@router.patch(
    "/product/programs/order",
    response_model=list[ProductProgramRegistry],
    dependencies=[Depends(require_access_context)],
)
def update_product_program_order_route(
    payload: ProductProgramOrderPatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ProductProgramRegistry]:
    try:
        return product_store.update_program_order(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/product/module-priority",
    response_model=list[ModulePriorityMap],
    dependencies=[Depends(require_access_context)],
)
def list_product_module_priority_route(
    request: Request,
    context_filter: str | None = Query(default=None, alias="context"),
    context: AccessContext = Depends(require_access_context),
) -> list[ModulePriorityMap]:
    return product_store.list_module_priority(
        _state(request).session_factory,
        context=context_filter,
    )


@router.patch(
    "/product/module-priority",
    response_model=ModulePriorityMap,
    dependencies=[Depends(require_access_context)],
)
def update_product_module_priority_route(
    payload: ModulePriorityMapPatch,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModulePriorityMap:
    try:
        return product_store.update_module_priority(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/product/cross-module/workflow-templates",
    response_model=list[CrossModuleWorkflowTemplate],
    dependencies=[Depends(require_access_context)],
)
def list_cross_module_workflow_templates_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[CrossModuleWorkflowTemplate]:
    return product_store.list_workflow_templates(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/product/cross-module/workflow-templates",
    response_model=CrossModuleWorkflowTemplate,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_cross_module_workflow_template_route(
    payload: CrossModuleWorkflowTemplateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleWorkflowTemplate:
    try:
        return product_store.create_workflow_template(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.post(
    "/bridges/spectroscopy-to-regulatory",
    response_model=SpectroscopyToRegulatoryBridge,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_spectroscopy_to_regulatory_bridge_route(
    payload: SpectroscopyToRegulatoryBridgeCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectroscopyToRegulatoryBridge:
    try:
        return product_store.create_spectroscopy_to_regulatory_bridge(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/bridges/spectroscopy-to-regulatory",
    response_model=list[SpectroscopyToRegulatoryBridge],
    dependencies=[Depends(require_access_context)],
)
def list_spectroscopy_to_regulatory_bridges_route(
    request: Request,
    dossier_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[SpectroscopyToRegulatoryBridge]:
    return product_store.list_spectroscopy_to_regulatory_bridges(
        _state(request).session_factory,
        dossier_id=dossier_id,
        limit=limit,
    )


@router.get(
    "/bridges/spectroscopy-to-regulatory/{bridge_id}",
    response_model=SpectroscopyToRegulatoryBridge,
    dependencies=[Depends(require_access_context)],
)
def get_spectroscopy_to_regulatory_bridge_route(
    bridge_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectroscopyToRegulatoryBridge:
    record = product_store.get_spectroscopy_to_regulatory_bridge(
        _state(request).session_factory, bridge_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Spectroscopy-to-regulatory bridge not found.")
    return record


@router.post(
    "/bridges/spectroscopy-to-regulatory/{bridge_id}/review",
    response_model=SpectroscopyToRegulatoryBridge,
    dependencies=[Depends(require_access_context)],
)
def review_spectroscopy_to_regulatory_bridge_route(
    bridge_id: int,
    payload: CrossModuleBridgeReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectroscopyToRegulatoryBridge:
    try:
        record = product_store.review_spectroscopy_to_regulatory_bridge(
            _state(request).session_factory,
            bridge_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Spectroscopy-to-regulatory bridge not found.")
    return record


@router.post(
    "/bridges/regulatory-to-reaction",
    response_model=RegulatoryToReactionBridge,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_to_reaction_bridge_route(
    payload: RegulatoryToReactionBridgeCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryToReactionBridge:
    try:
        return product_store.create_regulatory_to_reaction_bridge(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/bridges/regulatory-to-reaction",
    response_model=list[RegulatoryToReactionBridge],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_to_reaction_bridges_route(
    request: Request,
    reaction_project_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryToReactionBridge]:
    return product_store.list_regulatory_to_reaction_bridges(
        _state(request).session_factory,
        reaction_project_id=reaction_project_id,
        limit=limit,
    )


@router.get(
    "/bridges/regulatory-to-reaction/{bridge_id}",
    response_model=RegulatoryToReactionBridge,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_to_reaction_bridge_route(
    bridge_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryToReactionBridge:
    record = product_store.get_regulatory_to_reaction_bridge(
        _state(request).session_factory, bridge_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory-to-reaction bridge not found.")
    return record


@router.post(
    "/bridges/regulatory-to-reaction/{bridge_id}/review",
    response_model=RegulatoryToReactionBridge,
    dependencies=[Depends(require_access_context)],
)
def review_regulatory_to_reaction_bridge_route(
    bridge_id: int,
    payload: CrossModuleBridgeReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryToReactionBridge:
    try:
        record = product_store.review_regulatory_to_reaction_bridge(
            _state(request).session_factory,
            bridge_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory-to-reaction bridge not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/regulatory-constraints",
    response_model=RegulatoryConstraintSet,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_regulatory_constraint_route(
    reaction_project_id: int,
    payload: RegulatoryConstraintSetCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryConstraintSet:
    try:
        return product_store.create_regulatory_constraint(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/regulatory-constraints",
    response_model=list[RegulatoryConstraintSet],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_regulatory_constraints_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryConstraintSet]:
    try:
        return product_store.list_regulatory_constraints(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.patch(
    "/reaction-regulatory-constraints/{constraint_id}",
    response_model=RegulatoryConstraintSet,
    dependencies=[Depends(require_access_context)],
)
def update_reaction_regulatory_constraint_route(
    constraint_id: int,
    payload: RegulatoryConstraintSetUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryConstraintSet:
    try:
        record = product_store.update_regulatory_constraint(
            _state(request).session_factory,
            constraint_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory constraint set not found.")
    return record


@router.post(
    "/reaction-projects/{reaction_project_id}/compliance-objective",
    response_model=ComplianceDrivenOptimizationObjective,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_reaction_compliance_objective_route(
    reaction_project_id: int,
    payload: ComplianceDrivenOptimizationObjectiveCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ComplianceDrivenOptimizationObjective:
    try:
        return product_store.create_compliance_objective(
            _state(request).session_factory,
            reaction_project_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/reaction-projects/{reaction_project_id}/compliance-objective",
    response_model=list[ComplianceDrivenOptimizationObjective],
    dependencies=[Depends(require_access_context)],
)
def list_reaction_compliance_objectives_route(
    reaction_project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ComplianceDrivenOptimizationObjective]:
    try:
        return product_store.list_compliance_objectives(
            _state(request).session_factory,
            reaction_project_id,
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/ctd-module3-bundle",
    response_model=CTDModule3ReportBundle,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_ctd_module3_bundle_route(
    dossier_id: int,
    payload: CTDModule3ReportBundleCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CTDModule3ReportBundle:
    try:
        return product_store.create_ctd_module3_bundle(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/ctd-module3-bundle",
    response_model=list[CTDModule3ReportBundle],
    dependencies=[Depends(require_access_context)],
)
def list_ctd_module3_bundles_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CTDModule3ReportBundle]:
    try:
        return product_store.list_ctd_module3_bundles(
            _state(request).session_factory,
            dossier_id,
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/ctd-module3-bundles/{bundle_id}",
    response_model=CTDModule3ReportBundle,
    dependencies=[Depends(require_access_context)],
)
def get_ctd_module3_bundle_route(
    bundle_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CTDModule3ReportBundle:
    record = product_store.get_ctd_module3_bundle(_state(request).session_factory, bundle_id)
    if record is None:
        raise HTTPException(status_code=404, detail="CTD Module 3 bundle not found.")
    return record


@router.post(
    "/cross-module/action-items",
    response_model=CrossModuleActionItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_cross_module_action_item_route(
    payload: CrossModuleActionItemCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleActionItem:
    try:
        return product_store.create_cross_module_action_item(
            _state(request).session_factory,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise


@router.get(
    "/cross-module/action-items",
    response_model=list[CrossModuleActionItem],
    dependencies=[Depends(require_access_context)],
)
def list_cross_module_action_items_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[CrossModuleActionItem]:
    return product_store.list_cross_module_action_items(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/cross-module/action-items/{action_item_id}",
    response_model=CrossModuleActionItem,
    dependencies=[Depends(require_access_context)],
)
def update_cross_module_action_item_route(
    action_item_id: int,
    payload: CrossModuleActionItemUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleActionItem:
    try:
        record = product_store.update_cross_module_action_item(
            _state(request).session_factory,
            action_item_id,
            payload,
            actor=_product_actor(context),
        )
    except Exception as exc:
        _raise_product_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Cross-module action item not found.")
    return record


@router.get(
    "/cross-module/command-center",
    response_model=CrossModuleCommandCenterSummary,
    dependencies=[Depends(require_access_context)],
)
def get_cross_module_command_center_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleCommandCenterSummary:
    return product_store.command_center_summary(_state(request).session_factory)


@router.get(
    "/cross-module/command-center/project/{project_id}",
    response_model=CrossModuleCommandCenterSummary,
    dependencies=[Depends(require_access_context)],
)
def get_project_cross_module_command_center_route(
    project_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleCommandCenterSummary:
    return product_store.command_center_summary(
        _state(request).session_factory,
        scope="project",
        scope_id=project_id,
    )


@router.get(
    "/cross-module/command-center/compound/{compound_id}",
    response_model=CrossModuleCommandCenterSummary,
    dependencies=[Depends(require_access_context)],
)
def get_compound_cross_module_command_center_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleCommandCenterSummary:
    return product_store.command_center_summary(
        _state(request).session_factory,
        scope="compound",
        scope_id=compound_id,
    )


@router.get(
    "/cross-module/command-center/batch/{batch_id}",
    response_model=CrossModuleCommandCenterSummary,
    dependencies=[Depends(require_access_context)],
)
def get_batch_cross_module_command_center_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CrossModuleCommandCenterSummary:
    return product_store.command_center_summary(
        _state(request).session_factory,
        scope="batch",
        scope_id=batch_id,
    )


@router.post(
    "/regulatory/dossiers",
    response_model=RegulatoryDossier,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_dossier_route(
    payload: RegulatoryDossierCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryDossier:
    try:
        return regulatory_store.create_dossier(
            _state(request).session_factory,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers",
    response_model=list[RegulatoryDossier],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_dossiers_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryDossier]:
    return regulatory_store.list_dossiers(_state(request).session_factory, limit=limit)


@router.get(
    "/regulatory/dossiers/{dossier_id}",
    response_model=RegulatoryDossier,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_dossier_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryDossier:
    record = regulatory_store.get_dossier(_state(request).session_factory, dossier_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory dossier not found.")
    return record


@router.patch(
    "/regulatory/dossiers/{dossier_id}",
    response_model=RegulatoryDossier,
    dependencies=[Depends(require_access_context)],
)
def patch_regulatory_dossier_route(
    dossier_id: int,
    payload: RegulatoryDossierUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryDossier:
    try:
        record = regulatory_store.patch_dossier(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory dossier not found.")
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/requirements",
    response_model=RegulatoryRequirement,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_requirement_route(
    dossier_id: int,
    payload: RegulatoryRequirementCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRequirement:
    try:
        return regulatory_store.create_requirement(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/requirements",
    response_model=list[RegulatoryRequirement],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_requirements_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryRequirement]:
    try:
        return regulatory_store.list_requirements(_state(request).session_factory, dossier_id)
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.patch(
    "/regulatory/requirements/{requirement_id}",
    response_model=RegulatoryRequirement,
    dependencies=[Depends(require_access_context)],
)
def patch_regulatory_requirement_route(
    requirement_id: int,
    payload: RegulatoryRequirementUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRequirement:
    try:
        record = regulatory_store.patch_requirement(
            _state(request).session_factory,
            requirement_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory requirement not found.")
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/evidence-links",
    response_model=RegulatoryEvidenceLink,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_evidence_link_route(
    dossier_id: int,
    payload: RegulatoryEvidenceLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryEvidenceLink:
    try:
        return regulatory_store.create_evidence_link(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/evidence-links",
    response_model=list[RegulatoryEvidenceLink],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_evidence_links_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryEvidenceLink]:
    try:
        return regulatory_store.list_evidence_links(_state(request).session_factory, dossier_id)
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/query",
    response_model=RegulatoryQuery,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def answer_regulatory_dossier_query_route(
    dossier_id: int,
    payload: RegulatoryQueryCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryQuery:
    try:
        return regulatory_store.answer_query(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/queries/{query_id}",
    response_model=RegulatoryQuery,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_query_route(
    query_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryQuery:
    record = regulatory_store.get_query(_state(request).session_factory, query_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory query not found.")
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/risk-assessment",
    response_model=RegulatoryRiskAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_risk_assessment_route(
    dossier_id: int,
    request: Request,
    payload: RegulatoryRiskAssessmentRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRiskAssessment:
    try:
        return regulatory_store.create_risk_assessment(
            _state(request).session_factory,
            dossier_id,
            payload or RegulatoryRiskAssessmentRequest(),
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/risk-assessment",
    response_model=RegulatoryRiskAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_risk_assessment_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRiskAssessment:
    try:
        record = regulatory_store.get_latest_risk_assessment(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory risk assessment not found.")
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/review",
    response_model=RegulatoryReviewDecision,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_review_decision_route(
    dossier_id: int,
    payload: RegulatoryReviewDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryReviewDecision:
    try:
        return regulatory_store.create_review_decision(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/review",
    response_model=list[RegulatoryReviewDecision],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_review_decisions_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryReviewDecision]:
    try:
        return regulatory_store.list_review_decisions(_state(request).session_factory, dossier_id)
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/readiness-report",
    response_model=RegulatoryReadinessReport,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_readiness_report_route(
    dossier_id: int,
    request: Request,
    payload: RegulatoryReadinessReportRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryReadinessReport:
    try:
        return regulatory_store.create_readiness_report(
            _state(request).session_factory,
            dossier_id,
            payload or RegulatoryReadinessReportRequest(),
            actor=_regulatory_actor(context),
        )
    except Exception as exc:
        _raise_regulatory_http_error(exc)
        raise


@router.get(
    "/regulatory/readiness-reports/{report_id}",
    response_model=RegulatoryReadinessReport,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_readiness_report_route(
    report_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryReadinessReport:
    record = regulatory_store.get_readiness_report(_state(request).session_factory, report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory readiness report not found.")
    return record


@router.get(
    "/regulatory/rule-sets",
    response_model=list[RegulatoryRuleSet],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_rule_sets_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    jurisdiction_id: int | None = Query(default=None, ge=1),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryRuleSet]:
    return compliance_store.list_rule_sets(
        _state(request).session_factory,
        status=status_filter,
        jurisdiction_id=jurisdiction_id,
    )


@router.post(
    "/regulatory/rule-sets",
    response_model=RegulatoryRuleSet,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_rule_set_route(
    payload: RegulatoryRuleSetCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleSet:
    try:
        return compliance_store.create_rule_set(
            _state(request).session_factory,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/rule-sets/{rule_set_id}",
    response_model=RegulatoryRuleSet,
    dependencies=[Depends(require_access_context)],
)
def get_regulatory_rule_set_route(
    rule_set_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryRuleSet:
    record = compliance_store.get_rule_set(_state(request).session_factory, rule_set_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory rule set not found.")
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/batch-assessment",
    response_model=BatchRegulatoryAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_batch_assessment_route(
    dossier_id: int,
    payload: BatchRegulatoryAssessmentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BatchRegulatoryAssessment:
    try:
        return compliance_store.create_batch_assessment(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/batch-assessment",
    response_model=list[BatchRegulatoryAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_batch_assessments_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[BatchRegulatoryAssessment]:
    try:
        return compliance_store.list_batch_assessments(_state(request).session_factory, dossier_id)
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/impurity-risk-register",
    response_model=ImpurityRiskRegister,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_impurity_risk_register_route(
    dossier_id: int,
    payload: ImpurityRiskRegisterCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ImpurityRiskRegister:
    try:
        return compliance_store.create_impurity_risk_register(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/impurity-risk-register",
    response_model=list[ImpurityRiskRegister],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_impurity_risk_register_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ImpurityRiskRegister]:
    try:
        return compliance_store.list_impurity_risk_register(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/residual-solvent-assessment",
    response_model=BatchRegulatoryAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_residual_solvent_assessment_route(
    dossier_id: int,
    payload: ResidualSolventAssessmentRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BatchRegulatoryAssessment:
    try:
        return compliance_store.create_residual_solvent_assessment(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/residual-solvent-assessment",
    response_model=list[BatchRegulatoryAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_residual_solvent_assessments_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[BatchRegulatoryAssessment]:
    try:
        return compliance_store.list_residual_solvent_assessments(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/nitrosamine-watch",
    response_model=BatchRegulatoryAssessment,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_nitrosamine_watch_route(
    dossier_id: int,
    payload: NitrosamineWatchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BatchRegulatoryAssessment:
    try:
        return compliance_store.create_nitrosamine_watch(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/nitrosamine-watch",
    response_model=list[BatchRegulatoryAssessment],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_nitrosamine_watch_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[BatchRegulatoryAssessment]:
    try:
        return compliance_store.list_nitrosamine_watch(_state(request).session_factory, dossier_id)
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/qnmr-compliance",
    response_model=QNMRComplianceProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_qnmr_compliance_route(
    dossier_id: int,
    payload: QNMRComplianceProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QNMRComplianceProfile:
    try:
        return compliance_store.create_qnmr_compliance_profile(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/qnmr-compliance",
    response_model=list[QNMRComplianceProfile],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_qnmr_compliance_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[QNMRComplianceProfile]:
    try:
        return compliance_store.list_qnmr_compliance_profiles(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/method-validation-profile",
    response_model=AnalyticalMethodValidationProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_method_validation_profile_route(
    dossier_id: int,
    payload: AnalyticalMethodValidationProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AnalyticalMethodValidationProfile:
    try:
        return compliance_store.create_method_validation_profile(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/method-validation-profile",
    response_model=list[AnalyticalMethodValidationProfile],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_method_validation_profile_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[AnalyticalMethodValidationProfile]:
    try:
        return compliance_store.list_method_validation_profiles(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/ai-governance-record",
    response_model=AIGovernanceRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_ai_governance_record_route(
    dossier_id: int,
    payload: AIGovernanceRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AIGovernanceRecord:
    try:
        return compliance_store.create_ai_governance_record(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/ai-governance-record",
    response_model=list[AIGovernanceRecord],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_ai_governance_record_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[AIGovernanceRecord]:
    try:
        return compliance_store.list_ai_governance_records(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/dossiers/{dossier_id}/jurisdictional-map",
    response_model=JurisdictionalRequirementMap,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_jurisdictional_map_route(
    dossier_id: int,
    payload: JurisdictionalRequirementMapCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> JurisdictionalRequirementMap:
    try:
        return compliance_store.create_jurisdictional_map(
            _state(request).session_factory,
            dossier_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/dossiers/{dossier_id}/jurisdictional-map",
    response_model=list[JurisdictionalRequirementMap],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_jurisdictional_map_route(
    dossier_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[JurisdictionalRequirementMap]:
    try:
        return compliance_store.list_jurisdictional_maps(
            _state(request).session_factory, dossier_id
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.post(
    "/regulatory/action-items",
    response_model=RegulatoryActionItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_regulatory_action_item_route(
    payload: RegulatoryActionItemCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryActionItem:
    try:
        return compliance_store.create_action_item(
            _state(request).session_factory,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise


@router.get(
    "/regulatory/action-items",
    response_model=list[RegulatoryActionItem],
    dependencies=[Depends(require_access_context)],
)
def list_regulatory_action_items_route(
    request: Request,
    dossier_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[RegulatoryActionItem]:
    return compliance_store.list_action_items(
        _state(request).session_factory,
        dossier_id=dossier_id,
        status=status_filter,
        limit=limit,
    )


@router.patch(
    "/regulatory/action-items/{action_item_id}",
    response_model=RegulatoryActionItem,
    dependencies=[Depends(require_access_context)],
)
def update_regulatory_action_item_route(
    action_item_id: int,
    payload: RegulatoryActionItemUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> RegulatoryActionItem:
    try:
        record = compliance_store.update_action_item(
            _state(request).session_factory,
            action_item_id,
            payload,
            actor=_compliance_actor(context),
        )
    except Exception as exc:
        _raise_compliance_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Regulatory action item not found.")
    return record


@router.post(
    "/compound-registry/compounds",
    response_model=CompoundEntity,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_compound_route(
    payload: CompoundEntityCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundEntity:
    try:
        record = compound_store.create_compound(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.compound.create",
        message="Compound registry linked compound created.",
        entity_type="compound",
        entity_id=record.id,
        metadata={"status": record.status, "compound_type": record.compound_type},
    )
    return record


@router.get(
    "/compound-registry/compounds",
    response_model=list[CompoundEntity],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_compounds_route(
    request: Request,
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    compound_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundEntity]:
    return compound_store.list_compounds(
        _state(request).session_factory,
        q=q,
        status=status_filter,
        compound_type=compound_type,
        limit=limit,
    )


@router.get(
    "/compound-registry/compounds/{compound_id}",
    response_model=CompoundEntity,
    dependencies=[Depends(require_access_context)],
)
def get_compound_registry_compound_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundEntity:
    record = compound_store.get_compound(_state(request).session_factory, compound_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Compound not found.")
    return record


@router.patch(
    "/compound-registry/compounds/{compound_id}",
    response_model=CompoundEntity,
    dependencies=[Depends(require_access_context)],
)
def update_compound_registry_compound_route(
    compound_id: int,
    payload: CompoundEntityUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundEntity:
    try:
        record = compound_store.update_compound(
            _state(request).session_factory, compound_id, payload
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Compound not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.compound.update",
        message="Compound registry linked compound updated.",
        entity_type="compound",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/compound-registry/compounds/{compound_id}/structures",
    response_model=CompoundStructureRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_structure_route(
    compound_id: int,
    payload: CompoundStructureRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundStructureRecord:
    try:
        record = compound_store.create_structure_record(
            _state(request).session_factory, compound_id, payload
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.structure.create",
        message="Compound structure metadata record created.",
        entity_type="compound",
        entity_id=compound_id,
        metadata={"structure_record_id": record.id, "validation_status": record.validation_status},
    )
    return record


@router.get(
    "/compound-registry/compounds/{compound_id}/structures",
    response_model=list[CompoundStructureRecord],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_structures_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundStructureRecord]:
    try:
        return compound_store.list_structure_records(_state(request).session_factory, compound_id)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/compound-registry/compounds/{compound_id}/aliases",
    response_model=CompoundAlias,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_alias_route(
    compound_id: int,
    payload: CompoundAliasCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundAlias:
    try:
        record = compound_store.create_alias(_state(request).session_factory, compound_id, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.alias.create",
        message="Compound registry alias created.",
        entity_type="compound",
        entity_id=compound_id,
        metadata={"alias_id": record.id, "alias_type": record.alias_type},
    )
    return record


@router.get(
    "/compound-registry/compounds/{compound_id}/aliases",
    response_model=list[CompoundAlias],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_aliases_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundAlias]:
    try:
        return compound_store.list_aliases(_state(request).session_factory, compound_id)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/compound-registry/compounds/{compound_id}/relationships",
    response_model=CompoundRelationship,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_relationship_route(
    compound_id: int,
    payload: CompoundRelationshipCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRelationship:
    try:
        record = compound_store.create_relationship(
            _state(request).session_factory, compound_id, payload
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.relationship.create",
        message="Compound registry candidate relationship created.",
        entity_type="compound",
        entity_id=compound_id,
        metadata={
            "relationship_id": record.id,
            "target_compound_id": record.target_compound_id,
            "relationship_type": record.relationship_type,
            "confidence_label": record.confidence_label,
        },
    )
    return record


@router.get(
    "/compound-registry/compounds/{compound_id}/relationships",
    response_model=list[CompoundRelationship],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_relationships_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundRelationship]:
    try:
        return compound_store.list_relationships(_state(request).session_factory, compound_id)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/compound-registry/batches",
    response_model=CompoundBatch,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_batch_route(
    payload: CompoundBatchCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundBatch:
    try:
        record = compound_store.create_batch(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.batch.create",
        message="Compound registry batch created.",
        entity_type="compound_batch",
        entity_id=record.id,
        metadata={"compound_id": record.compound_id, "status": record.status},
    )
    return record


@router.get(
    "/compound-registry/batches",
    response_model=list[CompoundBatch],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_batches_route(
    request: Request,
    compound_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundBatch]:
    return compound_store.list_batches(
        _state(request).session_factory,
        compound_id=compound_id,
        status=status_filter,
        limit=limit,
    )


@router.get(
    "/compound-registry/batches/{batch_id}",
    response_model=CompoundBatch,
    dependencies=[Depends(require_access_context)],
)
def get_compound_registry_batch_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundBatch:
    record = compound_store.get_batch(_state(request).session_factory, batch_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Compound batch not found.")
    return record


@router.patch(
    "/compound-registry/batches/{batch_id}",
    response_model=CompoundBatch,
    dependencies=[Depends(require_access_context)],
)
def update_compound_registry_batch_route(
    batch_id: int,
    payload: CompoundBatchUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundBatch:
    try:
        record = compound_store.update_batch(_state(request).session_factory, batch_id, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Compound batch not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.batch.update",
        message="Compound registry batch updated.",
        entity_type="compound_batch",
        entity_id=record.id,
        metadata={"updated_fields": sorted(payload.model_fields_set)},
    )
    return record


@router.post(
    "/compound-registry/batches/{batch_id}/aliquots",
    response_model=SampleAliquot,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_aliquot_route(
    batch_id: int,
    payload: SampleAliquotCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SampleAliquot:
    try:
        record = compound_store.create_aliquot(_state(request).session_factory, batch_id, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.aliquot.create",
        message="Compound registry sample aliquot created.",
        entity_type="compound_batch",
        entity_id=batch_id,
        metadata={"aliquot_id": record.id, "status": record.status},
    )
    return record


@router.get(
    "/compound-registry/batches/{batch_id}/aliquots",
    response_model=list[SampleAliquot],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_aliquots_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[SampleAliquot]:
    try:
        return compound_store.list_aliquots(_state(request).session_factory, batch_id)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/compound-registry/evidence-links",
    response_model=CompoundEvidenceLink,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_evidence_link_route(
    payload: CompoundEvidenceLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundEvidenceLink:
    try:
        record = compound_store.create_evidence_link(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.evidence_link.create",
        message="Compound registry evidence link created.",
        entity_type="compound_evidence_link",
        entity_id=record.id,
        metadata={
            "compound_id": record.compound_id,
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
        },
    )
    return record


@router.get(
    "/compound-registry/compounds/{compound_id}/evidence-links",
    response_model=list[CompoundEvidenceLink],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_compound_evidence_links_route(
    compound_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundEvidenceLink]:
    try:
        return compound_store.list_compound_evidence_links(
            _state(request).session_factory, compound_id
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.get(
    "/compound-registry/batches/{batch_id}/evidence-links",
    response_model=list[CompoundEvidenceLink],
    dependencies=[Depends(require_access_context)],
)
def list_compound_registry_batch_evidence_links_route(
    batch_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[CompoundEvidenceLink]:
    try:
        return compound_store.list_batch_evidence_links(_state(request).session_factory, batch_id)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/compound-registry/graph/edges",
    response_model=ScientificKnowledgeGraphEdge,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_compound_registry_graph_edge_route(
    payload: ScientificKnowledgeGraphEdgeCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ScientificKnowledgeGraphEdge:
    try:
        record = compound_store.create_graph_edge(_state(request).session_factory, payload)
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.graph_edge.create",
        message="Scientific knowledge graph edge created.",
        entity_type="scientific_knowledge_graph_edge",
        entity_id=record.id,
        metadata={
            "relation_type": record.relation_type,
            "confidence_label": record.confidence_label,
        },
    )
    return record


@router.get(
    "/compound-registry/graph",
    response_model=ScientificKnowledgeGraph,
    dependencies=[Depends(require_access_context)],
)
def get_compound_registry_graph_route(
    request: Request,
    compound_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> ScientificKnowledgeGraph:
    try:
        return compound_store.get_graph(
            _state(request).session_factory, compound_id=compound_id, limit=limit
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise


@router.post(
    "/spectracheck/sessions/{session_id}/link-compound",
    response_model=CompoundRegistryLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_spectracheck_session_compound_route(
    session_id: int,
    payload: CompoundRegistryLinkRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRegistryLinkResponse:
    try:
        record = compound_store.link_resource_to_compound(
            _state(request).session_factory,
            resource_type="spectracheck_session",
            resource_id=session_id,
            payload=payload,
            default_title="SpectraCheck session linked compound",
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.link.spectracheck_session",
        message="SpectraCheck session linked compound created.",
        entity_type="compound_evidence_link",
        entity_id=record.evidence_link.id,
        metadata={"session_id": session_id, "compound_id": payload.compound_id},
    )
    return record


@router.post(
    "/reaction-experiments/{experiment_id}/link-compound",
    response_model=CompoundRegistryLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_reaction_experiment_compound_route(
    experiment_id: int,
    payload: CompoundRegistryLinkRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRegistryLinkResponse:
    try:
        record = compound_store.link_resource_to_compound(
            _state(request).session_factory,
            resource_type="reaction_experiment",
            resource_id=experiment_id,
            payload=payload,
            default_title="Reaction experiment linked compound",
            default_relation_type="product_of",
            compound_as_source=True,
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.link.reaction_experiment",
        message="Reaction experiment linked compound created.",
        entity_type="compound_evidence_link",
        entity_id=record.evidence_link.id,
        metadata={
            "experiment_id": experiment_id,
            "compound_id": payload.compound_id,
            "relation_type": record.graph_edge.relation_type,
        },
    )
    return record


@router.post(
    "/regulatory/dossiers/{dossier_id}/link-compound",
    response_model=CompoundRegistryLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_regulatory_dossier_compound_route(
    dossier_id: int,
    payload: CompoundRegistryLinkRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRegistryLinkResponse:
    try:
        record = compound_store.link_resource_to_compound(
            _state(request).session_factory,
            resource_type="regulatory_dossier",
            resource_id=dossier_id,
            payload=payload,
            default_title="Regulatory dossier linked compound",
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.link.regulatory_dossier",
        message="Regulatory dossier linked compound created.",
        entity_type="compound_evidence_link",
        entity_id=record.evidence_link.id,
        metadata={"dossier_id": dossier_id, "compound_id": payload.compound_id},
    )
    return record


@router.post(
    "/reports/{report_id}/link-compound",
    response_model=CompoundRegistryLinkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_report_compound_route(
    report_id: int,
    payload: CompoundRegistryLinkRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRegistryLinkResponse:
    try:
        record = compound_store.link_resource_to_compound(
            _state(request).session_factory,
            resource_type="report",
            resource_id=report_id,
            payload=payload,
            default_title="Report linked compound",
        )
    except Exception as exc:
        _raise_compound_registry_http_error(exc)
        raise
    _audit_from_context(
        request,
        context=context,
        event_type="compound_registry.link.report",
        message="Report linked compound created.",
        entity_type="compound_evidence_link",
        entity_id=record.evidence_link.id,
        metadata={"report_id": report_id, "compound_id": payload.compound_id},
    )
    return record


@router.post(
    "/compound-registry/search",
    response_model=CompoundRegistrySearchResult,
    dependencies=[Depends(require_access_context)],
)
def search_compound_registry_route(
    payload: CompoundRegistrySearchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CompoundRegistrySearchResult:
    return compound_store.search_compounds(_state(request).session_factory, payload)


@router.post(
    "/spectracheck/sessions/{session_id}/files",
    response_model=SessionFileLinkRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def link_file_to_spectracheck_session_route(
    session_id: int,
    payload: SessionFileLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SessionFileLinkRecord:
    try:
        return orch_store.link_file_to_session(
            _state(request).session_factory,
            session_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except orch_store.OrchestrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/files",
    response_model=list[SessionFileLinkRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_session_files_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[SessionFileLinkRecord]:
    try:
        return orch_store.list_session_file_links(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/spectracheck/sessions/{session_id}/files/{file_id}",
    response_model=MessageResponse,
    dependencies=[Depends(require_access_context)],
)
def unlink_file_from_spectracheck_session_route(
    session_id: int,
    file_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MessageResponse:
    deleted = orch_store.delete_session_file_link(
        _state(request).session_factory,
        session_id,
        file_id,
        owner_scope_id=_user_scope_for_context(context),
        actor_id=context.user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Session file link not found.")
    return MessageResponse(detail="Managed file unlinked from SpectraCheck session.")


@router.post(
    "/jobs",
    response_model=AnalysisJobRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_analysis_job_route(
    payload: AnalysisJobCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AnalysisJobRecord:
    try:
        record = orch_store.create_analysis_job(
            _state(request).session_factory,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            storage_root=_orchestration_storage_root(request),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except orch_store.OrchestrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="analysis_job.create",
        message="Analysis orchestration job created.",
        entity_type="analysis_job",
        entity_id=record.id,
        metadata={
            "job_type": record.job_type,
            "status": record.status,
            "session_id": record.session_id,
        },
    )
    return record


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=AnalysisJobRecord,
    dependencies=[Depends(require_access_context)],
)
def cancel_analysis_job_route(
    job_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AnalysisJobRecord:
    record = orch_store.cancel_analysis_job(
        _state(request).session_factory,
        job_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="analysis_job.cancel",
        message="Analysis orchestration job cancellation requested.",
        entity_type="analysis_job",
        entity_id=record.id,
        metadata={"status": record.status},
    )
    return record


@router.get(
    "/jobs/{job_id}/events",
    response_model=list[JobEventRecord],
    dependencies=[Depends(require_access_context)],
)
def list_analysis_job_events_route(
    job_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[JobEventRecord]:
    events = orch_store.list_job_events(
        _state(request).session_factory,
        job_id,
        owner_scope_id=_user_scope_for_context(context),
        limit=limit,
    )
    if events is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return events


@router.get(
    "/spectracheck/sessions/{session_id}/jobs",
    response_model=list[AnalysisJobRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_session_jobs_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[AnalysisJobRecord]:
    try:
        return orch_store.list_session_jobs(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/spectracheck/sessions/{session_id}/artifacts",
    response_model=list[ArtifactRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_session_artifacts_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ArtifactRecord]:
    try:
        return orch_store.list_session_artifacts(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/artifacts/{artifact_id}",
    response_model=ArtifactRecord,
    dependencies=[Depends(require_access_context)],
)
def get_artifact_route(
    artifact_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ArtifactRecord:
    record = orch_store.get_artifact_record(_state(request).session_factory, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return record


@router.get("/artifacts/{artifact_id}/download", dependencies=[Depends(require_access_context)])
def download_artifact_route(
    artifact_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    try:
        download = orch_store.get_artifact_download(
            _state(request).session_factory,
            artifact_id,
            storage_root=_orchestration_storage_root(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if download is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    record, content, content_type = download
    filename = (
        f"artifact-{record.id}.json"
        if content_type == "application/json"
        else f"artifact-{record.id}"
    )
    return StreamingResponse(
        iter([content]),
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/visualization/artifacts/{artifact_id}",
    response_model=VisualizationArtifact,
    dependencies=[Depends(require_access_context)],
)
def get_visualization_artifact_route(
    artifact_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> VisualizationArtifact:
    record = orch_store.get_artifact_record(_state(request).session_factory, artifact_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return normalize_artifact_record(record)


@router.post(
    "/visualization/normalize",
    response_model=VisualizationArtifact,
    dependencies=[Depends(require_access_context)],
)
def normalize_visualization_artifact_route(
    payload: VisualizationNormalizeRequest,
    context: AccessContext = Depends(require_access_context),
) -> VisualizationArtifact:
    return normalize_visualization_request(payload)


@router.post(
    "/organizations",
    response_model=OrganizationRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_organization_route(
    payload: OrganizationCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OrganizationRecord:
    try:
        return collab_store.create_organization(
            _state(request).session_factory,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/organizations",
    response_model=list[OrganizationRecord],
    dependencies=[Depends(require_access_context)],
)
def list_organizations_route(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[OrganizationRecord]:
    return collab_store.list_organizations(
        _state(request).session_factory,
        actor=_collaboration_actor(request, context),
        limit=limit,
    )


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationRecord,
    dependencies=[Depends(require_access_context)],
)
def get_organization_route(
    organization_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> OrganizationRecord:
    try:
        record = collab_store.get_organization(
            _state(request).session_factory,
            organization_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return record


@router.post(
    "/organizations/{organization_id}/members",
    response_model=TeamMemberRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def add_organization_member_route(
    organization_id: int,
    payload: TeamMemberCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TeamMemberRecord:
    try:
        return collab_store.add_team_member(
            _state(request).session_factory,
            organization_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/organizations/{organization_id}/members",
    response_model=list[TeamMemberRecord],
    dependencies=[Depends(require_access_context)],
)
def list_organization_members_route(
    organization_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[TeamMemberRecord]:
    try:
        return collab_store.list_team_members(
            _state(request).session_factory,
            organization_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.patch(
    "/organizations/{organization_id}/members/{member_id}",
    response_model=TeamMemberRecord,
    dependencies=[Depends(require_access_context)],
)
def update_organization_member_route(
    organization_id: int,
    member_id: int,
    payload: TeamMemberUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> TeamMemberRecord:
    try:
        record = collab_store.update_team_member(
            _state(request).session_factory,
            organization_id,
            member_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Team member not found.")
    return record


@router.post(
    "/projects/{project_id}/permissions",
    response_model=ProjectPermissionRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def add_project_permission_route(
    project_id: int,
    payload: ProjectPermissionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ProjectPermissionRecord:
    try:
        return collab_store.add_project_permission(
            _state(request).session_factory,
            project_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/projects/{project_id}/permissions",
    response_model=list[ProjectPermissionRecord],
    dependencies=[Depends(require_access_context)],
)
def list_project_permissions_route(
    project_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ProjectPermissionRecord]:
    try:
        return collab_store.list_project_permissions(
            _state(request).session_factory,
            project_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.patch(
    "/projects/{project_id}/permissions/{permission_id}",
    response_model=ProjectPermissionRecord,
    dependencies=[Depends(require_access_context)],
)
def update_project_permission_route(
    project_id: int,
    permission_id: int,
    payload: ProjectPermissionUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ProjectPermissionRecord:
    try:
        record = collab_store.update_project_permission(
            _state(request).session_factory,
            project_id,
            permission_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Project permission not found.")
    return record


@router.delete(
    "/projects/{project_id}/permissions/{permission_id}",
    response_model=ProjectPermissionRecord,
    dependencies=[Depends(require_access_context)],
)
def delete_project_permission_route(
    project_id: int,
    permission_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ProjectPermissionRecord:
    try:
        record = collab_store.delete_project_permission(
            _state(request).session_factory,
            project_id,
            permission_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Project permission not found.")
    return record


@router.post(
    "/spectracheck/sessions/{session_id}/reviewers",
    response_model=SessionReviewerRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def add_session_reviewer_route(
    session_id: int,
    payload: SessionReviewerCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SessionReviewerRecord:
    try:
        return collab_store.add_session_reviewer(
            _state(request).session_factory,
            session_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/spectracheck/sessions/{session_id}/reviewers",
    response_model=list[SessionReviewerRecord],
    dependencies=[Depends(require_access_context)],
)
def list_session_reviewers_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[SessionReviewerRecord]:
    try:
        return collab_store.list_session_reviewers(
            _state(request).session_factory,
            session_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.patch(
    "/spectracheck/sessions/{session_id}/reviewers/{reviewer_id}",
    response_model=SessionReviewerRecord,
    dependencies=[Depends(require_access_context)],
)
def update_session_reviewer_route(
    session_id: int,
    reviewer_id: int,
    payload: SessionReviewerUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SessionReviewerRecord:
    try:
        record = collab_store.update_session_reviewer(
            _state(request).session_factory,
            session_id,
            reviewer_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Session reviewer not found.")
    return record


@router.delete(
    "/spectracheck/sessions/{session_id}/reviewers/{reviewer_id}",
    response_model=SessionReviewerRecord,
    dependencies=[Depends(require_access_context)],
)
def remove_session_reviewer_route(
    session_id: int,
    reviewer_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SessionReviewerRecord:
    try:
        record = collab_store.remove_session_reviewer(
            _state(request).session_factory,
            session_id,
            reviewer_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Session reviewer not found.")
    return record


@router.post(
    "/spectracheck/sessions/{session_id}/comments",
    response_model=EvidenceCommentRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_session_comment_route(
    session_id: int,
    payload: EvidenceCommentCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> EvidenceCommentRecord:
    try:
        return collab_store.create_comment(
            _state(request).session_factory,
            session_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/spectracheck/sessions/{session_id}/comments",
    response_model=list[EvidenceCommentRecord],
    dependencies=[Depends(require_access_context)],
)
def list_session_comments_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[EvidenceCommentRecord]:
    try:
        return collab_store.list_comments(
            _state(request).session_factory,
            session_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.patch(
    "/spectracheck/sessions/{session_id}/comments/{comment_id}",
    response_model=EvidenceCommentRecord,
    dependencies=[Depends(require_access_context)],
)
def update_session_comment_route(
    session_id: int,
    comment_id: int,
    payload: EvidenceCommentUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> EvidenceCommentRecord:
    try:
        record = collab_store.update_comment(
            _state(request).session_factory,
            session_id,
            comment_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return record


@router.delete(
    "/spectracheck/sessions/{session_id}/comments/{comment_id}",
    response_model=EvidenceCommentRecord,
    dependencies=[Depends(require_access_context)],
)
def delete_session_comment_route(
    session_id: int,
    comment_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> EvidenceCommentRecord:
    try:
        record = collab_store.delete_comment(
            _state(request).session_factory,
            session_id,
            comment_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return record


@router.post(
    "/spectracheck/sessions/{session_id}/review-tasks",
    response_model=ReviewTaskRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_review_task_route(
    session_id: int,
    payload: ReviewTaskCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReviewTaskRecord:
    try:
        return collab_store.create_review_task(
            _state(request).session_factory,
            session_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/spectracheck/sessions/{session_id}/review-tasks",
    response_model=list[ReviewTaskRecord],
    dependencies=[Depends(require_access_context)],
)
def list_review_tasks_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ReviewTaskRecord]:
    try:
        return collab_store.list_review_tasks(
            _state(request).session_factory,
            session_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.patch(
    "/spectracheck/sessions/{session_id}/review-tasks/{task_id}",
    response_model=ReviewTaskRecord,
    dependencies=[Depends(require_access_context)],
)
def update_review_task_route(
    session_id: int,
    task_id: int,
    payload: ReviewTaskUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReviewTaskRecord:
    try:
        record = collab_store.update_review_task(
            _state(request).session_factory,
            session_id,
            task_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Review task not found.")
    return record


@router.post(
    "/spectracheck/sessions/{session_id}/approvals",
    response_model=ApprovalRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_session_approval_route(
    session_id: int,
    payload: ApprovalRecordCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ApprovalRecord:
    try:
        return collab_store.create_approval(
            _state(request).session_factory,
            session_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/spectracheck/sessions/{session_id}/approvals",
    response_model=list[ApprovalRecord],
    dependencies=[Depends(require_access_context)],
)
def list_session_approvals_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ApprovalRecord]:
    try:
        return collab_store.list_approvals(
            _state(request).session_factory,
            session_id,
            actor=_collaboration_actor(request, context),
            limit=limit,
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.post(
    "/reports/{report_id}/lock",
    response_model=ReportLock,
    dependencies=[Depends(require_access_context)],
)
def lock_report_route(
    report_id: int,
    request: Request,
    payload: ReportLockRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> ReportLock:
    try:
        return collab_store.lock_report(
            _state(request).session_factory,
            report_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.post(
    "/reports/{report_id}/unlock",
    response_model=ReportLock,
    dependencies=[Depends(require_access_context)],
)
def unlock_report_route(
    report_id: int,
    request: Request,
    payload: ReportLockRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> ReportLock:
    try:
        return collab_store.unlock_report(
            _state(request).session_factory,
            report_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.post(
    "/reports/{report_id}/release",
    response_model=ReportLock,
    dependencies=[Depends(require_access_context)],
)
def release_report_route(
    report_id: int,
    request: Request,
    payload: ReportReleaseRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> ReportLock:
    try:
        return collab_store.release_report(
            _state(request).session_factory,
            report_id,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get(
    "/reports/{report_id}/lock",
    response_model=ReportLock,
    dependencies=[Depends(require_access_context)],
)
def get_report_lock_route(
    report_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ReportLock:
    try:
        record = collab_store.get_report_lock(
            _state(request).session_factory,
            report_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Report lock not found.")
    return record


@router.post(
    "/share-links",
    response_model=SecureShareLinkRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_share_link_route(
    payload: SecureShareLinkCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SecureShareLinkRecord:
    try:
        return collab_store.create_share_link(
            _state(request).session_factory,
            payload,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise


@router.get("/share-links/{token}", response_model=SecureShareLinkRecord)
def get_share_link_route(token: str, request: Request) -> SecureShareLinkRecord:
    record = collab_store.get_share_link(_state(request).session_factory, token)
    if record is None:
        raise HTTPException(status_code=404, detail="Share link not found.")
    return record


@router.post(
    "/share-links/{share_id}/revoke",
    response_model=SecureShareLinkRecord,
    dependencies=[Depends(require_access_context)],
)
def revoke_share_link_route(
    share_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SecureShareLinkRecord:
    try:
        record = collab_store.revoke_share_link(
            _state(request).session_factory,
            share_id,
            actor=_collaboration_actor(request, context),
        )
    except Exception as exc:
        _raise_collaboration_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Share link not found.")
    return record


@router.get(
    "/method-registry",
    response_model=list[MethodRegistryEntry],
    dependencies=[Depends(require_access_context)],
)
def list_method_registry_route(
    request: Request,
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[MethodRegistryEntry]:
    return method_store.list_method_registry(
        _state(request).session_factory,
        category=category,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/method-registry",
    response_model=MethodRegistryEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_method_registry_route(
    payload: MethodRegistryEntryCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MethodRegistryEntry:
    try:
        return method_store.create_method_entry(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/method-registry/{method_id}",
    response_model=MethodRegistryEntry,
    dependencies=[Depends(require_access_context)],
)
def get_method_registry_route(
    method_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MethodRegistryEntry:
    record = method_store.get_method_entry(_state(request).session_factory, method_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Method registry entry not found.")
    return record


@router.patch(
    "/method-registry/{method_id}",
    response_model=MethodRegistryEntry,
    dependencies=[Depends(require_access_context)],
)
def update_method_registry_route(
    method_id: int,
    payload: MethodRegistryEntryUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MethodRegistryEntry:
    try:
        record = method_store.update_method_entry(
            _state(request).session_factory,
            method_id,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Method registry entry not found.")
    return record


@router.get(
    "/model-versions",
    response_model=list[ModelVersion],
    dependencies=[Depends(require_access_context)],
)
def list_model_versions_route(
    request: Request,
    method_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ModelVersion]:
    return method_store.list_model_versions(
        _state(request).session_factory,
        method_id=method_id,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/model-versions",
    response_model=ModelVersion,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_model_version_route(
    payload: ModelVersionCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelVersion:
    try:
        return method_store.create_model_version(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/model-versions/{model_version_id}",
    response_model=ModelVersion,
    dependencies=[Depends(require_access_context)],
)
def get_model_version_route(
    model_version_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelVersion:
    record = method_store.get_model_version(_state(request).session_factory, model_version_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model version not found.")
    return record


@router.patch(
    "/model-versions/{model_version_id}",
    response_model=ModelVersion,
    dependencies=[Depends(require_access_context)],
)
def update_model_version_route(
    model_version_id: int,
    payload: ModelVersionUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelVersion:
    try:
        record = method_store.update_model_version(
            _state(request).session_factory,
            model_version_id,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Model version not found.")
    return record


@router.get(
    "/scoring-profiles",
    response_model=list[ScoringProfile],
    dependencies=[Depends(require_access_context)],
)
def list_scoring_profiles_route(
    request: Request,
    method_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ScoringProfile]:
    return method_store.list_scoring_profiles(
        _state(request).session_factory,
        method_id=method_id,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/scoring-profiles",
    response_model=ScoringProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_scoring_profile_route(
    payload: ScoringProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ScoringProfile:
    try:
        return method_store.create_scoring_profile(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/scoring-profiles/{profile_id}",
    response_model=ScoringProfile,
    dependencies=[Depends(require_access_context)],
)
def get_scoring_profile_route(
    profile_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ScoringProfile:
    record = method_store.get_scoring_profile(_state(request).session_factory, profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Scoring profile not found.")
    return record


@router.patch(
    "/scoring-profiles/{profile_id}",
    response_model=ScoringProfile,
    dependencies=[Depends(require_access_context)],
)
def update_scoring_profile_route(
    profile_id: int,
    payload: ScoringProfileUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ScoringProfile:
    try:
        record = method_store.update_scoring_profile(
            _state(request).session_factory,
            profile_id,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Scoring profile not found.")
    return record


@router.get(
    "/threshold-profiles",
    response_model=list[ThresholdProfile],
    dependencies=[Depends(require_access_context)],
)
def list_threshold_profiles_route(
    request: Request,
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ThresholdProfile]:
    return method_store.list_threshold_profiles(
        _state(request).session_factory,
        category=category,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/threshold-profiles",
    response_model=ThresholdProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_threshold_profile_route(
    payload: ThresholdProfileCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ThresholdProfile:
    try:
        return method_store.create_threshold_profile(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/threshold-profiles/{profile_id}",
    response_model=ThresholdProfile,
    dependencies=[Depends(require_access_context)],
)
def get_threshold_profile_route(
    profile_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ThresholdProfile:
    record = method_store.get_threshold_profile(_state(request).session_factory, profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Threshold profile not found.")
    return record


@router.patch(
    "/threshold-profiles/{profile_id}",
    response_model=ThresholdProfile,
    dependencies=[Depends(require_access_context)],
)
def update_threshold_profile_route(
    profile_id: int,
    payload: ThresholdProfileUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ThresholdProfile:
    try:
        record = method_store.update_threshold_profile(
            _state(request).session_factory,
            profile_id,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise
    if record is None:
        raise HTTPException(status_code=404, detail="Threshold profile not found.")
    return record


@router.get(
    "/benchmark-datasets",
    response_model=list[BenchmarkDataset],
    dependencies=[Depends(require_access_context)],
)
def list_benchmark_datasets_route(
    request: Request,
    category: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[BenchmarkDataset]:
    return method_store.list_benchmark_datasets(
        _state(request).session_factory,
        category=category,
        limit=limit,
    )


@router.post(
    "/benchmark-datasets",
    response_model=BenchmarkDataset,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_benchmark_dataset_route(
    payload: BenchmarkDatasetCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BenchmarkDataset:
    try:
        return method_store.create_benchmark_dataset(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/benchmark-datasets/{benchmark_id}",
    response_model=BenchmarkDataset,
    dependencies=[Depends(require_access_context)],
)
def get_benchmark_dataset_route(
    benchmark_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> BenchmarkDataset:
    record = method_store.get_benchmark_dataset(_state(request).session_factory, benchmark_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Benchmark dataset not found.")
    return record


@router.post(
    "/validation-runs",
    response_model=ValidationRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_validation_run_route(
    payload: ValidationRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationRun:
    try:
        return method_store.create_validation_run(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/validation-runs",
    response_model=list[ValidationRun],
    dependencies=[Depends(require_access_context)],
)
def list_validation_runs_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[ValidationRun]:
    return method_store.list_validation_runs(_state(request).session_factory, limit=limit)


@router.get(
    "/validation-runs/{validation_run_id}",
    response_model=ValidationRun,
    dependencies=[Depends(require_access_context)],
)
def get_validation_run_route(
    validation_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ValidationRun:
    record = method_store.get_validation_run(_state(request).session_factory, validation_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Validation run not found.")
    return record


@router.post(
    "/method-comparisons",
    response_model=MethodComparisonRun,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_method_comparison_route(
    payload: MethodComparisonRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MethodComparisonRun:
    try:
        return method_store.create_method_comparison(
            _state(request).session_factory,
            payload,
            actor=_method_registry_actor(context),
        )
    except Exception as exc:
        _raise_method_registry_http_error(exc)
        raise


@router.get(
    "/method-comparisons",
    response_model=list[MethodComparisonRun],
    dependencies=[Depends(require_access_context)],
)
def list_method_comparisons_route(
    request: Request,
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[MethodComparisonRun]:
    return method_store.list_method_comparisons(_state(request).session_factory, limit=limit)


@router.get(
    "/method-comparisons/{comparison_id}",
    response_model=MethodComparisonRun,
    dependencies=[Depends(require_access_context)],
)
def get_method_comparison_route(
    comparison_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MethodComparisonRun:
    record = method_store.get_method_comparison(_state(request).session_factory, comparison_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Method comparison not found.")
    return record


@router.get(
    "/model-health",
    response_model=ModelHealthSummary,
    dependencies=[Depends(require_access_context)],
)
def get_model_health_route(
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ModelHealthSummary:
    return method_store.model_health(_state(request).session_factory)


@router.get(
    "/model-health/drift-alerts",
    response_model=list[DriftAlert],
    dependencies=[Depends(require_access_context)],
)
def list_drift_alerts_route(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: AccessContext = Depends(require_access_context),
) -> list[DriftAlert]:
    return method_store.list_drift_alerts(
        _state(request).session_factory,
        status=status_filter,
        limit=limit,
    )


@router.post(
    "/model-health/drift-alerts/{alert_id}/acknowledge",
    response_model=DriftAlert,
    dependencies=[Depends(require_access_context)],
)
def acknowledge_drift_alert_route(
    alert_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DriftAlert:
    record = method_store.set_drift_alert_status(
        _state(request).session_factory,
        alert_id,
        "acknowledged",
        actor=_method_registry_actor(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Drift alert not found.")
    return record


@router.post(
    "/model-health/drift-alerts/{alert_id}/resolve",
    response_model=DriftAlert,
    dependencies=[Depends(require_access_context)],
)
def resolve_drift_alert_route(
    alert_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> DriftAlert:
    record = method_store.set_drift_alert_status(
        _state(request).session_factory,
        alert_id,
        "resolved",
        actor=_method_registry_actor(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Drift alert not found.")
    return record


@router.post(
    "/quality-control/files/{file_id}/assess",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def assess_quality_file_route(
    file_id: int,
    request: Request,
    payload: QualityAssessmentRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    try:
        assessment = qc_store.assess_file(
            _state(request).session_factory,
            file_id,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            storage_root=_orchestration_storage_root(request),
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="quality.file.assess",
        message="Quality assessment created for managed file.",
        entity_type="quality_assessment",
        entity_id=assessment.id,
        metadata={
            "file_id": file_id,
            "qc_status": assessment.qc_status,
            "readiness_status": assessment.readiness_status,
        },
    )
    return assessment


@router.post(
    "/quality-control/artifacts/{artifact_id}/assess",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def assess_quality_artifact_route(
    artifact_id: int,
    request: Request,
    payload: QualityAssessmentRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    try:
        assessment = qc_store.assess_artifact(
            _state(request).session_factory,
            artifact_id,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="quality.artifact.assess",
        message="Quality assessment created for artifact.",
        entity_type="quality_assessment",
        entity_id=assessment.id,
        metadata={
            "artifact_id": artifact_id,
            "qc_status": assessment.qc_status,
            "readiness_status": assessment.readiness_status,
        },
    )
    return assessment


@router.post(
    "/quality-control/evidence/{evidence_id}/assess",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def assess_quality_evidence_route(
    evidence_id: int,
    request: Request,
    payload: QualityAssessmentRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    try:
        assessment = qc_store.assess_evidence(
            _state(request).session_factory,
            evidence_id,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="quality.evidence.assess",
        message="Quality assessment created for evidence record.",
        entity_type="quality_assessment",
        entity_id=assessment.id,
        metadata={
            "evidence_id": evidence_id,
            "qc_status": assessment.qc_status,
            "readiness_status": assessment.readiness_status,
        },
    )
    return assessment


@router.post(
    "/quality-control/sessions/{session_id}/assess",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def assess_quality_session_route(
    session_id: int,
    request: Request,
    payload: QualityAssessmentRequest | None = Body(default=None),
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    try:
        assessment = qc_store.assess_session(
            _state(request).session_factory,
            session_id,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            storage_root=_orchestration_storage_root(request),
            payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="quality.session.assess",
        message="Quality assessment created for SpectraCheck session.",
        entity_type="quality_assessment",
        entity_id=assessment.id,
        metadata={
            "session_id": session_id,
            "qc_status": assessment.qc_status,
            "readiness_status": assessment.readiness_status,
        },
    )
    return assessment


@router.get(
    "/quality-control/files/{file_id}",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_quality_file_route(
    file_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    assessment = qc_store.get_latest_assessment(
        _state(request).session_factory,
        target_type="file",
        target_id=file_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Quality assessment not found for file.")
    return assessment


@router.get(
    "/quality-control/artifacts/{artifact_id}",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_quality_artifact_route(
    artifact_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    assessment = qc_store.get_latest_assessment(
        _state(request).session_factory,
        target_type="artifact",
        target_id=artifact_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Quality assessment not found for artifact.")
    return assessment


@router.get(
    "/quality-control/evidence/{evidence_id}",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_quality_evidence_route(
    evidence_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    assessment = qc_store.get_latest_assessment(
        _state(request).session_factory,
        target_type="evidence",
        target_id=evidence_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Quality assessment not found for evidence.")
    return assessment


@router.get(
    "/quality-control/sessions/{session_id}",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def get_quality_session_route(
    session_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    assessment = qc_store.get_latest_assessment(
        _state(request).session_factory,
        target_type="session",
        target_id=session_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="Quality assessment not found for session.")
    return assessment


@router.post(
    "/quality-control/findings/{finding_id}/review",
    response_model=QualityFinding,
    dependencies=[Depends(require_access_context)],
)
def review_quality_finding_route(
    finding_id: int,
    payload: QualityFindingReviewRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityFinding:
    finding = qc_store.review_finding(
        _state(request).session_factory,
        finding_id,
        payload,
        actor_id=context.user_id,
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Quality finding not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="quality.finding.review",
        message="Quality finding reviewed.",
        entity_type="quality_finding",
        entity_id=finding.id,
        metadata={
            "target_type": finding.target_type,
            "target_id": finding.target_id,
            "decision": payload.decision,
        },
    )
    return finding


@router.post(
    "/quality-control/evidence/{evidence_id}/override",
    response_model=QualityAssessment,
    dependencies=[Depends(require_access_context)],
)
def override_quality_evidence_route(
    evidence_id: int,
    payload: QualityOverrideCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> QualityAssessment:
    try:
        assessment = qc_store.override_evidence(
            _state(request).session_factory,
            evidence_id,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="quality.evidence.override",
        message="Quality override recorded for evidence readiness.",
        entity_type="quality_assessment",
        entity_id=assessment.id,
        metadata={
            "evidence_id": evidence_id,
            "decision": payload.decision,
            "readiness_status": assessment.readiness_status,
        },
    )
    return assessment


@router.get(
    "/workflow-templates",
    response_model=list[WorkflowTemplateRecord],
    dependencies=[Depends(require_access_context)],
)
def list_workflow_templates_route(
    request: Request,
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowTemplateRecord]:
    return wf_store.list_workflow_templates(
        _state(request).session_factory, category=category, limit=limit
    )


@router.get(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateRecord,
    dependencies=[Depends(require_access_context)],
)
def get_workflow_template_route(
    template_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowTemplateRecord:
    record = wf_store.get_workflow_template(_state(request).session_factory, template_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow template not found.")
    return record


@router.post(
    "/workflow-templates",
    response_model=WorkflowTemplateRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_workflow_template_route(
    payload: WorkflowTemplateCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowTemplateRecord:
    try:
        record = wf_store.create_workflow_template(_state(request).session_factory, payload)
    except wf_store.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="workflow.template.create",
        message="Workflow template created.",
        entity_type="workflow_template",
        entity_id=record.id,
        metadata={"slug": record.slug, "category": record.category},
    )
    return record


@router.patch(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateRecord,
    dependencies=[Depends(require_access_context)],
)
def update_workflow_template_route(
    template_id: int,
    payload: WorkflowTemplateUpdate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowTemplateRecord:
    try:
        record = wf_store.update_workflow_template(
            _state(request).session_factory, template_id, payload
        )
    except wf_store.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow template not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="workflow.template.update",
        message="Workflow template updated.",
        entity_type="workflow_template",
        entity_id=record.id,
        metadata={"slug": record.slug},
    )
    return record


@router.post(
    "/workflow-runs",
    response_model=WorkflowRunRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def create_workflow_run_route(
    payload: WorkflowRunCreate,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowRunRecord:
    try:
        record = wf_store.create_workflow_run(
            _state(request).session_factory,
            payload,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except wf_store.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="workflow.run.create",
        message="Workflow run created.",
        entity_type="workflow_run",
        entity_id=record.id,
        metadata={"template_id": record.template_id, "session_id": record.session_id},
    )
    return record


@router.get(
    "/workflow-runs",
    response_model=list[WorkflowRunRecord],
    dependencies=[Depends(require_access_context)],
)
def list_workflow_runs_route(
    request: Request,
    session_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowRunRecord]:
    try:
        return wf_store.list_workflow_runs(
            _state(request).session_factory,
            owner_scope_id=_user_scope_for_context(context),
            session_id=session_id,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/workflow-runs/{workflow_run_id}",
    response_model=WorkflowRunRecord,
    dependencies=[Depends(require_access_context)],
)
def get_workflow_run_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowRunRecord:
    record = wf_store.get_workflow_run(
        _state(request).session_factory,
        workflow_run_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    return record


@router.post(
    "/workflow-runs/{workflow_run_id}/start",
    response_model=WorkflowRunRecord,
    dependencies=[Depends(require_access_context)],
)
def start_workflow_run_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowRunRecord:
    try:
        record = wf_store.start_workflow_run(
            _state(request).session_factory,
            workflow_run_id,
            owner_scope_id=_user_scope_for_context(context),
            actor_id=context.user_id,
            storage_root=_orchestration_storage_root(request),
        )
    except wf_store.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="workflow.run.start",
        message="Workflow run started.",
        entity_type="workflow_run",
        entity_id=record.id,
        metadata={"status": record.status, "progress_percent": record.progress_percent},
    )
    return record


@router.post(
    "/workflow-runs/{workflow_run_id}/cancel",
    response_model=WorkflowRunRecord,
    dependencies=[Depends(require_access_context)],
)
def cancel_workflow_run_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> WorkflowRunRecord:
    record = wf_store.cancel_workflow_run(
        _state(request).session_factory,
        workflow_run_id,
        owner_scope_id=_user_scope_for_context(context),
        actor_id=context.user_id,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="workflow.run.cancel",
        message="Workflow run cancellation requested.",
        entity_type="workflow_run",
        entity_id=record.id,
        metadata={"status": record.status},
    )
    return record


@router.get(
    "/workflow-runs/{workflow_run_id}/events",
    response_model=list[WorkflowRunEventRecord],
    dependencies=[Depends(require_access_context)],
)
def list_workflow_run_events_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowRunEventRecord]:
    records = wf_store.list_workflow_events(
        _state(request).session_factory,
        workflow_run_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if records is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    return records


@router.get(
    "/workflow-runs/{workflow_run_id}/steps",
    response_model=list[WorkflowRunStepRecord],
    dependencies=[Depends(require_access_context)],
)
def list_workflow_run_steps_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowRunStepRecord]:
    records = wf_store.list_workflow_steps(
        _state(request).session_factory,
        workflow_run_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if records is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    return records


@router.get(
    "/workflow-runs/{workflow_run_id}/artifacts",
    response_model=list[WorkflowRunArtifactRecord],
    dependencies=[Depends(require_access_context)],
)
def list_workflow_run_artifacts_route(
    workflow_run_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowRunArtifactRecord]:
    records = wf_store.list_workflow_artifacts(
        _state(request).session_factory,
        workflow_run_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if records is None:
        raise HTTPException(status_code=404, detail="Workflow run not found.")
    return records


@router.get(
    "/spectracheck/sessions/{session_id}/workflow-runs",
    response_model=list[WorkflowRunRecord],
    dependencies=[Depends(require_access_context)],
)
def list_spectracheck_session_workflow_runs_route(
    session_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    context: AccessContext = Depends(require_access_context),
) -> list[WorkflowRunRecord]:
    try:
        return wf_store.list_workflow_runs(
            _state(request).session_factory,
            owner_scope_id=_user_scope_for_context(context),
            session_id=session_id,
            limit=limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/workspaces/projects",
    response_model=list[ProjectRecord],
    dependencies=[Depends(require_access_context)],
)
def workspace_projects(
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    user: UserPublic = Depends(require_authenticated_user),
) -> list[ProjectRecord]:
    return list_projects(_state(request).session_factory, user_id=user.id, limit=limit)


@router.post(
    "/workspaces/projects",
    response_model=ProjectRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def workspace_create_project(
    payload: ProjectCreate,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> ProjectRecord:
    try:
        record = create_project(
            _state(request).session_factory,
            user_id=user.id,
            name=payload.name,
            description=payload.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="workspace.project.create",
        message="Workspace project created.",
        entity_type="project",
        entity_id=record.id,
        metadata={"name": record.name},
    )
    return record


@router.get(
    "/workspaces/projects/{project_id}/samples",
    response_model=list[ProjectSampleRecord],
    dependencies=[Depends(require_access_context)],
)
def workspace_project_samples(
    project_id: int,
    request: Request,
    limit: int = Query(default=200, ge=1, le=500),
    user: UserPublic = Depends(require_authenticated_user),
) -> list[ProjectSampleRecord]:
    if get_project_by_id(_state(request).session_factory, project_id, user_id=user.id) is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return list_project_samples(
        _state(request).session_factory, user_id=user.id, project_id=project_id, limit=limit
    )


@router.post(
    "/workspaces/projects/{project_id}/samples",
    response_model=ProjectSampleRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def workspace_create_project_sample(
    project_id: int,
    payload: ProjectSampleCreate,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> ProjectSampleRecord:
    try:
        record = create_project_sample(
            _state(request).session_factory, user_id=user.id, project_id=project_id, payload=payload
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="workspace.sample.create",
        message="Workspace sample created.",
        entity_type="project_sample",
        entity_id=record.id,
        metadata={"project_id": project_id, "analysis_id": payload.analysis_id},
    )
    return record


@router.post(
    "/workspaces/projects/{project_id}/samples/{sample_record_id}/link-analysis",
    response_model=ProjectSampleRecord,
    dependencies=[Depends(require_access_context)],
)
def workspace_link_project_sample_analysis(
    project_id: int,
    sample_record_id: int,
    payload: ProjectSampleAnalysisLink,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> ProjectSampleRecord:
    try:
        record = link_project_sample_analysis(
            _state(request).session_factory,
            user_id=user.id,
            project_id=project_id,
            sample_record_id=sample_record_id,
            analysis_id=payload.analysis_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project sample not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=AccessContext(user=user),
        event_type="workspace.sample.link_analysis",
        message="Workspace sample linked to an analysis.",
        entity_type="project_sample",
        entity_id=record.id,
        metadata={"project_id": project_id, "analysis_id": payload.analysis_id},
    )
    return record


@router.get(
    "/projects/{project_id}/dashboard",
    response_model=ProjectDashboardRecord,
    dependencies=[Depends(require_access_context)],
)
def project_dashboard(
    project_id: int,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> ProjectDashboardRecord:
    dashboard = build_project_dashboard(
        _state(request).session_factory, user_id=user.id, project_id=project_id
    )
    if dashboard is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return dashboard


@router.get(
    "/samples/{sample_id}/analyses",
    response_model=list[StoredAnalysisRecord],
    dependencies=[Depends(require_access_context)],
)
def sample_analyses(
    sample_id: str,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> list[StoredAnalysisRecord]:
    records = list_sample_analyses(
        _state(request).session_factory, user_id=user.id, sample_identity=sample_id
    )
    if records is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return records


@router.get(
    "/samples/{sample_id}/timeline",
    response_model=SampleTimelineRecord,
    dependencies=[Depends(require_access_context)],
)
def sample_timeline(
    sample_id: str,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> SampleTimelineRecord:
    record = get_sample_timeline(
        _state(request).session_factory, user_id=user.id, sample_identity=sample_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return record


@router.get(
    "/samples/{sample_id}/reports",
    response_model=SampleReportsRecord,
    dependencies=[Depends(require_access_context)],
)
def sample_reports(
    sample_id: str,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> SampleReportsRecord:
    record = list_sample_reports(
        _state(request).session_factory, user_id=user.id, sample_identity=sample_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return record


@router.get(
    "/samples/{sample_id}/compare",
    response_model=SampleAnalysisComparison,
    dependencies=[Depends(require_access_context)],
)
def sample_compare(
    sample_id: str,
    request: Request,
    user: UserPublic = Depends(require_authenticated_user),
) -> SampleAnalysisComparison:
    record = compare_sample_analyses(
        _state(request).session_factory, user_id=user.id, sample_identity=sample_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return record


@router.get(
    "/samples/{sample_id}",
    response_model=SampleDetailRecord | SpectraCheckSampleRecord,
    dependencies=[Depends(require_access_context)],
)
def sample_detail(
    sample_id: str,
    request: Request,
    context: AccessContext = Depends(require_access_context),
    user: UserPublic | None = Depends(lambda: None),
) -> SampleDetailRecord | SpectraCheckSampleRecord:
    if not isinstance(context, AccessContext):
        context = (
            AccessContext(user=user) if user is not None else AccessContext(system_api_key=True)
        )
    spectracheck_sample = sc_store.get_spectracheck_sample(
        _state(request).session_factory,
        sample_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if spectracheck_sample is not None:
        return spectracheck_sample
    if context.user is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    user = context.user
    record = get_sample_detail(
        _state(request).session_factory, user_id=user.id, sample_identity=sample_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return record


@router.post(
    "/reports/from-analysis/{analysis_id}",
    response_model=StoredReportRecord,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access_context)],
)
def report_from_analysis(
    analysis_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StoredReportRecord:
    user_id = _user_scope_for_context(context)
    record = create_report_from_analysis(
        _state(request).session_factory, analysis_id=analysis_id, user_id=user_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="report.generate",
        message="Versioned report generated from analysis.",
        entity_type="analysis",
        entity_id=analysis_id,
        metadata={"report_id": record.id, "version": record.version},
    )
    return record


@router.post(
    "/reports/structure-elucidation/compose",
    response_model=StructureElucidationReportResult,
    dependencies=[Depends(require_access_context)],
)
def compose_structure_elucidation_report_route(
    payload: StructureElucidationReportRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StructureElucidationReportResult:
    try:
        result = compose_structure_elucidation_report(payload)
    except (
        StructureElucidationReportError,
        UnifiedConfidenceError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="report.structure_elucidation.compose",
        message="Regulatory-ready structure elucidation report composed.",
        metadata={
            "report_id": result.report_id,
            "sample_id": result.sample_id,
            "status": result.status,
            "release_gate": result.release_gate,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "report_sha256": result.provenance.get("report_sha256"),
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/reports/structure-elucidation/compose/evidence",
    response_model=StructureElucidationReportResult,
    dependencies=[Depends(require_access_context)],
)
def compose_structure_elucidation_report_evidence_route(
    request: Request,
    candidates_text: str = Form(...),
    observed_proton_text: str | None = Form(default=None),
    observed_carbon13_text: str | None = Form(default=None),
    observed_nmr2d_text: str | None = Form(default=None),
    observed_nmr2d_experiment_type: str | None = Form(default=None),
    hrms_observed_mz: float | None = Form(default=None),
    hrms_adduct: str | None = Form(default=None),
    ion_mode: str | None = Form(default=None),
    hrms_ppm_tolerance: float = Form(default=5.0),
    observed_m_plus_1_percent: float | None = Form(default=None),
    observed_m_plus_2_percent: float | None = Form(default=None),
    ms1_peak_list_text: str | None = Form(default=None),
    use_inferred_adduct: bool = Form(default=True),
    adduct_ppm_tolerance: float = Form(default=10.0),
    isotope_mz_tolerance_da: float = Form(default=0.02),
    ms1_min_relative_intensity: float = Form(default=0.2),
    ms1_max_peaks_to_analyze: int = Form(default=200),
    msms_peak_list_text: str | None = Form(default=None),
    msms_precursor_mz: float | None = Form(default=None),
    msms_adduct: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    msms_ppm_tolerance: float = Form(default=20.0),
    msms_min_relative_intensity: float = Form(default=1.0),
    msms_max_peaks_to_analyze: int = Form(default=75),
    max_tree_depth: int = Form(default=3),
    lcms_family_table_text: str | None = Form(default=None),
    lcms_anchor_adduct: str | None = Form(default=None),
    lcms_mz_tolerance_da: float = Form(default=0.02),
    lcms_ppm_tolerance: float = Form(default=10.0),
    lcms_min_family_consensus_score: float = Form(default=0.42),
    lcms_require_promoted_family: bool = Form(default=True),
    lcms_selected_family_id: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    report_title: str = Form(default="Regulatory-ready Structure Elucidation Report"),
    project_name: str | None = Form(default=None),
    prepared_by: str | None = Form(default=None),
    reviewer_name: str | None = Form(default=None),
    review_status: str | None = Form(default=None),
    reviewer_comment: str | None = Form(default=None),
    intended_use: str = Form(default="research_decision_support"),
    require_human_approval: bool = Form(default=True),
    raw_data_sha256: str | None = Form(default=None),
    source_files_text: str | None = Form(default=None),
    processing_history_text: str | None = Form(default=None),
    requestor_notes: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> StructureElucidationReportResult:
    try:
        candidates = parse_candidate_text(candidates_text)
        unified_request = UnifiedCandidateConfidenceRequest(
            sample_id=sample_id,
            solvent=solvent,
            candidates=candidates,
            observed_proton_text=observed_proton_text,
            observed_carbon13_text=observed_carbon13_text,
            observed_nmr2d_text=observed_nmr2d_text,
            observed_nmr2d_experiment_type=observed_nmr2d_experiment_type,
            hrms_observed_mz=hrms_observed_mz,
            hrms_adduct=hrms_adduct,
            ion_mode=ion_mode,
            hrms_ppm_tolerance=hrms_ppm_tolerance,
            observed_m_plus_1_percent=observed_m_plus_1_percent,
            observed_m_plus_2_percent=observed_m_plus_2_percent,
            ms1_peak_list_text=ms1_peak_list_text,
            use_inferred_adduct=use_inferred_adduct,
            adduct_ppm_tolerance=adduct_ppm_tolerance,
            isotope_mz_tolerance_da=isotope_mz_tolerance_da,
            ms1_min_relative_intensity=ms1_min_relative_intensity,
            ms1_max_peaks_to_analyze=ms1_max_peaks_to_analyze,
            msms_peak_list_text=msms_peak_list_text,
            msms_precursor_mz=msms_precursor_mz,
            msms_adduct=msms_adduct or hrms_adduct,
            mz_tolerance_da=mz_tolerance_da,
            msms_ppm_tolerance=msms_ppm_tolerance,
            msms_min_relative_intensity=msms_min_relative_intensity,
            msms_max_peaks_to_analyze=msms_max_peaks_to_analyze,
            max_tree_depth=max_tree_depth,
            lcms_family_table_text=lcms_family_table_text,
            lcms_anchor_adduct=lcms_anchor_adduct or hrms_adduct or msms_adduct,
            lcms_mz_tolerance_da=lcms_mz_tolerance_da,
            lcms_ppm_tolerance=lcms_ppm_tolerance,
            lcms_min_family_consensus_score=lcms_min_family_consensus_score,
            lcms_require_promoted_family=lcms_require_promoted_family,
            lcms_selected_family_id=lcms_selected_family_id,
        )
        source_files = [
            line.strip() for line in (source_files_text or "").splitlines() if line.strip()
        ]
        processing_history = [
            line.strip() for line in (processing_history_text or "").splitlines() if line.strip()
        ]
        report_request = StructureElucidationReportRequest(
            report_title=report_title,
            sample_id=sample_id,
            project_name=project_name,
            prepared_by=prepared_by,
            reviewer_name=reviewer_name,
            review_status=review_status or None,
            reviewer_comment=reviewer_comment,
            intended_use=intended_use,
            require_human_approval=require_human_approval,
            requestor_notes=requestor_notes,
            raw_data_sha256=raw_data_sha256,
            source_files=source_files,
            processing_history=processing_history,
            unified_confidence_request=unified_request,
        )
        result = compose_structure_elucidation_report(report_request)
    except (
        StructureElucidationReportError,
        UnifiedConfidenceError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="report.structure_elucidation.compose.evidence",
        message="Regulatory-ready structure elucidation report composed from form evidence.",
        metadata={
            "report_id": result.report_id,
            "sample_id": result.sample_id,
            "status": result.status,
            "release_gate": result.release_gate,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "report_sha256": result.provenance.get("report_sha256"),
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/reports/structure-elucidation/compose/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_context)],
)
def compose_structure_elucidation_report_html_route(
    payload: StructureElucidationReportRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> HTMLResponse:
    try:
        result = compose_structure_elucidation_report(payload)
    except (
        StructureElucidationReportError,
        UnifiedConfidenceError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="report.structure_elucidation.html",
        message="Regulatory-ready structure elucidation report HTML rendered.",
        metadata={
            "report_id": result.report_id,
            "status": result.status,
            "release_gate": result.release_gate,
        },
    )
    return HTMLResponse(content=result.html_report)


@router.get(
    "/reports/{analysis_id}.json",
    response_model=AnalysisEvidenceReport,
    dependencies=[Depends(require_access_context)],
)
def evidence_report_json(
    analysis_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> AnalysisEvidenceReport:
    user_id = _user_scope_for_context(context)
    report = build_evidence_report(
        _state(request).session_factory, analysis_id=analysis_id, user_id=user_id
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="report.view_json",
        message="Evidence report JSON opened.",
        entity_type="analysis",
        entity_id=analysis_id,
    )
    return report


@router.get(
    "/reports/{analysis_id}.html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_access_context)],
)
def evidence_report_html(
    analysis_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> HTMLResponse:
    user_id = _user_scope_for_context(context)
    stored_report = get_report_by_id(
        _state(request).session_factory, report_id=analysis_id, user_id=user_id
    )
    if stored_report is not None:
        _audit_from_context(
            request,
            context=context,
            event_type="report.view_versioned_html",
            message="Versioned report HTML opened.",
            entity_type="analysis",
            entity_id=stored_report.analysis_id,
            metadata={"report_id": stored_report.id, "version": stored_report.version},
        )
        return HTMLResponse(_render_evidence_report_html(stored_report.report))
    report = build_evidence_report(
        _state(request).session_factory, analysis_id=analysis_id, user_id=user_id
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Analysis report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="report.view_html",
        message="Evidence report HTML opened.",
        entity_type="analysis",
        entity_id=analysis_id,
    )
    return HTMLResponse(_render_evidence_report_html(report))


@router.get(
    "/reports/{report_id}",
    response_model=StoredReportRecord,
    dependencies=[Depends(require_access_context)],
)
def report_detail(
    report_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> StoredReportRecord:
    user_id = _user_scope_for_context(context)
    record = get_report_by_id(_state(request).session_factory, report_id=report_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    _audit_from_context(
        request,
        context=context,
        event_type="report.view_versioned_json",
        message="Versioned report JSON opened.",
        entity_type="analysis",
        entity_id=record.analysis_id,
        metadata={"report_id": record.id, "version": record.version},
    )
    return record


@router.get(
    "/history",
    response_model=list[StoredAnalysisRecord],
    dependencies=[Depends(require_access_context)],
)
def history(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    context: AccessContext = Depends(require_access_context),
) -> list[StoredAnalysisRecord]:
    user_id = None if context.system_api_key else context.user_id
    return list_recent_analyses(_state(request).session_factory, limit=limit, user_id=user_id)


@router.get("/history/export.csv", dependencies=[Depends(require_access_context)])
def history_export_csv(
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=10_000),
    context: AccessContext = Depends(require_access_context),
) -> StreamingResponse:
    user_id = None if context.system_api_key else context.user_id
    csv_text = export_history_csv(_state(request).session_factory, limit=limit, user_id=user_id)
    headers = {"Content-Disposition": 'attachment; filename="nmrcheck-history.csv"'}
    return StreamingResponse(_stream_text(csv_text), media_type="text/csv", headers=headers)


@router.get(
    "/history/{analysis_id}/full",
    response_model=FullStoredAnalysisRecord,
    dependencies=[Depends(require_access_context)],
)
def history_detail_full(
    analysis_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> FullStoredAnalysisRecord:
    user_id = None if context.system_api_key else context.user_id
    record = get_full_analysis_by_id(
        _state(request).session_factory, analysis_id=analysis_id, user_id=user_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis record not found.")
    return record


@router.get(
    "/history/{analysis_id}",
    response_model=StoredAnalysisRecord,
    dependencies=[Depends(require_access_context)],
)
def history_detail(
    analysis_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> StoredAnalysisRecord:
    user_id = None if context.system_api_key else context.user_id
    record = get_analysis_by_id(
        _state(request).session_factory, analysis_id=analysis_id, user_id=user_id
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis record not found.")
    return record


@router.get(
    "/jobs",
    response_model=list[JobRecord | AnalysisJobRecord],
    dependencies=[Depends(require_access_context)],
)
def jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    context: AccessContext = Depends(require_access_context),
) -> list[JobRecord | AnalysisJobRecord]:
    user_id = None if context.system_api_key else context.user_id
    legacy_jobs = list_jobs(_state(request).session_factory, limit=limit, user_id=user_id)
    analysis_jobs = orch_store.list_analysis_jobs(
        _state(request).session_factory,
        owner_scope_id=_user_scope_for_context(context),
        limit=limit,
    )
    return [*legacy_jobs, *analysis_jobs][:limit]


@router.get(
    "/jobs/{job_id}",
    response_model=JobRecord | AnalysisJobRecord,
    dependencies=[Depends(require_access_context)],
)
def job_detail(
    job_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> JobRecord | AnalysisJobRecord:
    user_id = None if context.system_api_key else context.user_id
    record = get_job_by_id(_state(request).session_factory, job_id=job_id, user_id=user_id)
    if record is not None:
        return record
    record = orch_store.get_analysis_job(
        _state(request).session_factory,
        job_id,
        owner_scope_id=_user_scope_for_context(context),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return record


@router.get(
    "/jobs/{job_id}/items",
    response_model=list[StoredAnalysisRecord],
    dependencies=[Depends(require_access_context)],
)
def job_items(
    job_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> list[StoredAnalysisRecord]:
    user_id = None if context.system_api_key else context.user_id
    if get_job_by_id(_state(request).session_factory, job_id=job_id, user_id=user_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return list_job_analyses(_state(request).session_factory, job_id=job_id, user_id=user_id)


@router.get("/jobs/{job_id}/export.csv", dependencies=[Depends(require_access_context)])
def job_export_csv(
    job_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> StreamingResponse:
    user_id = None if context.system_api_key else context.user_id
    try:
        csv_text = export_job_csv(_state(request).session_factory, job_id=job_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    headers = {"Content-Disposition": f'attachment; filename="nmrcheck-job-{job_id}.csv"'}
    return StreamingResponse(_stream_text(csv_text), media_type="text/csv", headers=headers)


@router.get("/jobs/{job_id}/export.json", dependencies=[Depends(require_access_context)])
def job_export_json(
    job_id: int, request: Request, context: AccessContext = Depends(require_access_context)
) -> StreamingResponse:
    user_id = None if context.system_api_key else context.user_id
    try:
        json_text = export_job_json(_state(request).session_factory, job_id=job_id, user_id=user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
    headers = {"Content-Disposition": f'attachment; filename="nmrcheck-job-{job_id}.json"'}
    return StreamingResponse(
        _stream_text(json_text), media_type="application/json", headers=headers
    )


@router.get("/reviews", response_model=list[ReviewQueueItem], dependencies=[Depends(require_admin)])
def reviews(
    request: Request,
    context: AccessContext = Depends(require_admin),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReviewQueueItem]:
    _audit_from_context(
        request,
        context=context,
        event_type="review.list",
        message="Review queue opened.",
        metadata={"status": review_status, "limit": limit},
    )
    return list_review_queue(
        _state(request).session_factory, limit=limit, review_status=review_status
    )


@router.post(
    "/reviews/{analysis_id}/approve",
    response_model=ReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def review_approve(
    analysis_id: int,
    payload: ReviewDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> ReviewDecisionRecord:
    decision = submit_review_decision(
        _state(request).session_factory,
        analysis_id=analysis_id,
        reviewer_user_id=context.user.id if context.user else 0,
        action="approve",
        comment=payload.comment,
        final_label=payload.final_label,
        hours_saved_estimate=payload.hours_saved_estimate,
    )
    return decision


@router.post(
    "/reviews/{analysis_id}/reject",
    response_model=ReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def review_reject(
    analysis_id: int,
    payload: ReviewDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> ReviewDecisionRecord:
    return submit_review_decision(
        _state(request).session_factory,
        analysis_id=analysis_id,
        reviewer_user_id=context.user.id if context.user else 0,
        action="reject",
        comment=payload.comment,
        final_label=payload.final_label,
        hours_saved_estimate=payload.hours_saved_estimate,
    )


@router.post(
    "/reviews/{analysis_id}/override",
    response_model=ReviewDecisionRecord,
    dependencies=[Depends(require_admin)],
)
def review_override(
    analysis_id: int,
    payload: ReviewDecisionCreate,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> ReviewDecisionRecord:
    return submit_review_decision(
        _state(request).session_factory,
        analysis_id=analysis_id,
        reviewer_user_id=context.user.id if context.user else 0,
        action="override",
        comment=payload.comment,
        final_label=payload.final_label,
        hours_saved_estimate=payload.hours_saved_estimate,
    )


@router.get(
    "/reviews/{analysis_id}/decisions",
    response_model=list[ReviewDecisionRecord],
    dependencies=[Depends(require_access_context)],
)
def review_decisions(
    analysis_id: int,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> list[ReviewDecisionRecord]:
    state = _state(request)
    if not context.system_api_key and not (context.user and context.user.is_admin):
        if (
            get_analysis_by_id(
                state.session_factory, analysis_id=analysis_id, user_id=context.user_id
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Analysis record not found.")
    return list_review_decisions(state.session_factory, analysis_id=analysis_id)


@router.get(
    "/audit", response_model=list[AuditEventRecord], dependencies=[Depends(require_access_context)]
)
def audit_log(
    request: Request,
    context: AccessContext = Depends(require_access_context),
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None, ge=1),
) -> list[AuditEventRecord]:
    return _audit_events_for_context(
        request,
        context=context,
        limit=limit,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
    )


@router.get(
    "/audit/events",
    response_model=list[AuditEventRecord],
    dependencies=[Depends(require_access_context)],
)
def audit_events_log(
    request: Request,
    context: AccessContext = Depends(require_access_context),
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(
        default=None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$"
    ),
    entity_type: str | None = Query(
        default=None, min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$"
    ),
    entity_id: int | None = Query(default=None, ge=1),
) -> list[AuditEventRecord]:
    return _audit_events_for_context(
        request,
        context=context,
        limit=limit,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
    )


def _audit_events_for_context(
    request: Request,
    *,
    context: AccessContext,
    limit: int,
    event_type: str | None,
    entity_type: str | None,
    entity_id: int | None,
) -> list[AuditEventRecord]:
    state = _state(request)
    limit_value = limit if isinstance(limit, int) else 100
    event_type_value = event_type if isinstance(event_type, str) else None
    entity_type_value = entity_type if isinstance(entity_type, str) else None
    entity_id_value = entity_id if isinstance(entity_id, int) else None
    if not context.system_api_key and not (context.user and context.user.is_admin):
        if entity_type_value != "analysis" or entity_id_value is None:
            raise HTTPException(status_code=403, detail=PUBLIC_ACCESS_DENIED_DETAIL)
        if (
            get_analysis_by_id(
                state.session_factory, analysis_id=entity_id_value, user_id=context.user_id
            )
            is None
        ):
            raise HTTPException(status_code=404, detail="Analysis record not found.")
    return list_audit_events(
        state.session_factory,
        limit=limit_value,
        event_type=event_type_value,
        entity_type=entity_type_value,
        entity_id=entity_id_value,
    )


@router.get(
    "/metrics/summary", response_model=MetricsSummary, dependencies=[Depends(require_admin)]
)
def metrics_summary(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> MetricsSummary:
    return get_metrics_summary(_state(request).session_factory)


@router.get(
    "/metrics/dashboard", response_model=MetricsSummary, dependencies=[Depends(require_admin)]
)
def metrics_dashboard(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> MetricsSummary:
    return get_metrics_summary(_state(request).session_factory)


@router.get(
    "/admin/users", response_model=list[AdminUserRecord], dependencies=[Depends(require_admin)]
)
def admin_users(
    request: Request,
    context: AccessContext = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AdminUserRecord]:
    return list_admin_users(_state(request).session_factory, limit=limit)


@router.post(
    "/admin/users/{user_id}/promote",
    response_model=UserPublic,
    dependencies=[Depends(require_admin)],
)
def admin_promote_user(
    user_id: int,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> UserPublic:
    updated = set_user_admin_status(_state(request).session_factory, user_id=user_id, is_admin=True)
    _audit_from_context(
        request,
        context=context,
        event_type="admin.promote_user",
        message="User promoted to admin.",
        entity_type="user",
        entity_id=user_id,
    )
    return updated


@router.post(
    "/admin/users/{user_id}/demote",
    response_model=UserPublic,
    dependencies=[Depends(require_admin)],
)
def admin_demote_user(
    user_id: int,
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> UserPublic:
    updated = set_user_admin_status(
        _state(request).session_factory, user_id=user_id, is_admin=False
    )
    _audit_from_context(
        request,
        context=context,
        event_type="admin.demote_user",
        message="User demoted from admin.",
        entity_type="user",
        entity_id=user_id,
    )
    return updated


@router.get(
    "/admin/system", response_model=AdminSystemSummary, dependencies=[Depends(require_admin)]
)
def admin_system(
    request: Request,
    context: AccessContext = Depends(require_admin),
) -> AdminSystemSummary:
    queue = queue_status(request)
    return get_admin_system_summary(
        _state(request).session_factory,
        queue_backend=queue.backend,
        redis_configured=queue.redis_configured,
    )


@router.get("/admin/deployment", dependencies=[Depends(require_admin)])
def admin_deployment_diagnostics(request: Request) -> dict[str, object]:
    settings = _state(request).settings
    optional_fid_ready = (
        importlib.util.find_spec("nmrglue") is not None
        and importlib.util.find_spec("numpy") is not None
    )
    return {
        "app_env": settings.app_env,
        "database_url_configured": bool(settings.database_url),
        "redis_configured": bool(settings.redis_url),
        "api_key_configured": bool(settings.api_key),
        "local_auth_disabled": settings.local_auth_disabled,
        "admin_email_count": len(settings.admin_emails),
        "healthcheck_path": settings.healthcheck_path,
        "startup_issues": getattr(request.app.state, "startup_issues", []),
        "optional_fid_dependencies_ready": optional_fid_ready,
        "raw_fid_vendors_beta": ["Bruker", "Varian/Agilent"],
        "queue_name": settings.queue_name,
        "require_verified_email": settings.require_verified_email,
    }


@router.get("/admin/release-health", dependencies=[Depends(require_admin)])
def admin_release_health(request: Request) -> dict[str, object]:
    settings = _state(request).settings
    optional_fid_ready = (
        importlib.util.find_spec("nmrglue") is not None
        and importlib.util.find_spec("numpy") is not None
    )
    metrics = get_metrics_summary(_state(request).session_factory)
    queue = queue_status(request)
    return {
        "release_version": settings.release_version,
        "release_stage": settings.release_stage,
        "app_version": settings.release_version,
        "startup_issues": getattr(request.app.state, "startup_issues", []),
        "database_status": "configured" if settings.database_url else "missing",
        "redis_status": "configured" if settings.redis_url else "not_configured",
        "queue_status": queue.model_dump(),
        "fid_optional_dependencies_ready": optional_fid_ready,
        "supported_raw_fid_vendors_beta": ["Bruker", "Varian/Agilent"],
        "analyses_total": metrics.total_analyses,
        "jobs_total": metrics.total_jobs,
        "pending_review_total": metrics.pending_review,
        "hours_saved_estimate": metrics.hours_saved_estimate,
        "value_dashboard": [
            {"label": "Analyses run", "value": metrics.total_analyses},
            {"label": "Batch jobs", "value": metrics.total_jobs},
            {"label": "Pending reviews", "value": metrics.pending_review},
            {"label": "Estimated hours saved", "value": metrics.hours_saved_estimate},
        ],
        "recommended_smoke_tests": [
            "GET /health",
            "GET /admin/deployment",
            "GET /admin/release-health",
            "POST /proton/evidence",
            "POST /carbon13/analyze",
            "POST /carbon13/spectrum/analyze",
            "POST /carbon13/fid/analyze",
            "POST /spectrum/preview with a processed CSV",
            "POST /fid/preview with Bruker and Varian/Agilent beta fixtures",
        ],
    }


@router.post(
    "/proton/evidence",
    response_model=ProtonEvidenceReport,
    dependencies=[Depends(require_access_context)],
)
def proton_evidence_route(
    payload: AnalysisInputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> ProtonEvidenceReport:
    report = analyze_proton_evidence(
        smiles=payload.smiles,
        nmr_text=payload.nmr_text,
        sample_id=payload.sample_id,
        solvent=payload.solvent,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="proton.evidence",
        message="¹H NMR evidence scoring completed.",
        metadata={
            "sample_id": payload.sample_id,
            "label": report.label,
            "score": report.overall_score,
        },
    )
    return report


@router.post(
    "/carbon13/validate",
    response_model=Carbon13UploadPreview,
    dependencies=[Depends(require_access_context)],
)
def carbon13_validate_route(
    payload: Carbon13Inputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> Carbon13UploadPreview:
    try:
        peaks = parse_carbon13_text(payload.carbon13_text, solvent=payload.solvent)
    except (Carbon13ParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="¹³C peak-table upload") from exc
    warnings: list[str] = []
    if any(peak.is_likely_solvent for peak in peaks):
        warnings.append("One or more ¹³C shifts overlap known solvent-carbon regions.")
    if any(getattr(peak, "is_likely_impurity", False) for peak in peaks):
        warnings.append("One or more ¹³C shifts overlap embedded impurity-reference regions.")
    return Carbon13UploadPreview(
        filename="pasted_13c_text",
        source_mode="text",
        observed_signal_count=len(peaks),
        peaks=peaks,
        warnings=warnings,
        metadata={"sample_id": payload.sample_id, "solvent": payload.solvent},
    )


@router.post(
    "/carbon13/analyze",
    response_model=Carbon13AnalysisReport,
    dependencies=[Depends(require_access_context)],
)
def carbon13_analyze_route(
    payload: Carbon13Inputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> Carbon13AnalysisReport:
    try:
        report = analyze_carbon13_text(
            payload.smiles,
            payload.carbon13_text,
            solvent=payload.solvent,
            sample_id=payload.sample_id,
        )
    except (Carbon13ParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="¹³C processed spectrum preview") from exc
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.analyze",
        message="¹³C NMR validation completed.",
        metadata={
            "sample_id": payload.sample_id,
            "label": report.label,
            "observed_carbon_signals": report.observed_carbon_signals,
        },
    )
    return report


@router.post(
    "/carbon13/evidence",
    response_model=Carbon13AnalysisReport,
    dependencies=[Depends(require_access_context)],
)
def carbon13_evidence_route(
    payload: Carbon13Inputs,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> Carbon13AnalysisReport:
    return carbon13_analyze_route(payload=payload, request=request, context=context)


@router.post(
    "/carbon13/dept/preview",
    response_model=DeptAptPreviewReport,
    dependencies=[Depends(require_access_context)],
)
async def dept_apt_preview_route(
    request: Request,
    file: UploadFile = File(...),
    experiment_type: str | None = Form(default=None),
    apt_positive: str = Form(default="CH_CH3"),
    context: AccessContext = Depends(require_access_context),
) -> DeptAptPreviewReport:
    filename = file.filename or "dept_apt_peaks.csv"
    content = await file.read()
    try:
        preview = parse_dept_apt_table(
            filename,
            content,
            experiment_type=experiment_type,
            apt_positive=apt_positive,
        )
    except (DeptAptParseError, PydanticValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.dept.preview",
        message="DEPT/APT peak table previewed.",
        metadata={
            "filename": filename,
            "experiment": preview.experiment_detected,
            "peak_count": preview.peak_count,
            "typed_peak_count": preview.metadata.get("typed_peak_count"),
        },
    )
    return preview


@router.post(
    "/carbon13/dept/analyze",
    response_model=DeptAptAnalyzeResult,
    dependencies=[Depends(require_access_context)],
)
async def dept_apt_analyze_route(
    request: Request,
    file: UploadFile = File(...),
    carbon13_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    experiment_type: str | None = Form(default=None),
    apt_positive: str = Form(default="CH_CH3"),
    context: AccessContext = Depends(require_access_context),
) -> DeptAptAnalyzeResult:
    filename = file.filename or "dept_apt_peaks.csv"
    content = await file.read()
    try:
        preview = parse_dept_apt_table(
            filename,
            content,
            experiment_type=experiment_type,
            apt_positive=apt_positive,
        )
        result = analyze_dept_apt_preview(preview, carbon13_text=carbon13_text, solvent=solvent)
    except (DeptAptParseError, PydanticValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.dept.analyze",
        message="DEPT/APT evidence analyzed.",
        metadata={
            "filename": filename,
            "experiment": result.preview.experiment_detected,
            "matched_carbon13_count": result.matched_carbon13_count,
            "dept_apt_consistency_score": result.dept_apt_consistency_score,
        },
    )
    return result


@router.post(
    "/candidates/compare",
    response_model=CandidateComparisonResult,
    dependencies=[Depends(require_access_context)],
)
def candidate_compare_route(
    payload: CandidateComparisonRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CandidateComparisonResult:
    result = compare_candidates(payload)
    _audit_from_context(
        request,
        context=context,
        event_type="candidates.compare",
        message="Candidate structures compared against supplied spectral evidence.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "evidence_layers": result.evidence_layers_used,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/candidates/compare/evidence",
    response_model=CandidateComparisonResult,
    dependencies=[Depends(require_access_context)],
)
async def candidate_compare_evidence_route(
    request: Request,
    candidates_text: str = Form(...),
    proton_nmr_text: str | None = Form(default=None),
    carbon13_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    nmr2d_file: UploadFile | None = File(default=None),
    nmr2d_experiment_type: str | None = Form(default=None),
    dept_apt_file: UploadFile | None = File(default=None),
    dept_apt_experiment_type: str | None = Form(default=None),
    apt_positive: str = Form(default="CH_CH3"),
    context: AccessContext = Depends(require_access_context),
) -> CandidateComparisonResult:
    try:
        candidates = parse_candidate_text(candidates_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    dept_result: DeptAptAnalyzeResult | None = None
    dept_peaks = None
    if dept_apt_file is not None:
        dept_content = await dept_apt_file.read()
        if dept_content:
            try:
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
                dept_peaks = dept_result.preview.peaks
            except (DeptAptParseError, PydanticValidationError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    nmr2d_result = None
    if nmr2d_file is not None:
        if not bool(getattr(_state(request).settings, "enable_2d_nmr", False)):
            raise HTTPException(
                status_code=404, detail="2D NMR evidence engine is disabled by feature flag."
            )
        nmr2d_content = await nmr2d_file.read()
        if nmr2d_content:
            try:
                nmr2d_preview = parse_nmr2d_upload(
                    nmr2d_file.filename or "processed_2d_nmr.csv",
                    nmr2d_content,
                    experiment_hint=nmr2d_experiment_type,
                    include_contour_preview=False,
                )
                nmr2d_result = analyze_nmr2d_preview(
                    nmr2d_preview,
                    proton_nmr_text=proton_nmr_text,
                    carbon13_text=carbon13_text,
                    solvent=solvent,
                    dept_apt_peaks=dept_peaks,
                )
            except (NMR2DParseError, PydanticValidationError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload = CandidateComparisonRequest(
        sample_id=sample_id,
        solvent=solvent,
        proton_nmr_text=proton_nmr_text,
        carbon13_text=carbon13_text,
        candidates=candidates,
    )
    result = compare_candidates(payload, dept_apt_result=dept_result, nmr2d_result=nmr2d_result)
    _audit_from_context(
        request,
        context=context,
        event_type="candidates.compare.evidence",
        message="Candidate structures compared against uploaded spectral evidence layers.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "evidence_layers": result.evidence_layers_used,
            "has_2d": nmr2d_result is not None,
            "has_dept_apt": dept_result is not None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/similarity/score",
    response_model=SpectralSimilarityResult,
    dependencies=[Depends(require_access_context)],
)
def spectral_similarity_score_route(
    payload: SpectralSimilarityRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> SpectralSimilarityResult:
    result = score_similarity_request(payload)
    _audit_from_context(
        request,
        context=context,
        event_type="similarity.score",
        message="Spectral similarity scored across supplied NMR evidence layers.",
        metadata={
            "layers": result.evidence_layers_used,
            "overall_score": result.overall_score,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/similarity/score/evidence",
    response_model=SpectralSimilarityResult,
    dependencies=[Depends(require_access_context)],
)
async def spectral_similarity_evidence_route(
    request: Request,
    observed_proton_text: str | None = Form(default=None),
    reference_proton_text: str | None = Form(default=None),
    observed_carbon13_text: str | None = Form(default=None),
    reference_carbon13_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    observed_nmr2d_file: UploadFile | None = File(default=None),
    reference_nmr2d_file: UploadFile | None = File(default=None),
    nmr2d_experiment_type: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> SpectralSimilarityResult:
    payload = SpectralSimilarityRequest(
        sample_id=sample_id,
        solvent=solvent,
        observed_proton_text=observed_proton_text,
        reference_proton_text=reference_proton_text,
        observed_carbon13_text=observed_carbon13_text,
        reference_carbon13_text=reference_carbon13_text,
    )
    text_result = score_similarity_request(payload)
    layers = list(text_result.layers)
    warnings = list(text_result.warnings)

    if observed_nmr2d_file is not None and reference_nmr2d_file is not None:
        observed_content = await observed_nmr2d_file.read()
        reference_content = await reference_nmr2d_file.read()
        if observed_content and reference_content:
            try:
                observed_preview = parse_nmr2d_upload(
                    observed_nmr2d_file.filename or "observed_nmr2d.csv",
                    observed_content,
                    experiment_hint=nmr2d_experiment_type,
                )
                reference_preview = parse_nmr2d_upload(
                    reference_nmr2d_file.filename or "reference_nmr2d.csv",
                    reference_content,
                    experiment_hint=nmr2d_experiment_type,
                )
                layers.append(score_nmr2d_similarity(observed_preview, reference_preview))
            except NMR2DParseError as exc:
                warnings.append(f"2D similarity could not be scored: {exc}")
        else:
            warnings.append(
                "Both observed and reference 2D files must contain data to score 2D similarity."
            )
    elif observed_nmr2d_file is not None or reference_nmr2d_file is not None:
        warnings.append("Both observed and reference 2D files are required to score 2D similarity.")

    result = combine_similarity_layers(layers, sample_id=sample_id, solvent=solvent)
    if warnings:
        result = result.model_copy(update={"warnings": [*result.warnings, *warnings]})
    _audit_from_context(
        request,
        context=context,
        event_type="similarity.score.evidence",
        message="Spectral similarity scored across uploaded evidence layers.",
        metadata={
            "layers": result.evidence_layers_used,
            "overall_score": result.overall_score,
            "label": result.label,
            "has_2d": any(
                layer in result.evidence_layers_used
                for layer in ["2D", "COSY", "HSQC", "HMQC", "HMBC"]
            ),
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/prediction/nmr/preview",
    response_model=PredictedNMRReport,
    dependencies=[Depends(require_access_context)],
)
def predicted_nmr_preview_route(
    payload: CandidateInput,
    request: Request,
    solvent: str | None = Query(default=None),
    context: AccessContext = Depends(require_access_context),
) -> PredictedNMRReport:
    report = predict_nmr_from_smiles(payload.smiles, name=payload.name, solvent=solvent)
    _audit_from_context(
        request,
        context=context,
        event_type="prediction.nmr.preview",
        message="Candidate-specific predicted NMR preview generated.",
        metadata={
            "smiles": payload.smiles,
            "name": payload.name,
            "prediction_method": report.prediction_method,
            "confidence_label": report.confidence_label,
            "human_review_required": True,
        },
    )
    return report


@router.post(
    "/prediction/nmr/match",
    response_model=CandidatePredictedNMRMatchResult,
    dependencies=[Depends(require_access_context)],
)
def predicted_nmr_match_route(
    payload: CandidatePredictedNMRMatchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> CandidatePredictedNMRMatchResult:
    result = match_candidates_with_predicted_nmr(payload)
    _audit_from_context(
        request,
        context=context,
        event_type="prediction.nmr.match",
        message="Candidate structures matched against observed NMR using candidate-specific predicted shifts.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "layers": result.evidence_layers_used,
            "human_review_required": True,
        },
    )
    return result


def _nmr_match_error_detail(message: str, *, code: str) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
        },
        "warnings": [message],
        "notes": [
            "Candidate-specific predicted NMR matching returns ranking evidence and requires human review.",
        ],
        "limitations": PREDICTED_NMR_MATCH_LIMITATIONS,
    }


def _sha256_provenance(
    *,
    field_name: str,
    value: str | bytes,
    source: Literal["form", "json", "upload", "derived"],
    filename: str | None = None,
    content_type: str | None = None,
) -> EvidenceInputProvenance:
    content = value if isinstance(value, bytes) else value.encode("utf-8")
    return EvidenceInputProvenance(
        field_name=field_name,
        source=source,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        filename=filename,
        content_type=content_type,
    )


@router.post(
    "/prediction/nmr/match/evidence",
    response_model=CandidatePredictedNMRMatchResult,
    dependencies=[Depends(require_access_context)],
)
async def predicted_nmr_match_evidence_route(
    request: Request,
    candidates_text: str = Form(...),
    observed_proton_text: str | None = Form(default=None),
    observed_carbon13_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    observed_nmr2d_file: UploadFile | None = File(default=None),
    nmr2d_experiment_type: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> CandidatePredictedNMRMatchResult:
    try:
        form_request = CandidatePredictedNMRMatchEvidenceRequest(
            candidates_text=candidates_text,
            observed_proton_text=observed_proton_text,
            observed_carbon13_text=observed_carbon13_text,
            solvent=solvent,
            sample_id=sample_id,
            nmr2d_experiment_type=nmr2d_experiment_type,
        )
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=_nmr_match_error_detail(
                str(exc),
                code="invalid_nmr_match_evidence_request",
            ),
        ) from exc

    input_provenance = [
        _sha256_provenance(
            field_name="candidates_text",
            value=form_request.candidates_text,
            source="form",
        )
    ]
    if form_request.observed_proton_text:
        input_provenance.append(
            _sha256_provenance(
                field_name="observed_proton_text",
                value=form_request.observed_proton_text,
                source="form",
            )
        )
    if form_request.observed_carbon13_text:
        input_provenance.append(
            _sha256_provenance(
                field_name="observed_carbon13_text",
                value=form_request.observed_carbon13_text,
                source="form",
            )
        )

    try:
        candidates = parse_candidate_text(form_request.candidates_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_nmr_match_error_detail(str(exc), code="invalid_candidates_text"),
        ) from exc

    observed_nmr2d = None
    if observed_nmr2d_file is not None:
        try:
            content = await observed_nmr2d_file.read()
            if content:
                input_provenance.append(
                    _sha256_provenance(
                        field_name="observed_nmr2d_file",
                        value=content,
                        source="upload",
                        filename=observed_nmr2d_file.filename or "observed_nmr2d.csv",
                        content_type=observed_nmr2d_file.content_type,
                    )
                )
                observed_nmr2d = parse_nmr2d_upload(
                    observed_nmr2d_file.filename or "observed_nmr2d.csv",
                    content,
                    experiment_hint=form_request.nmr2d_experiment_type,
                )
        except NMR2DParseError as exc:
            raise HTTPException(
                status_code=400,
                detail=_nmr_match_error_detail(
                    str(exc),
                    code="invalid_observed_nmr2d_file",
                ),
            ) from exc

    payload = CandidatePredictedNMRMatchRequest(
        sample_id=form_request.sample_id,
        solvent=form_request.solvent,
        observed_proton_text=form_request.observed_proton_text,
        observed_carbon13_text=form_request.observed_carbon13_text,
        candidates=candidates,
    )
    result = match_candidates_with_predicted_nmr(payload, observed_nmr2d=observed_nmr2d)
    result = result.model_copy(
        update={
            "input_provenance": input_provenance,
            "metadata": {
                **result.metadata,
                "api_contract": "moltrace.spectracheck.predicted_nmr_match.evidence.v1",
                "input_provenance": [item.model_dump(mode="json") for item in input_provenance],
            },
        }
    )
    _audit_from_context(
        request,
        context=context,
        event_type="prediction.nmr.match.evidence",
        message="Candidate-specific predicted NMR matching run with uploaded evidence.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "layers": result.evidence_layers_used,
            "has_2d": observed_nmr2d is not None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/hrms/candidates/match",
    response_model=HRMSCandidateMatchResult,
    dependencies=[Depends(require_access_context)],
)
def hrms_candidate_match_route(
    payload: HRMSCandidateMatchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> HRMSCandidateMatchResult:
    try:
        result = match_hrms_candidates(payload)
    except HRMSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.hrms.candidates.match",
        message="HRMS exact-mass candidate constraint matching completed.",
        metadata={
            "candidate_count": result.candidate_count,
            "exact_match_count": result.exact_match_count,
            "observed_mz": result.observed_mz,
            "adduct": result.adduct.name,
            "best_match": result.best_match.smiles if result.best_match else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/hrms/candidates/match/evidence",
    response_model=HRMSCandidateMatchResult,
    dependencies=[Depends(require_access_context)],
)
def hrms_candidate_match_evidence_route(
    request: Request,
    candidates_text: str = Form(...),
    observed_mz: float = Form(...),
    adduct: str = Form(default="[M+H]+"),
    ion_mode: str | None = Form(default=None),
    ppm_tolerance: float = Form(default=5.0),
    observed_m_plus_1_percent: float | None = Form(default=None),
    observed_m_plus_2_percent: float | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> HRMSCandidateMatchResult:
    try:
        candidates = parse_candidate_text(candidates_text)
        payload = HRMSCandidateMatchRequest(
            sample_id=sample_id,
            observed_mz=observed_mz,
            adduct=adduct,
            ion_mode=ion_mode,
            ppm_tolerance=ppm_tolerance,
            observed_m_plus_1_percent=observed_m_plus_1_percent,
            observed_m_plus_2_percent=observed_m_plus_2_percent,
            candidates=candidates,
        )
        result = match_hrms_candidates(payload)
    except (HRMSError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.hrms.candidates.match.evidence",
        message="HRMS exact-mass candidate constraint matching completed from form evidence.",
        metadata={
            "candidate_count": result.candidate_count,
            "exact_match_count": result.exact_match_count,
            "observed_mz": result.observed_mz,
            "adduct": result.adduct.name,
            "best_match": result.best_match.smiles if result.best_match else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/hrms/formulas/search",
    response_model=HRMSFormulaSearchResult,
    dependencies=[Depends(require_access_context)],
)
def hrms_formula_search_route(
    payload: HRMSFormulaSearchRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> HRMSFormulaSearchResult:
    try:
        result = search_formulas_by_hrms(payload)
    except HRMSError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.hrms.formulas.search",
        message="HRMS formula search completed.",
        metadata={
            "observed_mz": result.observed_mz,
            "adduct": result.adduct.name,
            "formula_count": result.formula_count,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/adducts/infer",
    response_model=MS1AdductInferenceResult,
    dependencies=[Depends(require_access_context)],
)
def ms1_adduct_inference_route(
    payload: MS1AdductInferenceRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MS1AdductInferenceResult:
    try:
        result = infer_adducts_and_isotopes(payload)
    except (AdductInferenceError, HRMSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.adducts.infer",
        message="MS1 adduct and isotope pattern inference completed.",
        metadata={
            "primary_mz": result.primary_mz,
            "peak_count": result.peak_count,
            "cluster_count": len(result.isotope_clusters),
            "best_adduct": result.best_adduct_candidate.adduct.name
            if result.best_adduct_candidate
            else None,
            "best_score": result.best_adduct_candidate.candidate_score
            if result.best_adduct_candidate
            else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/adducts/infer/evidence",
    response_model=MS1AdductInferenceResult,
    dependencies=[Depends(require_access_context)],
)
def ms1_adduct_inference_evidence_route(
    request: Request,
    peak_list_text: str = Form(...),
    ion_mode: str | None = Form(default="positive"),
    target_mz: float | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=10.0),
    isotope_mz_tolerance_da: float = Form(default=0.02),
    min_relative_intensity: float = Form(default=0.2),
    max_peaks_to_analyze: int = Form(default=200),
    max_charge: int = Form(default=3),
    perform_formula_search: bool = Form(default=True),
    formula_candidates_per_adduct: int = Form(default=5),
    max_c: int = Form(default=20),
    max_h: int = Form(default=60),
    max_n: int = Form(default=4),
    max_o: int = Form(default=8),
    max_s: int = Form(default=2),
    max_p: int = Form(default=1),
    max_cl: int = Form(default=2),
    max_br: int = Form(default=1),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> MS1AdductInferenceResult:
    try:
        payload = MS1AdductInferenceRequest(
            sample_id=sample_id,
            peak_list_text=peak_list_text,
            ion_mode=ion_mode,
            target_mz=target_mz,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            isotope_mz_tolerance_da=isotope_mz_tolerance_da,
            min_relative_intensity=min_relative_intensity,
            max_peaks_to_analyze=max_peaks_to_analyze,
            max_charge=max_charge,
            perform_formula_search=perform_formula_search,
            formula_candidates_per_adduct=formula_candidates_per_adduct,
            max_c=max_c,
            max_h=max_h,
            max_n=max_n,
            max_o=max_o,
            max_s=max_s,
            max_p=max_p,
            max_cl=max_cl,
            max_br=max_br,
        )
        result = infer_adducts_and_isotopes(payload)
    except (AdductInferenceError, HRMSError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.adducts.infer.evidence",
        message="MS1 adduct and isotope pattern inference completed from form evidence.",
        metadata={
            "primary_mz": result.primary_mz,
            "peak_count": result.peak_count,
            "cluster_count": len(result.isotope_clusters),
            "best_adduct": result.best_adduct_candidate.adduct.name
            if result.best_adduct_candidate
            else None,
            "best_score": result.best_adduct_candidate.candidate_score
            if result.best_adduct_candidate
            else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/msms/annotate",
    response_model=MSMSAnnotationResult,
    dependencies=[Depends(require_access_context)],
)
def msms_annotate_route(
    payload: MSMSAnnotationRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MSMSAnnotationResult:
    try:
        result = annotate_msms(payload)
    except (MSMSError, HRMSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.msms.annotate",
        message="Processed MS/MS annotation completed.",
        metadata={
            "precursor_mz": result.precursor_mz,
            "adduct": result.adduct.name,
            "peak_count": result.peak_count,
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "annotated_peak_count": result.annotated_peak_count,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/msms/annotate/evidence",
    response_model=MSMSAnnotationResult,
    dependencies=[Depends(require_access_context)],
)
def msms_annotate_evidence_route(
    request: Request,
    peak_list_text: str = Form(...),
    precursor_mz: float = Form(...),
    adduct: str = Form(default="[M+H]+"),
    ion_mode: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_intensity: float = Form(default=1.0),
    max_peaks_to_annotate: int = Form(default=50),
    candidates_text: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> MSMSAnnotationResult:
    try:
        candidates = parse_candidate_text(candidates_text or "") if candidates_text else []
        payload = MSMSAnnotationRequest(
            sample_id=sample_id,
            precursor_mz=precursor_mz,
            adduct=adduct,
            ion_mode=ion_mode,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_intensity=min_relative_intensity,
            max_peaks_to_annotate=max_peaks_to_annotate,
            peak_list_text=peak_list_text,
            candidates=candidates,
        )
        result = annotate_msms(payload)
    except (MSMSError, HRMSError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.msms.annotate.evidence",
        message="Processed MS/MS annotation completed from form evidence.",
        metadata={
            "precursor_mz": result.precursor_mz,
            "adduct": result.adduct.name,
            "peak_count": result.peak_count,
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "annotated_peak_count": result.annotated_peak_count,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/msms/fragmentation-tree",
    response_model=MSMSFragmentationTreeResult,
    dependencies=[Depends(require_access_context)],
)
def msms_fragmentation_tree_route(
    payload: MSMSFragmentationTreeRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> MSMSFragmentationTreeResult:
    try:
        result = build_msms_fragmentation_tree(payload)
    except (MSMSFragmentationTreeError, MSMSError, HRMSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.msms.fragmentation_tree",
        message="Processed MS/MS fragmentation-tree reasoning completed.",
        metadata={
            "precursor_mz": result.precursor_mz,
            "adduct": result.adduct.name,
            "peak_count": result.peak_count,
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.tree_score if result.best_candidate else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/msms/fragmentation-tree/evidence",
    response_model=MSMSFragmentationTreeResult,
    dependencies=[Depends(require_access_context)],
)
def msms_fragmentation_tree_evidence_route(
    request: Request,
    peak_list_text: str = Form(...),
    precursor_mz: float = Form(...),
    adduct: str = Form(default="[M+H]+"),
    ion_mode: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_intensity: float = Form(default=1.0),
    max_peaks_to_analyze: int = Form(default=75),
    max_tree_depth: int = Form(default=3),
    candidates_text: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> MSMSFragmentationTreeResult:
    try:
        candidates = parse_candidate_text(candidates_text or "") if candidates_text else []
        payload = MSMSFragmentationTreeRequest(
            sample_id=sample_id,
            precursor_mz=precursor_mz,
            adduct=adduct,
            ion_mode=ion_mode,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_intensity=min_relative_intensity,
            max_peaks_to_analyze=max_peaks_to_analyze,
            max_tree_depth=max_tree_depth,
            peak_list_text=peak_list_text,
            candidates=candidates,
        )
        result = build_msms_fragmentation_tree(payload)
    except (
        MSMSFragmentationTreeError,
        MSMSError,
        HRMSError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.msms.fragmentation_tree.evidence",
        message="Processed MS/MS fragmentation-tree reasoning completed from form evidence.",
        metadata={
            "precursor_mz": result.precursor_mz,
            "adduct": result.adduct.name,
            "peak_count": result.peak_count,
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.tree_score if result.best_candidate else None,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/confidence/candidates/unified",
    response_model=UnifiedCandidateConfidenceResult,
    dependencies=[Depends(require_access_context)],
)
def unified_candidate_confidence_route(
    payload: UnifiedCandidateConfidenceRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UnifiedCandidateConfidenceResult:
    try:
        result = build_unified_candidate_confidence(payload)
    except (
        UnifiedConfidenceError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="confidence.candidates.unified",
        message="Unified NMR/MS candidate confidence completed.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.confidence_score if result.best_candidate else None,
            "evidence_layers_used": result.evidence_layers_used,
            "selected_adduct": result.selected_adduct,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/confidence/candidates/unified/lcms-bridge",
    response_model=UnifiedCandidateConfidenceResult,
    dependencies=[Depends(require_access_context)],
)
def unified_candidate_confidence_lcms_bridge_route(
    payload: UnifiedCandidateConfidenceRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UnifiedCandidateConfidenceResult:
    try:
        result = build_unified_candidate_confidence(payload)
    except (
        UnifiedConfidenceError,
        LCMSConfidenceBridgeError,
        LCMSFeatureFamilyConsensusError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="confidence.candidates.unified.lcms_bridge",
        message="Unified candidate confidence completed with LC-MS consensus bridge.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.confidence_score if result.best_candidate else None,
            "evidence_layers_used": result.evidence_layers_used,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/confidence/candidates/unified/evidence",
    response_model=UnifiedCandidateConfidenceResult,
    dependencies=[Depends(require_access_context)],
)
def unified_candidate_confidence_evidence_route(
    request: Request,
    candidates_text: str = Form(...),
    observed_proton_text: str | None = Form(default=None),
    observed_carbon13_text: str | None = Form(default=None),
    observed_nmr2d_text: str | None = Form(default=None),
    observed_nmr2d_experiment_type: str | None = Form(default=None),
    hrms_observed_mz: float | None = Form(default=None),
    hrms_adduct: str | None = Form(default=None),
    ion_mode: str | None = Form(default=None),
    hrms_ppm_tolerance: float = Form(default=5.0),
    observed_m_plus_1_percent: float | None = Form(default=None),
    observed_m_plus_2_percent: float | None = Form(default=None),
    ms1_peak_list_text: str | None = Form(default=None),
    use_inferred_adduct: bool = Form(default=True),
    adduct_ppm_tolerance: float = Form(default=10.0),
    isotope_mz_tolerance_da: float = Form(default=0.02),
    ms1_min_relative_intensity: float = Form(default=0.2),
    ms1_max_peaks_to_analyze: int = Form(default=200),
    msms_peak_list_text: str | None = Form(default=None),
    msms_precursor_mz: float | None = Form(default=None),
    msms_adduct: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    msms_ppm_tolerance: float = Form(default=20.0),
    msms_min_relative_intensity: float = Form(default=1.0),
    msms_max_peaks_to_analyze: int = Form(default=75),
    max_tree_depth: int = Form(default=3),
    lcms_family_table_text: str | None = Form(default=None),
    lcms_anchor_adduct: str | None = Form(default=None),
    lcms_mz_tolerance_da: float = Form(default=0.02),
    lcms_ppm_tolerance: float = Form(default=10.0),
    lcms_min_family_consensus_score: float = Form(default=0.42),
    lcms_require_promoted_family: bool = Form(default=True),
    lcms_selected_family_id: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> UnifiedCandidateConfidenceResult:
    try:
        candidates = parse_candidate_text(candidates_text)
        payload = UnifiedCandidateConfidenceRequest(
            sample_id=sample_id,
            solvent=solvent,
            candidates=candidates,
            observed_proton_text=observed_proton_text,
            observed_carbon13_text=observed_carbon13_text,
            observed_nmr2d_text=observed_nmr2d_text,
            observed_nmr2d_experiment_type=observed_nmr2d_experiment_type,
            hrms_observed_mz=hrms_observed_mz,
            hrms_adduct=hrms_adduct,
            ion_mode=ion_mode,
            hrms_ppm_tolerance=hrms_ppm_tolerance,
            observed_m_plus_1_percent=observed_m_plus_1_percent,
            observed_m_plus_2_percent=observed_m_plus_2_percent,
            ms1_peak_list_text=ms1_peak_list_text,
            use_inferred_adduct=use_inferred_adduct,
            adduct_ppm_tolerance=adduct_ppm_tolerance,
            isotope_mz_tolerance_da=isotope_mz_tolerance_da,
            ms1_min_relative_intensity=ms1_min_relative_intensity,
            ms1_max_peaks_to_analyze=ms1_max_peaks_to_analyze,
            msms_peak_list_text=msms_peak_list_text,
            msms_precursor_mz=msms_precursor_mz,
            msms_adduct=msms_adduct,
            mz_tolerance_da=mz_tolerance_da,
            msms_ppm_tolerance=msms_ppm_tolerance,
            msms_min_relative_intensity=msms_min_relative_intensity,
            msms_max_peaks_to_analyze=msms_max_peaks_to_analyze,
            max_tree_depth=max_tree_depth,
            lcms_family_table_text=lcms_family_table_text,
            lcms_anchor_adduct=lcms_anchor_adduct or hrms_adduct or msms_adduct,
            lcms_mz_tolerance_da=lcms_mz_tolerance_da,
            lcms_ppm_tolerance=lcms_ppm_tolerance,
            lcms_min_family_consensus_score=lcms_min_family_consensus_score,
            lcms_require_promoted_family=lcms_require_promoted_family,
            lcms_selected_family_id=lcms_selected_family_id,
        )
        result = build_unified_candidate_confidence(payload)
    except (
        UnifiedConfidenceError,
        HRMSError,
        MSMSError,
        MSMSFragmentationTreeError,
        AdductInferenceError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="confidence.candidates.unified.evidence",
        message="Unified NMR/MS candidate confidence completed from form evidence.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.confidence_score if result.best_candidate else None,
            "evidence_layers_used": result.evidence_layers_used,
            "selected_adduct": result.selected_adduct,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/confidence/candidates/unified/evidence-bundle",
    response_model=UnifiedEvidenceBundleConfidenceResult,
    dependencies=[Depends(require_access_context)],
)
def unified_candidate_confidence_evidence_bundle_route(
    payload: UnifiedEvidenceBundleRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> UnifiedEvidenceBundleConfidenceResult:
    try:
        result = build_unified_candidate_confidence_from_bundle(payload)
    except (UnifiedConfidenceError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="confidence.candidates.unified.evidence_bundle",
        message="Unified candidate confidence completed from Evidence Queue bundle.",
        metadata={
            "candidate_count": result.candidate_count,
            "best_candidate": result.best_candidate.smiles if result.best_candidate else None,
            "best_score": result.best_candidate.confidence_score if result.best_candidate else None,
            "evidence_layers_used": result.evidence_layers_used,
            "evidence_completeness": result.evidence_completeness,
            "agreement_count": result.agreement_count,
            "contradiction_count": result.contradiction_count,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/import/bridge",
    response_model=LCMSImportBridgeResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_import_bridge_route(
    payload: LCMSImportBridgeRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> LCMSImportBridgeResult:
    try:
        result = import_lcms_bridge(payload)
    except LCMSImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.import_bridge",
        message="LC-MS/MS import bridge completed.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "scan_count": result.scan_count,
            "ms1_scan_count": result.ms1_scan_count,
            "ms2_scan_count": result.ms2_scan_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/import/bridge/evidence",
    response_model=LCMSImportBridgeResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_import_bridge_evidence_route(
    request: Request,
    source_text: str = Form(...),
    filename: str | None = Form(default=None),
    source_format: str = Form(default="auto"),
    preferred_msms_precursor_mz: float | None = Form(default=None),
    min_relative_intensity: float = Form(default=0.5),
    max_ms1_peaks: int = Form(default=250),
    max_msms_peaks_per_spectrum: int = Form(default=250),
    max_peaks_per_spectrum: int = Form(default=50),
    max_scans_to_report: int = Form(default=250),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSImportBridgeResult:
    try:
        payload = LCMSImportBridgeRequest(
            sample_id=sample_id,
            filename=filename,
            source_format=source_format,
            source_text=source_text,
            preferred_msms_precursor_mz=preferred_msms_precursor_mz,
            min_relative_intensity=min_relative_intensity,
            max_ms1_peaks=max_ms1_peaks,
            max_msms_peaks_per_spectrum=max_msms_peaks_per_spectrum,
            max_peaks_per_spectrum=max_peaks_per_spectrum,
            max_scans_to_report=max_scans_to_report,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
        )
        result = import_lcms_bridge(payload)
    except (LCMSImportError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.import_bridge.evidence",
        message="LC-MS/MS import bridge completed from form evidence.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "scan_count": result.scan_count,
            "ms1_scan_count": result.ms1_scan_count,
            "ms2_scan_count": result.ms2_scan_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/import/bridge/upload",
    response_model=LCMSImportBridgeResult,
    dependencies=[Depends(require_access_context)],
)
async def lcms_import_bridge_upload_route(
    request: Request,
    file: UploadFile = File(...),
    source_format: str = Form(default="auto"),
    preferred_msms_precursor_mz: float | None = Form(default=None),
    min_relative_intensity: float = Form(default=0.5),
    max_ms1_peaks: int = Form(default=250),
    max_msms_peaks_per_spectrum: int = Form(default=250),
    max_peaks_per_spectrum: int = Form(default=50),
    max_scans_to_report: int = Form(default=250),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSImportBridgeResult:
    raw_bytes = await file.read()
    source_text = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = LCMSImportBridgeRequest(
            sample_id=sample_id,
            filename=file.filename,
            source_format=source_format,
            source_text=source_text,
            preferred_msms_precursor_mz=preferred_msms_precursor_mz,
            min_relative_intensity=min_relative_intensity,
            max_ms1_peaks=max_ms1_peaks,
            max_msms_peaks_per_spectrum=max_msms_peaks_per_spectrum,
            max_peaks_per_spectrum=max_peaks_per_spectrum,
            max_scans_to_report=max_scans_to_report,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
        )
        result = import_lcms_bridge(payload, raw_bytes=raw_bytes)
    except (LCMSImportError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.import_bridge.upload",
        message="LC-MS/MS import bridge completed from uploaded file.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "scan_count": result.scan_count,
            "ms1_scan_count": result.ms1_scan_count,
            "ms2_scan_count": result.ms2_scan_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/detect",
    response_model=LCMSFeatureDetectionResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_detection_route(
    payload: LCMSFeatureDetectionRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureDetectionResult:
    try:
        result = detect_lcms_features(payload)
    except LCMSFeatureDetectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.detect",
        message="LC-MS feature detection and peak-purity analysis completed.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "feature_count": result.feature_count,
            "clean_feature_count": result.clean_feature_count,
            "coeluting_feature_count": result.coeluting_feature_count,
            "weak_feature_count": result.weak_feature_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/detect/evidence",
    response_model=LCMSFeatureDetectionResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_detection_evidence_route(
    request: Request,
    source_text: str = Form(...),
    filename: str | None = Form(default=None),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_feature_height: float = Form(default=5.0),
    min_peak_height: float = Form(default=0.0),
    min_scans_per_feature: int = Form(default=2),
    smoothing_window: int = Form(default=1),
    purity_rt_window_min: float = Form(default=0.20),
    top_coeluting_ions: int = Form(default=5),
    max_features: int = Form(default=20),
    max_scans_to_report: int = Form(default=1000),
    max_xic_points: int = Form(default=5000),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureDetectionResult:
    try:
        payload = LCMSFeatureDetectionRequest(
            sample_id=sample_id,
            filename=filename,
            source_format=source_format,
            source_text=source_text,
            target_mz_text=target_mz_text,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_feature_height=min_relative_feature_height,
            min_peak_height=min_peak_height,
            min_scans_per_feature=min_scans_per_feature,
            smoothing_window=smoothing_window,
            purity_rt_window_min=purity_rt_window_min,
            top_coeluting_ions=top_coeluting_ions,
            max_features=max_features,
            max_scans_to_report=max_scans_to_report,
            max_xic_points=max_xic_points,
        )
        result = detect_lcms_features(payload)
    except (LCMSFeatureDetectionError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.detect.evidence",
        message="LC-MS feature detection completed from form evidence.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "feature_count": result.feature_count,
            "clean_feature_count": result.clean_feature_count,
            "coeluting_feature_count": result.coeluting_feature_count,
            "weak_feature_count": result.weak_feature_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/detect/upload",
    response_model=LCMSFeatureDetectionResult,
    dependencies=[Depends(require_access_context)],
)
async def lcms_feature_detection_upload_route(
    request: Request,
    file: UploadFile = File(...),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_feature_height: float = Form(default=5.0),
    min_peak_height: float = Form(default=0.0),
    min_scans_per_feature: int = Form(default=2),
    smoothing_window: int = Form(default=1),
    purity_rt_window_min: float = Form(default=0.20),
    top_coeluting_ions: int = Form(default=5),
    max_features: int = Form(default=20),
    max_scans_to_report: int = Form(default=1000),
    max_xic_points: int = Form(default=5000),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureDetectionResult:
    raw_bytes = await file.read()
    source_text = raw_bytes.decode("utf-8", errors="replace")
    try:
        payload = LCMSFeatureDetectionRequest(
            sample_id=sample_id,
            filename=file.filename,
            source_format=source_format,
            source_text=source_text,
            target_mz_text=target_mz_text,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_feature_height=min_relative_feature_height,
            min_peak_height=min_peak_height,
            min_scans_per_feature=min_scans_per_feature,
            smoothing_window=smoothing_window,
            purity_rt_window_min=purity_rt_window_min,
            top_coeluting_ions=top_coeluting_ions,
            max_features=max_features,
            max_scans_to_report=max_scans_to_report,
            max_xic_points=max_xic_points,
        )
        result = detect_lcms_features(payload, raw_bytes=raw_bytes)
    except (LCMSFeatureDetectionError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.detect.upload",
        message="LC-MS feature detection completed from uploaded file.",
        metadata={
            "source_format": result.source_format,
            "filename": result.filename,
            "feature_count": result.feature_count,
            "clean_feature_count": result.clean_feature_count,
            "coeluting_feature_count": result.coeluting_feature_count,
            "weak_feature_count": result.weak_feature_count,
            "file_sha256": result.file_sha256,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/group",
    response_model=LCMSFeatureGroupingResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_grouping_route(
    payload: LCMSFeatureGroupingRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureGroupingResult:
    try:
        result = group_lcms_features(payload)
    except (LCMSFeatureGroupingError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.group",
        message="LC-MS feature grouping, blank subtraction, and RT alignment completed.",
        metadata={
            "run_count": result.run_count,
            "group_count": result.group_count,
            "sample_enriched_group_count": result.sample_enriched_group_count,
            "background_group_count": result.background_group_count,
            "reference_run_id": result.reference_run_id,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/group/evidence",
    response_model=LCMSFeatureGroupingResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_grouping_evidence_route(
    request: Request,
    sample_source_text: str = Form(...),
    blank_source_text: str | None = Form(default=None),
    sample_filename: str | None = Form(default=None),
    blank_filename: str | None = Form(default=None),
    sample_run_id: str = Form(default="sample"),
    blank_run_id: str = Form(default="blank"),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    alignment_anchor_mz_text: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_feature_height: float = Form(default=5.0),
    min_peak_height: float = Form(default=0.0),
    min_scans_per_feature: int = Form(default=2),
    smoothing_window: int = Form(default=1),
    purity_rt_window_min: float = Form(default=0.20),
    group_rt_tolerance_min: float = Form(default=0.12),
    family_rt_tolerance_min: float = Form(default=0.15),
    rt_alignment_search_window_min: float = Form(default=1.0),
    blank_area_ratio_threshold: float = Form(default=0.30),
    possible_background_ratio_threshold: float = Form(default=0.10),
    blank_subtraction_factor: float = Form(default=1.0),
    max_features_per_run: int = Form(default=50),
    max_groups_to_report: int = Form(default=100),
    align_retention_times: bool = Form(default=True),
    annotate_feature_families: bool = Form(default=True),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureGroupingResult:
    runs = [
        LCMSFeatureGroupingRunInput(
            run_id=sample_run_id or "sample",
            role="sample",
            filename=sample_filename,
            source_format=source_format,
            source_text=sample_source_text,
        )
    ]
    if blank_source_text and blank_source_text.strip():
        runs.append(
            LCMSFeatureGroupingRunInput(
                run_id=blank_run_id or "blank",
                role="blank",
                filename=blank_filename,
                source_format=source_format,
                source_text=blank_source_text,
            )
        )
    try:
        payload = LCMSFeatureGroupingRequest(
            sample_id=sample_id,
            runs=runs,
            target_mz_text=target_mz_text,
            alignment_anchor_mz_text=alignment_anchor_mz_text,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_feature_height=min_relative_feature_height,
            min_peak_height=min_peak_height,
            min_scans_per_feature=min_scans_per_feature,
            smoothing_window=smoothing_window,
            purity_rt_window_min=purity_rt_window_min,
            group_rt_tolerance_min=group_rt_tolerance_min,
            family_rt_tolerance_min=family_rt_tolerance_min,
            rt_alignment_search_window_min=rt_alignment_search_window_min,
            blank_area_ratio_threshold=blank_area_ratio_threshold,
            possible_background_ratio_threshold=possible_background_ratio_threshold,
            blank_subtraction_factor=blank_subtraction_factor,
            max_features_per_run=max_features_per_run,
            max_groups_to_report=max_groups_to_report,
            align_retention_times=align_retention_times,
            annotate_feature_families=annotate_feature_families,
        )
        result = group_lcms_features(payload)
    except (LCMSFeatureGroupingError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.group.evidence",
        message="LC-MS feature grouping completed from form evidence.",
        metadata={
            "run_count": result.run_count,
            "group_count": result.group_count,
            "sample_enriched_group_count": result.sample_enriched_group_count,
            "background_group_count": result.background_group_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/group/upload",
    response_model=LCMSFeatureGroupingResult,
    dependencies=[Depends(require_access_context)],
)
async def lcms_feature_grouping_upload_route(
    request: Request,
    sample_file: UploadFile = File(...),
    blank_file: UploadFile | None = File(default=None),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    alignment_anchor_mz_text: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    min_relative_feature_height: float = Form(default=5.0),
    min_peak_height: float = Form(default=0.0),
    min_scans_per_feature: int = Form(default=2),
    smoothing_window: int = Form(default=1),
    purity_rt_window_min: float = Form(default=0.20),
    group_rt_tolerance_min: float = Form(default=0.12),
    family_rt_tolerance_min: float = Form(default=0.15),
    rt_alignment_search_window_min: float = Form(default=1.0),
    blank_area_ratio_threshold: float = Form(default=0.30),
    possible_background_ratio_threshold: float = Form(default=0.10),
    blank_subtraction_factor: float = Form(default=1.0),
    max_features_per_run: int = Form(default=50),
    max_groups_to_report: int = Form(default=100),
    align_retention_times: bool = Form(default=True),
    annotate_feature_families: bool = Form(default=True),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureGroupingResult:
    sample_text = (await sample_file.read()).decode("utf-8", errors="replace")
    runs = [
        LCMSFeatureGroupingRunInput(
            run_id="sample",
            role="sample",
            filename=sample_file.filename,
            source_format=source_format,
            source_text=sample_text,
        )
    ]
    if blank_file is not None:
        blank_text = (await blank_file.read()).decode("utf-8", errors="replace")
        if blank_text.strip():
            runs.append(
                LCMSFeatureGroupingRunInput(
                    run_id="blank",
                    role="blank",
                    filename=blank_file.filename,
                    source_format=source_format,
                    source_text=blank_text,
                )
            )
    try:
        payload = LCMSFeatureGroupingRequest(
            sample_id=sample_id,
            runs=runs,
            target_mz_text=target_mz_text,
            alignment_anchor_mz_text=alignment_anchor_mz_text,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            min_relative_feature_height=min_relative_feature_height,
            min_peak_height=min_peak_height,
            min_scans_per_feature=min_scans_per_feature,
            smoothing_window=smoothing_window,
            purity_rt_window_min=purity_rt_window_min,
            group_rt_tolerance_min=group_rt_tolerance_min,
            family_rt_tolerance_min=family_rt_tolerance_min,
            rt_alignment_search_window_min=rt_alignment_search_window_min,
            blank_area_ratio_threshold=blank_area_ratio_threshold,
            possible_background_ratio_threshold=possible_background_ratio_threshold,
            blank_subtraction_factor=blank_subtraction_factor,
            max_features_per_run=max_features_per_run,
            max_groups_to_report=max_groups_to_report,
            align_retention_times=align_retention_times,
            annotate_feature_families=annotate_feature_families,
        )
        result = group_lcms_features(payload)
    except (LCMSFeatureGroupingError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.group.upload",
        message="LC-MS feature grouping completed from uploaded files.",
        metadata={
            "run_count": result.run_count,
            "group_count": result.group_count,
            "sample_enriched_group_count": result.sample_enriched_group_count,
            "background_group_count": result.background_group_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/consensus",
    response_model=LCMSFeatureFamilyConsensusResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_family_consensus_route(
    payload: LCMSFeatureFamilyConsensusRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureFamilyConsensusResult:
    try:
        result = score_lcms_feature_family_consensus(payload)
    except (LCMSFeatureFamilyConsensusError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.consensus",
        message="LC-MS isotope/adduct feature-family consensus scoring completed.",
        metadata={
            "input_group_count": result.input_group_count,
            "family_count": result.family_count,
            "promoted_family_count": result.promoted_family_count,
            "conflicting_family_count": result.conflicting_family_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/consensus/evidence",
    response_model=LCMSFeatureFamilyConsensusResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_feature_family_consensus_evidence_route(
    request: Request,
    feature_table_text: str | None = Form(default=None),
    sample_source_text: str | None = Form(default=None),
    blank_source_text: str | None = Form(default=None),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    formula: str | None = Form(default=None),
    expected_anchor_adduct: str = Form(default="[M+H]+"),
    anchor_group_id: str | None = Form(default=None),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    family_rt_tolerance_min: float = Form(default=0.15),
    group_rt_tolerance_min: float = Form(default=0.12),
    min_blank_subtracted_area: float = Form(default=0.0),
    blank_area_ratio_threshold: float = Form(default=0.30),
    possible_background_ratio_threshold: float = Form(default=0.10),
    min_consensus_score_to_promote: float = Form(default=0.62),
    include_background_groups: bool = Form(default=False),
    require_sample_enrichment: bool = Form(default=True),
    score_isotope_relationships: bool = Form(default=True),
    score_adduct_relationships: bool = Form(default=True),
    score_in_source_losses: bool = Form(default=True),
    max_families_to_report: int = Form(default=50),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureFamilyConsensusResult:
    grouping_result = None
    if sample_source_text and sample_source_text.strip():
        runs = [
            LCMSFeatureGroupingRunInput(
                run_id="sample",
                role="sample",
                source_format=source_format,
                source_text=sample_source_text,
            )
        ]
        if blank_source_text and blank_source_text.strip():
            runs.append(
                LCMSFeatureGroupingRunInput(
                    run_id="blank",
                    role="blank",
                    source_format=source_format,
                    source_text=blank_source_text,
                )
            )
        try:
            grouping_result = group_lcms_features(
                LCMSFeatureGroupingRequest(
                    sample_id=sample_id,
                    runs=runs,
                    target_mz_text=target_mz_text,
                    mz_tolerance_da=mz_tolerance_da,
                    ppm_tolerance=ppm_tolerance,
                    group_rt_tolerance_min=group_rt_tolerance_min,
                    family_rt_tolerance_min=family_rt_tolerance_min,
                    blank_area_ratio_threshold=blank_area_ratio_threshold,
                    possible_background_ratio_threshold=possible_background_ratio_threshold,
                    max_groups_to_report=max_families_to_report * 3,
                )
            )
        except (LCMSFeatureGroupingError, ValueError, PydanticValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        payload = LCMSFeatureFamilyConsensusRequest(
            sample_id=sample_id,
            grouping_result=grouping_result,
            feature_table_text=feature_table_text,
            anchor_group_id=anchor_group_id,
            formula=formula,
            expected_anchor_adduct=expected_anchor_adduct,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            family_rt_tolerance_min=family_rt_tolerance_min,
            min_blank_subtracted_area=min_blank_subtracted_area,
            blank_area_ratio_threshold=blank_area_ratio_threshold,
            possible_background_ratio_threshold=possible_background_ratio_threshold,
            include_background_groups=include_background_groups,
            require_sample_enrichment=require_sample_enrichment,
            score_isotope_relationships=score_isotope_relationships,
            score_adduct_relationships=score_adduct_relationships,
            score_in_source_losses=score_in_source_losses,
            max_families_to_report=max_families_to_report,
            min_consensus_score_to_promote=min_consensus_score_to_promote,
        )
        result = score_lcms_feature_family_consensus(payload)
    except (LCMSFeatureFamilyConsensusError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.consensus.evidence",
        message="LC-MS feature-family consensus scoring completed from form evidence.",
        metadata={
            "family_count": result.family_count,
            "promoted_family_count": result.promoted_family_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/features/consensus/upload",
    response_model=LCMSFeatureFamilyConsensusResult,
    dependencies=[Depends(require_access_context)],
)
async def lcms_feature_family_consensus_upload_route(
    request: Request,
    feature_table_file: UploadFile | None = File(default=None),
    sample_file: UploadFile | None = File(default=None),
    blank_file: UploadFile | None = File(default=None),
    source_format: str = Form(default="auto"),
    target_mz_text: str | None = Form(default=None),
    formula: str | None = Form(default=None),
    expected_anchor_adduct: str = Form(default="[M+H]+"),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=20.0),
    family_rt_tolerance_min: float = Form(default=0.15),
    min_consensus_score_to_promote: float = Form(default=0.62),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSFeatureFamilyConsensusResult:
    feature_table_text = None
    if feature_table_file is not None:
        feature_table_text = (await feature_table_file.read()).decode("utf-8", errors="replace")
    grouping_result = None
    if sample_file is not None:
        sample_text = (await sample_file.read()).decode("utf-8", errors="replace")
        runs = [
            LCMSFeatureGroupingRunInput(
                run_id="sample",
                role="sample",
                filename=sample_file.filename,
                source_format=source_format,
                source_text=sample_text,
            )
        ]
        if blank_file is not None:
            blank_text = (await blank_file.read()).decode("utf-8", errors="replace")
            if blank_text.strip():
                runs.append(
                    LCMSFeatureGroupingRunInput(
                        run_id="blank",
                        role="blank",
                        filename=blank_file.filename,
                        source_format=source_format,
                        source_text=blank_text,
                    )
                )
        try:
            grouping_result = group_lcms_features(
                LCMSFeatureGroupingRequest(
                    sample_id=sample_id,
                    runs=runs,
                    target_mz_text=target_mz_text,
                    mz_tolerance_da=mz_tolerance_da,
                    ppm_tolerance=ppm_tolerance,
                    family_rt_tolerance_min=family_rt_tolerance_min,
                )
            )
        except (LCMSFeatureGroupingError, ValueError, PydanticValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = score_lcms_feature_family_consensus(
            LCMSFeatureFamilyConsensusRequest(
                sample_id=sample_id,
                grouping_result=grouping_result,
                feature_table_text=feature_table_text,
                formula=formula,
                expected_anchor_adduct=expected_anchor_adduct,
                mz_tolerance_da=mz_tolerance_da,
                ppm_tolerance=ppm_tolerance,
                family_rt_tolerance_min=family_rt_tolerance_min,
                min_consensus_score_to_promote=min_consensus_score_to_promote,
            )
        )
    except (LCMSFeatureFamilyConsensusError, ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.features.consensus.upload",
        message="LC-MS feature-family consensus scoring completed from upload.",
        metadata={
            "family_count": result.family_count,
            "promoted_family_count": result.promoted_family_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/confidence/candidates/lcms-consensus-bridge",
    response_model=LCMSConsensusCandidateBridgeResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_consensus_candidate_bridge_route(
    payload: LCMSConsensusCandidateBridgeRequest,
    request: Request,
    context: AccessContext = Depends(require_access_context),
) -> LCMSConsensusCandidateBridgeResult:
    try:
        result = score_lcms_candidates_against_consensus(payload)
    except (
        LCMSConfidenceBridgeError,
        LCMSFeatureFamilyConsensusError,
        HRMSError,
        ValueError,
        PydanticValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="confidence.candidates.lcms_consensus_bridge",
        message="LC-MS consensus candidate bridge scoring completed.",
        metadata={
            "candidate_count": result.candidate_count,
            "family_count": result.family_count,
            "eligible_family_count": result.eligible_family_count,
            "best_match": result.best_match.smiles if result.best_match else None,
            "best_score": result.best_match.score if result.best_match else None,
            "human_review_required": True,
        },
    )
    return result


def _looks_like_lcms_family_table(text: str | None) -> bool:
    if not text:
        return False
    first_line = next((line.strip().lower() for line in text.splitlines() if line.strip()), "")
    return "family_id" in first_line and (
        "anchor_mz" in first_line or "anchor_group_id" in first_line
    )


def _count_lcms_family_rows(text: str | None) -> int:
    if not text:
        return 0
    rows = [line for line in text.splitlines() if line.strip()]
    if not rows:
        return 0
    header = rows[0].lower()
    if "family_id" in header:
        return max(0, len(rows) - 1)
    return len(rows)


def _parse_json_candidate_library(text: str) -> list[CandidateInput] | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return None
    parsed = json.loads(stripped)
    if isinstance(parsed, dict):
        parsed = (
            parsed.get("candidates")
            or parsed.get("library")
            or parsed.get("items")
            or parsed.get("entries")
        )
    if not isinstance(parsed, list):
        raise ValueError(
            "Candidate library JSON must be a list or an object with a candidates list."
        )
    candidates: list[CandidateInput] = []
    for item in parsed:
        if isinstance(item, dict):
            candidates.append(CandidateInput.model_validate(item))
        elif isinstance(item, str):
            candidates.extend(parse_candidate_text(item))
        else:
            raise ValueError("Candidate library JSON entries must be objects or SMILES strings.")
    if not candidates:
        raise ValueError("No candidate structures were found in the library JSON.")
    if len(candidates) > 25:
        raise ValueError("Library dereplication is limited to 25 candidate structures per run.")
    return candidates


def _parse_delimited_candidate_library(text: str) -> list[CandidateInput] | None:
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = "\t" if "\t" in first_line else ","
    header = [part.strip().lower() for part in first_line.split(delimiter)]
    if "smiles" not in header:
        return None
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    candidates: list[CandidateInput] = []
    for row in reader:
        lowered = {str(key).strip().lower(): value for key, value in row.items() if key is not None}
        smiles = lowered.get("smiles") or lowered.get("structure") or lowered.get("smiles_string")
        if not smiles or not str(smiles).strip():
            continue
        candidates.append(
            CandidateInput(
                name=lowered.get("name") or lowered.get("compound") or lowered.get("id"),
                smiles=str(smiles),
                role=lowered.get("role") or lowered.get("source"),
            )
        )
    if not candidates:
        raise ValueError(
            "Candidate library table has a smiles header but no usable candidate rows."
        )
    if len(candidates) > 25:
        raise ValueError("Library dereplication is limited to 25 candidate structures per run.")
    return candidates


def _parse_lcms_candidate_library(text: str | None) -> list[CandidateInput]:
    if text is None or not text.strip():
        return []
    parsed_json = _parse_json_candidate_library(text)
    if parsed_json is not None:
        return parsed_json
    parsed_table = _parse_delimited_candidate_library(text)
    if parsed_table is not None:
        return parsed_table
    return parse_candidate_text(text)


def _lcms_library_dereplication_result(
    *,
    sample_id: str | None,
    filename: str | None,
    file_sha256: str | None,
    candidate_library_text: str | None,
    lcms_family_table_text: str | None,
    adduct: str,
    mz_tolerance_da: float,
    ppm_tolerance: float,
    min_family_consensus_score: float,
    require_promoted_family: bool,
    selected_family_id: str | None,
    source_kind: str,
) -> LCMSLibraryDereplicationResult:
    try:
        candidates = _parse_lcms_candidate_library(candidate_library_text)
    except (ValueError, PydanticValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Candidate library could not be parsed: {exc}"
        ) from exc

    family_count = _count_lcms_family_rows(lcms_family_table_text)
    base_metadata: dict[str, Any] = {
        "source_kind": source_kind,
        "underlying_logic": "confidence.candidates.lcms_consensus_bridge",
        "lcms_family_table_supplied": bool(
            lcms_family_table_text and lcms_family_table_text.strip()
        ),
        "candidate_library_supplied": bool(
            candidate_library_text and candidate_library_text.strip()
        ),
    }
    if file_sha256:
        base_metadata["file_sha256"] = file_sha256

    caution_note = (
        "Library dereplication is decision support only; candidate matches require expert review "
        "with orthogonal evidence and do not confirm identity."
    )

    if candidates and lcms_family_table_text and lcms_family_table_text.strip():
        try:
            bridge_result = score_lcms_candidates_against_consensus(
                LCMSConsensusCandidateBridgeRequest(
                    sample_id=sample_id,
                    candidates=candidates,
                    lcms_family_table_text=lcms_family_table_text,
                    adduct=adduct,
                    mz_tolerance_da=mz_tolerance_da,
                    ppm_tolerance=ppm_tolerance,
                    min_family_consensus_score=min_family_consensus_score,
                    require_promoted_family=require_promoted_family,
                    selected_family_id=selected_family_id,
                )
            )
        except (
            LCMSConfidenceBridgeError,
            LCMSFeatureFamilyConsensusError,
            HRMSError,
            ValueError,
            PydanticValidationError,
        ) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        best_summary = bridge_result.best_match.evidence_summary if bridge_result.best_match else []
        return LCMSLibraryDereplicationResult(
            sample_id=sample_id,
            filename=filename,
            file_sha256=file_sha256,
            adduct=bridge_result.adduct,
            label="candidate_matches_require_review"
            if bridge_result.best_match
            else "insufficient_evidence_for_dereplication",
            status="review_candidate_library_match"
            if bridge_result.best_match
            else "no_candidate_family_match_above_threshold",
            candidate_count=bridge_result.candidate_count,
            family_count=bridge_result.family_count,
            eligible_family_count=bridge_result.eligible_family_count,
            promoted_family_count=bridge_result.promoted_family_count,
            best_match=bridge_result.best_match,
            matches=bridge_result.matches,
            evidence_table_text=bridge_result.evidence_table_text,
            evidence_summary=[
                "Candidate library entries were compared with LC-MS feature-family consensus evidence.",
                *best_summary,
            ],
            warnings=list(bridge_result.warnings),
            notes=[*bridge_result.notes, caution_note],
            metadata={**base_metadata, "bridge_metadata": bridge_result.metadata},
            human_review_required=True,
        )

    missing: list[str] = []
    if not candidates:
        missing.append("candidate library")
    if not (lcms_family_table_text and lcms_family_table_text.strip()):
        missing.append("LC-MS feature-family consensus table")
    warning = (
        "No dereplication match was attempted because "
        + " and ".join(missing)
        + " evidence was not supplied."
    )
    return LCMSLibraryDereplicationResult(
        sample_id=sample_id,
        filename=filename,
        file_sha256=file_sha256,
        adduct=adduct,
        label="metadata_only_no_identification",
        status="metadata_only_no_library_match_run",
        candidate_count=len(candidates),
        family_count=family_count,
        eligible_family_count=0,
        promoted_family_count=0,
        evidence_summary=[
            "The upload was inspected for candidate-library and LC-MS feature-family evidence.",
            warning,
        ],
        warnings=[warning],
        notes=[caution_note],
        metadata=base_metadata,
        human_review_required=True,
    )


@router.post(
    "/ms/lcms/dereplication/evidence",
    response_model=LCMSLibraryDereplicationResult,
    dependencies=[Depends(require_access_context)],
)
def lcms_library_dereplication_evidence_route(
    request: Request,
    candidates_text: str | None = Form(default=None),
    library_text: str | None = Form(default=None),
    lcms_family_table_text: str | None = Form(default=None),
    adduct: str = Form(default="[M+H]+"),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=10.0),
    min_family_consensus_score: float = Form(default=0.42),
    require_promoted_family: bool = Form(default=True),
    selected_family_id: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSLibraryDereplicationResult:
    candidate_library_text = candidates_text or library_text
    if not (candidate_library_text and candidate_library_text.strip()) and not (
        lcms_family_table_text and lcms_family_table_text.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide candidates_text or library_text, and LC-MS family evidence when available.",
        )
    result = _lcms_library_dereplication_result(
        sample_id=sample_id,
        filename=None,
        file_sha256=None,
        candidate_library_text=candidate_library_text,
        lcms_family_table_text=lcms_family_table_text,
        adduct=adduct,
        mz_tolerance_da=mz_tolerance_da,
        ppm_tolerance=ppm_tolerance,
        min_family_consensus_score=min_family_consensus_score,
        require_promoted_family=require_promoted_family,
        selected_family_id=selected_family_id,
        source_kind="form_evidence",
    )
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.dereplication.evidence",
        message="LC-MS library dereplication evidence wrapper completed.",
        metadata={
            "candidate_count": result.candidate_count,
            "family_count": result.family_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/ms/lcms/dereplication/upload",
    response_model=LCMSLibraryDereplicationResult,
    dependencies=[Depends(require_access_context)],
)
async def lcms_library_dereplication_upload_route(
    request: Request,
    file: UploadFile = File(...),
    candidates_text: str | None = Form(default=None),
    lcms_family_table_text: str | None = Form(default=None),
    adduct: str = Form(default="[M+H]+"),
    mz_tolerance_da: float = Form(default=0.02),
    ppm_tolerance: float = Form(default=10.0),
    min_family_consensus_score: float = Form(default=0.42),
    require_promoted_family: bool = Form(default=True),
    selected_family_id: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> LCMSLibraryDereplicationResult:
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Uploaded dereplication file is empty.")
    filename = file.filename or "lcms_library_dereplication.txt"
    file_text = raw_bytes.decode("utf-8", errors="replace")
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    file_is_family_table = _looks_like_lcms_family_table(file_text)
    family_table_text = lcms_family_table_text
    candidate_library_text = candidates_text
    source_kind = "candidate_library_upload"
    if file_is_family_table and not family_table_text:
        family_table_text = file_text
        source_kind = "lcms_family_table_upload"
    elif not candidate_library_text:
        candidate_library_text = file_text

    result = _lcms_library_dereplication_result(
        sample_id=sample_id,
        filename=filename,
        file_sha256=file_sha256,
        candidate_library_text=candidate_library_text,
        lcms_family_table_text=family_table_text,
        adduct=adduct,
        mz_tolerance_da=mz_tolerance_da,
        ppm_tolerance=ppm_tolerance,
        min_family_consensus_score=min_family_consensus_score,
        require_promoted_family=require_promoted_family,
        selected_family_id=selected_family_id,
        source_kind=source_kind,
    )
    _audit_from_context(
        request,
        context=context,
        event_type="ms.lcms.dereplication.upload",
        message="LC-MS library dereplication upload wrapper completed.",
        metadata={
            "filename": filename,
            "file_sha256": file_sha256,
            "candidate_count": result.candidate_count,
            "family_count": result.family_count,
            "label": result.label,
            "human_review_required": True,
        },
    )
    return result


@router.post(
    "/carbon13/upload",
    response_model=Carbon13AnalysisReport,
    dependencies=[Depends(require_access_context)],
)
async def carbon13_upload_route(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    context: AccessContext = Depends(require_access_context),
) -> Carbon13AnalysisReport:
    filename = file.filename or "carbon13_peaks.csv"
    content = await file.read()
    try:
        preview = parse_carbon13_table(filename, content, solvent=solvent)
        report = analyze_carbon13(
            smiles=smiles,
            peaks=preview.peaks,
            solvent=solvent,
            sample_id=sample_id,
        )
    except Carbon13ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    combined_notes = list(report.notes)
    for warning in preview.warnings:
        if warning not in combined_notes:
            combined_notes.append(warning)
    report = report.model_copy(update={"notes": combined_notes})
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.upload.analyze",
        message="¹³C peak table uploaded and analyzed.",
        metadata={"filename": filename, "sample_id": sample_id, "label": report.label},
    )
    return report


@router.post(
    "/carbon13/spectrum/preview",
    response_model=Carbon13UploadPreview,
    dependencies=[Depends(require_access_context)],
)
async def carbon13_spectrum_preview_route(
    request: Request,
    file: UploadFile = File(...),
    solvent: str | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    processed_baseline_correction: str = Form(default="none"),
    processed_baseline_order: int = Form(default=3),
    context: AccessContext = Depends(require_access_context),
) -> Carbon13UploadPreview:
    filename = file.filename or "carbon13_spectrum.csv"
    content = await file.read()
    display_mode_value = _unwrap_form_default(display_mode)
    vertical_gain_value = _coerce_optional_form_float(vertical_gain, default=1.0)
    debug_preview_value = _coerce_optional_form_bool(debug_preview, default=False)
    try:
        preview = parse_carbon13_processed_spectrum(
            filename,
            content,
            solvent=solvent,
            peak_sensitivity=peak_sensitivity,
            mask_solvent_regions=mask_solvent_regions,
            display_mode=display_mode_value,
            vertical_gain=vertical_gain_value,
            debug_preview=debug_preview_value,
            processed_baseline_correction=_unwrap_form_default(processed_baseline_correction),
            processed_baseline_order=int(_unwrap_form_default(processed_baseline_order) or 3),
        )
    except Carbon13ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.spectrum.preview",
        message="¹³C processed spectrum preview generated.",
        metadata={
            "filename": filename,
            "solvent": solvent,
            "observed_signal_count": preview.observed_signal_count,
        },
    )
    return preview


@router.post(
    "/carbon13/spectrum/analyze",
    response_model=Carbon13AnalysisReport,
    dependencies=[Depends(require_access_context)],
)
async def carbon13_spectrum_analyze_route(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    manual_peaks_json: str | None = Form(default=None),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    processed_baseline_correction: str = Form(default="none"),
    processed_baseline_order: int = Form(default=3),
    context: AccessContext = Depends(require_access_context),
) -> Carbon13AnalysisReport:
    filename = file.filename or "carbon13_spectrum.csv"
    content = await file.read()
    display_mode_value = _unwrap_form_default(display_mode)
    vertical_gain_value = _coerce_optional_form_float(vertical_gain, default=1.0)
    debug_preview_value = _coerce_optional_form_bool(debug_preview, default=False)
    try:
        preview = parse_carbon13_processed_spectrum(
            filename,
            content,
            solvent=solvent,
            peak_sensitivity=peak_sensitivity,
            mask_solvent_regions=mask_solvent_regions,
            display_mode=display_mode_value,
            vertical_gain=vertical_gain_value,
            debug_preview=debug_preview_value,
            processed_baseline_correction=_unwrap_form_default(processed_baseline_correction),
            processed_baseline_order=int(_unwrap_form_default(processed_baseline_order) or 3),
        )
        reviewed_peaks = _manual_carbon13_peaks_from_json(manual_peaks_json, solvent=solvent)
        report = analyze_carbon13(
            smiles=smiles,
            peaks=reviewed_peaks or preview.peaks,
            solvent=solvent,
            sample_id=sample_id,
        )
    except (Carbon13ParseError, StructureParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="¹³C processed spectrum analysis") from exc
    combined_notes = list(report.notes)
    if (
        manual_peaks_json
        and "Reviewer-adjusted ¹³C peak acceptance/exclusion decisions were used for analysis."
        not in combined_notes
    ):
        combined_notes.append(
            "Reviewer-adjusted ¹³C peak acceptance/exclusion decisions were used for analysis."
        )
    for warning in preview.warnings:
        if warning not in combined_notes:
            combined_notes.append(warning)
    report = report.model_copy(update={"notes": combined_notes})
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.spectrum.analyze",
        message="¹³C processed spectrum uploaded and analyzed.",
        metadata={"filename": filename, "sample_id": sample_id, "label": report.label},
    )
    return report


def _carbon13_raw_fid_preview_from_upload(
    *,
    filename: str,
    content: bytes,
    solvent: str | None,
    smiles: str | None,
    proton_nmr_text: str | None,
    reference_ppm: float | None,
    settings: FIDProcessingSettings,
    raw_upload_provenance: dict[str, object] | None = None,
) -> tuple[Carbon13UploadPreview, FIDPreviewReport]:
    fid_preview = process_bruker_1d_zip(
        filename=filename,
        content=content,
        solvent=solvent,
        nucleus="13C",
        reference_ppm=reference_ppm,
        reference_nmr_text=None,
        settings=settings,
        expected_total_h=None,
        expected_non_labile_h=None,
        raw_upload_provenance=raw_upload_provenance,
    )
    peaks = carbon13_peaks_from_shift_values(
        [(peak.shift_ppm, peak.integration_h) for peak in fid_preview.inferred_peaks],
        solvent=solvent,
    )
    peaks, context_meta, context_notes = refine_carbon13_peaks_with_context(
        peaks,
        smiles=smiles,
        proton_nmr_text=proton_nmr_text,
        solvent=solvent,
    )
    warnings = list(fid_preview.warnings)
    warnings.extend(note for note in context_notes if note not in warnings)
    warnings.append(
        "Raw ¹³C FID beta processing reuses the automatic 1D FID transform path; review phasing, baseline, and peak picking before signoff."
    )
    preview = Carbon13UploadPreview(
        filename=filename,
        source_mode="raw_fid",
        observed_signal_count=len(peaks),
        peaks=peaks,
        warnings=warnings,
        metadata={
            "solvent": solvent,
            "format_detected": fid_preview.format_detected,
            "point_count": fid_preview.point_count,
            "preview_points": [
                point.model_dump(mode="json") for point in fid_preview.preview_points
            ],
            "original_spectrum_state": fid_preview.metadata.get("original_spectrum_state"),
            "baseline_flatness_qa": fid_preview.metadata.get("baseline_flatness_qa"),
            "display_preprocessing": fid_preview.metadata.get("display_preprocessing"),
            "evidence_trace_mode": fid_preview.metadata.get("evidence_trace_mode"),
            "display_mode": fid_preview.metadata.get("display_mode"),
            "display_gain": fid_preview.metadata.get("display_gain"),
            "baseline_lock_visual_only": fid_preview.metadata.get("baseline_lock_visual_only"),
            "preview_downsampling": fid_preview.metadata.get("preview_downsampling"),
            "fid_processing": fid_preview.processing_metadata.model_dump(mode="json"),
            "raw_upload_provenance": fid_preview.processing_metadata.raw_upload_provenance,
            "analysis_artifact_policy": fid_preview.processing_metadata.analysis_artifact_policy,
            "fid_quality": fid_preview.metadata.get("fid_quality"),
            "baseline_qa": fid_preview.metadata.get("baseline_qa"),
            "display": fid_preview.metadata.get("display"),
            "context_guidance": context_meta,
        },
    )
    return (preview, fid_preview)


@router.post(
    "/carbon13/fid/preview",
    response_model=Carbon13UploadPreview,
    dependencies=[Depends(require_access_context)],
)
async def carbon13_fid_preview_route(
    request: Request,
    file: UploadFile = File(...),
    smiles: str | None = Form(default=None),
    proton_nmr_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    reference_ppm: float | None = Form(default=77.0),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> Carbon13UploadPreview:
    filename = file.filename or "carbon13_dataset.zip"
    content = await file.read()
    raw_upload_provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview, _fid_preview = _carbon13_raw_fid_preview_from_upload(
            filename=filename,
            content=content,
            solvent=solvent,
            smiles=smiles,
            proton_nmr_text=proton_nmr_text,
            reference_ppm=reference_ppm,
            settings=settings,
            raw_upload_provenance=raw_upload_provenance,
        )
    except (FIDProcessingError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="¹³C raw FID preview") from exc
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.fid.preview",
        message="¹³C raw FID beta preview generated.",
        metadata={
            "filename": filename,
            "solvent": solvent,
            "observed_signal_count": preview.observed_signal_count,
        },
    )
    return preview


@router.post(
    "/carbon13/fid/analyze",
    response_model=Carbon13AnalysisReport,
    dependencies=[Depends(require_access_context)],
)
async def carbon13_fid_analyze_route(
    request: Request,
    file: UploadFile = File(...),
    smiles: str = Form(...),
    proton_nmr_text: str | None = Form(default=None),
    solvent: str | None = Form(default=None),
    sample_id: str | None = Form(default=None),
    reference_ppm: float | None = Form(default=77.0),
    selected_preset: str | None = Form(default="balanced"),
    processing_preset: str | None = Form(default=None),
    zero_fill_factor: int | None = Form(default=None),
    line_broadening_hz: float | None = Form(default=None),
    apodization_mode: str = Form(default="exponential"),
    apply_group_delay: bool = Form(default=True),
    auto_phase: bool = Form(default=True),
    auto_baseline: bool = Form(default=True),
    phase_mode: str = Form(default="auto"),
    phase_p0: float = Form(default=0.0),
    phase_p1: float = Form(default=0.0),
    baseline_correction: str = Form(default="bernstein"),
    baseline_order: int = Form(default=3),
    baseline_lock: bool | None = Form(default=None),
    peak_sensitivity: float | None = Form(default=None),
    mask_solvent_regions: bool = Form(default=True),
    manual_peaks_json: str | None = Form(default=None),
    display_mode: str = Form(default="real"),
    vertical_gain: float = Form(default=1.0),
    debug_preview: bool = Form(default=False),
    context: AccessContext = Depends(require_access_context),
) -> Carbon13AnalysisReport:
    filename = file.filename or "carbon13_dataset.zip"
    content = await file.read()
    raw_upload_provenance = _raw_fid_upload_provenance(
        request,
        filename=filename,
        content=content,
        content_type=file.content_type,
        user_id=context.user_id,
    )
    settings = _fid_settings_from_form(
        selected_preset=selected_preset,
        processing_preset=processing_preset,
        zero_fill_factor=zero_fill_factor,
        line_broadening_hz=line_broadening_hz,
        apodization_mode=apodization_mode,
        apply_group_delay=apply_group_delay,
        auto_phase=auto_phase,
        auto_baseline=auto_baseline,
        phase_mode=phase_mode,
        phase_p0=phase_p0,
        phase_p1=phase_p1,
        baseline_correction=baseline_correction,
        baseline_order=baseline_order,
        baseline_lock=baseline_lock,
        peak_sensitivity=peak_sensitivity,
        mask_solvent_regions=mask_solvent_regions,
        display_mode=display_mode,
        vertical_gain=vertical_gain,
        debug_preview=debug_preview,
    )
    try:
        preview, _fid_preview = _carbon13_raw_fid_preview_from_upload(
            filename=filename,
            content=content,
            solvent=solvent,
            smiles=smiles,
            proton_nmr_text=proton_nmr_text,
            reference_ppm=reference_ppm,
            settings=settings,
            raw_upload_provenance=raw_upload_provenance,
        )
        reviewed_peaks = _manual_carbon13_peaks_from_json(manual_peaks_json, solvent=solvent)
        report = analyze_carbon13(
            smiles=smiles,
            peaks=reviewed_peaks or preview.peaks,
            solvent=solvent,
            sample_id=sample_id,
        )
    except (FIDProcessingError, StructureParseError, PydanticValidationError, ValueError) as exc:
        raise _upload_http_400(exc, operation="¹³C raw FID analysis") from exc
    combined_notes = list(report.notes)
    if (
        manual_peaks_json
        and "Reviewer-adjusted ¹³C peak acceptance/exclusion decisions were used for analysis."
        not in combined_notes
    ):
        combined_notes.append(
            "Reviewer-adjusted ¹³C peak acceptance/exclusion decisions were used for analysis."
        )
    for warning in preview.warnings:
        if warning not in combined_notes:
            combined_notes.append(warning)
    report = report.model_copy(update={"notes": combined_notes})
    _audit_from_context(
        request,
        context=context,
        event_type="carbon13.fid.analyze",
        message="¹³C raw FID beta uploaded and analyzed.",
        metadata={"filename": filename, "sample_id": sample_id, "label": report.label},
    )
    return report


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    session_factory = create_session_factory(settings.database_url)
    startup_issues = validate_startup_settings(settings)

    @asynccontextmanager
    async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_db(session_factory)
        method_store.ensure_builtin_methods(session_factory)
        analytics_store.ensure_default_tasks(session_factory)
        ml_store.ensure_builtin_ml_tasks(session_factory)
        ai_store.ensure_builtin_services(session_factory)
        product_store.ensure_default_programs(session_factory)
        yield

    app = FastAPI(
        title="NMRCheck API",
        version=settings.release_version,
        description=(
            "API for rule-based ¹H NMR text analysis against a structure represented as SMILES, now with email verification, password reset, Alembic-ready persistence, optional Redis/RQ background workers, review workflow, admin metrics dashboards, processed spectrum upload for CSV/TSV/JCAMP-DX files, Bruker and Varian/Agilent 1D raw FID beta processing, E2E regression scaffolds, deployment diagnostics, scientific validation fixtures, CI release-health checks, evidence-confidence reporting, ¹H/¹³C solvent-aware spectral evidence scoring, processed NMR/MS evidence layers, unified candidate confidence ranking, and regulatory-ready structure elucidation report composition."
        ),
        lifespan=app_lifespan,
    )
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def pwa_freshness_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = _correlation_id_from_request(request)
        request.state.correlation_id = correlation_id
        generated_at = _generated_at_iso()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled API error",
                extra={"correlation_id": correlation_id, "path": request.url.path},
            )
            response = JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=_stable_unavailable_payload(request),
            )
        data_mode = "unavailable" if response.status_code >= 500 else "live"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-MolTrace-Backend-Version"] = settings.release_version
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        response.headers[REQUEST_ID_HEADER] = correlation_id
        response.headers[DATA_MODE_HEADER] = data_mode
        response.headers[GENERATED_AT_HEADER] = generated_at
        return response

    @app.exception_handler(HTTPException)
    async def safe_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning(
                "HTTP exception returned as safe error response",
                extra={
                    "correlation_id": _request_correlation_id(request),
                    "path": request.url.path,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
            content = _stable_unavailable_payload(request)
            status_code = exc.status_code
        else:
            content = {"detail": _safe_http_exception_detail(exc.status_code, exc.detail)}
            status_code = exc.status_code
        return JSONResponse(
            status_code=status_code,
            content=content,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def safe_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info(
            "Request validation failed",
            extra={
                "correlation_id": _request_correlation_id(request),
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": _safe_validation_errors(exc)},
        )

    app.include_router(router)
    from .nmr2d_routes import router as nmr2d_router

    app.include_router(nmr2d_router)
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.api_key = settings.api_key
    app.state.startup_issues = startup_issues
    app.state.started_at = datetime.now(UTC)
    return app
