"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { KNOWLEDGE_EXTRACTION_TYPES } from "@/components/knowledge/knowledge-constants"
import { Activity, AlertTriangle, ArrowLeft, FileText, Loader2, PlayCircle } from "lucide-react"

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

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

export function KnowledgeExtractionsWorkspace() {
  const [sources, setSources] = useState<Record<string, unknown>[]>([])
  const [sourcesErr, setSourcesErr] = useState("")
  const [sourcesLoading, setSourcesLoading] = useState(true)

  const [runs, setRuns] = useState<Record<string, unknown>[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [runsErr, setRunsErr] = useState("")

  const [runSourceId, setRunSourceId] = useState<string>("")
  const [runFileId, setRunFileId] = useState<string>("")
  const [extractionType, setExtractionType] = useState<string>("mixed")
  const [runBusy, setRunBusy] = useState(false)
  const [runErr, setRunErr] = useState("")
  const [runOk, setRunOk] = useState("")

  const [files, setFiles] = useState<Record<string, unknown>[]>([])
  const [filesLoading, setFilesLoading] = useState(false)
  const [filesErr, setFilesErr] = useState("")

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [runDetail, setRunDetail] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailErr, setDetailErr] = useState("")

  const loadSources = useCallback(async () => {
    setSourcesLoading(true)
    setSourcesErr("")
    try {
      const raw = await apiFetch<unknown>("/knowledge/sources?limit=500", { method: "GET" })
      setSources(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setSources([])
      setSourcesErr(formatApiError(e, "Could not load sources."))
    } finally {
      setSourcesLoading(false)
    }
  }, [])

  const loadRuns = useCallback(async () => {
    setRunsLoading(true)
    setRunsErr("")
    try {
      const raw = await apiFetch<unknown>("/knowledge/extractions/runs?limit=500", { method: "GET" })
      const rows = asArray(raw).filter(isRecord) as Record<string, unknown>[]
      rows.sort((a, b) => {
        const ida = readRecordNumber(a, "id") ?? 0
        const idb = readRecordNumber(b, "id") ?? 0
        return idb - ida
      })
      setRuns(rows)
    } catch (e) {
      setRuns([])
      setRunsErr(formatApiError(e, "Could not load extraction runs."))
    } finally {
      setRunsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSources()
    void loadRuns()
  }, [loadSources, loadRuns])

  const sourceIdNum = useMemo(() => {
    const n = Number.parseInt(runSourceId, 10)
    return Number.isFinite(n) && n >= 1 ? n : null
  }, [runSourceId])

  useEffect(() => {
    if (sourceIdNum == null) {
      setFiles([])
      setRunFileId("")
      setFilesErr("")
      return
    }
    let cancelled = false
    setFilesLoading(true)
    setFilesErr("")
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/knowledge/sources/${sourceIdNum}/files`, { method: "GET" })
        if (cancelled) return
        setFiles(asArray(raw).filter(isRecord) as Record<string, unknown>[])
      } catch (e) {
        if (!cancelled) setFilesErr(formatApiError(e, "Could not load files for source."))
      } finally {
        if (!cancelled) setFilesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sourceIdNum])

  useEffect(() => {
    if (selectedRunId == null) {
      setRunDetail(null)
      setDetailErr("")
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setDetailErr("")
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/knowledge/extractions/runs/${selectedRunId}`, { method: "GET" })
        if (cancelled) return
        setRunDetail(isRecord(raw) ? raw : null)
      } catch (e) {
        if (!cancelled) setDetailErr(formatApiError(e, "Could not load run detail."))
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  async function submitRun() {
    setRunErr("")
    setRunOk("")
    const sid = Number.parseInt(runSourceId, 10)
    const fid = Number.parseInt(runFileId, 10)
    if (!Number.isFinite(sid) || sid < 1) {
      setRunErr("source_id is required.")
      return
    }
    if (!Number.isFinite(fid) || fid < 1) {
      setRunErr("source_file_id is required.")
      return
    }
    setRunBusy(true)
    try {
      await apiFetch("/knowledge/extractions/run", {
        method: "POST",
        body: {
          source_id: sid,
          source_file_id: fid,
          extraction_type: extractionType,
          metadata_json: {},
        },
      })
      setRunOk("Extraction run started.")
      await loadRuns()
    } catch (e) {
      setRunErr(formatApiError(e, "Extraction run failed."))
    } finally {
      setRunBusy(false)
    }
  }

  const warningLines = runDetail ? readStringList(runDetail.warnings_json) : []
  const noteLines = runDetail ? readStringList(runDetail.notes_json) : []

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/knowledge">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Knowledge Library
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/sources">Sources</Link>
        </Button>
      </div>

      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal)" }}
        >
          MolTrace · Knowledge Extractions
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Knowledge extractions</h1>
        <p className="text-sm text-muted-foreground">
          Run typed extractions against uploaded files. Outputs require human review before reuse.
        </p>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Decision support</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Extraction status and counts come from the tenant API — not validated scientific conclusions.
        </AlertDescription>
      </Alert>

      <ModuleCard
        accent="teal"
        eyebrow="Run"
        title="Run extraction"
        icon={PlayCircle}
        description="Trigger an extraction pipeline run on a source document to parse and classify knowledge claims for review queue intake."
      >
        <div className="space-y-4">
          {runErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{runErr}</AlertDescription>
            </Alert>
          ) : null}
          {runOk ? (
            <Alert>
              <AlertDescription className="text-sm">{runOk}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>source_id</Label>
              <Select
                value={runSourceId || "__none__"}
                onValueChange={(v) => {
                  setRunSourceId(v === "__none__" ? "" : v)
                  setRunFileId("")
                }}
                disabled={sourcesLoading}
              >
                <SelectTrigger>
                  <SelectValue placeholder={sourcesLoading ? "Loading sources…" : "Select source"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {sources.map((row) => {
                    const id = readRecordNumber(row, "id")
                    const title = readRecordString(row, "title")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        {id} · {title ?? "—"}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
              {sourcesErr ? <p className="text-xs text-muted-foreground">{sourcesErr}</p> : null}
            </div>
            <div className="space-y-2">
              <Label>source_file_id</Label>
              <Select
                value={runFileId || "__none__"}
                onValueChange={(v) => setRunFileId(v === "__none__" ? "" : v)}
                disabled={sourceIdNum == null || filesLoading}
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={
                      sourceIdNum == null
                        ? "Select a source first"
                        : filesLoading
                          ? "Loading files…"
                          : "Select file"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {files.map((row) => {
                    const id = readRecordNumber(row, "id")
                    const fn = readRecordString(row, "filename")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        {id} · {fn ?? "—"}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
              {filesErr ? <p className="text-xs text-destructive">{filesErr}</p> : null}
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label>extraction_type</Label>
              <Select value={extractionType} onValueChange={setExtractionType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KNOWLEDGE_EXTRACTION_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button type="button" disabled={runBusy || sourceIdNum == null} onClick={() => void submitRun()}>
            {runBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Run extraction
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="History"
        title="Extraction runs"
        icon={Activity}
        description="History of extraction pipeline runs — status, extracted claim count, and completion timestamp for each source document processed."
      >
        <div className="table-scroll min-w-0">
          <div className="mb-3">
            <Button type="button" variant="outline" size="sm" disabled={runsLoading} onClick={() => void loadRuns()}>
              {runsLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
              Refresh runs
            </Button>
          </div>
          {runsLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : runsErr ? (
            <p className="text-sm text-muted-foreground">{runsErr}</p>
          ) : runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extraction runs returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead className="w-[88px]">source_id</TableHead>
                  <TableHead className="w-[96px]">source_file_id</TableHead>
                  <TableHead>extraction_type</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="text-right">extracted_count</TableHead>
                  <TableHead>finished_at</TableHead>
                  <TableHead className="w-[100px]">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const ec = row["extracted_count"]
                  const ecNum = typeof ec === "number" && Number.isFinite(ec) ? ec : null
                  return (
                    <TableRow key={id != null ? `run-${id}` : `run-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordNumber(row, "source_id") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordNumber(row, "source_file_id") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "extraction_type") ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">{ecNum != null ? ecNum : "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "finished_at"))}
                      </TableCell>
                      <TableCell>
                        {id != null ? (
                          <Button
                            type="button"
                            variant={selectedRunId === id ? "secondary" : "outline"}
                            size="sm"
                            className="h-8"
                            onClick={() => setSelectedRunId(id)}
                          >
                            Open
                          </Button>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      {selectedRunId != null ? (
        <ModuleCard
          accent="teal"
          eyebrow="Detail"
          title="Extraction run detail"
          icon={FileText}
          description="Full detail for the selected extraction run — extracted claims, warnings, and processing metadata."
        >
          <div className="space-y-4">
            {detailLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : detailErr ? (
              <p className="text-sm text-destructive">{detailErr}</p>
            ) : runDetail ? (
              <>
                {warningLines.length > 0 ? (
                  <Alert variant="destructive">
                    <AlertTitle className="text-sm">warnings_json</AlertTitle>
                    <AlertDescription>
                      <ul className="list-inside list-disc text-sm">
                        {warningLines.map((w, i) => (
                          <li key={`${i}-${w.slice(0, 80)}`}>{w}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                ) : null}
                {noteLines.length > 0 ? (
                  <Alert>
                    <AlertTitle className="text-sm">notes_json</AlertTitle>
                    <AlertDescription>
                      <ul className="list-inside list-disc text-sm">
                        {noteLines.map((n, i) => (
                          <li key={`${i}-${n.slice(0, 80)}`}>{n}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                ) : null}
                <MlModelProvenanceSummary sources={[runDetail]} className="rounded-md border border-dashed px-3 py-2" />
                <DeveloperJsonPanel data={runDetail} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No detail.</p>
            )}
          </div>
        </ModuleCard>
      ) : null}
    </div>
  )
}
