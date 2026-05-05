"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackRegulatoryBatchAssessmentRun } from "@/src/lib/analytics/analytics-client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordString } from "@/components/projects/project-workspace-utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Loader2, ChevronDown } from "lucide-react"
import { readRegulatoryDossierCompoundLink } from "@/components/regulatory-hub/regulatory-dossier-linked-compound-card"

const BATCH_REGULATORY_ASSESSMENT_TOOLTIP =
  "Aggregates impurity register counts, residual solvent and nitrosamine prior assessments on dossier, latest qNMR compliance snapshot, AI governance snapshot, and open regulatory action items."

const MISSING_BATCH_MSG = "Link a compound batch before running batch-level assessment."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function readinessLabel(raw: string | undefined): string {
  if (!raw) return "—"
  return raw.replace(/_/g, " ")
}

function readStringArray(row: Record<string, unknown>, key: string): string[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string")
}

function readIntListField(row: Record<string, unknown>, key: string): number[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function warningLines(row: Record<string, unknown>): string[] {
  if (Array.isArray(row.warnings)) {
    return row.warnings.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(row, "warnings_json")
}

function noteLines(row: Record<string, unknown>): string[] {
  if (Array.isArray(row.notes)) {
    return row.notes.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(row, "notes_json")
}

export type BatchRegulatoryAssessmentPanelProps = {
  dossierId: number
  /** When set (e.g. batch registry), POST uses these in addition to session link. */
  contextBatchId?: number | null
  contextCompoundId?: number | null
  compact?: boolean
  /** Increment when compound/batch link in session may have changed (dossier workspace). */
  compoundLinkVersion?: number
}

export function BatchRegulatoryAssessmentPanel({
  dossierId,
  contextBatchId,
  contextCompoundId,
  compact,
  compoundLinkVersion = 0,
}: BatchRegulatoryAssessmentPanelProps) {
  const [list, setList] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [runBusy, setRunBusy] = useState(false)
  const [linkTick, setLinkTick] = useState(0)

  const load = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    setLoading(true)
    setErr("")
    try {
      const raw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/batch-assessment`, { method: "GET" })
      setList(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setErr(formatApiError(e, "Could not load batch assessments."))
      setList([])
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const onFocus = () => setLinkTick((n) => n + 1)
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [])

  const sessionLink = useMemo(() => {
    if (typeof window === "undefined") return null
    void linkTick
    void compoundLinkVersion
    return readRegulatoryDossierCompoundLink(dossierId)
  }, [dossierId, linkTick, compoundLinkVersion])

  const hasBatchForRun = useMemo(() => {
    if (contextBatchId != null && Number.isFinite(contextBatchId) && contextBatchId >= 1) return true
    const bid = sessionLink?.batch_id
    return bid != null && Number.isFinite(bid) && bid >= 1
  }, [contextBatchId, sessionLink])

  const latest = list[0] ?? null

  const run = async () => {
    if (!Number.isFinite(dossierId)) return
    if (!hasBatchForRun) {
      setErr(MISSING_BATCH_MSG)
      return
    }
    setRunBusy(true)
    setErr("")
    try {
      const body: Record<string, unknown> = { metadata_json: {} }
      const b =
        contextBatchId != null && Number.isFinite(contextBatchId) && contextBatchId >= 1
          ? contextBatchId
          : sessionLink?.batch_id
      const c =
        contextCompoundId != null && Number.isFinite(contextCompoundId) && contextCompoundId >= 1
          ? contextCompoundId
          : sessionLink?.compound_id
      if (b != null && Number.isFinite(b) && b >= 1) body.batch_id = b
      if (c != null && Number.isFinite(c) && c >= 1) body.compound_id = c
      await apiFetch(`/regulatory/dossiers/${dossierId}/batch-assessment`, {
        method: "POST",
        body,
      })
      trackRegulatoryBatchAssessmentRun({ dossier_id: dossierId, status: "batch_linked_run" })
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Run batch assessment failed."))
    } finally {
      setRunBusy(false)
    }
  }

  const hrr =
    latest && typeof latest.human_review_required === "boolean"
      ? String(latest.human_review_required)
      : latest
        ? "true"
        : "—"

  return (
    <Card className={compact ? "border-muted" : undefined}>
      <CardHeader className={compact ? "pb-2" : undefined}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className={compact ? "text-base" : "text-lg"}>Batch Regulatory Assessment</CardTitle>
              <InfoTooltip label="Batch regulatory assessment" content={BATCH_REGULATORY_ASSESSMENT_TOOLTIP} />
            </div>
            <CardDescription>
              POST /regulatory/dossiers/{"{dossier_id}"}/batch-assessment · GET
              /regulatory/dossiers/{"{dossier_id}"}/batch-assessment
            </CardDescription>
          </div>
          <Button type="button" size="sm" variant="outline" disabled={runBusy} onClick={() => void run()}>
            {runBusy ? <Loader2 className="mr-2 size-4 animate-spin" aria-hidden /> : null}
            Run batch assessment
          </Button>
        </div>
      </CardHeader>
      <CardContent className={compact ? "space-y-3" : "space-y-4"}>
        {!hasBatchForRun ? (
          <Alert>
            <AlertDescription className="text-sm">{MISSING_BATCH_MSG}</AlertDescription>
          </Alert>
        ) : null}

        {err ? (
          <Alert variant="destructive">
            <AlertDescription className="text-sm">{err}</AlertDescription>
          </Alert>
        ) : null}

        {loading ? (
          <p className="text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline size-4 animate-spin" aria-hidden />
            Loading assessments…
          </p>
        ) : !latest ? (
          <p className="text-sm text-muted-foreground">No batch assessments yet for this dossier.</p>
        ) : (
          <div className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">overall status</dt>
                <dd className="mt-1 text-sm font-medium">{readinessLabel(readRecordString(latest, "overall_status"))}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">action item count</dt>
                <dd className="mt-1 font-mono text-sm">{readIntListField(latest, "action_item_ids_json").length}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  human_review_required
                </dt>
                <dd className="mt-1 font-mono text-xs">{hrr}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">created_at</dt>
                <dd className="mt-1 text-xs text-muted-foreground">{readRecordString(latest, "created_at") ?? "—"}</dd>
              </div>
            </dl>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">warnings</p>
              {warningLines(latest).length ? (
                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                  {warningLines(latest).map((w, i) => (
                    <li key={`ba-w-${i}`}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">—</p>
              )}
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">notes</p>
              {noteLines(latest).length ? (
                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                  {noteLines(latest).map((n, i) => (
                    <li key={`ba-n-${i}`}>{n}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">—</p>
              )}
            </div>

            <div className="grid gap-3 lg:grid-cols-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">impurity summary</p>
                <div className="mt-2">
                  <DeveloperJsonPanel data={latest.impurity_summary_json && typeof latest.impurity_summary_json === "object" ? latest.impurity_summary_json : {}} />
                </div>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  residual solvent summary
                </p>
                <div className="mt-2">
                  <DeveloperJsonPanel
                    data={
                      latest.residual_solvent_summary_json && typeof latest.residual_solvent_summary_json === "object"
                        ? latest.residual_solvent_summary_json
                        : {}
                    }
                  />
                </div>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">nitrosamine summary</p>
                <div className="mt-2">
                  <DeveloperJsonPanel
                    data={
                      latest.nitrosamine_summary_json && typeof latest.nitrosamine_summary_json === "object"
                        ? latest.nitrosamine_summary_json
                        : {}
                    }
                  />
                </div>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">qNMR summary</p>
                <div className="mt-2">
                  <DeveloperJsonPanel
                    data={latest.qnmr_summary_json && typeof latest.qnmr_summary_json === "object" ? latest.qnmr_summary_json : {}}
                  />
                </div>
              </div>
              <div className="lg:col-span-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">AI governance summary</p>
                <div className="mt-2">
                  <DeveloperJsonPanel
                    data={
                      latest.ai_governance_summary_json && typeof latest.ai_governance_summary_json === "object"
                        ? latest.ai_governance_summary_json
                        : {}
                    }
                  />
                </div>
              </div>
            </div>

            <Collapsible className="rounded-md border bg-muted/15">
              <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/40">
                metadata_json (latest row)
                <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
              </CollapsibleTrigger>
              <CollapsibleContent className="border-t px-3 pb-3 pt-2">
                <DeveloperJsonPanel
                  data={latest.metadata_json && typeof latest.metadata_json === "object" ? latest.metadata_json : {}}
                />
              </CollapsibleContent>
            </Collapsible>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
