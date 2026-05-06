"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ServerOff } from "lucide-react"

const TOOLTIP =
  "The method registry records the exact scientific methods, model versions, scoring profiles, and thresholds used to produce evidence and reports."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function extractRows(data: unknown, arrayKeys: string[]): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  for (const k of arrayKeys) {
    const v = data[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function summarizeUnknown(v: unknown, maxLen = 160): string {
  if (v == null || v === "") return "—"
  if (typeof v === "string") return v.trim() || "—"
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  if (Array.isArray(v)) {
    const joined = v
      .map((x) => (typeof x === "string" ? x : JSON.stringify(x)))
      .join(", ")
    return joined.length > maxLen ? `${joined.slice(0, maxLen)}…` : joined || "—"
  }
  if (isRecord(v)) {
    const s = JSON.stringify(v)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return "—"
}

function formatEndpointsCell(raw: unknown): string {
  if (raw == null) return "—"
  if (typeof raw === "string") return raw.trim() || "—"
  if (Array.isArray(raw)) {
    const parts = raw.map((x) => (typeof x === "string" ? x : JSON.stringify(x)))
    return parts.length ? parts.join(", ") : "—"
  }
  if (isRecord(raw)) return summarizeUnknown(raw, 240)
  return "—"
}

function extractDriftPayload(data: unknown): {
  rows: Record<string, unknown>[]
  summaryLine: string | null
} {
  if (Array.isArray(data)) {
    return { rows: data.filter(isRecord) as Record<string, unknown>[], summaryLine: null }
  }
  if (!isRecord(data)) return { rows: [], summaryLine: null }
  const keys = ["drift_alerts", "alerts", "items", "results", "rows"]
  for (const k of keys) {
    const v = data[k]
    if (Array.isArray(v)) {
      return { rows: v.filter(isRecord) as Record<string, unknown>[], summaryLine: null }
    }
  }
  const summary =
    readStr(data, ["summary", "message", "overview"]) ||
    (isRecord(data.summary) ? readStr(data.summary as Record<string, unknown>, ["text", "message"]) : "")
  const count =
    readStr(data, ["count", "total", "alert_count"]) ||
    (typeof data.count === "number" ? String(data.count) : "")
  let summaryLine: string | null = null
  if (summary) summaryLine = summary
  else if (count) summaryLine = `${count} alert(s)`
  return { rows: [], summaryLine }
}

export function MethodRegistryWorkspace() {
  const [methods, setMethods] = useState<Record<string, unknown>[]>([])
  const [models, setModels] = useState<Record<string, unknown>[]>([])
  const [scoring, setScoring] = useState<Record<string, unknown>[]>([])
  const [thresholds, setThresholds] = useState<Record<string, unknown>[]>([])
  const [driftRows, setDriftRows] = useState<Record<string, unknown>[]>([])
  const [driftSummaryLine, setDriftSummaryLine] = useState<string | null>(null)

  const [errMethods, setErrMethods] = useState("")
  const [errModels, setErrModels] = useState("")
  const [errScoring, setErrScoring] = useState("")
  const [errThresholds, setErrThresholds] = useState("")
  const [errDrift, setErrDrift] = useState("")

  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    setLoading(true)
    setErrMethods("")
    setErrModels("")
    setErrScoring("")
    setErrThresholds("")
    setErrDrift("")

    const run = async (
      path: string,
      setRows: (r: Record<string, unknown>[]) => void,
      setErr: (s: string) => void,
      listKeys: string[],
    ) => {
      try {
        const data = await apiFetch<unknown>(path, { method: "GET" })
        setRows(extractRows(data, listKeys))
      } catch (e) {
        setErr(formatErr(e, `Could not load ${path}.`))
        setRows([])
      }
    }

    await Promise.all([
      run("/method-registry", setMethods, setErrMethods, ["methods", "items", "results", "data", "rows"]),
      run("/model-versions", setModels, setErrModels, ["model_versions", "models", "items", "results", "data", "rows"]),
      run("/scoring-profiles", setScoring, setErrScoring, ["profiles", "items", "results", "data", "rows"]),
      run("/threshold-profiles", setThresholds, setErrThresholds, ["profiles", "items", "results", "data", "rows"]),
    ])

    try {
      const driftRaw = await apiFetch<unknown>("/model-health/drift-alerts", { method: "GET" })
      const { rows, summaryLine } = extractDriftPayload(driftRaw)
      setDriftRows(rows)
      setDriftSummaryLine(summaryLine)
    } catch (e) {
      setErrDrift(formatErr(e, "Could not load drift alerts."))
      setDriftRows([])
      setDriftSummaryLine(null)
    }

    setLoading(false)
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  return (
    <TooltipProvider delayDuration={300}>
      <div className="space-y-6">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Method Registry</h1>
            <InfoTooltip content={TOOLTIP} label="About method registry" />
          </div>
          <p className="text-muted-foreground">
            Read-only view of registered methods, models, scoring, thresholds, and drift signals from the backend.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void reload()}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        </div>

        {errMethods || errModels || errScoring || errThresholds ? (
          <Alert variant="destructive">
            <AlertTitle>Some data could not be loaded</AlertTitle>
            <AlertDescription className="space-y-1 text-xs">
              {errMethods ? <p>Method registry: {errMethods}</p> : null}
              {errModels ? <p>Model versions: {errModels}</p> : null}
              {errScoring ? <p>Scoring profiles: {errScoring}</p> : null}
              {errThresholds ? <p>Threshold profiles: {errThresholds}</p> : null}
            </AlertDescription>
          </Alert>
        ) : null}

        {/* 1. Method registry table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Method registry table</CardTitle>
            <CardDescription>Methods registered for SpectraCheck and reporting workflows.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Method name</TableHead>
                      <TableHead className="text-xs">Category</TableHead>
                      <TableHead className="text-xs">Version</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Default scoring profile</TableHead>
                      <TableHead className="text-xs">Default threshold profile</TableHead>
                      <TableHead className="text-xs">Endpoint paths</TableHead>
                      <TableHead className="text-xs">Updated date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {methods.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-xs text-muted-foreground">
                          No method registry rows returned.
                        </TableCell>
                      </TableRow>
                    ) : (
                      methods.map((row, i) => (
                        <TableRow key={readStr(row, ["id", "method_id", "slug"]) || String(i)}>
                          <TableCell className="max-w-[10rem] text-xs font-medium">
                            {readStr(row, ["name", "method_name", "title", "display_name"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">{readStr(row, ["category", "method_category"]) || "—"}</TableCell>
                          <TableCell className="text-xs">{readStr(row, ["version", "semver"]) || "—"}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[10rem] text-xs">
                            {readStr(row, [
                              "default_scoring_profile",
                              "default_scoring_profile_name",
                              "scoring_profile",
                              "scoring_profile_name",
                            ]) || "—"}
                          </TableCell>
                          <TableCell className="max-w-[10rem] text-xs">
                            {readStr(row, [
                              "default_threshold_profile",
                              "default_threshold_profile_name",
                              "threshold_profile",
                              "threshold_profile_name",
                            ]) || "—"}
                          </TableCell>
                          <TableCell className="max-w-[14rem] font-mono text-[10px] break-all">
                            {formatEndpointsCell(row.endpoint_paths ?? row.endpoints ?? row.api_paths)}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {readStr(row, ["updated_at", "updatedAt", "modified_at", "modifiedAt"]) || "—"}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 2. Model versions table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Model versions table</CardTitle>
            <CardDescription>Deployed model artifacts and validation references.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Model name</TableHead>
                      <TableHead className="text-xs">Model family</TableHead>
                      <TableHead className="text-xs">Version</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Model hash</TableHead>
                      <TableHead className="text-xs">Validation summary</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {models.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-xs text-muted-foreground">
                          No model versions returned.
                        </TableCell>
                      </TableRow>
                    ) : (
                      models.map((row, i) => (
                        <TableRow key={readStr(row, ["id", "model_id"]) || String(i)}>
                          <TableCell className="max-w-[12rem] text-xs font-medium">
                            {readStr(row, ["name", "model_name", "title"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">{readStr(row, ["model_family", "family"]) || "—"}</TableCell>
                          <TableCell className="text-xs">{readStr(row, ["version"]) || "—"}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[12rem] font-mono text-[10px] break-all">
                            {readStr(row, ["model_hash", "hash", "artifact_hash", "sha256"]) || "—"}
                          </TableCell>
                          <TableCell className="max-w-[18rem] text-xs">{summarizeUnknown(row.validation_summary ?? row.validation ?? row.summary)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 3. Scoring profiles table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Scoring profiles table</CardTitle>
            <CardDescription>Named scoring configurations linked to methods where applicable.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Name</TableHead>
                      <TableHead className="text-xs">Version</TableHead>
                      <TableHead className="text-xs">Method</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Weights summary</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {scoring.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-xs text-muted-foreground">
                          No scoring profiles returned.
                        </TableCell>
                      </TableRow>
                    ) : (
                      scoring.map((row, i) => (
                        <TableRow key={readStr(row, ["id", "profile_id"]) || String(i)}>
                          <TableCell className="max-w-[12rem] text-xs font-medium">
                            {readStr(row, ["name", "profile_name", "title"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">{readStr(row, ["version"]) || "—"}</TableCell>
                          <TableCell className="text-xs">{readStr(row, ["method", "method_name", "linked_method"]) || "—"}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[20rem] text-xs">{summarizeUnknown(row.weights_summary ?? row.weights)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 4. Threshold profiles table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Threshold profiles table</CardTitle>
            <CardDescription>QC and gating thresholds by category.</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Name</TableHead>
                      <TableHead className="text-xs">Category</TableHead>
                      <TableHead className="text-xs">Version</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs">Thresholds summary</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {thresholds.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-xs text-muted-foreground">
                          No threshold profiles returned.
                        </TableCell>
                      </TableRow>
                    ) : (
                      thresholds.map((row, i) => (
                        <TableRow key={readStr(row, ["id", "profile_id"]) || String(i)}>
                          <TableCell className="max-w-[12rem] text-xs font-medium">
                            {readStr(row, ["name", "profile_name", "title"]) || "—"}
                          </TableCell>
                          <TableCell className="text-xs">{readStr(row, ["category"]) || "—"}</TableCell>
                          <TableCell className="text-xs">{readStr(row, ["version"]) || "—"}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {readStr(row, ["status"]) || "—"}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[20rem] text-xs">{summarizeUnknown(row.thresholds_summary ?? row.thresholds)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 5. Drift alerts summary */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Drift alerts summary</CardTitle>
            <CardDescription>Model health drift signals from the monitoring service.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : errDrift ? (
              <div className="flex items-start gap-2 text-sm text-destructive">
                <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>{errDrift}</span>
              </div>
            ) : (
              <>
                {driftSummaryLine ? (
                  <p className="text-sm text-muted-foreground">{driftSummaryLine}</p>
                ) : null}
                {driftRows.length === 0 && !driftSummaryLine ? (
                  <p className="text-sm text-muted-foreground">No drift alerts returned.</p>
                ) : null}
                {driftRows.length > 0 ? (
                  <div className="overflow-x-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Severity</TableHead>
                          <TableHead className="text-xs">Title</TableHead>
                          <TableHead className="text-xs">Detail</TableHead>
                          <TableHead className="text-xs">Detected</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {driftRows.map((row, i) => (
                          <TableRow key={readStr(row, ["id", "alert_id"]) || String(i)}>
                            <TableCell className="text-xs">
                              <Badge variant="outline" className="font-normal">
                                {readStr(row, ["severity", "level", "priority"]) || "—"}
                              </Badge>
                            </TableCell>
                            <TableCell className="max-w-[14rem] text-xs font-medium">
                              {readStr(row, ["title", "name", "alert_type"]) || "—"}
                            </TableCell>
                            <TableCell className="max-w-[24rem] text-xs">{summarizeUnknown(row.message ?? row.detail ?? row.description)}</TableCell>
                            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                              {readStr(row, ["detected_at", "created_at", "timestamp"]) || "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  )
}
