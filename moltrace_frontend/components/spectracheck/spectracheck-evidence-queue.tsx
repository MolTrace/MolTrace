"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { FileJson, Trash2 } from "lucide-react"
import { EvidenceItemVisualSection } from "@/components/spectracheck/EvidenceItemVisualSection"
import { QualityOverrideDialog, type QualityOverridePayload } from "@/src/components/spectracheck/QualityOverrideDialog"
import { QualityStatusBadge } from "@/src/components/spectracheck/QualityStatusBadge"
import { ReadinessStatusBadge } from "@/src/components/spectracheck/ReadinessStatusBadge"
import { apiFetch } from "@/src/lib/api/client"
import {
  fetchSessionComments,
  pickCommentText,
  pickCommentType,
  postSessionComment,
  sessionCommentMatchesEvidence,
  SESSION_COMMENT_TYPES,
} from "@/src/lib/spectracheck/spectracheck-session-comments"
import type { EvidenceItem, EvidenceItemStatus } from "@/src/lib/spectracheck/evidence-types"
import { hasMethodProvenanceFields } from "@/src/lib/spectracheck/evidence-method-provenance"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import {
  effectiveEvidenceReadiness,
  isUnifiedSendBlocked,
  mapAssessmentResponseToEvidencePatch,
  patchEvidenceAfterOverride,
} from "@/src/lib/spectracheck/evidence-queue-qc"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { cn } from "@/lib/utils"

const EVIDENCE_QUEUE_TOOLTIP =
  "Selected analysis results from NMR, MS, LC-MS, and prediction tabs. These are the evidence layers that can be sent into Unified Evidence."

const METHOD_PROVENANCE_TOOLTIP =
  "Method provenance records which algorithm, model version, scoring profile, and thresholds produced this evidence."

function statusBadgeClass(status: EvidenceItemStatus) {
  switch (status) {
    case "ready":
      return "border-transparent bg-secondary text-secondary-foreground"
    case "warning":
      return "border border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-100"
    case "error":
      return "border-transparent bg-destructive text-white dark:bg-destructive/60"
    case "pending_review":
      return "border border-muted-foreground/30 text-muted-foreground"
    default:
      return "border-transparent bg-secondary text-secondary-foreground"
  }
}

function statusLabel(status: EvidenceItemStatus) {
  switch (status) {
    case "ready":
      return "ready"
    case "warning":
      return "warning"
    case "error":
      return "error"
    case "pending_review":
      return "pending review"
    default:
      return status
  }
}

function useEvidenceQueueStats(evidenceItems: EvidenceItem[]) {
  return useMemo(() => {
    const total = evidenceItems.length
    const selected = evidenceItems.filter((e) => e.selectedForUnified).length
    const withWarnings = evidenceItems.filter(
      (e) => e.status === "warning" || (e.warnings?.length ?? 0) > 0,
    ).length
    const withContradictions = evidenceItems.filter((e) => (e.contradictions?.length ?? 0) > 0).length
    return { total, selected, withWarnings, withContradictions }
  }, [evidenceItems])
}

function readinessLabelForDialog(status: ReturnType<typeof effectiveEvidenceReadiness>): string {
  switch (status) {
    case "ready_for_unified_evidence":
      return "Ready for Unified Evidence"
    case "usable_with_warnings":
      return "Usable with warnings"
    case "blocked_until_review":
      return "Blocked until review"
    case "not_ready":
      return "Not ready"
    default:
      return status
  }
}

type LocalEvidenceComment = {
  localId: string
  comment_type: string
  comment: string
}

type EvidenceItemRowProps = {
  item: EvidenceItem
  runQcBusy: boolean
  onRunEvidenceQc: (item: EvidenceItem) => void
  onOpenOverride: (item: EvidenceItem) => void
  sessionId: string | null
  serverCommentRows: Record<string, unknown>[]
  localComments: LocalEvidenceComment[]
  sessionCommentsBusy: boolean
  onOpenEvidenceComments: (item: EvidenceItem, mode: "view" | "add") => void
}

function EvidenceItemRow({
  item,
  runQcBusy,
  onRunEvidenceQc,
  onOpenOverride,
  sessionId,
  serverCommentRows,
  localComments,
  sessionCommentsBusy,
  onOpenEvidenceComments,
}: EvidenceItemRowProps) {
  const { toggleSelectedForUnified, removeEvidenceItem } = useSpectraCheckEvidence()
  const qcStatus = item.qcStatus ?? "not_assessed"
  const readiness = effectiveEvidenceReadiness(item)
  const hasBackendId = item.backendEvidenceId != null
  const commentTotal = serverCommentRows.length + localComments.length
  const showOverride =
    hasBackendId &&
    (item.qcStatus === "qc_fail" ||
      item.qcStatus === "requires_human_review" ||
      readiness === "blocked_until_review")

  return (
    <li className="min-w-0 list-none border-b border-border/50 py-3 last:border-0 last:pb-0">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <p className="truncate text-sm font-medium leading-tight" title={item.title}>
              {item.title}
            </p>
            {item.visualReviewed ? (
              <Badge variant="outline" className="shrink-0 text-[10px] font-normal">
                Preview inspected
              </Badge>
            ) : null}
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <Badge
              variant="outline"
              className="max-w-full truncate font-mono text-[10px] leading-tight"
              title={item.layer}
            >
              {item.layer}
            </Badge>
            <span
              className={cn(
                "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
                statusBadgeClass(item.status),
              )}
            >
              {statusLabel(item.status)}
            </span>
            {item.score !== undefined && (
              <Badge variant="secondary" className="shrink-0">
                score {typeof item.score === "number" ? item.score.toFixed(3) : String(item.score)}
              </Badge>
            )}
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-1">
            <QualityStatusBadge status={qcStatus} />
            <ReadinessStatusBadge status={readiness} />
          </div>
          <div className="min-w-0 pt-0.5">
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                Method provenance
              </span>
              <InfoTooltip content={METHOD_PROVENANCE_TOOLTIP} label="Method provenance" />
            </div>
            {hasMethodProvenanceFields(item) ? (
              <div className="mt-0.5 space-y-0.5 text-[11px] text-muted-foreground">
                {item.methodName || item.methodId || item.methodVersion ? (
                  <p>
                    <span className="text-foreground/80">Method: </span>
                    {[item.methodName ?? item.methodId, item.methodVersion].filter(Boolean).join(" · ") || "—"}
                  </p>
                ) : null}
                {item.modelName || item.modelVersionId || item.modelVersion ? (
                  <p>
                    <span className="text-foreground/80">Model: </span>
                    {[item.modelName, item.modelVersionId, item.modelVersion].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
                {item.scoringProfileName || item.scoringProfileId ? (
                  <p>
                    <span className="text-foreground/80">Scoring: </span>
                    {item.scoringProfileName ?? item.scoringProfileId}
                  </p>
                ) : null}
                {item.thresholdProfileName || item.thresholdProfileId ? (
                  <p>
                    <span className="text-foreground/80">QC thresholds: </span>
                    {item.thresholdProfileName ?? item.thresholdProfileId}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="mt-0.5 text-[11px] text-muted-foreground">Method provenance not recorded.</p>
            )}
            <div className="pt-1.5">
              <MlModelProvenanceSummary
                itemFields={{
                  modelArtifactId: item.modelArtifactId,
                  datasetVersionId: item.datasetVersionId,
                  evaluationRunId: item.evaluationRunId,
                  deploymentCandidateId: item.deploymentCandidateId,
                  modelCardId: item.modelCardId,
                  approvalStatus: item.approvalStatus,
                  methodId: item.methodId,
                  modelName: item.modelName,
                  modelVersion: item.modelVersion,
                }}
                sources={[item.response, item.requestPreview]}
              />
            </div>
          </div>
          {!hasBackendId ? (
            <p className="text-[11px] text-muted-foreground">Save evidence to session before QC assessment.</p>
          ) : qcStatus === "not_assessed" ? (
            <p className="text-[11px] text-amber-800/90 dark:text-amber-200/90">
              Run QC to assess quality before sending to Unified Evidence.
            </p>
          ) : null}
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-muted-foreground tabular-nums">{commentTotal} comments</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-[11px]"
              disabled={sessionCommentsBusy && Boolean(sessionId?.trim())}
              onClick={() => onOpenEvidenceComments(item, "add")}
            >
              Add comment
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[11px]"
              onClick={() => onOpenEvidenceComments(item, "view")}
            >
              View comments
            </Button>
          </div>
          {!hasBackendId ? (
            <p className="text-[11px] text-muted-foreground">
              Save evidence to session before attaching backend comments.
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:justify-end">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8"
            disabled={!hasBackendId || runQcBusy}
            onClick={() => onRunEvidenceQc(item)}
          >
            {runQcBusy ? "Running…" : "Run QC"}
          </Button>
          {showOverride ? (
            <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => onOpenOverride(item)}>
              Override
            </Button>
          ) : null}
          <Checkbox
            checked={item.selectedForUnified}
            onCheckedChange={() => toggleSelectedForUnified(item.id)}
            id={`ev-q-${item.id}`}
            aria-label="Selected for Unified Evidence"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-muted-foreground"
            onClick={() => removeEvidenceItem(item.id)}
            aria-label="Remove"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <Collapsible className="min-w-0 sm:max-w-[11rem]">
            <CollapsibleTrigger asChild>
              <Button type="button" variant="outline" size="sm" className="h-8 max-w-full shrink px-2 text-xs">
                <FileJson className="mr-1 h-3.5 w-3.5 shrink-0" />
                View details
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 min-w-0 data-[state=closed]:hidden">
              <pre className="max-h-48 overflow-x-auto overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-2 text-[10px] leading-relaxed">
                {JSON.stringify(item, null, 2)}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </div>
      <EvidenceItemVisualSection item={item} spectracheckSessionId={sessionId} />
    </li>
  )
}

function StatsGrid({
  total,
  selected,
  withWarnings,
  withContradictions,
}: {
  total: number
  selected: number
  withWarnings: number
  withContradictions: number
}) {
  return (
    <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <div className="rounded-md border bg-muted/20 px-2 py-1.5">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Items</p>
        <p className="font-semibold tabular-nums">{total}</p>
      </div>
      <div className="rounded-md border bg-muted/20 px-2 py-1.5">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Selected</p>
        <p className="font-semibold tabular-nums">{selected}</p>
      </div>
      <div className="rounded-md border bg-muted/20 px-2 py-1.5">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Warnings</p>
        <p className="font-semibold tabular-nums">{withWarnings}</p>
      </div>
      <div className="rounded-md border bg-muted/20 px-2 py-1.5">
        <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Contradictions</p>
        <p className="font-semibold tabular-nums">{withContradictions}</p>
      </div>
    </div>
  )
}

type SpectraCheckEvidenceQueuePanelProps = {
  onSendToUnified: () => void
  /** Backend SpectraCheck session id — loads session-scoped comments when set. */
  sessionId?: string | null
}

export function SpectraCheckEvidenceQueuePanel({
  onSendToUnified,
  sessionId = null,
}: SpectraCheckEvidenceQueuePanelProps) {
  const { evidenceItems, clearEvidenceItems, selectAllForUnified, updateEvidenceItem, getSelectedEvidenceItems } =
    useSpectraCheckEvidence()
  const stats = useEvidenceQueueStats(evidenceItems)
  const empty = evidenceItems.length === 0

  const sid = sessionId?.trim() ?? ""

  const [sessionCommentRows, setSessionCommentRows] = useState<Record<string, unknown>[]>([])
  const [sessionCommentsBusy, setSessionCommentsBusy] = useState(false)
  const [sessionCommentsErr, setSessionCommentsErr] = useState("")
  const [localCommentsByItemId, setLocalCommentsByItemId] = useState<Record<string, LocalEvidenceComment[]>>({})

  const [evidenceCommentItem, setEvidenceCommentItem] = useState<EvidenceItem | null>(null)
  const [evidenceCommentMode, setEvidenceCommentMode] = useState<"view" | "add">("view")
  const [evidenceCommentType, setEvidenceCommentType] = useState<string>(SESSION_COMMENT_TYPES[0])
  const [evidenceCommentDraft, setEvidenceCommentDraft] = useState("")
  const [evidenceCommentPostBusy, setEvidenceCommentPostBusy] = useState(false)
  const [evidenceCommentPostErr, setEvidenceCommentPostErr] = useState("")

  const loadSessionComments = useCallback(async () => {
    if (!sid) {
      setSessionCommentRows([])
      setSessionCommentsErr("")
      return
    }
    setSessionCommentsBusy(true)
    setSessionCommentsErr("")
    try {
      const rows = await fetchSessionComments(sid)
      setSessionCommentRows(rows)
    } catch (err) {
      setSessionCommentsErr(formatApiError(err, "Could not load session comments."))
      setSessionCommentRows([])
    } finally {
      setSessionCommentsBusy(false)
    }
  }, [sid])

  useEffect(() => {
    void loadSessionComments()
  }, [loadSessionComments])

  const commentRowsByItemId = useMemo(() => {
    const m = new Map<string, Record<string, unknown>[]>()
    for (const item of evidenceItems) {
      const rows = sessionCommentRows.filter((c) => sessionCommentMatchesEvidence(c, item))
      m.set(item.id, rows)
    }
    return m
  }, [sessionCommentRows, evidenceItems])

  const [runQcItemId, setRunQcItemId] = useState<string | null>(null)
  const [overrideItem, setOverrideItem] = useState<EvidenceItem | null>(null)
  const [overrideBusy, setOverrideBusy] = useState(false)
  const [blockedOpen, setBlockedOpen] = useState(false)
  const [blockedItems, setBlockedItems] = useState<EvidenceItem[]>([])

  async function runEvidenceQc(item: EvidenceItem) {
    if (item.backendEvidenceId == null) return
    const eid = String(item.backendEvidenceId)
    setRunQcItemId(item.id)
    try {
      const res = await apiFetch<unknown>(`/quality-control/evidence/${encodeURIComponent(eid)}/assess`, {
        method: "POST",
        body: {},
      })
      updateEvidenceItem(item.id, mapAssessmentResponseToEvidencePatch(res))
    } catch {
      try {
        const g = await apiFetch<unknown>(`/quality-control/evidence/${encodeURIComponent(eid)}`, { method: "GET" })
        updateEvidenceItem(item.id, mapAssessmentResponseToEvidencePatch(g))
      } catch {
        // QC endpoints may be unavailable; queue remains usable without assessment.
      }
    } finally {
      setRunQcItemId(null)
    }
  }

  function handleSendToUnifiedClick() {
    const selected = getSelectedEvidenceItems()
    const blocked = selected.filter((item) => isUnifiedSendBlocked(item))
    if (blocked.length > 0) {
      setBlockedItems(blocked)
      setBlockedOpen(true)
      return
    }
    onSendToUnified()
  }

  async function handleOverrideSave(payload: QualityOverridePayload) {
    if (!overrideItem) return
    setOverrideBusy(true)
    try {
      updateEvidenceItem(overrideItem.id, patchEvidenceAfterOverride(overrideItem, payload))
      setOverrideItem(null)
    } finally {
      setOverrideBusy(false)
    }
  }

  function openEvidenceComments(item: EvidenceItem, mode: "view" | "add") {
    setEvidenceCommentItem(item)
    setEvidenceCommentMode(mode)
    setEvidenceCommentPostErr("")
    if (mode === "add") {
      setEvidenceCommentDraft("")
      setEvidenceCommentType(SESSION_COMMENT_TYPES[0])
    }
  }

  async function submitEvidenceQueueComment() {
    const item = evidenceCommentItem
    if (!item) return
    const comment = evidenceCommentDraft.trim()
    if (!comment) {
      setEvidenceCommentPostErr("Comment is required.")
      return
    }
    const canPostSession = Boolean(sid) && item.backendEvidenceId != null
    if (canPostSession) {
      setEvidenceCommentPostBusy(true)
      setEvidenceCommentPostErr("")
      try {
        await postSessionComment(sid, {
          comment_type: evidenceCommentType,
          comment,
          evidence_id: item.backendEvidenceId as number | string,
        })
        setEvidenceCommentDraft("")
        await loadSessionComments()
      } catch (err) {
        setEvidenceCommentPostErr(formatApiError(err, "Could not post comment."))
      } finally {
        setEvidenceCommentPostBusy(false)
      }
      return
    }
    const localId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `local-${Date.now()}-${Math.random().toString(16).slice(2)}`
    setLocalCommentsByItemId((prev) => ({
      ...prev,
      [item.id]: [...(prev[item.id] ?? []), { localId, comment_type: evidenceCommentType, comment }],
    }))
    setEvidenceCommentDraft("")
    setEvidenceCommentPostErr("")
  }

  const dialogItem = evidenceCommentItem
  const dialogServerRows = dialogItem ? (commentRowsByItemId.get(dialogItem.id) ?? []) : []
  const dialogLocalRows = dialogItem ? (localCommentsByItemId[dialogItem.id] ?? []) : []
  const dialogCanPostSession = Boolean(sid && dialogItem?.backendEvidenceId != null)

  return (
    <Card className="min-w-0 shadow-sm">
      <CardHeader className="space-y-1 pb-3">
        <CardTitle className="flex items-start gap-2 text-base">
          <span>Evidence Queue</span>
          <InfoTooltip content={EVIDENCE_QUEUE_TOOLTIP} label="About Evidence Queue" className="mt-0.5" />
        </CardTitle>
        <CardDescription className="text-xs">Registry of analysis results for Unified Evidence.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatsGrid
          total={stats.total}
          selected={stats.selected}
          withWarnings={stats.withWarnings}
          withContradictions={stats.withContradictions}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="w-full sm:w-auto"
            disabled={empty}
            onClick={selectAllForUnified}
          >
            Select all
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full sm:w-auto"
            disabled={empty}
            onClick={clearEvidenceItems}
          >
            Clear all
          </Button>
          <Button
            type="button"
            size="sm"
            className="w-full sm:w-auto"
            disabled={stats.selected === 0}
            onClick={handleSendToUnifiedClick}
          >
            Send selected to Unified Evidence
          </Button>
        </div>
        {empty ? (
          <p className="text-xs text-muted-foreground">
            No items yet. When tabs enqueue analysis results, they appear here for review and selection.
          </p>
        ) : (
          <ul className="max-h-[min(55vh,28rem)] min-w-0 space-y-0 overflow-y-auto overflow-x-hidden pr-0.5 [-webkit-overflow-scrolling:touch]">
            {evidenceItems.map((item) => (
              <EvidenceItemRow
                key={item.id}
                item={item}
                runQcBusy={runQcItemId === item.id}
                onRunEvidenceQc={runEvidenceQc}
                onOpenOverride={setOverrideItem}
                sessionId={sessionId}
                serverCommentRows={commentRowsByItemId.get(item.id) ?? []}
                localComments={localCommentsByItemId[item.id] ?? []}
                sessionCommentsBusy={sessionCommentsBusy}
                onOpenEvidenceComments={openEvidenceComments}
              />
            ))}
          </ul>
        )}
      </CardContent>

      <QualityOverrideDialog
        open={overrideItem != null}
        onOpenChange={(o) => !o && setOverrideItem(null)}
        onSave={(p) => void handleOverrideSave(p)}
        saveBusy={overrideBusy}
      />

      <Dialog
        open={dialogItem != null}
        onOpenChange={(o) => {
          if (!o) {
            setEvidenceCommentItem(null)
            setEvidenceCommentPostErr("")
          }
        }}
      >
        <DialogContent className="max-w-lg max-h-[min(90vh,640px)] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="pr-6">Comments</DialogTitle>
            <DialogDescription className="line-clamp-2">
              {dialogItem ? (
                <>
                  <span className="font-medium text-foreground">{dialogItem.title}</span>
                  {evidenceCommentMode === "add" ? (
                    <span className="text-muted-foreground"> — add a comment</span>
                  ) : null}
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          {sessionCommentsErr ? <p className="text-xs text-destructive">{sessionCommentsErr}</p> : null}
          {!sid ? (
            <p className="text-xs text-muted-foreground">
              No backend session is connected. Notes below can be stored locally in this browser only.
            </p>
          ) : null}
          {dialogItem && !dialogItem.backendEvidenceId ? (
            <p className="text-xs text-muted-foreground">
              Save evidence to session before attaching backend comments.
            </p>
          ) : null}
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Linked comments</p>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Type</TableHead>
                    <TableHead className="text-xs">Comment</TableHead>
                    <TableHead className="text-xs text-right">Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {dialogServerRows.length === 0 && dialogLocalRows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-xs text-muted-foreground">
                        No comments yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    <>
                      {dialogServerRows.map((row, i) => (
                        <TableRow key={String((row as { id?: unknown }).id ?? (row as { comment_id?: unknown }).comment_id ?? `s-${i}`)}>
                          <TableCell className="align-top text-xs">
                            <Badge variant="outline" className="font-normal">
                              {pickCommentType(row)}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-prose align-top text-xs whitespace-pre-wrap break-words">
                            {pickCommentText(row) || "—"}
                          </TableCell>
                          <TableCell className="align-top text-right text-[10px] text-muted-foreground">Session</TableCell>
                        </TableRow>
                      ))}
                      {dialogLocalRows.map((row) => (
                        <TableRow key={row.localId}>
                          <TableCell className="align-top text-xs">
                            <Badge variant="outline" className="font-normal">
                              {row.comment_type}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-prose align-top text-xs whitespace-pre-wrap break-words">
                            {row.comment}
                          </TableCell>
                          <TableCell className="align-top text-right text-[10px] text-muted-foreground">
                            <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1 py-0.5 text-amber-900 dark:text-amber-100">
                              Local only
                            </span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
          <div className="space-y-3 border-t pt-3">
            <p className="text-xs font-medium text-muted-foreground">Add comment</p>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Comment type</Label>
                <Select value={evidenceCommentType} onValueChange={setEvidenceCommentType}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SESSION_COMMENT_TYPES.map((t) => (
                      <SelectItem key={t} value={t} className="text-xs">
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ev-q-comment-body" className="text-xs">
                Comment
              </Label>
              <Textarea
                id="ev-q-comment-body"
                value={evidenceCommentDraft}
                onChange={(e) => setEvidenceCommentDraft(e.target.value)}
                rows={3}
                className="text-sm"
              />
            </div>
            {evidenceCommentPostErr ? <p className="text-xs text-destructive">{evidenceCommentPostErr}</p> : null}
            <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
              {dialogCanPostSession ? (
                <Button
                  type="button"
                  size="sm"
                  disabled={evidenceCommentPostBusy || sessionCommentsBusy}
                  onClick={() => void submitEvidenceQueueComment()}
                >
                  {evidenceCommentPostBusy ? "Posting…" : "Post to session"}
                </Button>
              ) : (
                <Button type="button" size="sm" variant="secondary" onClick={() => void submitEvidenceQueueComment()}>
                  Add local note (this browser only)
                </Button>
              )}
              <Button type="button" variant="outline" size="sm" onClick={() => setEvidenceCommentItem(null)}>
                Close
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={blockedOpen} onOpenChange={setBlockedOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Cannot send to Unified Evidence</DialogTitle>
            <DialogDescription>
              One or more selected items are not ready or require review. Run QC, then use Override only when permitted.
              Blocked evidence is not sent silently.
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-56 list-inside list-disc space-y-1 overflow-y-auto text-sm">
            {blockedItems.map((b) => (
              <li key={b.id}>
                <span className="font-medium">{b.title}</span>
                <span className="text-muted-foreground"> — {readinessLabelForDialog(effectiveEvidenceReadiness(b))}</span>
              </li>
            ))}
          </ul>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={() => setBlockedOpen(false)}>
              Close
            </Button>
            <div className="flex flex-wrap gap-2">
              {blockedItems.map((b) =>
                b.backendEvidenceId != null ? (
                  <Button
                    key={`run-${b.id}`}
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={runQcItemId === b.id}
                    onClick={() => void runEvidenceQc(b)}
                  >
                    Run QC ({b.title.slice(0, 24)}
                    {b.title.length > 24 ? "…" : ""})
                  </Button>
                ) : null,
              )}
              {blockedItems.map((b) =>
                (b.qcStatus === "qc_fail" || b.qcStatus === "requires_human_review") && b.backendEvidenceId != null ? (
                  <Button
                    key={`ov-${b.id}`}
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setBlockedOpen(false)
                      setOverrideItem(b)
                    }}
                  >
                    Override ({b.title.slice(0, 20)}
                    {b.title.length > 20 ? "…" : ""})
                  </Button>
                ) : null,
              )}
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

/** Compact summary for the Unified evidence tab; mirrors queue counts without duplicating MS Evidence content. */
export function SpectraCheckEvidenceQueueUnifiedSummary() {
  const { evidenceItems } = useSpectraCheckEvidence()
  const stats = useEvidenceQueueStats(evidenceItems)

  return (
    <Card className="min-w-0 border-dashed shadow-none">
      <CardHeader className="pb-2 pt-4">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          Evidence Queue
          <InfoTooltip content={EVIDENCE_QUEUE_TOOLTIP} label="About Evidence Queue" className="size-4" />
        </CardTitle>
        <CardDescription className="text-xs">
          On wide screens the full queue is in the side panel; counts stay in sync here.
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-4 pt-0">
        <StatsGrid
          total={stats.total}
          selected={stats.selected}
          withWarnings={stats.withWarnings}
          withContradictions={stats.withContradictions}
        />
      </CardContent>
    </Card>
  )
}
