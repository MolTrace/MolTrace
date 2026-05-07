"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { apiFetch } from "@/lib/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

type Row = Record<string, unknown>

type MobileReactionDraft = {
  rationale?: string
  comment?: string
  decision?: "approve" | "reject"
  execution_status?: string
  updated_at: string
}

type MobileReactionSummary = {
  reactionProjectId: string
  pendingRecommendations: number | null
  regulatoryConstraints: string[]
  costSafetyFlags: string[]
  executionBatchStatus: string
  experimentsNeedingOutcomeConfirmation: number | null
  nextBoCycleReadiness: string
}

const DRAFTS_KEY = "moltrace:mobile:reaction-approval-drafts:v1"

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

function readList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(readStr).filter(Boolean)
}

function readFirstString(rec: Row, keys: string[]): string {
  for (const key of keys) {
    const value = readStr(rec[key])
    if (value) return value
  }
  return ""
}

function readFirstNumber(rec: Row, keys: string[]): number | null {
  for (const key of keys) {
    const value = readNum(rec[key])
    if (value != null) return value
  }
  return null
}

function loadDrafts(): Record<string, MobileReactionDraft> {
  if (typeof window === "undefined") return {}
  try {
    const raw = window.localStorage.getItem(DRAFTS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    return isRecord(parsed) ? (parsed as Record<string, MobileReactionDraft>) : {}
  } catch {
    return {}
  }
}

function saveDrafts(drafts: Record<string, MobileReactionDraft>) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts))
  } catch {
    // ignore localStorage failures
  }
}

function parseSummary(reactionProjectId: string, payload: unknown): MobileReactionSummary {
  const root = isRecord(payload) ? payload : {}
  const regulatoryConstraints = [
    ...readList(root.regulatory_constraints),
    ...readList(root.regulatory_constraints_json),
    ...readList(root.constraint_badges),
  ]
  const costSafetyFlags = [...readList(root.cost_safety_flags), ...readList(root.cost_safety_flags_json), ...readList(root.flags)]
  return {
    reactionProjectId,
    pendingRecommendations: readFirstNumber(root, [
      "pending_recommendations",
      "pending_recommendations_count",
      "open_recommendations_count",
    ]),
    regulatoryConstraints: Array.from(new Set(regulatoryConstraints)),
    costSafetyFlags: Array.from(new Set(costSafetyFlags)),
    executionBatchStatus:
      readFirstString(root, ["execution_batch_status", "batch_status", "execution_status"]) || "Unknown",
    experimentsNeedingOutcomeConfirmation: readFirstNumber(root, [
      "experiments_needing_outcome_confirmation",
      "outcome_confirmation_required_count",
      "pending_outcome_confirmation_count",
    ]),
    nextBoCycleReadiness:
      readFirstString(root, ["next_bo_cycle_readiness", "next_cycle_readiness", "bo_cycle_readiness"]) || "Unknown",
  }
}

export function MobileReactionApprovalBoard({
  reactionProjectId: reactionProjectIdProp = null,
}: {
  reactionProjectId?: string | null
}) {
  const searchParams = useSearchParams()
  const reactionProjectId = (reactionProjectIdProp ?? searchParams.get("reactionProjectId") ?? "").trim()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [online, setOnline] = useState(true)
  const [summary, setSummary] = useState<MobileReactionSummary | null>(null)
  const [drafts, setDrafts] = useState<Record<string, MobileReactionDraft>>({})

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
    if (!reactionProjectId) {
      setSummary(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError("")
    void apiFetch<unknown>(`/mobile/reactions/${encodeURIComponent(reactionProjectId)}/summary`, { method: "GET" })
      .then((payload) => {
        if (cancelled) return
        setSummary(parseSummary(reactionProjectId, payload))
      })
      .catch(() => {
        if (!cancelled) {
          setSummary(null)
          setError("Could not load mobile reaction summary.")
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reactionProjectId])

  function updateDraft(patch: Partial<MobileReactionDraft>) {
    if (!reactionProjectId) return
    const key = reactionProjectId
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

  function requireRationale(): string | null {
    const rationale = (drafts[reactionProjectId]?.rationale ?? "").trim()
    if (!rationale) {
      setError("Approval requires rationale.")
      return null
    }
    return rationale
  }

  function handleApprove() {
    setError("")
    const rationale = requireRationale()
    if (!rationale) return
    updateDraft({ decision: "approve", rationale })
  }

  function handleReject() {
    setError("")
    const rationale = requireRationale()
    if (!rationale) return
    updateDraft({ decision: "reject", rationale })
  }

  function handleConfirmExecution() {
    setError("")
    const rationale = requireRationale()
    if (!rationale) return
    const status = (drafts[reactionProjectId]?.execution_status ?? "").trim()
    updateDraft({ execution_status: status || "confirmed", rationale })
  }

  const draft = reactionProjectId ? drafts[reactionProjectId] : undefined
  const reactionHref = useMemo(
    () =>
      reactionProjectId
        ? `/reactions?reactionProjectId=${encodeURIComponent(reactionProjectId)}`
        : "/reactions",
    [reactionProjectId],
  )
  const regulatoryHref = useMemo(
    () =>
      reactionProjectId
        ? `/regulatory?reactionProjectId=${encodeURIComponent(reactionProjectId)}`
        : "/regulatory",
    [reactionProjectId],
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mobile Reaction Approval Board</CardTitle>
        <CardDescription>
          <code className="text-xs">GET /mobile/reactions/{"{reaction_project_id}"}/summary</code> for review support on
          phone workflows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!online ? (
          <p className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
            Draft only. This action is not final until synced.
          </p>
        ) : null}
        {!reactionProjectId ? (
          <p className="text-xs text-muted-foreground">Open a reaction project to load mobile approval summary.</p>
        ) : null}
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        {loading ? <p className="text-xs text-muted-foreground">Loading reaction approval summary…</p> : null}

        {reactionProjectId && summary ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">pending recommendations</p>
                <p className="text-sm font-medium">
                  {summary.pendingRecommendations != null ? summary.pendingRecommendations : "—"}
                </p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">execution batch status</p>
                <p className="text-sm font-medium">{summary.executionBatchStatus}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">experiments needing outcome confirmation</p>
                <p className="text-sm font-medium">
                  {summary.experimentsNeedingOutcomeConfirmation != null
                    ? summary.experimentsNeedingOutcomeConfirmation
                    : "—"}
                </p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">next BO cycle readiness</p>
                <p className="text-sm font-medium">{summary.nextBoCycleReadiness}</p>
              </div>
            </div>

            <div className="rounded-md border p-3">
              <p className="mb-2 text-xs text-muted-foreground">regulatory constraints</p>
              <div className="flex flex-wrap gap-2">
                {summary.regulatoryConstraints.length > 0 ? (
                  summary.regulatoryConstraints.map((constraint) => (
                    <Badge key={constraint} variant="outline" className="text-[11px]">
                      {constraint}
                    </Badge>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">—</p>
                )}
              </div>
            </div>

            <div className="rounded-md border p-3">
              <p className="mb-2 text-xs text-muted-foreground">cost/safety flags</p>
              <p className="text-xs text-muted-foreground">
                {summary.costSafetyFlags.length > 0 ? summary.costSafetyFlags.join(" · ") : "—"}
              </p>
            </div>
          </>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="mobile-reaction-rationale" className="text-xs">
              rationale (required for approval/rejection)
            </Label>
            <Textarea
              id="mobile-reaction-rationale"
              rows={2}
              value={draft?.rationale ?? ""}
              onChange={(e) => updateDraft({ rationale: e.target.value })}
              className="text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mobile-reaction-comment" className="text-xs">
              review comment
            </Label>
            <Input
              id="mobile-reaction-comment"
              value={draft?.comment ?? ""}
              onChange={(e) => updateDraft({ comment: e.target.value })}
              className="h-8 text-xs"
            />
            <Label htmlFor="mobile-reaction-execution-status" className="text-xs">
              execution status draft
            </Label>
            <Input
              id="mobile-reaction-execution-status"
              value={draft?.execution_status ?? ""}
              onChange={(e) => updateDraft({ execution_status: e.target.value })}
              className="h-8 text-xs"
              placeholder="confirmed | blocked | pending"
            />
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={handleApprove}>
            Approve recommendation
          </Button>
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={handleReject}>
            Reject recommendation
          </Button>
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={() => updateDraft({ comment: draft?.comment ?? "" })}>
            Add review comment
          </Button>
          <Button type="button" size="sm" variant="outline" className="w-full sm:w-auto" onClick={handleConfirmExecution}>
            Confirm execution status
          </Button>
          <Button type="button" size="sm" className="w-full sm:w-auto" asChild>
            <Link href={regulatoryHref}>View linked Regulatory Hub constraint</Link>
          </Button>
          <Button type="button" size="sm" variant="secondary" className="w-full sm:w-auto" asChild>
            <Link href={reactionHref}>Open full reaction view</Link>
          </Button>
        </div>

        {!online ? (
          <p className="text-xs text-muted-foreground">Offline mode stores draft input only; final approval remains server-validated.</p>
        ) : null}
      </CardContent>
    </Card>
  )
}
