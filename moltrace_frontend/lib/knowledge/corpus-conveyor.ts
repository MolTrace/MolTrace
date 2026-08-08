// The corpus conveyor — how curated records become a deployed model, and what
// has to be true at each step before the next one is allowed to run.
//
// Two rules shape everything here, and both are enforced server-side. The UI's
// job is to make them legible rather than to re-implement them:
//
//  1. PROMOTING A DATASET VERSION TAKES TWO DIFFERENT PEOPLE. The approval
//     request carries a comment and nothing else — who approved comes from the
//     signed-in principal. A field naming the approver would let one person
//     nominate another, which is exactly the control being bought. Progress is
//     therefore a count ("1 of 2"), never a boolean: "awaiting a second
//     approver" is a different state from "not approved".
//
//  2. EACH CONVEYOR STEP REFUSES TO RUN WITHOUT THE ONE BEFORE IT. A candidate
//     needs a dataset version two people approved, a canary needs a passed
//     gate, and promotion needs a canary even when the gate passed. Offering a
//     step that will be refused presents a governed sequence as a menu.
//
// And one display rule that is easy to get wrong: a PASSED GATE IS ELIGIBILITY,
// NOT APPROVAL. `requires_human_signoff` is always true, so a passed gate must
// never be rendered as a completed promotion.

import { apiFetch } from "@/lib/api/client"
import { humanizeField } from "@/lib/ui/status"
import type { components } from "@/src/lib/api/schema"

export type DatasetVersionApproval = components["schemas"]["DatasetVersionApproval"]
export type DatasetVersionApprovalState = components["schemas"]["DatasetVersionApprovalState"]
export type KnowledgeDeploymentCandidate = components["schemas"]["KnowledgeDeploymentCandidate"]

// ── 1 · two-person promotion ──────────────────────────────────────────────────

export async function fetchDatasetVersionApprovals(
  datasetVersionId: number,
): Promise<DatasetVersionApprovalState> {
  return apiFetch<DatasetVersionApprovalState>(
    `/knowledge/dataset-versions/${encodeURIComponent(String(datasetVersionId))}/approvals`,
  )
}

/**
 * Record *your* approval.
 *
 * The body carries a comment and nothing else, deliberately. There is no
 * approver parameter to pass and there must never be one: identity comes from
 * who is signed in, and a caller-supplied approver would defeat the two-person
 * rule in a single request.
 */
export async function approveDatasetVersion(
  datasetVersionId: number,
  comment: string,
): Promise<DatasetVersionApprovalState> {
  const trimmed = comment.trim()
  return apiFetch<DatasetVersionApprovalState>(
    `/knowledge/dataset-versions/${encodeURIComponent(String(datasetVersionId))}/approvals`,
    { method: "POST", body: trimmed ? { comment: trimmed } : {} },
  )
}

export type ApprovalProgress = {
  /** "1 of 2 approvals" — a count, because a boolean cannot say "awaiting a second". */
  countLabel: string
  /** What is still needed, in a sentence. */
  statusLabel: string
  distinct: number
  required: number
  promoted: boolean
}

export function approvalProgress(state: DatasetVersionApprovalState | null): ApprovalProgress {
  const distinct = state?.distinct_approvers ?? 0
  // `approvals_required` is the server's number; defaulting it locally would let
  // the screen keep showing "of 2" after the rule changed.
  const required = state?.approvals_required ?? 0
  const promoted = state?.promoted ?? false
  const remaining = Math.max(required - distinct, 0)
  let statusLabel: string
  if (promoted) {
    statusLabel = "Approved by the required number of people, and promoted."
  } else if (distinct === 0) {
    statusLabel = "Not approved yet."
  } else if (remaining === 1) {
    statusLabel = "Awaiting a second approver. It has to be someone other than the person who already approved."
  } else {
    statusLabel = `Awaiting ${remaining} more approvers, each a different person.`
  }
  return {
    countLabel: `${distinct} of ${required} approvals`,
    statusLabel,
    distinct,
    required,
    promoted,
  }
}

/**
 * Why the approver is never a form field. Shown next to the control, because
 * the absence of the field is the feature and otherwise reads as an oversight.
 */
export const APPROVAL_IDENTITY_NOTE =
  "Your approval is recorded against whoever is signed in. You cannot approve on someone else's behalf, and approving twice yourself does not count twice."

/**
 * The refusals this control expects.
 *
 * Approving twice, and approving with a machine credential, are both ordinary
 * outcomes of the rule working — not failures. The service explains each one in
 * a full sentence, so that sentence is shown as-is instead of being classified
 * by matching its wording, which would quietly stop working the moment the copy
 * changed.
 */
export const APPROVAL_REFUSAL_FALLBACK =
  "That approval was not recorded. Approving needs a signed-in person, and the second approval has to come from someone other than the first."

// ── 2 · the deployment conveyor ───────────────────────────────────────────────
//
// Distinct from the model-factory deployment screens. That conveyor governs
// model artifacts; this one governs what a model was trained on. They are not
// two views of the same queue and must not be merged.

export type DeploymentStatus = "draft" | "gate_passed" | "gate_failed" | "canary" | "promoted"

export const DEPLOYMENT_STATUSES: readonly DeploymentStatus[] = [
  "draft",
  "gate_passed",
  "gate_failed",
  "canary",
  "promoted",
] as const

export type DeploymentStatusPresentation = {
  label: string
  description: string
  tone: "neutral" | "passed" | "failed" | "running" | "promoted"
}

export const DEPLOYMENT_STATUS_PRESENTATION: Record<DeploymentStatus, DeploymentStatusPresentation> = {
  draft: {
    label: "Proposed",
    description: "Proposed from an approved dataset version. It has not been checked against the model in service yet.",
    tone: "neutral",
  },
  gate_passed: {
    // Not "Approved". The check says eligible; a person still decides.
    label: "Eligible",
    description:
      "It cleared the check against the model in service. That makes it eligible for a limited rollout — it is not an approval, and nothing has shipped.",
    tone: "passed",
  },
  gate_failed: {
    label: "Blocked",
    description: "The check refused it. The reasons it gives are the full account of why.",
    tone: "failed",
  },
  canary: {
    label: "In limited rollout",
    description: "Running for a slice of traffic so it can be watched before it replaces the model in service.",
    tone: "running",
  },
  promoted: {
    label: "In service",
    description: "It came through a limited rollout and now serves. The previous model stays available to roll back to.",
    tone: "promoted",
  },
}

export function readDeploymentStatus(value: unknown): DeploymentStatus {
  const raw = typeof value === "string" ? value.trim().toLowerCase() : ""
  return (DEPLOYMENT_STATUSES as readonly string[]).includes(raw) ? (raw as DeploymentStatus) : "draft"
}

/**
 * Which steps the service will actually accept for a candidate in this state.
 *
 * Mirrors the server's own refusals rather than adding a second opinion: a
 * canary needs a passed check, promotion needs a canary even when the check
 * passed, and something already rolling out cannot be re-checked — re-judging it
 * would rewind its state while its rollout timestamps still said it shipped.
 */
export type ConveyorSteps = { canGate: boolean; canCanary: boolean; canPromote: boolean }

export function conveyorSteps(status: DeploymentStatus): ConveyorSteps {
  return {
    canGate: status === "draft" || status === "gate_passed" || status === "gate_failed",
    canCanary: status === "gate_passed",
    canPromote: status === "canary",
  }
}

/** Why a step is not offered, so an absent button is not read as a broken one. */
export function stepUnavailableReason(status: DeploymentStatus, step: keyof ConveyorSteps): string {
  if (step === "canGate") {
    return "Already in a limited rollout or in service. Propose a new candidate rather than re-checking this one."
  }
  if (step === "canCanary") {
    if (status === "draft") return "Run the check first."
    if (status === "gate_failed") return "The check refused this candidate, so it cannot start a rollout."
    if (status === "canary") return "Already in a limited rollout."
    return "Already in service."
  }
  if (status === "promoted") return "Already in service."
  return "A limited rollout has to run first — clearing the check is not enough on its own."
}

export const CONVEYOR_SEPARATE_FROM_MODEL_FACTORY_NOTE =
  "This governs models trained from the curated corpus. It is a separate queue from the model factory's deployment reviews."

// ── 3 · the gate verdict ──────────────────────────────────────────────────────

export type GateVerdict = {
  promotable: boolean
  safetyRegression: boolean
  dominates: boolean
  requiresHumanSignoff: boolean
  rollbackAvailable: boolean
  /** Shown verbatim. Summarising these to "did not improve" loses the only account of why. */
  reasons: string[]
  excludedMetrics: string[]
  blockingMetricName: string | null
  /** False when the candidate has not been checked yet — no verdict to read. */
  present: boolean
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

export function readGateVerdict(value: unknown): GateVerdict {
  const raw = isRecord(value) ? value : {}
  const present = Object.keys(raw).length > 0
  return {
    promotable: raw.promotable === true,
    safetyRegression: raw.safety_regression === true,
    dominates: raw.dominates === true,
    // Always true on the wire. Defaulting it to true when absent keeps a missing
    // field from reading as "no sign-off needed".
    requiresHumanSignoff: raw.requires_human_signoff !== false,
    rollbackAvailable: raw.rollback_available === true,
    reasons: readStringList(raw.reasons),
    excludedMetrics: readStringList(raw.excluded_metrics),
    blockingMetricName:
      typeof raw.blocking_metric_name === "string" && raw.blocking_metric_name.trim()
        ? raw.blocking_metric_name.trim()
        : null,
    present,
  }
}

/** `citation_support_recall` → "Citation support recall". Display only — the key is never renamed. */
export function metricLabel(name: string): string {
  return humanizeField(name)
}

/**
 * The caveat that has to accompany any passed check.
 *
 * `requires_human_signoff` is always true, so "the check passed" and "this is
 * approved to ship" are never the same statement.
 */
export const GATE_ELIGIBILITY_NOTE =
  "Clearing this check makes a candidate eligible. It is not sign-off, and it does not deploy anything."

/**
 * Why a refusal with a thin-looking reason is usually a missing measure.
 *
 * The check fails closed: a measure that is absent or not a real number blocks,
 * however good everything else looks. Said plainly so a blocked candidate is not
 * read as a near miss.
 */
export const GATE_FAILS_CLOSED_NOTE =
  "This check fails closed. A measure that is missing, or that is not a real number, blocks the candidate no matter how good the rest looks — so a refusal with little to say usually means a measure was absent rather than that it was a close call."

// ── 4 · conveyor requests ─────────────────────────────────────────────────────

export async function fetchDeploymentCandidates(
  status?: string,
  limit = 200,
): Promise<KnowledgeDeploymentCandidate[]> {
  const params = new URLSearchParams()
  params.set("limit", String(limit))
  if (status) params.set("status", status)
  return apiFetch<KnowledgeDeploymentCandidate[]>(`/knowledge/deployment-candidates?${params.toString()}`)
}

export type DeploymentCandidateDraft = {
  dataset_version_id: number
  model_version: string
  metrics_json: Record<string, number>
  incumbent_metrics_json: Record<string, number>
  metric_directions_json: Record<string, string>
  blocking_metric_name?: string
  blocking_metric_value?: number
  incumbent_blocking_metric_value?: number
}

export async function createDeploymentCandidate(
  draft: DeploymentCandidateDraft,
): Promise<KnowledgeDeploymentCandidate> {
  return apiFetch<KnowledgeDeploymentCandidate>("/knowledge/deployment-candidates", {
    method: "POST",
    body: { ...draft, metadata_json: {} },
  })
}

export type ConveyorAction = "gate" | "canary" | "promote"

export async function advanceDeploymentCandidate(
  candidateId: number,
  action: ConveyorAction,
): Promise<KnowledgeDeploymentCandidate> {
  return apiFetch<KnowledgeDeploymentCandidate>(
    `/knowledge/deployment-candidates/${encodeURIComponent(String(candidateId))}/${action}`,
    { method: "POST" },
  )
}
