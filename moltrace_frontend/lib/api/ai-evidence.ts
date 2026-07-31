import { apiFetch } from "@/lib/api/client"

export type AIEvidenceModule = "spectracheck" | "regulatory" | "reactions" | "ai_services"
export type AIEvidenceStatus = "draft" | "pending_review" | "approved" | "rejected" | "contradiction"
export type AIEvidenceReviewStatus = "approved" | "rejected" | "pending_review"
export type AIEvidenceRiskLevel = "low" | "medium" | "high" | "critical" | "unknown"

export type AIEvidenceItem = {
  id: number
  module: AIEvidenceModule
  entity_type: string
  entity_id: number
  status: AIEvidenceStatus
  confidence_score?: number | null
  risk_level: AIEvidenceRiskLevel
  summary: string
  reviewer_id?: number | null
  reviewed_at?: string | null
  review_comment?: string | null
  created_at: string
  updated_at: string
}

export type AIEvidenceReviewRequest = {
  status: AIEvidenceReviewStatus
  review_comment?: string | null
}

export type AIEvidenceReviewResponse = {
  evidence_item: AIEvidenceItem
  audit_event_id: number
  updated_status: AIEvidenceStatus
  reviewed_at: string
  reviewer_id?: number | null
  reviewer_display_name?: string | null
}

function asAiEvidenceItems(payload: unknown): AIEvidenceItem[] {
  if (Array.isArray(payload)) return payload as AIEvidenceItem[]
  if (!payload || typeof payload !== "object") return []

  const record = payload as Record<string, unknown>
  for (const key of ["items", "results", "rows", "data", "evidence_items"]) {
    const value = record[key]
    if (Array.isArray(value)) return value as AIEvidenceItem[]
  }

  return []
}

export async function fetchAiEvidenceQueue(limit = 100): Promise<AIEvidenceItem[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  const payload = await apiFetch<unknown>(`/ai/evidence-queue?${params.toString()}`, { method: "GET" })
  return asAiEvidenceItems(payload)
}

export const AI_EVIDENCE_MODULES: AIEvidenceModule[] = [
  "spectracheck",
  "regulatory",
  "reactions",
  "ai_services",
]

/** Where a module's own workspace lives, for linking out of the queue. */
export const AI_EVIDENCE_MODULE_HREFS: Record<AIEvidenceModule, string> = {
  spectracheck: "/spectracheck",
  regulatory: "/regulatory",
  reactions: "/reactions",
  ai_services: "/ai",
}

/**
 * The shared queue read.
 *
 * The topbar badge and the evidence panel both mount inside the app shell and
 * both used to fetch the queue on their own — two requests per navigation whose
 * answers could disagree, so the badge could read 3 while the panel listed 5.
 * Routing both through one snapshot key makes the number single-sourced and
 * costs one request per shell lifetime rather than one per component.
 */
export function loadSharedAiEvidenceQueue(
  loadSnapshot: <T>(key: string, loader: () => Promise<T>) => Promise<T>,
  key: string,
  limit = 100,
): Promise<AIEvidenceItem[]> {
  return loadSnapshot(key, () => fetchAiEvidenceQueue(limit))
}

/**
 * Announces a fresh queue read to anything already on screen.
 *
 * Writing the shared snapshot is not enough on its own: the topbar reads it once
 * when it mounts, so a manual refresh in the panel would leave the badge showing
 * the count from before the refresh until the next navigation remounted it.
 */
export const AI_EVIDENCE_QUEUE_UPDATED_EVENT = "moltrace:ai-evidence-queue-updated"

export function publishAiEvidenceQueue(rows: AIEvidenceItem[]): void {
  if (typeof window === "undefined") return
  try {
    window.dispatchEvent(new CustomEvent(AI_EVIDENCE_QUEUE_UPDATED_EVENT, { detail: rows.length }))
  } catch {
    /* CustomEvent unsupported — the badge catches up on the next navigation */
  }
}

export async function reviewAiEvidenceItem(
  evidence_id: number | string,
  body: AIEvidenceReviewRequest,
): Promise<AIEvidenceReviewResponse> {
  return apiFetch<AIEvidenceReviewResponse>(
    `/ai/evidence-queue/${encodeURIComponent(String(evidence_id))}/review`,
    {
      method: "PATCH",
      body,
    },
  )
}
