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
