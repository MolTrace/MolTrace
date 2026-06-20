"use client"

import { useCallback, useEffect, useState } from "react"
import { FileStack, Loader2, TriangleAlert, UploadCloud } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { cn } from "@/lib/utils"
import {
  getValidationPackage,
  ingestReleaseEvidence,
  qualStatusBadge,
  type QualBlock,
  type QualTone,
  type ValidationPackage,
} from "@/lib/validation/validation-package"

// formatApiError only unpacks detail for 401/403/404; the evidence ingest fails
// with a 409/400 whose detail ("…already approved…") must reach the user.
function ingestErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const detail = err.data && typeof err.data === "object" ? (err.data as { detail?: unknown }).detail : undefined
    if (typeof detail === "string" && detail.trim()) return detail
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === "object" && typeof (d as { msg?: unknown }).msg === "string" ? (d as { msg: string }).msg : ""))
        .filter(Boolean)
      if (msgs.length) return msgs.join("; ")
    }
    return err.message || fallback
  }
  return formatApiError(err, fallback)
}

const TONE_CLASS: Record<QualTone, string> = {
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200",
  error: "border-red-500/50 bg-red-500/10 text-red-900 dark:text-red-200",
  warning: "border-amber-500/45 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  customer: "border-[color:var(--mt-violet)]/40 bg-[color:var(--mt-violet-soft)] text-[color:var(--mt-violet-ink)]",
  neutral: "border-border bg-muted/40 text-muted-foreground",
}

function StatusBadge({ status }: { status: string }) {
  const { tone, label } = qualStatusBadge(status)
  return <span className={cn("inline-block rounded-md border px-2 py-0.5 text-xs font-medium", TONE_CLASS[tone])}>{label}</span>
}

function QualCard({ title, sub, block }: { title: string; sub: string; block: QualBlock }) {
  const counts = block.status === "pass" || block.status === "fail"
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{title}</p>
        <StatusBadge status={block.status} />
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p>
      {counts ? (
        <p className="mt-2 font-mono text-xs tabular-nums">
          {block.passed ?? 0} passed · {block.failed ?? 0} failed
          {block.skipped != null ? ` · ${block.skipped} skipped` : ""}
          {block.coveragePercent != null ? ` · ${block.coveragePercent}% cov` : ""}
        </p>
      ) : block.note ? (
        <p className="mt-2 text-xs text-muted-foreground">{block.note}</p>
      ) : null}
    </div>
  )
}

export function ValidationPackagePanel({ releaseId }: { releaseId: number | string }) {
  const [pkg, setPkg] = useState<ValidationPackage | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const [testJson, setTestJson] = useState("")
  const [riskJson, setRiskJson] = useState("")
  const [source, setSource] = useState<"ci" | "manual">("ci")
  const [ingestBusy, setIngestBusy] = useState(false)
  const [ingestMsg, setIngestMsg] = useState("")
  const [ingestErr, setIngestErr] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      setPkg(await getValidationPackage(releaseId))
    } catch (e) {
      setError(formatApiError(e, "Could not load the validation package."))
      setPkg(null)
    } finally {
      setLoading(false)
    }
  }, [releaseId])

  useEffect(() => {
    void load()
  }, [load])

  async function handleIngest() {
    setIngestErr("")
    setIngestMsg("")
    let testObj: Record<string, unknown> | undefined
    let riskObj: Record<string, unknown> | undefined
    try {
      if (testJson.trim()) testObj = JSON.parse(testJson)
      if (riskJson.trim()) riskObj = JSON.parse(riskJson)
    } catch {
      setIngestErr("Test/risk summary must be valid JSON.")
      return
    }
    setIngestBusy(true)
    try {
      await ingestReleaseEvidence(releaseId, {
        ...(testObj ? { test_summary_json: testObj } : {}),
        ...(riskObj ? { risk_summary_json: riskObj } : {}),
        source,
      })
      setIngestMsg("CI evidence ingested.")
      setTestJson("")
      setRiskJson("")
      await load()
    } catch (e) {
      // 409/400 when the release is already approved/released — surface verbatim.
      setIngestErr(ingestErrorMessage(e, "Could not ingest evidence."))
    } finally {
      setIngestBusy(false)
    }
  }

  return (
    <ModuleCard
      accent="cyan"
      eyebrow="Validation · GAMP 5 / CSA"
      title="Validation package"
      icon={FileStack}
      description="Regenerable evidence assembly (requirement→risk→test traceability + CI test evidence) that SUPPORTS the customer's CSV. It does not perform IQ/OQ/PQ execution or sign-off."
    >
      <div className="space-y-5">
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {loading && !pkg ? <p className="text-sm text-muted-foreground">Loading validation package…</p> : null}

        {pkg ? (
          <>
            {/* Traceability */}
            <div className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">Requirement → risk → test traceability</p>
                <StatusBadge status={pkg.traceability.status} />
              </div>
              {pkg.traceability.note ? (
                <p className="text-xs text-muted-foreground">{pkg.traceability.note}</p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                {pkg.traceability.coverage != null ? `coverage: ${pkg.traceability.coverage}% · ` : ""}
                gaps: {pkg.traceability.gaps.length}
              </p>
            </div>

            {/* IQ / OQ / PQ */}
            <div className="grid gap-3 sm:grid-cols-3">
              <QualCard title="IQ" sub="Installation qualification" block={pkg.iq} />
              <QualCard title="OQ" sub="Operational qualification (CI tests)" block={pkg.oq} />
              <QualCard title="PQ" sub="Performance qualification" block={pkg.pq} />
            </div>

            {/* Change control + risk */}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md bg-muted/40 p-3 text-sm">
                <p className="text-xs text-muted-foreground">change-control state</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="text-xs">
                    {pkg.changeControl.validated ? "validated" : "not validated"}
                  </Badge>
                  {pkg.changeControl.changeControlled ? (
                    <Badge variant="outline" className="text-xs">
                      change-controlled
                    </Badge>
                  ) : null}
                  <Badge variant="outline" className="tabular-nums text-xs">
                    {pkg.changeControl.openDeviationCount} open deviations
                  </Badge>
                </div>
              </div>
              <div className="rounded-md bg-muted/40 p-3 text-sm">
                <p className="text-xs text-muted-foreground">risk summary</p>
                <p className="mt-1 font-mono text-xs">
                  {Object.keys(pkg.riskSummary).length
                    ? Object.entries(pkg.riskSummary)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(" · ")
                    : "—"}
                </p>
              </div>
            </div>

            {/* Signatures */}
            <div className="space-y-1">
              <p className="text-sm font-medium">Release approval signatures</p>
              {pkg.signatures.length ? (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {pkg.signatures.map((s, i) => (
                    <li key={i} className="font-mono">
                      {String(s.meaning_label ?? s.signature_meaning ?? "signed")} ·{" "}
                      {String(s.printed_name ?? s.signer_name ?? s.signer_user_id ?? "—")} ·{" "}
                      {String(s.signed_at_utc ?? s.signed_at ?? "")}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">No release-approval signatures yet.</p>
              )}
            </div>

            {/* Notice (verbatim) */}
            {pkg.notice ? (
              <div className="rounded-md border border-dashed border-border bg-muted/30 p-3">
                <p className="text-xs italic text-muted-foreground">{pkg.notice}</p>
              </div>
            ) : null}
          </>
        ) : null}

        {/* CI evidence ingest (optional / admin) */}
        <Collapsible className="rounded-md border border-border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
            <span className="inline-flex items-center gap-2">
              <UploadCloud className="h-4 w-4" aria-hidden />
              Attach CI evidence
            </span>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-3 border-t border-border px-3 py-3">
            <p className="text-xs text-muted-foreground">
              POST parsed pytest/coverage + risk JSON into this release (typically a CI step). Ingest is
              rejected (409/400) once the release is approved/released.
            </p>
            {ingestErr ? (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
                {ingestErr}
              </div>
            ) : null}
            {ingestMsg ? (
              <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-xs text-emerald-900 dark:text-emerald-200">
                {ingestMsg}
              </div>
            ) : null}
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="vp-test-json">
                test_summary_json
              </Label>
              <Textarea
                id="vp-test-json"
                className="min-h-[60px] font-mono text-xs"
                placeholder='{ "passed": 142, "failed": 0, "coverage_percent": 87.4 }'
                value={testJson}
                onChange={(e) => setTestJson(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="vp-risk-json">
                risk_summary_json
              </Label>
              <Textarea
                id="vp-risk-json"
                className="min-h-[48px] font-mono text-xs"
                placeholder='{ "high": 1, "medium": 4, "open": 2 }'
                value={riskJson}
                onChange={(e) => setRiskJson(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <Label className="text-xs">source</Label>
                <Select value={source} onValueChange={(v) => setSource(v as "ci" | "manual")}>
                  <SelectTrigger className="h-9 w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ci">ci</SelectItem>
                    <SelectItem value="manual">manual</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button type="button" className="gap-2" onClick={handleIngest} disabled={ingestBusy}>
                {ingestBusy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <UploadCloud className="h-4 w-4" aria-hidden />}
                {ingestBusy ? "Ingesting…" : "Ingest evidence"}
              </Button>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </ModuleCard>
  )
}
