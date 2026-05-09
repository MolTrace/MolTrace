"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import {
  trackFileNormalizationRun,
  trackIngestionRunCompleted,
  trackIngestionRunStarted,
} from "@/src/lib/analytics/analytics-client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type Row = Record<string, unknown>

type IngestionRunRow = {
  ingestion_run_id: string
  status: string
  source_system: string
  source_path: string
  discovered_count: number | null
  ingested_count: number | null
  skipped_count: number | null
  failed_count: number | null
  warnings: string[]
  notes: string
  raw: Row
}

type NormalizationRunRow = {
  normalization_run_id: string
  file_id: string
  status: string
  source_format: string
  target_format: string
  output_artifact_id: string
  warnings: string[]
  notes: string
  raw: Row
}

const TARGET_ROUTE_OPTIONS = [
  "moltrace_spectrum_json",
  "moltrace_lcms_json",
  "moltrace_regulatory_source_json",
  "moltrace_reaction_table_json",
  "unchanged",
] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  if (Array.isArray(payload.items)) return payload.items.filter(isRecord)
  if (Array.isArray(payload.results)) return payload.results.filter(isRecord)
  if (Array.isArray(payload.ingestion_runs)) return payload.ingestion_runs.filter(isRecord)
  if (Array.isArray(payload.normalization_runs)) return payload.normalization_runs.filter(isRecord)
  return []
}

function readStr(v: unknown): string {
  if (typeof v === "string") return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function readWarnings(v: unknown): string[] {
  if (Array.isArray(v)) {
    return v
      .map((item) => readStr(item))
      .filter((item) => item.length > 0)
  }
  const single = readStr(v)
  return single ? [single] : []
}

function parseIngestionRunRow(row: Row): IngestionRunRow | null {
  const ingestionRunId = readStr(row.ingestion_run_id ?? row.id)
  if (!ingestionRunId) return null
  return {
    ingestion_run_id: ingestionRunId,
    status: readStr(row.status) || "unknown",
    source_system: readStr(row.source_system) || "—",
    source_path: readStr(row.source_path) || "—",
    discovered_count: readNum(row.discovered_count ?? row.discovered),
    ingested_count: readNum(row.ingested_count ?? row.ingested),
    skipped_count: readNum(row.skipped_count ?? row.skipped),
    failed_count: readNum(row.failed_count ?? row.failed),
    warnings: readWarnings(row.warnings ?? row.warning),
    notes: readStr(row.notes) || "—",
    raw: row,
  }
}

function parseNormalizationRunRow(row: Row): NormalizationRunRow | null {
  const normalizationRunId = readStr(row.normalization_run_id ?? row.id)
  if (!normalizationRunId) return null
  return {
    normalization_run_id: normalizationRunId,
    file_id: readStr(row.file_id) || "—",
    status: readStr(row.status) || "unknown",
    source_format: readStr(row.source_format) || "—",
    target_format: readStr(row.target_format) || "—",
    output_artifact_id: readStr(row.output_artifact_id) || "—",
    warnings: readWarnings(row.warnings ?? row.warning),
    notes: readStr(row.notes) || "—",
    raw: row,
  }
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s.includes("success") || s.includes("completed") || s.includes("imported") || s.includes("normalized")) {
    return "border-success/50 text-success"
  }
  if (s.includes("warning") || s.includes("skipped") || s.includes("partial")) {
    return "border-warning/50 text-warning"
  }
  if (s.includes("failed") || s.includes("error")) {
    return "border-destructive/50 text-destructive"
  }
  return "text-muted-foreground"
}

export function FileIngestionNormalizationWorkspace() {
  const completedIngestionAnalyticsIds = useRef<Set<string>>(new Set())
  const [loadingRuns, setLoadingRuns] = useState(true)
  const [ingestionRuns, setIngestionRuns] = useState<IngestionRunRow[]>([])
  const [ingestionError, setIngestionError] = useState("")
  const [selectedIngestionRunId, setSelectedIngestionRunId] = useState("")
  const [selectedIngestionRun, setSelectedIngestionRun] = useState<IngestionRunRow | null>(null)
  const [ingestionDetailError, setIngestionDetailError] = useState("")

  const [sourceSystem, setSourceSystem] = useState("")
  const [sourcePath, setSourcePath] = useState("")
  const [ingestionNotes, setIngestionNotes] = useState("")
  const [createIngestionBusy, setCreateIngestionBusy] = useState(false)

  const [fileId, setFileId] = useState("")
  const [targetRoute, setTargetRoute] = useState<(typeof TARGET_ROUTE_OPTIONS)[number]>("moltrace_spectrum_json")
  const [normalizeBusy, setNormalizeBusy] = useState(false)

  const [loadingNormalizationRuns, setLoadingNormalizationRuns] = useState(false)
  const [normalizationRuns, setNormalizationRuns] = useState<NormalizationRunRow[]>([])
  const [normalizationError, setNormalizationError] = useState("")
  const [selectedNormalizationRunId, setSelectedNormalizationRunId] = useState("")
  const [selectedNormalizationRun, setSelectedNormalizationRun] = useState<NormalizationRunRow | null>(null)
  const [normalizationDetailError, setNormalizationDetailError] = useState("")

  const loadIngestionRuns = useCallback(async () => {
    setLoadingRuns(true)
    setIngestionError("")
    try {
      const payload = await apiFetch<unknown>("/ingestion-runs", { method: "GET" })
      const rows = asRows(payload).map(parseIngestionRunRow).filter((row): row is IngestionRunRow => row != null)
      setIngestionRuns(rows)
      if (!selectedIngestionRunId && rows.length > 0) setSelectedIngestionRunId(rows[0]!.ingestion_run_id)
    } catch (e) {
      setIngestionError(e instanceof Error ? e.message : "Could not load ingestion runs.")
      setIngestionRuns([])
    } finally {
      setLoadingRuns(false)
    }
  }, [selectedIngestionRunId])

  const loadIngestionRunDetail = useCallback(async (ingestionRunId: string) => {
    if (!ingestionRunId) {
      setSelectedIngestionRun(null)
      return
    }
    setIngestionDetailError("")
    try {
      const payload = await apiFetch<unknown>(`/ingestion-runs/${ingestionRunId}`, { method: "GET" })
      const row = isRecord(payload) ? parseIngestionRunRow(payload) : null
      if (!row) throw new Error("Ingestion run detail unavailable.")
      setSelectedIngestionRun(row)
      const normalizedStatus = row.status.toLowerCase()
      const isCompletedLike =
        normalizedStatus.includes("completed") ||
        normalizedStatus.includes("imported") ||
        normalizedStatus.includes("succeeded") ||
        normalizedStatus.includes("failed") ||
        normalizedStatus.includes("error")
      if (isCompletedLike && !completedIngestionAnalyticsIds.current.has(row.ingestion_run_id)) {
        trackIngestionRunCompleted({
          status: row.status,
          source_format: row.source_system,
          success_count: row.ingested_count ?? 0,
          failure_count: row.failed_count ?? 0,
          warning_count: row.warnings.length,
        })
        completedIngestionAnalyticsIds.current.add(row.ingestion_run_id)
      }
    } catch (e) {
      setIngestionDetailError(e instanceof Error ? e.message : "Could not load ingestion run detail.")
      setSelectedIngestionRun(null)
    }
  }, [])

  const loadNormalizationRuns = useCallback(async () => {
    if (!fileId.trim()) {
      setNormalizationRuns([])
      setSelectedNormalizationRun(null)
      setSelectedNormalizationRunId("")
      return
    }
    setLoadingNormalizationRuns(true)
    setNormalizationError("")
    try {
      const payload = await apiFetch<unknown>(`/files/${fileId.trim()}/normalization-runs`, { method: "GET" })
      const rows = asRows(payload)
        .map(parseNormalizationRunRow)
        .filter((row): row is NormalizationRunRow => row != null)
      setNormalizationRuns(rows)
      if (rows.length > 0) setSelectedNormalizationRunId(rows[0]!.normalization_run_id)
    } catch (e) {
      setNormalizationError(e instanceof Error ? e.message : "Could not load normalization runs.")
      setNormalizationRuns([])
    } finally {
      setLoadingNormalizationRuns(false)
    }
  }, [fileId])

  const loadNormalizationRunDetail = useCallback(async (normalizationRunId: string) => {
    if (!normalizationRunId) {
      setSelectedNormalizationRun(null)
      return
    }
    setNormalizationDetailError("")
    try {
      const payload = await apiFetch<unknown>(`/normalization-runs/${normalizationRunId}`, { method: "GET" })
      const row = isRecord(payload) ? parseNormalizationRunRow(payload) : null
      if (!row) throw new Error("Normalization run detail unavailable.")
      setSelectedNormalizationRun(row)
    } catch (e) {
      setNormalizationDetailError(e instanceof Error ? e.message : "Could not load normalization run detail.")
      setSelectedNormalizationRun(null)
    }
  }, [])

  useEffect(() => {
    void loadIngestionRuns()
  }, [loadIngestionRuns])

  useEffect(() => {
    if (!selectedIngestionRunId) return
    void loadIngestionRunDetail(selectedIngestionRunId)
  }, [selectedIngestionRunId, loadIngestionRunDetail])

  useEffect(() => {
    if (!selectedNormalizationRunId) return
    void loadNormalizationRunDetail(selectedNormalizationRunId)
  }, [selectedNormalizationRunId, loadNormalizationRunDetail])

  async function createIngestionRun() {
    setCreateIngestionBusy(true)
    setIngestionError("")
    try {
      const payload = await apiFetch<unknown>("/ingestion-runs", {
        method: "POST",
        body: {
          source_system: sourceSystem.trim(),
          source_path: sourcePath.trim(),
          notes: ingestionNotes.trim(),
        },
      })
      const rec = isRecord(payload) ? payload : {}
      trackIngestionRunStarted({
        status: readStr(rec.status) || "started",
        source_format: sourceSystem.trim(),
        warning_count: readWarnings(rec.warnings ?? rec.warning).length,
      })
      await loadIngestionRuns()
    } catch (e) {
      setIngestionError(e instanceof Error ? e.message : "Could not create ingestion run.")
    } finally {
      setCreateIngestionBusy(false)
    }
  }

  async function normalizeFile() {
    if (!fileId.trim()) return
    setNormalizeBusy(true)
    setNormalizationError("")
    try {
      const payload = await apiFetch<unknown>(`/files/${fileId.trim()}/normalize`, {
        method: "POST",
        body: { target_route: targetRoute },
      })
      const rec = isRecord(payload) ? payload : {}
      trackFileNormalizationRun({
        status: readStr(rec.status) || "started",
        file_kind: readStr(rec.file_kind) || "file",
        source_format: readStr(rec.source_format),
        target_format: readStr(rec.target_format) || targetRoute,
        warning_count: readWarnings(rec.warnings ?? rec.warning).length,
        failure_count:
          readNum(rec.failed_count ?? rec.failed) ??
          (readStr(rec.status).toLowerCase().includes("failed") || readStr(rec.status).toLowerCase().includes("error")
            ? 1
            : 0),
      })
      await loadNormalizationRuns()
    } catch (e) {
      setNormalizationError(e instanceof Error ? e.message : "Could not normalize file.")
    } finally {
      setNormalizeBusy(false)
    }
  }

  const developerJson = useMemo(
    () => ({
      selected_ingestion_run: selectedIngestionRun?.raw ?? null,
      selected_normalization_run: selectedNormalizationRun?.raw ?? null,
      ingestion_runs: ingestionRuns.map((row) => row.raw),
      normalization_runs: normalizationRuns.map((row) => row.raw),
    }),
    [selectedIngestionRun, selectedNormalizationRun, ingestionRuns, normalizationRuns],
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">File Ingestion + Normalization Dashboard</h1>
        <p className="text-muted-foreground">
          Track imported files, view normalized artifact outputs, and review derived output metadata. Imported data
          requires review.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create ingestion run</CardTitle>
          <CardDescription>
            Trigger a batch import of instrument or connector files into the platform.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {ingestionError ? <p className="text-xs text-destructive">{ingestionError}</p> : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="ingestion-source-system">source system/path: source system</Label>
              <Input
                id="ingestion-source-system"
                value={sourceSystem}
                onChange={(e) => setSourceSystem(e.target.value)}
                placeholder="instrument_watch_folder"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ingestion-source-path">source system/path: source path</Label>
              <Input
                id="ingestion-source-path"
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                placeholder="/incoming/instruments/run_001"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="ingestion-notes">notes</Label>
              <Textarea
                id="ingestion-notes"
                rows={3}
                value={ingestionNotes}
                onChange={(e) => setIngestionNotes(e.target.value)}
                placeholder="imported batch requires review before downstream decisions"
              />
            </div>
          </div>
          <Button type="button" disabled={createIngestionBusy} onClick={() => void createIngestionRun()}>
            {createIngestionBusy ? "Creating…" : "Create ingestion run"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ingestion runs table</CardTitle>
          <CardDescription>
            All ingestion runs across tenants. Click a run to view its detail and per-file outcomes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {loadingRuns ? <p className="text-sm text-muted-foreground">Loading ingestion runs…</p> : null}
          {!loadingRuns ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ingestion run ID</TableHead>
                    <TableHead>status badges</TableHead>
                    <TableHead>source system/path</TableHead>
                    <TableHead>discovered count</TableHead>
                    <TableHead>ingested count</TableHead>
                    <TableHead>skipped count</TableHead>
                    <TableHead>failed count</TableHead>
                    <TableHead>warnings</TableHead>
                    <TableHead>notes</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ingestionRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-xs text-muted-foreground">
                        No ingestion runs returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    ingestionRuns.map((run) => (
                      <TableRow key={run.ingestion_run_id}>
                        <TableCell className="font-mono text-[10px]">{run.ingestion_run_id}</TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className={`font-normal ${statusBadgeClass(run.status)}`}>
                            {run.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs">
                          {run.source_system} / {run.source_path}
                        </TableCell>
                        <TableCell className="text-xs">{run.discovered_count ?? "—"}</TableCell>
                        <TableCell className="text-xs">{run.ingested_count ?? "—"}</TableCell>
                        <TableCell className="text-xs">{run.skipped_count ?? "—"}</TableCell>
                        <TableCell className="text-xs">{run.failed_count ?? "—"}</TableCell>
                        <TableCell className="text-xs">{run.warnings.length ? run.warnings.join("; ") : "—"}</TableCell>
                        <TableCell className="text-xs">{run.notes}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedIngestionRunId === run.ingestion_run_id ? "secondary" : "outline"}
                            onClick={() => setSelectedIngestionRunId(run.ingestion_run_id)}
                          >
                            Open
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
          {ingestionDetailError ? <p className="text-xs text-destructive">{ingestionDetailError}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Normalization action</CardTitle>
          <CardDescription>
            Run normalization on an ingested file and review the history of normalization runs for that file.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {normalizationError ? <p className="text-xs text-destructive">{normalizationError}</p> : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="normalization-file-id">select file ID</Label>
              <Input
                id="normalization-file-id"
                value={fileId}
                onChange={(e) => setFileId(e.target.value)}
                placeholder="file_123"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="normalization-target-route">choose target route</Label>
              <select
                id="normalization-target-route"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={targetRoute}
                onChange={(e) => setTargetRoute(e.target.value as (typeof TARGET_ROUTE_OPTIONS)[number])}
              >
                {TARGET_ROUTE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={normalizeBusy || !fileId.trim()} onClick={() => void normalizeFile()}>
              {normalizeBusy ? "Normalizing…" : "Normalize file"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={loadingNormalizationRuns || !fileId.trim()}
              onClick={() => void loadNormalizationRuns()}
            >
              {loadingNormalizationRuns ? "Loading…" : "Refresh normalization runs"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Normalization runs table</CardTitle>
          <CardDescription>Normalization history for selected file ID.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>normalization run ID</TableHead>
                  <TableHead>status badges</TableHead>
                  <TableHead>file ID</TableHead>
                  <TableHead>source format</TableHead>
                  <TableHead>target format</TableHead>
                  <TableHead>output artifact ID</TableHead>
                  <TableHead>warnings</TableHead>
                  <TableHead>notes</TableHead>
                  <TableHead>open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {normalizationRuns.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-xs text-muted-foreground">
                      No normalization runs returned.
                    </TableCell>
                  </TableRow>
                ) : (
                  normalizationRuns.map((run) => (
                    <TableRow key={run.normalization_run_id}>
                      <TableCell className="font-mono text-[10px]">{run.normalization_run_id}</TableCell>
                      <TableCell className="text-xs">
                        <Badge variant="outline" className={`font-normal ${statusBadgeClass(run.status)}`}>
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{run.file_id}</TableCell>
                      <TableCell className="text-xs">{run.source_format}</TableCell>
                      <TableCell className="text-xs">{run.target_format}</TableCell>
                      <TableCell className="text-xs">{run.output_artifact_id}</TableCell>
                      <TableCell className="text-xs">{run.warnings.length ? run.warnings.join("; ") : "—"}</TableCell>
                      <TableCell className="text-xs">{run.notes}</TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="sm"
                          variant={selectedNormalizationRunId === run.normalization_run_id ? "secondary" : "outline"}
                          onClick={() => setSelectedNormalizationRunId(run.normalization_run_id)}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          {normalizationDetailError ? <p className="text-xs text-destructive">{normalizationDetailError}</p> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Selected run detail</CardTitle>
          <CardDescription>Imported records and normalized artifact metadata require review.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <div className="rounded-md border p-3">
            <p>
              <span className="font-semibold">ingestion run:</span> {selectedIngestionRun?.ingestion_run_id ?? "—"}
            </p>
            <p>
              <span className="font-semibold">normalization run:</span>{" "}
              {selectedNormalizationRun?.normalization_run_id ?? "—"}
            </p>
            <p>
              <span className="font-semibold">normalized artifact:</span>{" "}
              {selectedNormalizationRun?.output_artifact_id ?? "—"}
            </p>
            <p>
              <span className="font-semibold">derived output:</span> {selectedNormalizationRun?.target_format ?? "—"}
            </p>
            <p>
              <span className="font-semibold">requires review:</span> yes
            </p>
          </div>
          <details className="rounded-md border p-3">
            <summary className="cursor-pointer text-sm font-medium">Developer JSON</summary>
            <pre className="mt-3 max-h-[24rem] overflow-auto text-[10px]">{JSON.stringify(developerJson, null, 2)}</pre>
          </details>
        </CardContent>
      </Card>
    </div>
  )
}
