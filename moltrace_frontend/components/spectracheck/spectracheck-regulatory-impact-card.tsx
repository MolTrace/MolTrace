"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { ChevronDown } from "lucide-react"

const TOOLTIP =
  "Converts SpectraCheck evidence such as impurity peaks, residual solvent flags, nitrosamine-like signals, qNMR outputs, QC warnings, and AI provenance into regulatory action items for review."

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

type Props = {
  sessionId: string | null
  evidenceItemIds?: Array<string | number>
}

export function SpectraCheckRegulatoryImpactCard({ sessionId, evidenceItemIds = [] }: Props) {
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState("")
  const [bridges, setBridges] = useState<Record<string, unknown>[]>([])
  const [lastBridge, setLastBridge] = useState<Record<string, unknown> | null>(null)
  const [reportIdInput, setReportIdInput] = useState("")
  const [dossierIdInput, setDossierIdInput] = useState("")
  const [compoundIdInput, setCompoundIdInput] = useState("")
  const [batchIdInput, setBatchIdInput] = useState("")

  const load = useCallback(async () => {
    const sid = sessionId?.trim()
    if (!sid) {
      setBridges([])
      setLastBridge(null)
      return
    }
    setLoading(true)
    setErr("")
    try {
      const data = await apiFetch<unknown>(
        `/bridges/spectroscopy-to-regulatory?spectracheck_session_id=${encodeURIComponent(sid)}`,
        { method: "GET" },
      )
      const rows = asArray(data).map(asRecord).filter((v): v is Record<string, unknown> => v != null)
      setBridges(rows)
      setLastBridge(rows[0] ?? null)
    } catch (e) {
      setErr(formatApiError(e, "Regulatory bridge summary unavailable."))
      setBridges([])
      setLastBridge(null)
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => {
    void load()
  }, [load])

  async function sendToRegulatoryHub() {
    const sid = sessionId?.trim()
    if (!sid) return
    setSending(true)
    setErr("")
    try {
      const body: Record<string, unknown> = {
        spectracheck_session_id: sid,
        evidence_item_ids: evidenceItemIds.map((v) => String(v)),
      }
      const reportId = parseOptionalNumber(reportIdInput)
      const dossierId = parseOptionalNumber(dossierIdInput)
      const compoundId = parseOptionalNumber(compoundIdInput)
      const batchId = parseOptionalNumber(batchIdInput)
      if (reportId != null) body.report_id = reportId
      if (dossierId != null) body.dossier_id = dossierId
      if (compoundId != null) body.compound_id = compoundId
      if (batchId != null) body.batch_id = batchId
      const created = await apiFetch<unknown>("/bridges/spectroscopy-to-regulatory", {
        method: "POST",
        body,
      })
      const createdRec = asRecord(created)
      if (createdRec) setLastBridge(createdRec)
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Send evidence to Regulatory Hub failed."))
    } finally {
      setSending(false)
    }
  }

  const extractedSignals = asArray(lastBridge?.extracted_regulatory_signals_json)
  const createdRequirements = asArray(lastBridge?.created_requirement_ids_json)
  const createdActionItems = asArray(lastBridge?.created_action_item_ids_json)
  const warnings = asArray(lastBridge?.warnings_json)
  const notes = asArray(lastBridge?.notes_json)
  const humanReviewRequired =
    typeof lastBridge?.human_review_required === "boolean" ? lastBridge.human_review_required : true

  const hasSession = Boolean(sessionId?.trim())

  return (
    <Card className="border-muted">
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Regulatory Impact</CardTitle>
          <InfoTooltip label="Regulatory impact" content={TOOLTIP} />
        </div>
        <CardDescription>
          Bridge handoff to Regulatory Hub for review-required action items. Decision support only — not legal advice.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="bridge-session-id">SpectraCheck session ID</Label>
            <Input id="bridge-session-id" value={sessionId ?? ""} disabled />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bridge-evidence-item-ids">Evidence item IDs</Label>
            <Input id="bridge-evidence-item-ids" value={evidenceItemIds.map(String).join(", ")} disabled />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bridge-report-id">Report ID (optional)</Label>
            <Input id="bridge-report-id" value={reportIdInput} onChange={(e) => setReportIdInput(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bridge-dossier-id">Dossier ID (optional)</Label>
            <Input id="bridge-dossier-id" value={dossierIdInput} onChange={(e) => setDossierIdInput(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bridge-compound-id">Compound ID (optional)</Label>
            <Input id="bridge-compound-id" value={compoundIdInput} onChange={(e) => setCompoundIdInput(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bridge-batch-id">Batch ID (optional)</Label>
            <Input id="bridge-batch-id" value={batchIdInput} onChange={(e) => setBatchIdInput(e.target.value)} />
          </div>
        </div>

        {!dossierIdInput.trim() ? (
          <p className="text-xs text-muted-foreground">
            Create or select a regulatory dossier before creating dossier-linked regulatory action items.
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => void sendToRegulatoryHub()} disabled={sending || !hasSession}>
            {sending ? "Sending…" : "Send evidence to Regulatory Hub"}
          </Button>
          <Button type="button" variant="outline" asChild>
            <Link href="/regulatory">Open Regulatory Hub</Link>
          </Button>
        </div>

        {!hasSession ? (
          <p className="text-xs text-muted-foreground">
            Connect or create a SpectraCheck backend session to enable bridge handoff.
          </p>
        ) : null}
        {loading ? <p className="text-xs text-muted-foreground">Loading regulatory bridge records…</p> : null}
        {err ? <p className="text-xs text-destructive">{err}</p> : null}

        <div className="grid gap-2 md:grid-cols-2">
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Extracted regulatory signals</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {extractedSignals.length ? extractedSignals.map((v) => readString(v) || JSON.stringify(v)).join(", ") : "—"}
            </p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Created requirements</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {createdRequirements.length ? createdRequirements.map((v) => readString(v) || JSON.stringify(v)).join(", ") : "—"}
            </p>
          </div>
          <div className="rounded-md border bg-muted/20 px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Created action items</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {createdActionItems.length ? createdActionItems.map((v) => readString(v) || JSON.stringify(v)).join(", ") : "—"}
            </p>
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
                  spectracheck_session_id: sessionId?.trim() || null,
                  evidence_item_ids: evidenceItemIds.map(String),
                  report_id: parseOptionalNumber(reportIdInput),
                  dossier_id: parseOptionalNumber(dossierIdInput),
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
