"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { ChevronDown } from "lucide-react"

const TOOLTIP =
  "Turns regulatory action items into reaction optimization constraints, such as impurity limits, residual solvent limits, nitrosamine risk avoidance, and method-validation requirements."

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

function readString(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function parseOptionalNumber(v: string): number | null {
  const t = v.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function parseActionItemIdsCsv(v: string): number[] {
  return v
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n))
}

type ReactionOptimizationHandoffCardProps = {
  dossierId: number
  reactionProjectId: number | null
  compoundId?: number | null
  batchId?: number | null
}

export function ReactionOptimizationHandoffCard({
  dossierId,
  reactionProjectId,
  compoundId = null,
  batchId = null,
}: ReactionOptimizationHandoffCardProps) {
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState("")
  const [bridges, setBridges] = useState<Record<string, unknown>[]>([])
  const [lastBridge, setLastBridge] = useState<Record<string, unknown> | null>(null)

  const [actionItemIdsInput, setActionItemIdsInput] = useState("")
  const [reactionProjectIdInput, setReactionProjectIdInput] = useState(reactionProjectId != null ? String(reactionProjectId) : "")
  const [compoundIdInput, setCompoundIdInput] = useState(compoundId != null ? String(compoundId) : "")
  const [batchIdInput, setBatchIdInput] = useState(batchId != null ? String(batchId) : "")

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const bridgeRaw = await apiFetch<unknown>(`/bridges/regulatory-to-reaction?dossier_id=${dossierId}`, { method: "GET" })
      const bridgeRows = asArray(bridgeRaw).map(asRecord).filter((v): v is Record<string, unknown> => v != null)
      setBridges(bridgeRows)
      setLastBridge(bridgeRows[0] ?? null)

      const actionRaw = await apiFetch<unknown>(`/regulatory/action-items?dossier_id=${dossierId}&limit=200`, { method: "GET" })
      const actionRows = asArray(actionRaw).map(asRecord).filter((v): v is Record<string, unknown> => v != null)
      const ids = actionRows
        .map((row) => row.id)
        .filter((v): v is number => typeof v === "number" && Number.isFinite(v))
      setActionItemIdsInput(ids.join(", "))
    } catch (e) {
      setErr(formatApiError(e, "Could not load reaction handoff bridge records."))
      setBridges([])
      setLastBridge(null)
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setReactionProjectIdInput(reactionProjectId != null ? String(reactionProjectId) : "")
  }, [reactionProjectId])

  useEffect(() => {
    setCompoundIdInput(compoundId != null ? String(compoundId) : "")
  }, [compoundId])

  useEffect(() => {
    setBatchIdInput(batchId != null ? String(batchId) : "")
  }, [batchId])

  async function createReactionConstraints() {
    setSending(true)
    setErr("")
    try {
      const body: Record<string, unknown> = {
        dossier_id: dossierId,
        regulatory_action_item_ids: parseActionItemIdsCsv(actionItemIdsInput),
        reaction_project_id: parseOptionalNumber(reactionProjectIdInput),
      }
      const compoundIdNum = parseOptionalNumber(compoundIdInput)
      const batchIdNum = parseOptionalNumber(batchIdInput)
      if (compoundIdNum != null) body.compound_id = compoundIdNum
      if (batchIdNum != null) body.batch_id = batchIdNum
      const created = await apiFetch<unknown>("/bridges/regulatory-to-reaction", { method: "POST", body })
      const rec = asRecord(created)
      if (rec) setLastBridge(rec)
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Create reaction constraints failed."))
    } finally {
      setSending(false)
    }
  }

  const generatedRegulatoryConstraints = asArray(lastBridge?.regulatory_constraints_json)
  const optimizationObjectives = asArray(lastBridge?.optimization_objectives_json)
  const warnings = asArray(lastBridge?.warnings_json)
  const notes = asArray(lastBridge?.notes_json)
  const humanReviewRequired =
    typeof lastBridge?.human_review_required === "boolean" ? lastBridge.human_review_required : true

  const resolvedReactionProjectId = parseOptionalNumber(reactionProjectIdInput)
  const hasReactionProject = resolvedReactionProjectId != null
  const openReactionHref = hasReactionProject ? `/reactions/${encodeURIComponent(String(resolvedReactionProjectId))}` : "/reactions"

  const constraintsLine = useMemo(
    () =>
      generatedRegulatoryConstraints.length
        ? generatedRegulatoryConstraints.map((v) => readString(v) || JSON.stringify(v)).join(", ")
        : "—",
    [generatedRegulatoryConstraints],
  )
  const objectivesLine = useMemo(
    () =>
      optimizationObjectives.length
        ? optimizationObjectives.map((v) => readString(v) || JSON.stringify(v)).join(", ")
        : "—",
    [optimizationObjectives],
  )

  return (
    <Card className="border-muted">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Reaction Optimization Handoff</CardTitle>
          <InfoTooltip label="Reaction Optimization handoff" content={TOOLTIP} />
        </div>
        <CardDescription>
          Bridge handoff from dossier action items into compliance-driven optimization constraints. Requires qualified human
          review.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor={`rr-dossier-${dossierId}`}>Dossier ID</Label>
            <Input id={`rr-dossier-${dossierId}`} value={String(dossierId)} disabled />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`rr-action-items-${dossierId}`}>Regulatory action item IDs</Label>
            <Input
              id={`rr-action-items-${dossierId}`}
              value={actionItemIdsInput}
              onChange={(e) => setActionItemIdsInput(e.target.value)}
              placeholder="e.g. 101, 102, 103"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`rr-reaction-project-${dossierId}`}>Reaction project ID</Label>
            <Input
              id={`rr-reaction-project-${dossierId}`}
              value={reactionProjectIdInput}
              onChange={(e) => setReactionProjectIdInput(e.target.value)}
              placeholder="reaction project id"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`rr-compound-${dossierId}`}>Compound ID (optional)</Label>
            <Input
              id={`rr-compound-${dossierId}`}
              value={compoundIdInput}
              onChange={(e) => setCompoundIdInput(e.target.value)}
              placeholder="compound id"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`rr-batch-${dossierId}`}>Batch ID (optional)</Label>
            <Input
              id={`rr-batch-${dossierId}`}
              value={batchIdInput}
              onChange={(e) => setBatchIdInput(e.target.value)}
              placeholder="batch id"
            />
          </div>
        </div>

        {!hasReactionProject ? (
          <p className="text-xs text-muted-foreground">
            Create or select a reaction project before generating compliance-driven optimization constraints.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => void createReactionConstraints()} disabled={sending || !hasReactionProject}>
            {sending ? "Creating…" : "Create reaction constraints"}
          </Button>
          <Button type="button" variant="outline" asChild>
            <Link href={openReactionHref}>Open Reaction Optimization</Link>
          </Button>
        </div>

        {loading ? <p className="text-xs text-muted-foreground">Loading reaction handoff bridge records…</p> : null}
        {err ? <p className="text-xs text-destructive">{err}</p> : null}

        <div className="grid gap-2 md:grid-cols-2">
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Generated regulatory constraints</p>
            <p className="mt-1 text-xs text-muted-foreground">{constraintsLine}</p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Optimization objectives</p>
            <p className="mt-1 text-xs text-muted-foreground">{objectivesLine}</p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Human review required</p>
            <p className="mt-1 text-xs text-muted-foreground">{humanReviewRequired ? "true" : "false"}</p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2 md:col-span-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Warnings</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {warnings.length ? warnings.map((v) => readString(v) || JSON.stringify(v)).join(" · ") : "—"}
            </p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2 md:col-span-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Notes</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {notes.length ? notes.map((v) => readString(v) || JSON.stringify(v)).join(" · ") : "—"}
            </p>
          </div>
        </div>

        <Collapsible className="rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium hover:bg-muted/50">
            Developer JSON
            <ChevronDown className="h-4 w-4" />
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t px-3 py-3">
            <DeveloperJsonPanel
              data={{
                latest_bridge: lastBridge,
                bridge_records: bridges,
                request_preview: {
                  dossier_id: dossierId,
                  regulatory_action_item_ids: parseActionItemIdsCsv(actionItemIdsInput),
                  reaction_project_id: parseOptionalNumber(reactionProjectIdInput),
                  compound_id: parseOptionalNumber(compoundIdInput),
                  batch_id: parseOptionalNumber(batchIdInput),
                },
              }}
            />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}
