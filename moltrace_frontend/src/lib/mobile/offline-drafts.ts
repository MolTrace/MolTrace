import { apiFetch } from "@/lib/api/client"

export type MobileDraftDecisionStatus = "approve" | "reject" | "open" | "in_progress" | "resolved" | "deferred" | "draft"

export type MobileOfflineDraft = {
  local_id: string
  draft_id: number | null
  action_type: string
  target_type: string
  target_id: string
  short_comment: string
  decision_status: MobileDraftDecisionStatus
  timestamp: string
  sync_state: "pending" | "accepted" | "rejected"
  sync_reason: string
}

type Row = Record<string, unknown>

const STORAGE_KEY = "moltrace:mobile:offline-action-drafts:v1"
const BLOCKED_PATTERNS = [
  "raw fid",
  "raw_fid",
  "raw spectra",
  "raw_spectra",
  "full smiles",
  "smiles",
  "source document",
  "report html",
  "model artifact",
  "token",
  "password",
  "secret",
]

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function normalizeShortComment(v: string): string {
  return v.replace(/\s+/g, " ").trim().slice(0, 280)
}

function looksSensitive(input: string): boolean {
  const text = input.toLowerCase()
  return BLOCKED_PATTERNS.some((p) => text.includes(p))
}

function loadStoredDrafts(): MobileOfflineDraft[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter(isRecord)
      .map((row): MobileOfflineDraft => ({
        local_id: readStr(row.local_id) || crypto.randomUUID(),
        draft_id: typeof row.draft_id === "number" ? row.draft_id : null,
        action_type: readStr(row.action_type),
        target_type: readStr(row.target_type),
        target_id: readStr(row.target_id),
        short_comment: normalizeShortComment(readStr(row.short_comment)),
        decision_status: (readStr(row.decision_status) || "draft") as MobileDraftDecisionStatus,
        timestamp: readStr(row.timestamp) || new Date().toISOString(),
        sync_state: (readStr(row.sync_state) || "pending") as MobileOfflineDraft["sync_state"],
        sync_reason: readStr(row.sync_reason),
      }))
  } catch {
    return []
  }
}

function saveStoredDrafts(drafts: MobileOfflineDraft[]) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts))
}

export function getOfflineDrafts(): MobileOfflineDraft[] {
  return loadStoredDrafts().sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))
}

export function addOfflineDraft(input: {
  action_type: string
  target_type: string
  target_id: string
  short_comment: string
  decision_status: MobileDraftDecisionStatus
}): { ok: true; draft: MobileOfflineDraft } | { ok: false; reason: string } {
  const action_type = readStr(input.action_type)
  const target_type = readStr(input.target_type)
  const target_id = readStr(input.target_id)
  const short_comment = normalizeShortComment(readStr(input.short_comment))
  const decision_status = (readStr(input.decision_status) || "draft") as MobileDraftDecisionStatus
  if (!action_type || !target_type || !target_id) {
    return { ok: false, reason: "action_type, target_type, and target_id are required." }
  }
  const sensitiveCheck = `${action_type} ${target_type} ${target_id} ${short_comment}`
  if (looksSensitive(sensitiveCheck)) {
    return { ok: false, reason: "Sensitive payloads are blocked from offline draft storage." }
  }
  const draft: MobileOfflineDraft = {
    local_id: crypto.randomUUID(),
    draft_id: null,
    action_type,
    target_type,
    target_id,
    short_comment,
    decision_status,
    timestamp: new Date().toISOString(),
    sync_state: "pending",
    sync_reason: "",
  }
  const drafts = loadStoredDrafts()
  drafts.push(draft)
  saveStoredDrafts(drafts)
  return { ok: true, draft }
}

export function clearRejectedOfflineDrafts() {
  const drafts = loadStoredDrafts().filter((d) => d.sync_state !== "rejected")
  saveStoredDrafts(drafts)
}

function saveOneDraft(update: MobileOfflineDraft) {
  const drafts = loadStoredDrafts().map((draft) => (draft.local_id === update.local_id ? update : draft))
  saveStoredDrafts(drafts)
}

function toApiBody(draft: MobileOfflineDraft): Record<string, unknown> {
  return {
    action_type: draft.action_type,
    target_type: draft.target_type,
    target_id: draft.target_id,
    short_comment: draft.short_comment,
    decision_status: draft.decision_status,
    timestamp: draft.timestamp,
  }
}

export async function getServerActionDrafts(): Promise<unknown> {
  return apiFetch("/mobile/action-drafts", { method: "GET" })
}

export async function syncOfflineDraftsNow(): Promise<MobileOfflineDraft[]> {
  const drafts = loadStoredDrafts()
  for (const draft of drafts) {
    try {
      let serverDraftId = draft.draft_id
      if (serverDraftId == null) {
        const created = await apiFetch<unknown>("/mobile/action-drafts", { method: "POST", body: toApiBody(draft) })
        if (isRecord(created) && typeof created.draft_id === "number") {
          serverDraftId = created.draft_id
        }
      } else {
        await apiFetch(`/mobile/action-drafts/${serverDraftId}`, { method: "PATCH", body: toApiBody(draft) })
      }

      let nextState: MobileOfflineDraft["sync_state"] = "accepted"
      let nextReason = ""
      const syncResult = await apiFetch<unknown>("/mobile/sync", {
        method: "POST",
        body: { draft_id: serverDraftId, local_id: draft.local_id },
      })
      if (isRecord(syncResult)) {
        const status = readStr(syncResult.status).toLowerCase()
        if (status === "rejected") {
          nextState = "rejected"
          nextReason = readStr(syncResult.reason) || "Rejected by server validation."
        } else if (status === "accepted") {
          nextState = "accepted"
        }
      }
      saveOneDraft({
        ...draft,
        draft_id: serverDraftId ?? draft.draft_id,
        sync_state: nextState,
        sync_reason: nextReason,
      })
    } catch (error) {
      const reason = error instanceof Error ? error.message : "Sync failed."
      saveOneDraft({ ...draft, sync_state: "rejected", sync_reason: reason.slice(0, 240) })
    }
  }
  return getOfflineDrafts()
}
