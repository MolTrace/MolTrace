"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackConnectorCreated, trackConnectorHealthCheckRun } from "@/src/lib/analytics/analytics-client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type Row = Record<string, unknown>

type ConnectorRow = {
  id: number
  display_name: string
  connector_type: string
  target_program: string
  status: string
  last_health_check: string
  updated_date: string
  recent_ingestion_runs: number
  failed_sync_jobs: number
}

const CONNECTOR_TYPE_OPTIONS = [
  "instrument_watch_folder",
  "object_storage",
  "eln",
  "lims",
  "sdms",
  "chromatography_data_system",
  "regulatory_document_system",
  "webhook",
  "generic_rest",
  "other",
] as const

const TARGET_PROGRAM_OPTIONS = [
  "spectracheck",
  "regulatory_hub",
  "reaction_optimization",
  "cross_module",
] as const

const STATUS_OPTIONS = ["active", "warning", "paused", "disabled"] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return 0
}

function asRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  if (Array.isArray(payload.items)) return payload.items.filter(isRecord)
  if (Array.isArray(payload.results)) return payload.results.filter(isRecord)
  if (Array.isArray(payload.connectors)) return payload.connectors.filter(isRecord)
  return []
}

function parseConnectorRow(row: Row): ConnectorRow | null {
  const id = readNum(row.id)
  if (!id) return null
  return {
    id,
    display_name: readStr(row.display_name) || "—",
    connector_type: readStr(row.connector_type) || "—",
    target_program: readStr(row.target_program) || "—",
    status: readStr(row.status) || "—",
    last_health_check:
      readStr(row.last_health_check) || readStr(row.last_health_check_at) || readStr(row.last_checked_at) || "—",
    updated_date: readStr(row.updated_date) || readStr(row.updated_at) || "—",
    recent_ingestion_runs: readNum(row.recent_ingestion_runs ?? row.ingestion_runs_count),
    failed_sync_jobs: readNum(row.failed_sync_jobs ?? row.failed_sync_jobs_count),
  }
}

export function ConnectorsCenterWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [connectors, setConnectors] = useState<ConnectorRow[]>([])
  const [selectedConnectorId, setSelectedConnectorId] = useState<number | null>(null)
  const [healthChecks, setHealthChecks] = useState<Row[]>([])
  const [healthLoading, setHealthLoading] = useState(false)
  const [healthError, setHealthError] = useState("")

  const [connectorKey, setConnectorKey] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [connectorType, setConnectorType] = useState<(typeof CONNECTOR_TYPE_OPTIONS)[number]>("instrument_watch_folder")
  const [targetProgram, setTargetProgram] = useState<(typeof TARGET_PROGRAM_OPTIONS)[number]>("spectracheck")
  const [status, setStatus] = useState<(typeof STATUS_OPTIONS)[number]>("active")
  const [createBusy, setCreateBusy] = useState(false)

  const loadConnectors = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/connectors", { method: "GET" })
      const rows = asRows(payload).map(parseConnectorRow).filter((x): x is ConnectorRow => x != null)
      setConnectors(rows)
      if (rows.length > 0 && !selectedConnectorId) setSelectedConnectorId(rows[0]!.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load connectors.")
      setConnectors([])
    } finally {
      setLoading(false)
    }
  }, [selectedConnectorId])

  const loadHealthChecks = useCallback(async (connectorId: number | null) => {
    if (!connectorId) {
      setHealthChecks([])
      return
    }
    setHealthLoading(true)
    setHealthError("")
    try {
      const payload = await apiFetch<unknown>(`/connectors/${connectorId}/health-checks`, { method: "GET" })
      setHealthChecks(asRows(payload))
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : "Could not load health checks.")
      setHealthChecks([])
    } finally {
      setHealthLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadConnectors()
  }, [loadConnectors])

  useEffect(() => {
    void loadHealthChecks(selectedConnectorId)
  }, [selectedConnectorId, loadHealthChecks])

  async function createConnector() {
    setCreateBusy(true)
    setError("")
    try {
      await apiFetch("/connectors", {
        method: "POST",
        body: {
          connector_key: connectorKey.trim(),
          display_name: displayName.trim(),
          connector_type: connectorType,
          target_program: targetProgram,
          status,
        },
      })
      trackConnectorCreated({
        connector_type: connectorType,
        target_program: targetProgram,
        status,
      })
      setConnectorKey("")
      setDisplayName("")
      await loadConnectors()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create connector.")
    } finally {
      setCreateBusy(false)
    }
  }

  async function runHealthCheck() {
    if (!selectedConnectorId) return
    setHealthLoading(true)
    setHealthError("")
    try {
      const payload = await apiFetch<unknown>(`/connectors/${selectedConnectorId}/health-check`, { method: "POST" })
      const rec = isRecord(payload) ? payload : {}
      const warningCount =
        Array.isArray(rec.warnings) ? rec.warnings.filter((item) => typeof item === "string" && item.trim()).length : 0
      const selected = connectors.find((connector) => connector.id === selectedConnectorId)
      trackConnectorHealthCheckRun({
        connector_type: selected?.connector_type,
        target_program: selected?.target_program,
        status: readStr(rec.status) || selected?.status,
        warning_count: warningCount,
      })
      await loadHealthChecks(selectedConnectorId)
      await loadConnectors()
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : "Health check failed.")
    } finally {
      setHealthLoading(false)
    }
  }

  const summary = useMemo(() => {
    const activeConnectors = connectors.filter((c) => c.status.toLowerCase() === "active").length
    const connectorsWithWarnings = connectors.filter((c) => {
      const s = c.status.toLowerCase()
      return s.includes("warning") || s.includes("degraded") || s.includes("error")
    }).length
    const recentIngestionRuns = connectors.reduce((sum, c) => sum + c.recent_ingestion_runs, 0)
    const failedSyncJobs = connectors.reduce((sum, c) => sum + c.failed_sync_jobs, 0)
    return { activeConnectors, connectorsWithWarnings, recentIngestionRuns, failedSyncJobs }
  }, [connectors])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Connector Center</h1>
        <p className="text-muted-foreground">
          Connect instruments, storage, ELN, LIMS, SDMS, regulatory document systems, and webhooks to MolTrace.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">active connectors</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.activeConnectors}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">connectors with warnings</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.connectorsWithWarnings}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">recent ingestion runs</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.recentIngestionRuns}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">failed sync jobs</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.failedSyncJobs}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connector table</CardTitle>
          <CardDescription>
            All configured external integrations with their type, status, and last health check.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          {loading ? <p className="text-sm text-muted-foreground">Loading connectors…</p> : null}
          {!loading ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>display name</TableHead>
                    <TableHead>connector type</TableHead>
                    <TableHead>target program</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>last health check</TableHead>
                    <TableHead>updated date</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {connectors.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No connectors returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    connectors.map((connector) => (
                      <TableRow key={connector.id}>
                        <TableCell className="text-xs">{connector.display_name}</TableCell>
                        <TableCell className="text-xs">{connector.connector_type}</TableCell>
                        <TableCell className="text-xs">{connector.target_program}</TableCell>
                        <TableCell className="text-xs">{connector.status}</TableCell>
                        <TableCell className="text-xs">{connector.last_health_check}</TableCell>
                        <TableCell className="text-xs">{connector.updated_date}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedConnectorId === connector.id ? "secondary" : "outline"}
                            onClick={() => setSelectedConnectorId(connector.id)}
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create connector card</CardTitle>
          <CardDescription>
            Register a new connector to LIMS, ELN, vendor instruments, or other external systems.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="connector-key">connector key</Label>
              <Input id="connector-key" value={connectorKey} onChange={(e) => setConnectorKey(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="display-name">display name</Label>
              <Input id="display-name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="connector-type">connector type</Label>
              <select
                id="connector-type"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                value={connectorType}
                onChange={(e) => setConnectorType(e.target.value as (typeof CONNECTOR_TYPE_OPTIONS)[number])}
              >
                {CONNECTOR_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="target-program">target program</Label>
              <select
                id="target-program"
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
              <Label htmlFor="status">status</Label>
              <select
                id="status"
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
          <Button type="button" disabled={createBusy} onClick={() => void createConnector()}>
            {createBusy ? "Creating…" : "Create connector"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Health check panel</CardTitle>
          <CardDescription>
            Trigger an on-demand connectivity test and review the most recent health check results for the selected connector.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            Connector credentials are stored as secret references only. Secrets are never displayed.
          </p>
          {healthError ? <p className="text-xs text-destructive">{healthError}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={!selectedConnectorId || healthLoading} onClick={() => void runHealthCheck()}>
              {healthLoading ? "Running…" : "Run health check"}
            </Button>
            <Button type="button" variant="outline" disabled={!selectedConnectorId || healthLoading} onClick={() => void loadHealthChecks(selectedConnectorId)}>
              Refresh checks
            </Button>
          </div>
          {!selectedConnectorId ? (
            <p className="text-xs text-muted-foreground">Open a connector to view health checks.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>status</TableHead>
                    <TableHead>checked at</TableHead>
                    <TableHead>message</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {healthChecks.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-xs text-muted-foreground">
                        No health checks returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    healthChecks.map((row, idx) => (
                      <TableRow key={`${readStr(row.id) || idx}`}>
                        <TableCell className="text-xs">{readStr(row.status) || "—"}</TableCell>
                        <TableCell className="text-xs">{readStr(row.checked_at ?? row.created_at) || "—"}</TableCell>
                        <TableCell className="text-xs">{readStr(row.message ?? row.detail) || "—"}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
