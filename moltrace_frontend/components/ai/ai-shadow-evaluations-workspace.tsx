"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordString } from "@/components/projects/project-workspace-utils"
import {
  trackAiShadowEvaluationCompleted,
  trackAiShadowEvaluationStarted,
} from "@/src/lib/analytics/analytics-client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { GitCompare, ListChecks } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"

type Row = Record<string, unknown>
const SHADOW_KEYS = ["shadow_evaluations", "runs", "items", "results", "rows", "data"]

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function extractRows(data: unknown): Row[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Row[]
  if (!isRecord(data)) return []
  for (const key of SHADOW_KEYS) {
    const value = data[key]
    if (Array.isArray(value)) return value.filter(isRecord) as Row[]
  }
  return []
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const data = err.data
    if (isRecord(data) && typeof data.detail === "string" && data.detail.trim()) return data.detail
    return `HTTP ${err.status}: ${err.message || fallback}`
  }
  if (err instanceof Error) return err.message
  return fallback
}

function formatWhen(iso: string): string {
  if (iso === "-") return iso
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString()
}

function readStr(row: Row, keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "string" && value.trim()) return value.trim()
    if (typeof value === "number" && Number.isFinite(value)) return String(value)
  }
  return "-"
}

export function AiShadowEvaluationsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [rows, setRows] = useState<Row[]>([])
  const [loadErr, setLoadErr] = useState("")
  const [detailErr, setDetailErr] = useState("")
  const [selected, setSelected] = useState<Row | null>(null)

  const [serviceKey, setServiceKey] = useState("")
  const [productionModelArtifact, setProductionModelArtifact] = useState("")
  const [candidateModelArtifact, setCandidateModelArtifact] = useState("")
  const [datasetVersion, setDatasetVersion] = useState("")
  const [submitBusy, setSubmitBusy] = useState(false)
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const data = await apiFetch<unknown>("/ai/shadow-evaluations", { method: "GET" })
      setRows(extractRows(data))
    } catch (err) {
      setLoadErr(formatErr(err, "Could not load /ai/shadow-evaluations."))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  async function loadDetail(shadowRunId: string) {
    setDetailErr("")
    try {
      const data = await apiFetch<unknown>(`/ai/shadow-evaluations/${shadowRunId}`, { method: "GET" })
      setSelected(isRecord(data) ? data : null)
    } catch (err) {
      setDetailErr(formatErr(err, `Could not load /ai/shadow-evaluations/${shadowRunId}.`))
      setSelected(null)
    }
  }

  async function submitRun() {
    setFormErr("")
    setFormOk("")
    if (!serviceKey.trim() || !productionModelArtifact.trim() || !candidateModelArtifact.trim() || !datasetVersion.trim()) {
      setFormErr("service key, production model artifact, candidate model artifact, and dataset version are required.")
      return
    }
    trackAiShadowEvaluationStarted({
      service_key: serviceKey.trim(),
      status: "started",
    })
    setSubmitBusy(true)
    try {
      await apiFetch("/ai/shadow-evaluations", {
        method: "POST",
        body: {
          service_key: serviceKey.trim(),
          production_model_artifact: Number(productionModelArtifact),
          candidate_model_artifact: Number(candidateModelArtifact),
          dataset_version: Number(datasetVersion),
        },
      })
      trackAiShadowEvaluationCompleted({
        service_key: serviceKey.trim(),
        status: "submitted",
      })
      setFormOk("Shadow evaluation submitted.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setFormErr(formatErr(err, "Could not submit shadow evaluation."))
    } finally {
      setSubmitBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="font-mono text-2xl font-bold tracking-tight">Shadow Evaluations</h1>
        <p className="text-sm text-muted-foreground">Run side-by-side candidate checks and review results before deployment decisions.</p>
      </div>
      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertTitle>Human review required</AlertTitle>
        <AlertDescription>Shadow results are decision support and require review.</AlertDescription>
      </Alert>
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />} Refresh
        </Button>
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="Run"
        title="Run shadow evaluation"
        icon={GitCompare}
        description="Compare a candidate model against the production model on the same dataset, without serving traffic."
      >
        <div className="space-y-4">
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-emerald-700">{formOk}</p> : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="se-service-key">service key</Label><Input id="se-service-key" value={serviceKey} onChange={(e) => setServiceKey(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="se-prod-artifact">production model artifact</Label><Input id="se-prod-artifact" inputMode="numeric" value={productionModelArtifact} onChange={(e) => setProductionModelArtifact(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="se-candidate-artifact">candidate model artifact</Label><Input id="se-candidate-artifact" inputMode="numeric" value={candidateModelArtifact} onChange={(e) => setCandidateModelArtifact(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="se-dataset-version">dataset version</Label><Input id="se-dataset-version" inputMode="numeric" value={datasetVersion} onChange={(e) => setDatasetVersion(e.target.value)} /></div>
          </div>
          <Button type="button" onClick={() => void submitRun()} disabled={submitBusy}>
            {submitBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Run
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Runs"
        title="Shadow runs"
        icon={ListChecks}
        description="All offline candidate-vs-production comparisons with their status and timing."
      >
        <div className="overflow-x-auto">
          {loadErr ? <p className="mb-3 text-sm text-destructive">{loadErr}</p> : null}
          <Table>
            <TableHeader><TableRow><TableHead>shadow run</TableHead><TableHead>service key</TableHead><TableHead>status</TableHead><TableHead>created</TableHead><TableHead>detail</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((row, idx) => {
                const id = readStr(row, ["shadow_run_id", "id"])
                return (
                  <TableRow key={`${id}-${idx}`}>
                    <TableCell>{id}</TableCell>
                    <TableCell>{readStr(row, ["service_key"])}</TableCell>
                    <TableCell><Badge variant="outline">{readStr(row, ["status"])}</Badge></TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatWhen(readStr(row, ["created_at", "timestamp"]))}</TableCell>
                    <TableCell><Button size="sm" variant="outline" onClick={() => void loadDetail(id)}>Open</Button></TableCell>
                  </TableRow>
                )
              })}
              {rows.length === 0 ? <TableRow><TableCell colSpan={5} className="text-muted-foreground">No shadow evaluations returned.</TableCell></TableRow> : null}
            </TableBody>
          </Table>
          {detailErr ? <p className="mt-3 text-sm text-destructive">{detailErr}</p> : null}
          {selected ? (
            <div className="mt-3 rounded-md border bg-muted/20 p-3 text-sm">
              <p><span className="font-medium">shadow run:</span> {readRecordString(selected, "shadow_run_id") ?? readRecordString(selected, "id") ?? "-"}</p>
              <p><span className="font-medium">status:</span> {readRecordString(selected, "status") ?? "-"}</p>
              <p><span className="font-medium">summary:</span> {readRecordString(selected, "summary") ?? "-"}</p>
            </div>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
