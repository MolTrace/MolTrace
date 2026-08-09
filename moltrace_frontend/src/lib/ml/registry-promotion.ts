/**
 * Promotion is the second, narrower half of an approval: approving a candidate is a product
 * decision, and making predictions resolve to it is a separate one that needs facts the
 * artifact row does not carry — which role it plays, for which nucleus, and what data built
 * it. None of those may be defaulted here. A guessed role would promote an artifact into a
 * slot nobody chose, and a guessed data lineage would make an unreproducible promotion look
 * reproducible, which is the opposite of what the lineage is for.
 *
 * So every required field is collected from the reviewer or the request is not sent, and
 * approving with no promotion block at all stays a first-class outcome: approved, not serving.
 */

export const PROMOTION_ROLES = [
  "nmrnet_checkpoint",
  "hose_kb",
  "lora_adapter",
  "embedding_model",
  "csi_fingerid",
  "rt_predictor",
  "dp4_ranker",
] as const

export type PromotionRole = (typeof PROMOTION_ROLES)[number]

/** Display spellings the generic humanizer would get wrong (casing, initialisms). */
const ROLE_LABELS: Record<PromotionRole, string> = {
  nmrnet_checkpoint: "NMRNet checkpoint",
  hose_kb: "HOSE knowledge base",
  lora_adapter: "LoRA adapter",
  embedding_model: "Embedding model",
  csi_fingerid: "CSI:FingerID",
  rt_predictor: "Retention-time predictor",
  dp4_ranker: "DP4 ranker",
}

export function promotionRoleLabel(role: string): string {
  return ROLE_LABELS[role as PromotionRole] ?? role
}

/** Free-text mirror of the form. Every field is a string so an empty box stays empty. */
export type PromotionDraft = {
  role: string
  semanticVersion: string
  datasetSnapshotHash: string
  datasetRowCount: string
  nucleus: string
  datasetTag: string
  datasetSource: string
  artifactSha256: string
  confidenceBandPpm: string
}

export const EMPTY_PROMOTION_DRAFT: PromotionDraft = {
  role: "",
  semanticVersion: "",
  datasetSnapshotHash: "",
  datasetRowCount: "",
  nucleus: "",
  datasetTag: "",
  datasetSource: "",
  artifactSha256: "",
  confidenceBandPpm: "",
}

export type PromotionFieldErrors = Partial<Record<keyof PromotionDraft, string>>

export type PromotionBuildResult =
  | { ok: true; body: Record<string, unknown> }
  | { ok: false; errors: PromotionFieldErrors }

const SHA256_HEX = /^[0-9a-fA-F]{64}$/

/** True when the reviewer has typed nothing at all — the "approve without promoting" case. */
export function isPromotionDraftEmpty(draft: PromotionDraft): boolean {
  return Object.values(draft).every((v) => v.trim().length === 0)
}

/**
 * Validate the draft against the promotion contract and return the request block, or the
 * per-field reasons it cannot be sent. Bounds mirror the server's so a reviewer sees which
 * box is wrong instead of one rejection for the whole form.
 *
 * Optional fields left blank are omitted rather than sent empty: the block rejects keys it
 * does not declare, and an empty string is not the same as "not supplied".
 */
export function buildRegistryPromotionBody(draft: PromotionDraft): PromotionBuildResult {
  const errors: PromotionFieldErrors = {}

  const role = draft.role.trim()
  if (!role) {
    errors.role = "Choose the role this artifact will serve. It cannot be inferred from the artifact."
  } else if (!PROMOTION_ROLES.includes(role as PromotionRole)) {
    errors.role = "That is not a role the registry serves."
  }

  const semanticVersion = draft.semanticVersion.trim()
  if (!semanticVersion) {
    errors.semanticVersion = "A semantic version is required."
  } else if (semanticVersion.length > 64) {
    errors.semanticVersion = "Keep the semantic version to 64 characters or fewer."
  }

  const datasetSnapshotHash = draft.datasetSnapshotHash.trim()
  if (!datasetSnapshotHash) {
    errors.datasetSnapshotHash =
      "A dataset snapshot hash is required — a promotion with no data lineage cannot be reproduced."
  } else if (datasetSnapshotHash.length > 200) {
    errors.datasetSnapshotHash = "Keep the dataset snapshot hash to 200 characters or fewer."
  }

  const rowCountRaw = draft.datasetRowCount.trim()
  let datasetRowCount: number | null = null
  if (!rowCountRaw) {
    errors.datasetRowCount = "A dataset row count is required."
  } else if (!/^\d+$/.test(rowCountRaw)) {
    errors.datasetRowCount = "Enter the dataset row count as a whole number."
  } else {
    datasetRowCount = Number.parseInt(rowCountRaw, 10)
    if (!Number.isSafeInteger(datasetRowCount)) {
      errors.datasetRowCount = "That dataset row count is too large to record."
      datasetRowCount = null
    }
  }

  const nucleus = draft.nucleus.trim()
  if (nucleus.length > 16) {
    errors.nucleus = "Keep the nucleus to 16 characters or fewer."
  }

  const datasetTag = draft.datasetTag.trim()
  if (datasetTag.length > 200) {
    errors.datasetTag = "Keep the dataset tag to 200 characters or fewer."
  }

  const datasetSource = draft.datasetSource.trim()
  if (datasetSource.length > 200) {
    errors.datasetSource = "Keep the dataset source to 200 characters or fewer."
  }

  const artifactSha256 = draft.artifactSha256.trim()
  if (artifactSha256 && !SHA256_HEX.test(artifactSha256)) {
    errors.artifactSha256 = "A SHA-256 digest is exactly 64 hexadecimal characters."
  }

  const bandRaw = draft.confidenceBandPpm.trim()
  let confidenceBandPpm: number | null = null
  if (bandRaw) {
    const parsed = Number(bandRaw)
    if (!Number.isFinite(parsed) || parsed <= 0) {
      errors.confidenceBandPpm = "Enter a confidence band greater than 0 ppm."
    } else {
      confidenceBandPpm = parsed
    }
  }

  if (Object.keys(errors).length > 0) return { ok: false, errors }

  const body: Record<string, unknown> = {
    role,
    semantic_version: semanticVersion,
    dataset_snapshot_hash: datasetSnapshotHash,
    dataset_row_count: datasetRowCount,
  }
  if (nucleus) body.nucleus = nucleus
  if (datasetTag) body.dataset_tag = datasetTag
  if (datasetSource) body.dataset_source = datasetSource
  if (artifactSha256) body.artifact_sha256 = artifactSha256
  if (confidenceBandPpm != null) body.confidence_band_ppm = confidenceBandPpm

  return { ok: true, body }
}

export type MetricComparison = {
  /** The reason text, without the prefix. */
  reason: string
  /** False when the comparison stood aside — which must not read as an endorsement. */
  applied: boolean
}

const APPLIED_PREFIX = "Metric comparison:"
const SKIPPED_PREFIX = "Metric comparison skipped:"

function stripTrailingPeriod(text: string): string {
  return text.replace(/\.\s*$/, "")
}

/**
 * Pull the metric-comparison outcome out of an approval's notes.
 *
 * The distinction is the whole point: a comparison that ran and passed endorses the model, and
 * one that stood aside — a task family it cannot score — has no opinion at all. Rendering the
 * second as though it were the first turns silence into approval.
 */
export function readMetricComparison(notes: unknown): MetricComparison | null {
  if (!Array.isArray(notes)) return null
  for (const note of notes) {
    if (typeof note !== "string") continue
    const text = note.trim()
    if (text.startsWith(SKIPPED_PREFIX)) {
      return { reason: stripTrailingPeriod(text.slice(SKIPPED_PREFIX.length).trim()), applied: false }
    }
    if (text.startsWith(APPLIED_PREFIX)) {
      return { reason: stripTrailingPeriod(text.slice(APPLIED_PREFIX.length).trim()), applied: true }
    }
  }
  return null
}
