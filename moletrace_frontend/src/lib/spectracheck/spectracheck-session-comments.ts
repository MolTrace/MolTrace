/**
 * Session-scoped comments API — paths and request field names match backend contract.
 */

import { apiFetch } from "@/lib/api/client"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function normalizeSessionCommentsList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (isRecord(data)) {
    if (Array.isArray(data.comments)) return data.comments.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.items)) return data.items.filter(isRecord) as Record<string, unknown>[]
    if (Array.isArray(data.results)) return data.results.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

export async function fetchSessionComments(sessionId: string): Promise<Record<string, unknown>[]> {
  const sid = sessionId.trim()
  if (!sid) return []
  const data = await apiFetch<unknown>(`/spectracheck/sessions/${encodeURIComponent(sid)}/comments`, {
    method: "GET",
  })
  return normalizeSessionCommentsList(data)
}

export type PostSessionCommentBody = {
  comment_type: string
  comment: string
  evidence_id?: number | string
  artifact_id?: string
}

export async function postSessionComment(sessionId: string, body: PostSessionCommentBody): Promise<void> {
  const sid = sessionId.trim()
  if (!sid) throw new Error("Session id required.")
  await apiFetch(`/spectracheck/sessions/${encodeURIComponent(sid)}/comments`, {
    method: "POST",
    body,
  })
}

/** Match a session comment row to an evidence queue item (backend id or client item id). */
export function sessionCommentMatchesEvidence(row: Record<string, unknown>, item: EvidenceItem): boolean {
  const be = item.backendEvidenceId
  if (be != null) {
    const rid = row.evidence_id ?? row.evidenceId
    if (rid != null && String(rid) === String(be)) return true
  }
  const link = row.evidence_item_id ?? row.evidenceItemId
  if (typeof link === "string" && link === item.id) return true
  return false
}

export function sessionCommentMatchesArtifact(row: Record<string, unknown>, artifactId: string): boolean {
  const aid = row.artifact_id ?? row.artifactId
  return aid != null && String(aid).trim() === String(artifactId).trim()
}

export function pickCommentText(row: Record<string, unknown>): string {
  const t = row.comment ?? row.text ?? row.body ?? row.message
  return typeof t === "string" ? t : ""
}

export function pickCommentType(row: Record<string, unknown>): string {
  const t = row.comment_type ?? row.type
  return typeof t === "string" ? t : "—"
}

export const SESSION_COMMENT_TYPES = ["note", "question", "concern", "contradiction", "approval_note"] as const
