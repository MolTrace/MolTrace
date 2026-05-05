"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { apiFetch } from "@/src/lib/api/client"
import { parseSessionQualityControlPayload } from "@/src/lib/spectracheck/quality-control-assessment"

const CARD_TOOLTIP =
  "Session-level quality control summarizes whether files, artifacts, and evidence items are ready to influence Unified Evidence and reports."

type Props = {
  sessionId: string | null
}

function metric(label: string, value: string | number) {
  return (
    <div className="rounded-md border bg-muted/20 px-2 py-1.5">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-semibold tabular-nums">{value}</p>
    </div>
  )
}

export function SessionEvidenceReadinessCard({ sessionId }: Props) {
  const [payload, setPayload] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [fetchBusy, setFetchBusy] = useState(false)
  const [error, setError] = useState("")

  const sid = sessionId?.trim() ?? ""
  const hasSession = Boolean(sid)

  const parsed = useMemo(() => parseSessionQualityControlPayload(payload), [payload])

  const loadGet = useCallback(async () => {
    if (!sid) return
    setFetchBusy(true)
    setError("")
    try {
      const data = await apiFetch<unknown>(`/quality-control/sessions/${encodeURIComponent(sid)}`, { method: "GET" })
      setPayload(data)
    } catch {
      // Preserve previous payload when GET fails (e.g. offline backend).
    } finally {
      setFetchBusy(false)
    }
  }, [sid])

  useEffect(() => {
    if (!sid) {
      setPayload(null)
      setError("")
      return
    }
    setPayload(null)
    void loadGet()
  }, [sid, loadGet])

  async function runSessionAssess() {
    if (!sid) return
    setBusy(true)
    setError("")
    try {
      const data = await apiFetch<unknown>(`/quality-control/sessions/${encodeURIComponent(sid)}/assess`, {
        method: "POST",
        body: {},
      })
      setPayload(data)
    } catch {
      try {
        await loadGet()
      } catch {
        setError("Session QC could not be completed right now. You can retry when the backend is available.")
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="min-w-0 border-muted">
      <CardHeader className="pb-2">
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Evidence Readiness
          <InfoTooltip content={CARD_TOOLTIP} label="About Evidence Readiness" className="size-4" />
        </CardTitle>
        <CardDescription className="text-xs">Summarize QC counts and findings for this SpectraCheck session.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!hasSession ? (
          <p className="text-sm text-muted-foreground">
            Create or load a SpectraCheck session before running session-level QC.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" disabled={busy || fetchBusy} onClick={() => void runSessionAssess()}>
                {busy ? "Running session QC…" : "Run session QC"}
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={fetchBusy || busy} onClick={() => void loadGet()}>
                {fetchBusy ? "Refreshing…" : "Refresh status"}
              </Button>
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Session readiness status</p>
              <p className="text-sm font-medium">{parsed.sessionReadiness}</p>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {metric("Total assessed", parsed.totalAssessed ?? "—")}
              {metric("QC passed", parsed.qcPassed ?? "—")}
              {metric("Warnings", parsed.warnings ?? "—")}
              {metric("Failed", parsed.failed ?? "—")}
              {metric("Requires review", parsed.requiresReview ?? "—")}
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Recommended actions</p>
              {parsed.recommendedActions.length === 0 ? (
                <p className="text-xs text-muted-foreground">—</p>
              ) : (
                <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                  {parsed.recommendedActions.map((line, i) => (
                    <li key={`${i}-${line.slice(0, 24)}`}>{line}</li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground">Findings summary</p>
              {parsed.findings.length === 0 ? (
                <p className="text-xs text-muted-foreground">No findings in the latest session QC payload.</p>
              ) : (
                <ul className="max-h-48 space-y-2 overflow-y-auto pr-1">
                  {parsed.findings.slice(0, 16).map((f, i) => (
                    <li key={`${f.code}-${i}`} className="rounded-md border border-border/60 bg-muted/10 px-2 py-1.5 text-xs">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant="outline" className="font-mono text-[10px] uppercase">
                          {f.severity}
                        </Badge>
                        <span className="font-mono text-[10px] text-muted-foreground">{f.code}</span>
                      </div>
                      <p className="mt-0.5 font-medium leading-snug">{f.title}</p>
                      {f.message !== "—" ? (
                        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{f.message}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
              {parsed.findings.length > 16 ? (
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Showing 16 of {parsed.findings.length} findings. See Developer JSON for the full list.
                </p>
              ) : null}
            </div>

            {payload != null ? <DeveloperJsonPanel data={payload} /> : null}
          </>
        )}
      </CardContent>
    </Card>
  )
}
