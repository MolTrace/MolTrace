"use client"

import dynamic from "next/dynamic"
import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { apiFetch } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false }) as React.ComponentType<Record<string, unknown>>

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return null
}

function readList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(readStr).filter(Boolean)
}

function readFirstString(rec: Row | null, keys: string[]): string {
  if (!rec) return ""
  for (const key of keys) {
    const value = readStr(rec[key])
    if (value) return value
  }
  return ""
}

function readFirstNumber(rec: Row | null, keys: string[]): number | null {
  if (!rec) return null
  for (const key of keys) {
    const value = readNum(rec[key])
    if (value != null) return value
  }
  return null
}

function downsampleSeries(x: number[], y: number[], maxPoints = 400): { x: number[]; y: number[] } {
  const len = Math.min(x.length, y.length)
  if (len <= maxPoints) return { x: x.slice(0, len), y: y.slice(0, len) }
  const step = Math.ceil(len / maxPoints)
  const nx: number[] = []
  const ny: number[] = []
  for (let i = 0; i < len; i += step) {
    nx.push(x[i]!)
    ny.push(y[i]!)
  }
  return { x: nx, y: ny }
}

type SpectraCheckMobileSummary = {
  sessionId: string
  sampleStatus: string
  latestQcStatus: string
  evidenceQueueCount: number | null
  regulatoryImpactStatus: string
  warnings: string[]
  reportReadiness: string
  compactSpectrum: { x: number[]; y: number[] } | null
}

function parseCompactSpectrum(root: Row): { x: number[]; y: number[] } | null {
  const candidates: unknown[] = [
    root.compact_spectrum_preview_json,
    root.compact_spectrum_json,
    root.spectrum_preview_json,
    root.spectrum_preview,
    root.preview_spectrum,
  ]
  for (const candidate of candidates) {
    if (!isRecord(candidate)) continue
    const xRaw = Array.isArray(candidate.x) ? candidate.x : []
    const yRaw = Array.isArray(candidate.y) ? candidate.y : []
    const x = xRaw.map(readNum).filter((n): n is number => n != null)
    const y = yRaw.map(readNum).filter((n): n is number => n != null)
    if (x.length > 0 && y.length > 0) {
      return downsampleSeries(x, y, 360)
    }
  }
  return null
}

function parseSummary(sessionId: string, payload: unknown): SpectraCheckMobileSummary {
  const root = isRecord(payload) ? payload : {}
  return {
    sessionId,
    sampleStatus:
      readFirstString(root, ["sample_session_status", "sample_status", "session_status", "status"]) || "Unknown",
    latestQcStatus: readFirstString(root, ["latest_qc_status", "qc_status", "quality_status"]) || "Unknown",
    evidenceQueueCount: readFirstNumber(root, [
      "evidence_queue_count",
      "evidence_count",
      "queue_count",
      "open_evidence_items_count",
    ]),
    regulatoryImpactStatus:
      readFirstString(root, ["regulatory_impact_status", "regulatory_status", "impact_status"]) || "Unknown",
    warnings: [...readList(root.warnings), ...readList(root.warnings_json)],
    reportReadiness: readFirstString(root, ["report_readiness", "report_status", "report_readiness_status"]) || "Unknown",
    compactSpectrum: parseCompactSpectrum(root),
  }
}

export function MobileSpectraCheckReview({ sessionId: sessionIdProp = null }: { sessionId?: string | null }) {
  const searchParams = useSearchParams()
  const sessionId = (sessionIdProp ?? searchParams.get("sessionId") ?? "").trim()
  const [loading, setLoading] = useState(false)
  const [summary, setSummary] = useState<SpectraCheckMobileSummary | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setSummary(null)
      return
    }
    let cancelled = false
    setLoading(true)
    void apiFetch<unknown>(`/mobile/spectracheck/sessions/${encodeURIComponent(sessionId)}/summary`, { method: "GET" })
      .then((payload) => {
        if (cancelled) return
        setSummary(parseSummary(sessionId, payload))
      })
      .catch(() => {
        if (!cancelled) setSummary(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  const desktopHref = useMemo(
    () => (sessionId ? `/spectracheck?desktop=1&sessionId=${encodeURIComponent(sessionId)}` : "/spectracheck?desktop=1"),
    [sessionId],
  )

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mobile SpectraCheck Review</CardTitle>
        <CardDescription>
          <code className="text-xs">GET /mobile/spectracheck/sessions/{"{session_id}"}/summary</code> — compact review
          mode for phone workflows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!sessionId ? (
          <p className="text-xs text-muted-foreground">Open a SpectraCheck session to load mobile review summary.</p>
        ) : null}
        {sessionId && summary ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">sample/session status</p>
                <p className="text-sm font-medium">{summary.sampleStatus}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">latest QC status</p>
                <p className="text-sm font-medium">{summary.latestQcStatus}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">evidence queue count</p>
                <p className="text-sm font-medium">{summary.evidenceQueueCount != null ? summary.evidenceQueueCount : "—"}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">regulatory impact status</p>
                <p className="text-sm font-medium">{summary.regulatoryImpactStatus}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">open warnings</p>
                <p className="text-sm font-medium">{summary.warnings.length > 0 ? summary.warnings.slice(0, 3).join(" · ") : "—"}</p>
              </div>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">report readiness</p>
                <p className="text-sm font-medium">{summary.reportReadiness}</p>
              </div>
            </div>

            <div className="rounded-md border p-2">
              <p className="mb-2 text-xs text-muted-foreground">compact spectrum preview</p>
              {summary.compactSpectrum ? (
                <div className="min-h-[220px] w-full min-w-0 overflow-hidden rounded-md border bg-card">
                  <Plot
                    data={[
                      {
                        type: "scattergl",
                        mode: "lines",
                        x: summary.compactSpectrum.x,
                        y: summary.compactSpectrum.y,
                        line: { width: 1.4, color: "#42A5F5" },
                        hoverinfo: "x+y",
                      },
                    ]}
                    layout={{
                      autosize: true,
                      margin: { l: 36, r: 12, t: 12, b: 28 },
                      paper_bgcolor: "rgba(0,0,0,0)",
                      plot_bgcolor: "rgba(0,0,0,0)",
                      xaxis: { title: "ppm", autorange: "reversed", fixedrange: false },
                      yaxis: { title: "Intensity", fixedrange: false },
                      showlegend: false,
                    }}
                    config={{
                      responsive: true,
                      displaylogo: false,
                      displayModeBar: true,
                      scrollZoom: true,
                    }}
                    style={{ width: "100%", height: 220 }}
                    useResizeHandler
                  />
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No compact preview data available for this session.</p>
              )}
            </div>
          </>
        ) : null}

        {loading ? <p className="text-xs text-muted-foreground">Loading mobile SpectraCheck summary…</p> : null}

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" asChild>
            <Link href={desktopHref}>Add comment</Link>
          </Button>
          <Button type="button" size="sm" variant="outline" asChild>
            <Link href={desktopHref}>Mark reviewed</Link>
          </Button>
          <Button type="button" size="sm" variant="outline" asChild>
            <Link href={desktopHref}>Open Regulatory Impact</Link>
          </Button>
          <Button type="button" size="sm" variant="outline" asChild>
            <Link href={desktopHref}>Open Report Preview</Link>
          </Button>
          <Button type="button" size="sm" asChild>
            <Link href={desktopHref}>Open full desktop view</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
