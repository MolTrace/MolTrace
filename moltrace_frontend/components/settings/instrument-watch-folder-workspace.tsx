"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackWatchFolderScanRun } from "@/src/lib/analytics/analytics-client"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Eye, FolderSearch, Plus } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
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

type WatchFolderRow = {
  watch_folder_id: string
  connector_id: string
  folder_path: string
  file_patterns: string
  recursive: boolean
  target_program: string
  target_route: string
  status: string
  last_scan: string
  discovered_count: number | null
  ingested_count: number | null
  skipped_count: number | null
  failed_count: number | null
  warnings: string[]
  raw: Row
}

type ConnectorOption = {
  id: string
  label: string
}

const TARGET_PROGRAM_OPTIONS = ["spectracheck", "regulatory_hub", "reaction_optimization"] as const
const TARGET_ROUTE_OPTIONS = [
  "processed_nmr",
  "raw_fid",
  "nmr2d",
  "dept_apt",
  "msms",
  "ms_raw",
  "lcms",
  "lcms_raw",
  "spectrum_file",
  "regulatory_source",
  "reaction_outcome",
  "other",
] as const
const STATUS_OPTIONS = ["active", "paused", "disabled"] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string") return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readBool(v: unknown): boolean {
  if (typeof v === "boolean") return v
  if (typeof v === "number") return v === 1
  if (typeof v === "string") {
    const normalized = v.trim().toLowerCase()
    return normalized === "true" || normalized === "1" || normalized === "yes"
  }
  return false
}

function readCount(v: unknown): number | null {
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

function asRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  if (Array.isArray(payload.items)) return payload.items.filter(isRecord)
  if (Array.isArray(payload.results)) return payload.results.filter(isRecord)
  if (Array.isArray(payload.watch_folders)) return payload.watch_folders.filter(isRecord)
  return []
}

function parseWatchFolderRow(row: Row): WatchFolderRow | null {
  const watchFolderId = readStr(row.watch_folder_id ?? row.id)
  if (!watchFolderId) return null
  return {
    watch_folder_id: watchFolderId,
    connector_id: readStr(row.connector_id),
    folder_path: readStr(row.folder_path) || "—",
    file_patterns: readStr(row.file_patterns),
    recursive: readBool(row.recursive),
    target_program: readStr(row.target_program) || "—",
    target_route: readStr(row.target_route) || "—",
    status: readStr(row.status) || "—",
    last_scan: readStr(row.last_scan ?? row.last_scan_at ?? row.scanned_at) || "—",
    discovered_count: readCount(row.discovered_count ?? row.discovered),
    ingested_count: readCount(row.ingested_count ?? row.ingested),
    skipped_count: readCount(row.skipped_count ?? row.skipped),
    failed_count: readCount(row.failed_count ?? row.failed),
    warnings: readWarnings(row.warnings ?? row.warning),
    raw: row,
  }
}

function parseConnectorOptions(payload: unknown): ConnectorOption[] {
  return asRows(payload)
    .map((row) => {
      const id = readStr(row.id ?? row.connector_id ?? row.connector_key)
      if (!id) return null
      const displayName = readStr(row.display_name) || readStr(row.name) || id
      return { id, label: `${displayName} (${id})` }
    })
    .filter((row): row is ConnectorOption => row != null)
}

export function InstrumentWatchFolderWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [watchFolders, setWatchFolders] = useState<WatchFolderRow[]>([])
  const [selectedWatchFolderId, setSelectedWatchFolderId] = useState("")
  const [selectedDetails, setSelectedDetails] = useState<WatchFolderRow | null>(null)
  const [detailsError, setDetailsError] = useState("")
  const [detailsLoading, setDetailsLoading] = useState(false)

  const [connectors, setConnectors] = useState<ConnectorOption[]>([])

  const [connectorId, setConnectorId] = useState("")
  const [folderPath, setFolderPath] = useState("")
  const [filePatterns, setFilePatterns] = useState("")
  const [recursive, setRecursive] = useState(true)
  const [targetProgram, setTargetProgram] = useState<(typeof TARGET_PROGRAM_OPTIONS)[number]>("spectracheck")
  const [targetRoute, setTargetRoute] = useState<(typeof TARGET_ROUTE_OPTIONS)[number]>("processed_nmr")
  const [status, setStatus] = useState<(typeof STATUS_OPTIONS)[number]>("active")

  const [createBusy, setCreateBusy] = useState(false)
  const [saveBusy, setSaveBusy] = useState(false)
  const [scanBusy, setScanBusy] = useState(false)

  const loadWatchFolders = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/instrument-watch-folders", { method: "GET" })
      const rows = asRows(payload).map(parseWatchFolderRow).filter((row): row is WatchFolderRow => row != null)
      setWatchFolders(rows)
      if (!selectedWatchFolderId && rows.length > 0) {
        setSelectedWatchFolderId(rows[0]!.watch_folder_id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load watch folders.")
      setWatchFolders([])
    } finally {
      setLoading(false)
    }
  }, [selectedWatchFolderId])

  const loadConnectors = useCallback(async () => {
    try {
      const payload = await apiFetch<unknown>("/connectors", { method: "GET" })
      const options = parseConnectorOptions(payload)
      setConnectors(options)
      if (!connectorId && options.length > 0) setConnectorId(options[0]!.id)
    } catch {
      setConnectors([])
    }
  }, [connectorId])

  const loadDetails = useCallback(async (watchFolderId: string) => {
    if (!watchFolderId) {
      setSelectedDetails(null)
      return
    }
    setDetailsLoading(true)
    setDetailsError("")
    try {
      const payload = await apiFetch<unknown>(`/instrument-watch-folders/${watchFolderId}`, { method: "GET" })
      const row = isRecord(payload) ? parseWatchFolderRow(payload) : null
      if (!row) throw new Error("Watch folder details are unavailable.")
      setSelectedDetails(row)
      setConnectorId(row.connector_id || connectorId)
      setFolderPath(row.folder_path === "—" ? "" : row.folder_path)
      setFilePatterns(row.file_patterns)
      setRecursive(row.recursive)
      if (TARGET_PROGRAM_OPTIONS.includes(row.target_program as (typeof TARGET_PROGRAM_OPTIONS)[number])) {
        setTargetProgram(row.target_program as (typeof TARGET_PROGRAM_OPTIONS)[number])
      }
      if (TARGET_ROUTE_OPTIONS.includes(row.target_route as (typeof TARGET_ROUTE_OPTIONS)[number])) {
        setTargetRoute(row.target_route as (typeof TARGET_ROUTE_OPTIONS)[number])
      }
      if (STATUS_OPTIONS.includes(row.status as (typeof STATUS_OPTIONS)[number])) {
        setStatus(row.status as (typeof STATUS_OPTIONS)[number])
      }
    } catch (e) {
      setDetailsError(e instanceof Error ? e.message : "Could not load watch folder details.")
      setSelectedDetails(null)
    } finally {
      setDetailsLoading(false)
    }
  }, [connectorId])

  useEffect(() => {
    void loadWatchFolders()
    void loadConnectors()
  }, [loadWatchFolders, loadConnectors])

  useEffect(() => {
    if (!selectedWatchFolderId) return
    void loadDetails(selectedWatchFolderId)
  }, [selectedWatchFolderId, loadDetails])

  async function createWatchFolder() {
    setCreateBusy(true)
    setError("")
    try {
      await apiFetch("/instrument-watch-folders", {
        method: "POST",
        body: {
          connector_id: connectorId,
          folder_path: folderPath.trim(),
          file_patterns: filePatterns.trim(),
          recursive,
          target_program: targetProgram,
          target_route: targetRoute,
          status,
        },
      })
      setFolderPath("")
      setFilePatterns("")
      await loadWatchFolders()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create watch folder.")
    } finally {
      setCreateBusy(false)
    }
  }

  async function saveWatchFolder() {
    if (!selectedWatchFolderId) return
    setSaveBusy(true)
    setDetailsError("")
    try {
      await apiFetch(`/instrument-watch-folders/${selectedWatchFolderId}`, {
        method: "PATCH",
        body: {
          connector_id: connectorId,
          folder_path: folderPath.trim(),
          file_patterns: filePatterns.trim(),
          recursive,
          target_program: targetProgram,
          target_route: targetRoute,
          status,
        },
      })
      await loadDetails(selectedWatchFolderId)
      await loadWatchFolders()
    } catch (e) {
      setDetailsError(e instanceof Error ? e.message : "Could not update watch folder.")
    } finally {
      setSaveBusy(false)
    }
  }

  async function runScanNow() {
    if (!selectedWatchFolderId) return
    setScanBusy(true)
    setDetailsError("")
    try {
      const payload = await apiFetch<unknown>(`/instrument-watch-folders/${selectedWatchFolderId}/scan`, { method: "POST" })
      const rec = isRecord(payload) ? payload : {}
      const warningCount =
        Array.isArray(rec.warnings) ? rec.warnings.filter((item) => typeof item === "string" && item.trim()).length : 0
      trackWatchFolderScanRun({
        target_program: targetProgram,
        status: readStr(rec.status) || selectedDetails?.status,
        success_count: readCount(rec.ingested_count ?? rec.ingested) ?? 0,
        failure_count: readCount(rec.failed_count ?? rec.failed) ?? 0,
        warning_count: warningCount,
      })
      await loadDetails(selectedWatchFolderId)
      await loadWatchFolders()
    } catch (e) {
      setDetailsError(e instanceof Error ? e.message : "Could not run scan.")
    } finally {
      setScanBusy(false)
    }
  }

  const selectedCounts = useMemo(() => {
    if (!selectedDetails) return "—"
    const discovered = selectedDetails.discovered_count ?? "—"
    const ingested = selectedDetails.ingested_count ?? "—"
    const skipped = selectedDetails.skipped_count ?? "—"
    const failed = selectedDetails.failed_count ?? "—"
    return `discovered ${discovered} / ingested ${ingested} / skipped ${skipped} / failed ${failed}`
  }, [selectedDetails])

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-slate)" }}
        >
          MolTrace · Settings · Instrument Watch Folder
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Instrument Watch Folder</h1>
        <p className="text-sm text-muted-foreground">
          Configure watch folders for connector-driven ingestion into SpectraCheck, Regulatory Hub, and Reaction Optimization.
        </p>
      </div>

      <ModuleCard
        accent="slate"
        eyebrow="Create"
        title="Create watch folder"
        icon={Plus}
        description="Configure a new directory for the platform to monitor for new instrument files."
      >
        <div className="space-y-4">
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="watch-connector">connector selector</Label>
              <select
                id="watch-connector"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={connectorId}
                onChange={(e) => setConnectorId(e.target.value)}
              >
                <option value="">Select connector</option>
                {connectors.map((connector) => (
                  <option key={connector.id} value={connector.id}>
                    {connector.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="watch-folder-path">folder path</Label>
              <Input id="watch-folder-path" value={folderPath} onChange={(e) => setFolderPath(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="watch-file-patterns">file patterns</Label>
              <Textarea
                id="watch-file-patterns"
                rows={3}
                value={filePatterns}
                onChange={(e) => setFilePatterns(e.target.value)}
                placeholder="*.fid, *.mzML, *.raw"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="watch-target-program">target program</Label>
              <select
                id="watch-target-program"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={targetProgram}
                onChange={(e) => setTargetProgram(e.target.value as (typeof TARGET_PROGRAM_OPTIONS)[number])}
              >
                {TARGET_PROGRAM_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="watch-target-route">target route</Label>
              <select
                id="watch-target-route"
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
            <div className="space-y-1">
              <Label htmlFor="watch-status">status</Label>
              <select
                id="watch-status"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={status}
                onChange={(e) => setStatus(e.target.value as (typeof STATUS_OPTIONS)[number])}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex items-center gap-3 rounded-md border p-3">
            <Label htmlFor="watch-recursive" className="text-sm">
              recursive toggle
            </Label>
            <Switch id="watch-recursive" checked={recursive} onCheckedChange={setRecursive} />
          </div>
          <Button type="button" disabled={createBusy} onClick={() => void createWatchFolder()}>
            {createBusy ? "Creating…" : "Create watch folder"}
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Folders"
        title="Watch folder list"
        icon={FolderSearch}
        description="All configured watch folders with their connector, scan cadence, and last activity."
      >
        <div className="space-y-3">
          {loading ? <p className="text-sm text-muted-foreground">Loading watch folders…</p> : null}
          {!loading ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>folder path</TableHead>
                    <TableHead>target program</TableHead>
                    <TableHead>target route</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>last scan</TableHead>
                    <TableHead>counts</TableHead>
                    <TableHead>warnings</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {watchFolders.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-xs text-muted-foreground">
                        No watch folders returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    watchFolders.map((row) => (
                      <TableRow key={row.watch_folder_id}>
                        <TableCell className="text-xs">{row.folder_path}</TableCell>
                        <TableCell className="text-xs">{row.target_program}</TableCell>
                        <TableCell className="text-xs">{row.target_route}</TableCell>
                        <TableCell className="text-xs">{row.status}</TableCell>
                        <TableCell className="text-xs">{row.last_scan}</TableCell>
                        <TableCell className="text-xs">
                          discovered {row.discovered_count ?? "—"} / ingested {row.ingested_count ?? "—"} / skipped{" "}
                          {row.skipped_count ?? "—"} / failed {row.failed_count ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs">{row.warnings.length ? row.warnings.join("; ") : "—"}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedWatchFolderId === row.watch_folder_id ? "secondary" : "outline"}
                            onClick={() => setSelectedWatchFolderId(row.watch_folder_id)}
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Detail"
        title="Watch folder detail"
        icon={Eye}
        description="View, edit, or trigger an on-demand scan of the selected watch folder."
      >
        <div className="space-y-3">
          {detailsError ? <p className="text-xs text-destructive">{detailsError}</p> : null}
          {detailsLoading ? <p className="text-sm text-muted-foreground">Loading watch folder detail…</p> : null}
          {!selectedWatchFolderId ? (
            <p className="text-xs text-muted-foreground">Open a watch folder to view details.</p>
          ) : (
            <>
              <div className="rounded-md border p-3 text-xs">
                <p>
                  <span className="font-semibold">folder path:</span> {selectedDetails?.folder_path ?? "—"}
                </p>
                <p>
                  <span className="font-semibold">target program:</span> {selectedDetails?.target_program ?? "—"}
                </p>
                <p>
                  <span className="font-semibold">target route:</span> {selectedDetails?.target_route ?? "—"}
                </p>
                <p>
                  <span className="font-semibold">status:</span> {selectedDetails?.status ?? "—"}
                </p>
                <p>
                  <span className="font-semibold">last scan:</span> {selectedDetails?.last_scan ?? "—"}
                </p>
                <p>
                  <span className="font-semibold">counts:</span> {selectedCounts}
                </p>
                <p>
                  <span className="font-semibold">warnings:</span>{" "}
                  {selectedDetails?.warnings.length ? selectedDetails.warnings.join("; ") : "—"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" disabled={scanBusy} onClick={() => void runScanNow()}>
                  {scanBusy ? "Running…" : "Run scan now"}
                </Button>
                <Button type="button" variant="outline" disabled={saveBusy} onClick={() => void saveWatchFolder()}>
                  {saveBusy ? "Saving…" : "Save changes"}
                </Button>
              </div>
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer text-sm font-medium">Developer JSON</summary>
                <pre className="mt-3 overflow-x-auto text-xs">
                  {JSON.stringify(selectedDetails?.raw ?? {}, null, 2)}
                </pre>
              </details>
            </>
          )}
        </div>
      </ModuleCard>
    </div>
  )
}
