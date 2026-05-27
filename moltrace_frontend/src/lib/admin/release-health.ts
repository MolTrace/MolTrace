export type ReleaseHealthRuntimeEffectValue = string | number | boolean | null

export type ReleaseHealthRuntimeEffect = Record<string, ReleaseHealthRuntimeEffectValue>

export type RawFidManualPromotionGate = {
  status: string
  visibility: string
  policy: string
  runtimeActivationAllowed: boolean
  requiresManualCodeChange: boolean
  requiresExplicitRuntimeFeatureFlag: boolean
  ciStep: string
  ciArtifact: string
  outputDir: string
  ciCommand: string
}

export type RawFidManualPromotionDesign = {
  status: string
  visibility: string
  policy: string
  runtimeActivationAllowed: boolean
  docPath: string
  docTitle: string
  requiredGuardrailCommand: string
  requiredGates: string[]
  promotionStages: string[]
  rollbackMode: string
}

export type RawFidProvenanceChecksumArtifact = {
  status: string
  visibility: string
  policy: string
  runtimeActivationAllowed: boolean
  ciStep: string
  ciArtifact: string
  outputDir: string
  ciCommand: string
  files: string[]
}

export type RawFidShadowComparisonArtifact = {
  status: string
  visibility: string
  policy: string
  runtimeActivationAllowed: boolean
  ciStep: string
  ciArtifact: string
  outputDir: string
  ciCommand: string
  files: string[]
}

export type RawFidReleaseReadinessArtifact = {
  status: string
  visibility: string
  policy: string
  runtimeActivationAllowed: boolean
  ciStep: string
  ciArtifact: string
  outputDir: string
  ciCommand: string
  files: string[]
}

export type RawFidPromptSidecarSmoke = {
  status: string
  policy: string
  activeVisiblePipeline: string
  promptPipelineActive: boolean
  failureScope: string
  ciCommand: string
  adminReportEndpoint: string
  runtimeEffect: ReleaseHealthRuntimeEffect
  manualPromotionGate: RawFidManualPromotionGate | null
  manualPromotionDesign: RawFidManualPromotionDesign | null
  provenanceChecksumArtifact: RawFidProvenanceChecksumArtifact | null
  shadowComparisonArtifact: RawFidShadowComparisonArtifact | null
  releaseReadinessArtifact: RawFidReleaseReadinessArtifact | null
}

export type ReleaseHealthDiagnostics = {
  rawFidPromptSidecarSmoke: RawFidPromptSidecarSmoke | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readString(record: Record<string, unknown>, key: string): string {
  const value = record[key]
  if (typeof value === "string") return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function readBoolean(record: Record<string, unknown>, key: string): boolean {
  const value = record[key]
  if (typeof value === "boolean") return value
  if (typeof value === "string") return value.trim().toLowerCase() === "true"
  return false
}

function readStringArray(record: Record<string, unknown>, key: string): string[] {
  const value = record[key]
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
}

function readRuntimeEffect(value: unknown): ReleaseHealthRuntimeEffect {
  if (!isRecord(value)) return {}
  return Object.entries(value).reduce<ReleaseHealthRuntimeEffect>((acc, [key, entry]) => {
    if (typeof entry === "string" || typeof entry === "number" || typeof entry === "boolean" || entry === null) {
      acc[key] = entry
    }
    return acc
  }, {})
}

function parseManualPromotionGate(value: unknown): RawFidManualPromotionGate | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    visibility: readString(value, "visibility"),
    policy: readString(value, "policy"),
    runtimeActivationAllowed: readBoolean(value, "runtime_activation_allowed"),
    requiresManualCodeChange: readBoolean(value, "requires_manual_code_change"),
    requiresExplicitRuntimeFeatureFlag: readBoolean(value, "requires_explicit_runtime_feature_flag"),
    ciStep: readString(value, "ci_step"),
    ciArtifact: readString(value, "ci_artifact"),
    outputDir: readString(value, "output_dir"),
    ciCommand: readString(value, "ci_command"),
  }
}

function parseManualPromotionDesign(value: unknown): RawFidManualPromotionDesign | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    visibility: readString(value, "visibility"),
    policy: readString(value, "policy"),
    runtimeActivationAllowed: readBoolean(value, "runtime_activation_allowed"),
    docPath: readString(value, "doc_path"),
    docTitle: readString(value, "doc_title"),
    requiredGuardrailCommand: readString(value, "required_guardrail_command"),
    requiredGates: readStringArray(value, "required_gates"),
    promotionStages: readStringArray(value, "promotion_stages"),
    rollbackMode: readString(value, "rollback_mode"),
  }
}

function parseProvenanceChecksumArtifact(value: unknown): RawFidProvenanceChecksumArtifact | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    visibility: readString(value, "visibility"),
    policy: readString(value, "policy"),
    runtimeActivationAllowed: readBoolean(value, "runtime_activation_allowed"),
    ciStep: readString(value, "ci_step"),
    ciArtifact: readString(value, "ci_artifact"),
    outputDir: readString(value, "output_dir"),
    ciCommand: readString(value, "ci_command"),
    files: readStringArray(value, "files"),
  }
}

function parseShadowComparisonArtifact(value: unknown): RawFidShadowComparisonArtifact | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    visibility: readString(value, "visibility"),
    policy: readString(value, "policy"),
    runtimeActivationAllowed: readBoolean(value, "runtime_activation_allowed"),
    ciStep: readString(value, "ci_step"),
    ciArtifact: readString(value, "ci_artifact"),
    outputDir: readString(value, "output_dir"),
    ciCommand: readString(value, "ci_command"),
    files: readStringArray(value, "files"),
  }
}

function parseReleaseReadinessArtifact(value: unknown): RawFidReleaseReadinessArtifact | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    visibility: readString(value, "visibility"),
    policy: readString(value, "policy"),
    runtimeActivationAllowed: readBoolean(value, "runtime_activation_allowed"),
    ciStep: readString(value, "ci_step"),
    ciArtifact: readString(value, "ci_artifact"),
    outputDir: readString(value, "output_dir"),
    ciCommand: readString(value, "ci_command"),
    files: readStringArray(value, "files"),
  }
}

function parseRawFidPromptSidecarSmoke(value: unknown): RawFidPromptSidecarSmoke | null {
  if (!isRecord(value)) return null
  return {
    status: readString(value, "status"),
    policy: readString(value, "policy"),
    activeVisiblePipeline: readString(value, "active_visible_pipeline"),
    promptPipelineActive: readBoolean(value, "prompt_pipeline_active"),
    failureScope: readString(value, "failure_scope"),
    ciCommand: readString(value, "ci_command"),
    adminReportEndpoint: readString(value, "admin_report_endpoint"),
    runtimeEffect: readRuntimeEffect(value.runtime_effect),
    manualPromotionGate: parseManualPromotionGate(value.manual_promotion_gate),
    manualPromotionDesign: parseManualPromotionDesign(value.manual_promotion_design),
    provenanceChecksumArtifact: parseProvenanceChecksumArtifact(value.provenance_checksum_artifact),
    shadowComparisonArtifact: parseShadowComparisonArtifact(value.shadow_comparison_artifact),
    releaseReadinessArtifact: parseReleaseReadinessArtifact(value.release_readiness_artifact),
  }
}

export function parseReleaseHealthDiagnostics(payload: unknown): ReleaseHealthDiagnostics {
  if (!isRecord(payload)) return { rawFidPromptSidecarSmoke: null }
  return {
    rawFidPromptSidecarSmoke: parseRawFidPromptSidecarSmoke(payload.raw_fid_prompt_sidecar_smoke),
  }
}
