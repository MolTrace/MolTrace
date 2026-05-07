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

type Row = Record<string, unknown>

type MobileReportDraft = {
  comment?: string
  decision?: "approve" | "reject"
  share_requested?: boolean
  updated_at: string
}

type MobileReportPreviewSummary = {
  reportId: string
  reportTitle: string
  sampleCompoundBatch: string
  reviewStatus: string
  qcSummary: string
  regulatoryActionSummary: string
  methodModelProvenance: string
  sourceHashes: string[]
  humanApprovalState: string
  keyWarnings: string[]
  canApproveReject: boolean
  canShare: boolean
  largeReport: boolean
}

const DRAFTS_KEY = "moltrace:mobile:report-preview-drafts:v1"

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readBool(v: unknown): boolean {
  if (typeof v === "boolean") return v
  if (typeof v === "string") return ["true", "1", "yes", "allowed"].includes(v.trim().toLowerCase())
  if (typeof v === "number") return v === 1
  return false
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

function loadDrafts(): Record<string, MobileReportDraft> {
  if (typeof window === "undefined") return {}
  try {
    const raw = window.localStorage.getItem(DRAFTS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    return isRecord(parsed) ? (parsed as Record<string, MobileReportDraft>) : {}
  } catch {
    return {}
  }
}

function saveDrafts(drafts: Record<string, MobileReportDraft>) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts))
  } catch {
    // ignore localStorage failures
  }
}

function compactText(v: string, maxLen = 220): string {
  if (v.length <= maxLen) return v
  return `${v.slice(0, maxLen - 1)}…`
}

function parsePreview(reportId: string, payload: unknown): MobileReportPreviewSummary {
  const root = isRecord(payload) ? payload : {}
  const sourceHashes = [...readList(root.source_hashes), ...readList(root.source_hashes_json)]
  const keyWarnings = [...readList(root.key_warnings), ...readList(root.warnings), ...readList(root.warnings_json)]
  const largeReport = readBool(root.is_large_report) || readBool(root.large_report) || readBool(root.compact_only)
  return {
    reportId,
    reportTitle: readFirstString(root, ["report_title", "title"]) || "Untitled report",
    sampleCompoundBatch:
      readFirstString(root, ["sample_compound_batch", "sample_compound_batch_summary", "sample_compound_batch_label"]) || "—",
    reviewStatus: readFirstString(root, ["review_status", "status"]) || "Unknown",
    qcSummary: compactText(readFirstString(root, ["qc_summary", "qc_summary_text", "quality_summary"]) || "—"),
    regulatoryActionSummary: compactText(
      readFirstString(root, ["regulatory_action_summary", "regulatory_summary", "regulatory_actions_summary"]) || "—",
    ),
    methodModelProvenance: compactText(
      readFirstString(root, ["method_model_provenance", "provenance_summary", "method_provenance"]) || "—",
    ),
    sourceHashes: Array.from(new Set(sourceHashes)).slice(0, 6),
    humanApprovalState: readFirstString(root, ["human_approval_state", "approval_state"]) || "Unknown",
    keyWarnings: Array.from(new Set(keyWarnings)).slice(0, 5),
    canApproveReject: readBool(root.approve_reject_allowed) || readBool(root.can_approve_reject),
    canShare: readBool(root.share_allowed) || readBool(root.can_share),
    largeReport,
  }
}

export function MobileReportPreview({ reportId: reportIdProp = null }: { reportId?: string | null }) {
  const searchParams = useSearchParams()
  const reportId = (reportIdProp ?? searchParams.get("reportId") ?? "").trim()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [preview, setPreview] = useState<MobileReportPreviewSummary | null>(null)
  const [drafts, setDrafts] = useState<Record<string, MobileReportDraft>>({})

  useEffect(() => {
    setDrafts(loadDrafts())
  }, [])

  useEffect(() => {
    if (!reportId) {
      setPreview(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError("")
    void apiFetch<unknown>(`/mobile/reports/${encodeURIComponent(reportId)}/preview`, { method: "GET" })
      .then((payload) => {
        if (cancelled) return
        setPreview(parsePreview(reportId, payload))
      })
      .catch(() => {
        if (!cancelled) {
          setPreview(null)
          setError("Could not load mobile report preview.")
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reportId])

  function updateDraft(patch: Partial<MobileReportDraft>) {
    if (!reportId) return
    const key = reportId
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

  const draft = reportId ? drafts[reportId] : undefined
  const desktopHref = useMemo(
    () => (reportId ? `/reports?reportId=${encodeURIComponent(reportId)}` : "/reports"),
    [reportId],
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mobile Report Preview</CardTitle>
        <CardDescription>
          <code className="text-xs">GET /mobile/reports/{"{report_id}"}/preview</code> — compact preview for phone
          review workflows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!reportId ? <p className="text-xs text-muted-foreground">Open a report to load mobile preview.</p> : null}
        {loading ? <p className="text-xs text-muted-foreground">Loading mobile report preview…</p> : null}
        {error ? <p className="text-xs text-destructive">{error}</p> : null}

        {reportId && preview ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">report title</p>
                <p className="text-sm font-medium">{preview.reportTitle}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">sample/compound/batch</p>
                <p className="text-sm font-medium">{preview.sampleCompoundBatch}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">review status</p>
                <p className="text-sm font-medium">{preview.reviewStatus}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">human approval state</p>
                <p className="text-sm font-medium">{preview.humanApprovalState}</p>
              </div>
            </div>

            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">QC summary</p>
              <p className="mt-1 text-xs text-muted-foreground">{preview.qcSummary}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">regulatory action summary</p>
              <p className="mt-1 text-xs text-muted-foreground">{preview.regulatoryActionSummary}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">method/model provenance</p>
              <p className="mt-1 text-xs text-muted-foreground">{preview.methodModelProvenance}</p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">source hashes</p>
              <p className="mt-1 break-all text-xs text-muted-foreground">
                {preview.sourceHashes.length > 0 ? preview.sourceHashes.join(" · ") : "—"}
              </p>
            </div>
            <div className="rounded-md border p-3">
              <p className="text-xs text-muted-foreground">key warnings</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {preview.keyWarnings.length > 0 ? preview.keyWarnings.join(" · ") : "—"}
              </p>
            </div>
          </>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="mobile-report-comment" className="text-xs">
              review comment
            </Label>
            <Input
              id="mobile-report-comment"
              value={draft?.comment ?? ""}
              onChange={(e) => updateDraft({ comment: e.target.value })}
              className="h-8 text-xs"
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => updateDraft({ comment: draft?.comment ?? "" })}>
            Add review comment
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!preview?.canApproveReject}
            onClick={() => updateDraft({ decision: "approve" })}
          >
            Approve
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!preview?.canApproveReject}
            onClick={() => updateDraft({ decision: "reject" })}
          >
            Reject
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!preview?.canShare}
            onClick={() => updateDraft({ share_requested: true })}
          >
            Share
          </Button>
          <Button type="button" size="sm" asChild>
            <Link href={desktopHref}>Download/open full report</Link>
          </Button>
        </div>

        {preview?.largeReport ? (
          <p className="text-xs text-muted-foreground">
            Large report detected. Showing compact sections only; open full desktop report for complete content.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
