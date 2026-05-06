"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ChevronDown, Loader2 } from "lucide-react"

type Props = {
  dossierId: number
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readString(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(readString).filter(Boolean)
}

function pickBundle(raw: unknown): Record<string, unknown> | null {
  if (isRecord(raw)) return raw
  if (!Array.isArray(raw)) return null
  const first = raw.find(isRecord)
  return first ?? null
}

function sectionText(bundle: Record<string, unknown> | null, ...keys: string[]): string {
  if (!bundle) return ""
  for (const key of keys) {
    const direct = bundle[key]
    if (typeof direct === "string" && direct.trim()) return direct.trim()
    if (isRecord(direct)) return JSON.stringify(direct)
    if (Array.isArray(direct)) return JSON.stringify(direct)
  }
  const reportJson = isRecord(bundle.report_json) ? (bundle.report_json as Record<string, unknown>) : null
  if (!reportJson) return ""
  for (const key of keys) {
    const nested = reportJson[key]
    if (typeof nested === "string" && nested.trim()) return nested.trim()
    if (isRecord(nested)) return JSON.stringify(nested)
    if (Array.isArray(nested)) return JSON.stringify(nested)
  }
  return ""
}

export function CtdModule3BundleCard({ dossierId }: Props) {
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")
  const [bundle, setBundle] = useState<Record<string, unknown> | null>(null)

  const loadBundle = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const data = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/ctd-module3-bundle`, { method: "GET" })
      const picked = pickBundle(data)
      setBundle(picked)
      const bundleId = picked?.id
      if (typeof bundleId === "number" && Number.isFinite(bundleId)) {
        try {
          const detail = await apiFetch<unknown>(`/ctd-module3-bundles/${bundleId}`, { method: "GET" })
          if (isRecord(detail)) setBundle(detail)
        } catch {
          // Best-effort detail refresh.
        }
      }
    } catch (e) {
      setBundle(null)
      setErr(formatApiError(e, "Could not load CTD Module 3 / CMC bundle."))
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void loadBundle()
  }, [loadBundle])

  async function generateBundle() {
    setBusy(true)
    setErr("")
    try {
      const created = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/ctd-module3-bundle`, {
        method: "POST",
      })
      const picked = pickBundle(created)
      if (picked) setBundle(picked)
      const bundleId = picked?.id
      if (typeof bundleId === "number" && Number.isFinite(bundleId)) {
        const detail = await apiFetch<unknown>(`/ctd-module3-bundles/${bundleId}`, { method: "GET" })
        if (isRecord(detail)) setBundle(detail)
      } else {
        await loadBundle()
      }
    } catch (e) {
      setErr(formatApiError(e, "Generate CTD / CMC bundle failed."))
    } finally {
      setBusy(false)
    }
  }

  const warnings = useMemo(() => {
    if (!bundle) return []
    return [...readList(bundle.warnings), ...readList(bundle.warnings_json)]
  }, [bundle])

  const reviewStatus = readString(bundle?.status) || "—"
  const reportSha = readString(bundle?.report_sha256) || sectionText(bundle, "report_sha256", "sha256") || "—"

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            CTD Module 3 / CMC Evidence Bundle
            <InfoTooltip
              label="CTD Module 3 / CMC bundle"
              content="Assembles analytical evidence, impurity register, residual solvent review, nitrosamine watch, qNMR/method validation, AI governance, source citations, review state, and provenance into a draft CTD Module 3 support bundle."
            />
          </CardTitle>
          <CardDescription>
            POST /regulatory/dossiers/{"{dossier_id}"}/ctd-module3-bundle · GET
            /regulatory/dossiers/{"{dossier_id}"}/ctd-module3-bundle · GET /ctd-module3-bundles/{"{bundle_id}"}.
            Generates a <span className="font-medium text-foreground">draft CTD support bundle</span> that is{" "}
            <span className="font-medium text-foreground">review required</span> before use.
          </CardDescription>
        </div>
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={() => void generateBundle()}>
          {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
          Generate CTD / CMC bundle
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <AlertDescription className="text-xs text-muted-foreground">
            Treat returned sections as draft support records. Use "ready for review" and "evidence gap" signals to
            drive human review.
          </AlertDescription>
        </Alert>
        {err ? (
          <Alert variant="destructive">
            <AlertDescription className="text-sm">{err}</AlertDescription>
          </Alert>
        ) : null}
        {loading ? <p className="text-sm text-muted-foreground">Loading CTD / CMC bundle…</p> : null}
        {!loading && !bundle ? <p className="text-sm text-muted-foreground">No CTD / CMC bundle loaded in this session.</p> : null}
        {bundle ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-md border bg-card p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">human review status</p>
                <p className="mt-1">
                  <Badge variant="outline" className="text-xs">
                    {reviewStatus}
                  </Badge>
                </p>
              </div>
              <div className="rounded-md border bg-card p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">report SHA-256</p>
                <p className="mt-1 break-all font-mono text-xs">{reportSha}</p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">analytical evidence summary</p>
                <p className="mt-1 text-xs">{sectionText(bundle, "analytical_evidence_summary", "analytical_summary") || "—"}</p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">impurity register</p>
                <p className="mt-1 text-xs">{sectionText(bundle, "impurity_register", "impurity_register_summary") || "—"}</p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">residual solvent assessment</p>
                <p className="mt-1 text-xs">
                  {sectionText(bundle, "residual_solvent_assessment", "residual_solvent_summary") || "—"}
                </p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">nitrosamine watch summary</p>
                <p className="mt-1 text-xs">
                  {sectionText(bundle, "nitrosamine_watch_summary", "nitrosamine_summary") || "—"}
                </p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">qNMR / method validation summary</p>
                <p className="mt-1 text-xs">
                  {sectionText(bundle, "qnmr_method_validation_summary", "method_validation_summary") || "—"}
                </p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">AI governance summary</p>
                <p className="mt-1 text-xs">{sectionText(bundle, "ai_governance_summary", "ai_governance") || "—"}</p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">source citations</p>
                <p className="mt-1 text-xs">{sectionText(bundle, "source_citations", "citations") || "—"}</p>
              </section>
              <section className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs font-medium uppercase text-muted-foreground">provenance hashes</p>
                <p className="mt-1 break-all font-mono text-[11px]">
                  {sectionText(bundle, "provenance_hashes", "provenance") || "—"}
                </p>
              </section>
            </div>

            <div>
              <p className="mb-1 text-xs font-medium uppercase text-muted-foreground">warnings / evidence gap</p>
              {warnings.length ? (
                <ul className="list-inside list-disc text-xs text-muted-foreground">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">—</p>
              )}
            </div>

            <Collapsible className="rounded-md border">
              <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium hover:bg-muted/50">
                Developer JSON
                <ChevronDown className="h-4 w-4" />
              </CollapsibleTrigger>
              <CollapsibleContent className="border-t px-3 py-3">
                <DeveloperJsonPanel data={bundle} />
              </CollapsibleContent>
            </Collapsible>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
