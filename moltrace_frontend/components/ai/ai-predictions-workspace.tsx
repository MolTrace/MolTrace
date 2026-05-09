"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordString } from "@/components/projects/project-workspace-utils"
import {
  trackAiPredictionRunCompleted,
  trackAiPredictionRunStarted,
} from "@/src/lib/analytics/analytics-client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"

type Row = Record<string, unknown>

const PREDICTION_KEYS = ["predictions", "items", "results", "rows", "data"]
const AUDIT_KEYS = ["audit", "audit_log", "events", "items", "results", "rows", "data"]
const TARGET_MODULE_OPTIONS = [
  "spectracheck",
  "reaction_optimization",
  "regulatory",
  "knowledge_extraction",
  "reports",
  "validation",
] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function extractRows(data: unknown, keys: string[]): Row[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Row[]
  if (!isRecord(data)) return []
  for (const key of keys) {
    const value = data[key]
    if (Array.isArray(value)) return value.filter(isRecord) as Row[]
  }
  return []
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "-"
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString()
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

function confidenceBucketFromUnknown(raw: unknown): string {
  let n: number | null = null
  if (typeof raw === "number" && Number.isFinite(raw)) n = raw
  if (typeof raw === "string" && raw.trim() && Number.isFinite(Number(raw))) n = Number(raw)
  if (n == null) return "unknown"
  if (n <= 1) {
    if (n < 0.5) return "low"
    if (n < 0.8) return "medium"
    return "high"
  }
  if (n < 50) return "low"
  if (n < 80) return "medium"
  return "high"
}

export function AiPredictionsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const [predictions, setPredictions] = useState<Row[]>([])
  const [auditRows, setAuditRows] = useState<Row[]>([])
  const [loadErrPredictions, setLoadErrPredictions] = useState("")
  const [loadErrAudit, setLoadErrAudit] = useState("")

  const [serviceKey, setServiceKey] = useState("")
  const [targetModule, setTargetModule] = useState<string>(TARGET_MODULE_OPTIONS[0])
  const [taskKey, setTaskKey] = useState("")
  const [inputSummaryJson, setInputSummaryJson] = useState("{}")
  const [artifactId, setArtifactId] = useState("")
  const [evidenceItemId, setEvidenceItemId] = useState("")
  const [compoundId, setCompoundId] = useState("")
  const [sessionId, setSessionId] = useState("")
  const [experimentalMode, setExperimentalMode] = useState(false)
  const [notes, setNotes] = useState("")
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")
  const [submitBusy, setSubmitBusy] = useState(false)

  const jsonWarningVisible = useMemo(() => inputSummaryJson.trim().length > 0, [inputSummaryJson])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErrPredictions("")
    setLoadErrAudit("")
    await Promise.all([
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/predictions", { method: "GET" })
          setPredictions(extractRows(data, PREDICTION_KEYS))
        } catch (err) {
          setLoadErrPredictions(formatErr(err, "Could not load /ai/predictions."))
          setPredictions([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/prediction-audit", { method: "GET" })
          setAuditRows(extractRows(data, AUDIT_KEYS))
        } catch (err) {
          setLoadErrAudit(formatErr(err, "Could not load /ai/prediction-audit."))
          setAuditRows([])
        }
      })(),
    ])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  async function submitRunPrediction() {
    setFormErr("")
    setFormOk("")
    if (!serviceKey.trim() || !targetModule.trim() || !taskKey.trim()) {
      setFormErr("service_key, target_module, and task_key are required.")
      return
    }

    let parsedSummary: Record<string, unknown>
    try {
      const parsed = JSON.parse(inputSummaryJson.trim() || "{}") as unknown
      if (!isRecord(parsed)) {
        setFormErr("input_summary_json must be a JSON object.")
        return
      }
      parsedSummary = parsed
    } catch {
      setFormErr("input_summary_json must be valid JSON.")
      return
    }

    const artifact = Number.parseInt(artifactId, 10)
    const evidence = Number.parseInt(evidenceItemId, 10)
    const compound = Number.parseInt(compoundId, 10)
    const session = Number.parseInt(sessionId, 10)

    const body: Record<string, unknown> = {
      service_key: serviceKey.trim(),
      target_module: targetModule,
      task_key: taskKey.trim(),
      input_summary_json: parsedSummary,
      artifact_id: Number.isFinite(artifact) && artifact > 0 ? artifact : null,
      evidence_item_id: Number.isFinite(evidence) && evidence > 0 ? evidence : null,
      compound_id: Number.isFinite(compound) && compound > 0 ? compound : null,
      session_id: Number.isFinite(session) && session > 0 ? session : null,
      experimental_mode: experimentalMode,
      notes: notes.trim() || null,
    }

    trackAiPredictionRunStarted({
      service_key: serviceKey.trim(),
      target_module: targetModule,
      task_key: taskKey.trim(),
      status: "started",
    })

    setSubmitBusy(true)
    try {
      const created = await apiFetch<unknown>("/ai/predictions", { method: "POST", body })
      const createdId = readRecordString(created, "prediction_id") ?? readRecordString(created, "id")
      const createdRec = isRecord(created) ? created : {}
      trackAiPredictionRunCompleted({
        service_key: serviceKey.trim(),
        target_module: targetModule,
        task_key: taskKey.trim(),
        status: readRecordString(createdRec, "status") ?? "submitted",
        confidence_bucket: confidenceBucketFromUnknown(createdRec.confidence_score ?? createdRec.confidence),
        ood_status: readRecordString(createdRec, "ood_status") ?? readRecordString(createdRec, "is_ood") ?? "unknown",
        warning_count: Array.isArray(createdRec.warnings) ? createdRec.warnings.length : 0,
      })
      setFormOk(createdId ? `Prediction submitted (${createdId}).` : "Prediction submitted.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setFormErr(formatErr(err, "Could not run prediction."))
    } finally {
      setSubmitBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Prediction Playground</h1>
        <p className="text-sm text-muted-foreground">
          Submit controlled prediction requests and review prediction audit history.
        </p>
      </div>

      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertTitle>Human review required</AlertTitle>
        <AlertDescription>
          Predictions are decision support and require review before scientific or regulatory use.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
          Refresh
        </Button>
        <Badge variant="outline">POST /ai/predictions</Badge>
        <Badge variant="outline">GET /ai/predictions</Badge>
        <Badge variant="outline">GET /ai/prediction-audit</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Run prediction</CardTitle>
          <CardDescription>Use IDs and summaries only. Do not include raw scientific payloads.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-emerald-700">{formOk}</p> : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="prediction-service-key">service key</Label>
              <Input id="prediction-service-key" value={serviceKey} onChange={(e) => setServiceKey(e.target.value)} placeholder="service_key" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-target-module">target module</Label>
              <Select value={targetModule} onValueChange={setTargetModule}>
                <SelectTrigger id="prediction-target-module">
                  <SelectValue placeholder="Select target module" />
                </SelectTrigger>
                <SelectContent>
                  {TARGET_MODULE_OPTIONS.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-task-key">task key</Label>
              <Input id="prediction-task-key" value={taskKey} onChange={(e) => setTaskKey(e.target.value)} placeholder="task_key" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-artifact-id">artifact ID optional</Label>
              <Input id="prediction-artifact-id" value={artifactId} onChange={(e) => setArtifactId(e.target.value)} inputMode="numeric" placeholder="artifact_id" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-evidence-item-id">evidence item ID optional</Label>
              <Input
                id="prediction-evidence-item-id"
                value={evidenceItemId}
                onChange={(e) => setEvidenceItemId(e.target.value)}
                inputMode="numeric"
                placeholder="evidence_item_id"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-compound-id">compound ID optional</Label>
              <Input id="prediction-compound-id" value={compoundId} onChange={(e) => setCompoundId(e.target.value)} inputMode="numeric" placeholder="compound_id" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="prediction-session-id">session ID optional</Label>
              <Input id="prediction-session-id" value={sessionId} onChange={(e) => setSessionId(e.target.value)} inputMode="numeric" placeholder="session_id" />
            </div>
            <div className="flex items-center justify-between rounded-md border p-3">
              <div className="space-y-1">
                <Label htmlFor="prediction-experimental-mode">experimental mode toggle</Label>
                <p className="text-xs text-muted-foreground">Use only when backend policy allows this request path.</p>
              </div>
              <Switch id="prediction-experimental-mode" checked={experimentalMode} onCheckedChange={setExperimentalMode} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="prediction-input-summary-json">input summary JSON</Label>
            <Textarea
              id="prediction-input-summary-json"
              value={inputSummaryJson}
              onChange={(e) => setInputSummaryJson(e.target.value)}
              rows={6}
              placeholder='{"summary": "ID-based analytical context only"}'
            />
          </div>

          {jsonWarningVisible ? (
            <Alert className="border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertDescription>
                Do not paste raw spectra, full structures, source text, secrets, or private data into this field.
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="prediction-notes">notes</Label>
            <Textarea
              id="prediction-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Prediction request notes (no private scientific payloads)."
            />
          </div>

          <Button type="button" onClick={() => void submitRunPrediction()} disabled={submitBusy}>
            {submitBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Run prediction
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Predictions</CardTitle>
          <CardDescription>
            All inference results across services with their confidence and out-of-distribution flags.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {loadErrPredictions ? <p className="mb-3 text-sm text-destructive">{loadErrPredictions}</p> : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>prediction</TableHead>
                <TableHead>service key</TableHead>
                <TableHead>status</TableHead>
                <TableHead>confidence</TableHead>
                <TableHead>OOD</TableHead>
                <TableHead>created</TableHead>
                <TableHead>detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {predictions.slice(0, 25).map((row, idx) => {
                const id = readRecordString(row, "prediction_id") ?? readRecordString(row, "id") ?? String(idx + 1)
                const confidence = readRecordString(row, "confidence") ?? readRecordString(row, "confidence_score") ?? "-"
                const ood = readRecordString(row, "ood_status") ?? readRecordString(row, "is_ood") ?? "-"
                return (
                  <TableRow key={`${id}-${idx}`}>
                    <TableCell>{id}</TableCell>
                    <TableCell>{readRecordString(row, "service_key") ?? "-"}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{readRecordString(row, "status") ?? "-"}</Badge>
                    </TableCell>
                    <TableCell>{confidence}</TableCell>
                    <TableCell>{ood}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWhen(readRecordString(row, "created_at") ?? readRecordString(row, "timestamp"))}
                    </TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={`/ai/predictions/${encodeURIComponent(id)}`}>Open</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
              {predictions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-muted-foreground">
                    No predictions returned.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Prediction audit</CardTitle>
          <CardDescription>
            Append-only log of every prediction with reviewer feedback and override decisions for compliance.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {loadErrAudit ? <p className="mb-3 text-sm text-destructive">{loadErrAudit}</p> : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>event</TableHead>
                <TableHead>prediction</TableHead>
                <TableHead>status</TableHead>
                <TableHead>actor</TableHead>
                <TableHead>timestamp</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {auditRows.slice(0, 30).map((row, idx) => {
                const predictionId = readRecordString(row, "prediction_id") ?? "-"
                return (
                  <TableRow key={`${predictionId}-${idx}`}>
                    <TableCell>{readRecordString(row, "event_type") ?? readRecordString(row, "event") ?? "-"}</TableCell>
                    <TableCell>{predictionId}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{readRecordString(row, "status") ?? "-"}</Badge>
                    </TableCell>
                    <TableCell>{readRecordString(row, "actor") ?? readRecordString(row, "reviewer") ?? "-"}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWhen(readRecordString(row, "created_at") ?? readRecordString(row, "timestamp"))}
                    </TableCell>
                  </TableRow>
                )
              })}
              {auditRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-muted-foreground">
                    No audit events returned.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
