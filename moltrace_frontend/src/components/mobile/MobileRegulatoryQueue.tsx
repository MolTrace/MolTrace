"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

type Row = Record<string, unknown>

type MobileActionDraft = {
  comment?: string
  status?: string
  assigned_to?: string
  marked_read?: boolean
  updated_at: string
}

type QueueItem = {
  id: number
  title: string
  severity: string
  status: string
  dossier: string
  sourceEvidence: string
  dueDate: string
  humanReviewRequired: string
  canAssignOwner: boolean
}

const ACTION_DRAFTS_KEY = "moltrace:mobile:action-drafts:v1"
const STATUS_OPTIONS = ["open", "in_progress", "resolved", "dismissed", "deferred"] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (isRecord(data)) {
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.results)) return data.results
    if (Array.isArray(data.action_items)) return data.action_items
  }
  return []
}

function parseQueueRow(row: Row): QueueItem | null {
  const id = readNum(row.id)
  if (id == null) return null
  const sourceEvidence = (() => {
    const citationCount = Array.isArray(row.citation_ids_json) ? row.citation_ids_json.length : null
    const evidenceLabel = readStr(row.source_evidence) || readStr(row.evidence_source) || readStr(row.source)
    if (evidenceLabel) return evidenceLabel
    if (citationCount != null) return `${citationCount} citations`
    return "—"
  })()
  const humanReviewRequiredRaw =
    row.human_review_required ?? row.requires_human_review ?? row.needs_human_review ?? row.manual_review_required
  const canAssignOwnerRaw =
    row.assign_owner_allowed ?? row.can_assign_owner ?? row.owner_assignment_allowed ?? row.permissions_assign_owner
  const canAssignOwner =
    typeof canAssignOwnerRaw === "boolean"
      ? canAssignOwnerRaw
      : typeof canAssignOwnerRaw === "string"
        ? ["true", "1", "yes", "allowed"].includes(canAssignOwnerRaw.trim().toLowerCase())
        : false
  return {
    id,
    title: readStr(row.title) || "—",
    severity: readStr(row.severity) || "—",
    status: readStr(row.status) || "—",
    dossier: readStr(row.dossier_title) || readStr(row.dossier) || readStr(row.dossier_id) || "—",
    sourceEvidence,
    dueDate: readStr(row.due_date) || "—",
    humanReviewRequired:
      typeof humanReviewRequiredRaw === "boolean"
        ? humanReviewRequiredRaw
          ? "Yes"
          : "No"
        : readStr(humanReviewRequiredRaw) || "Unknown",
    canAssignOwner,
  }
}

function loadDrafts(): Record<string, MobileActionDraft> {
  if (typeof window === "undefined") return {}
  try {
    const raw = window.localStorage.getItem(ACTION_DRAFTS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    return isRecord(parsed) ? (parsed as Record<string, MobileActionDraft>) : {}
  } catch {
    return {}
  }
}

function saveDrafts(drafts: Record<string, MobileActionDraft>) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(ACTION_DRAFTS_KEY, JSON.stringify(drafts))
  } catch {
    // ignore localStorage failures
  }
}

export function MobileRegulatoryQueue() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [items, setItems] = useState<QueueItem[]>([])
  const [sourceEndpoint, setSourceEndpoint] = useState<string | null>(null)
  const [online, setOnline] = useState(true)
  const [drafts, setDrafts] = useState<Record<string, MobileActionDraft>>({})
  const [busyId, setBusyId] = useState<number | null>(null)

  useEffect(() => {
    setDrafts(loadDrafts())
    const handleOnlineState = () => setOnline(navigator.onLine)
    handleOnlineState()
    window.addEventListener("online", handleOnlineState)
    window.addEventListener("offline", handleOnlineState)
    return () => {
      window.removeEventListener("online", handleOnlineState)
      window.removeEventListener("offline", handleOnlineState)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError("")
    void (async () => {
      const endpoints = ["/mobile/action-queue", "/regulatory/action-items"]
      let loaded = false
      for (const endpoint of endpoints) {
        try {
          const data = await apiFetch<unknown>(endpoint, { method: "GET" })
          const parsed = asArray(data).filter(isRecord).map(parseQueueRow).filter((r): r is QueueItem => r != null)
          if (cancelled) return
          setItems(parsed)
          setSourceEndpoint(endpoint)
          loaded = true
          break
        } catch (e) {
          if (endpoint === endpoints[endpoints.length - 1] && !cancelled) {
            setError(formatApiError(e, "Could not load mobile regulatory action queue."))
          }
        }
      }
      if (!loaded && !cancelled) {
        setItems([])
        setSourceEndpoint(null)
      }
      if (!cancelled) setLoading(false)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  function updateDraft(id: number, patch: Partial<MobileActionDraft>) {
    const key = String(id)
    const next = {
      ...drafts,
      [key]: {
        ...drafts[key],
        ...patch,
        updated_at: new Date().toISOString(),
      },
    }
    setDrafts(next)
    saveDrafts(next)
  }

  async function patchAction(id: number, body: Record<string, unknown>) {
    setBusyId(id)
    setError("")
    try {
      await apiFetch(`/regulatory/action-items/${id}`, { method: "PATCH", body })
      setItems((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                status: typeof body.status === "string" ? body.status : item.status,
              }
            : item,
        ),
      )
    } catch (e) {
      setError(formatApiError(e, "Update failed."))
    } finally {
      setBusyId(null)
    }
  }

  async function handleMarkRead(item: QueueItem) {
    if (!online) {
      updateDraft(item.id, { marked_read: true })
      return
    }
    await patchAction(item.id, { status: item.status })
  }

  async function handleAddComment(item: QueueItem) {
    const draft = drafts[String(item.id)]
    const comment = (draft?.comment ?? "").trim()
    if (!comment) {
      setError("Comment is required.")
      return
    }
    if (!online) {
      updateDraft(item.id, { comment })
      return
    }
    await patchAction(item.id, { reviewer_comment: comment })
  }

  async function handleAssignOwner(item: QueueItem) {
    const draft = drafts[String(item.id)]
    const assigned = (draft?.assigned_to ?? "").trim()
    if (!assigned) {
      setError("Owner is required.")
      return
    }
    if (!online) {
      updateDraft(item.id, { assigned_to: assigned })
      return
    }
    await patchAction(item.id, { assigned_to: assigned })
  }

  async function handleChangeStatus(item: QueueItem) {
    const draft = drafts[String(item.id)]
    const status = (draft?.status ?? "").trim()
    if (!status) {
      setError("Status is required.")
      return
    }
    if (!online) {
      updateDraft(item.id, { status })
      return
    }
    await patchAction(item.id, { status })
  }

  const queueRows = useMemo(() => items, [items])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mobile Regulatory Action Queue</CardTitle>
        <CardDescription>
          <code className="text-xs">{`GET ${sourceEndpoint ?? "/mobile/action-queue"}`}</code> with fallback to{" "}
          <code className="text-xs">GET /regulatory/action-items</code>. Operational workflow support only; not legal advice.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!online ? (
          <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            Draft only. This action is not final until synced.
          </p>
        ) : null}
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        {loading ? <p className="text-xs text-muted-foreground">Loading action queue…</p> : null}
        {!loading && queueRows.length === 0 ? (
          <p className="text-xs text-muted-foreground">No action items were returned.</p>
        ) : null}

        {queueRows.map((item) => {
          const key = String(item.id)
          const draft = drafts[key]
          const busy = busyId === item.id
          return (
            <div key={item.id} className="rounded-md border bg-muted/20 p-3">
              <p className="text-sm font-medium">{item.title}</p>
              <div className="mt-2 grid gap-1 text-xs text-muted-foreground">
                <p>
                  <span className="font-medium text-foreground">severity:</span> {item.severity}
                </p>
                <p>
                  <span className="font-medium text-foreground">status:</span> {item.status}
                </p>
                <p>
                  <span className="font-medium text-foreground">dossier:</span> {item.dossier}
                </p>
                <p>
                  <span className="font-medium text-foreground">source evidence:</span> {item.sourceEvidence}
                </p>
                <p>
                  <span className="font-medium text-foreground">due date:</span> {item.dueDate}
                </p>
                <p>
                  <span className="font-medium text-foreground">human review required:</span> {item.humanReviewRequired}
                </p>
              </div>

              <div className="mt-3 flex min-w-0 flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" disabled={busy} onClick={() => void handleMarkRead(item)}>
                  Mark read
                </Button>
                <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" disabled={busy} onClick={() => void handleAddComment(item)}>
                  Add comment
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-full sm:w-auto"
                  disabled={busy || !item.canAssignOwner}
                  onClick={() => void handleAssignOwner(item)}
                >
                  Assign owner
                </Button>
                <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" disabled={busy} onClick={() => void handleChangeStatus(item)}>
                  Change status
                </Button>
                <Button type="button" size="sm" className="w-full sm:w-auto" asChild>
                  <Link href="/regulatory/action-queue">Open action</Link>
                </Button>
              </div>

              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor={`mq-comment-${item.id}`} className="text-xs">
                    comment draft
                  </Label>
                  <Textarea
                    id={`mq-comment-${item.id}`}
                    rows={2}
                    value={draft?.comment ?? ""}
                    onChange={(e) => updateDraft(item.id, { comment: e.target.value })}
                    className="text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label htmlFor={`mq-owner-${item.id}`} className="text-xs">
                      assigned owner draft
                    </Label>
                    <Input
                      id={`mq-owner-${item.id}`}
                      value={draft?.assigned_to ?? ""}
                      onChange={(e) => updateDraft(item.id, { assigned_to: e.target.value })}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">status draft</Label>
                    <Select value={draft?.status ?? ""} onValueChange={(value) => updateDraft(item.id, { status: value })}>
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue placeholder="Select status" />
                      </SelectTrigger>
                      <SelectContent>
                        {STATUS_OPTIONS.map((status) => (
                          <SelectItem key={status} value={status} className="text-xs">
                            {status}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
