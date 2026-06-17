"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Loader2, RefreshCw } from "lucide-react"

type AnyRecord = Record<string, unknown>

function isRecord(v: unknown): v is AnyRecord {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const data = err.data
    if (isRecord(data) && typeof data.detail === "string") return data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function extractRows(data: unknown, keys: string[]): AnyRecord[] {
  if (Array.isArray(data)) return data.filter(isRecord) as AnyRecord[]
  if (!isRecord(data)) return []
  for (const key of keys) {
    const value = data[key]
    if (Array.isArray(value)) return value.filter(isRecord) as AnyRecord[]
  }
  return []
}

function readString(row: AnyRecord, keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "string" && value.trim()) return value.trim()
    if (typeof value === "number" && Number.isFinite(value)) return String(value)
  }
  return "—"
}

function readNumber(row: AnyRecord, keys: string[]): number | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return null
}

function readBool(row: AnyRecord, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "boolean") return value
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase()
      if (normalized === "true") return true
      if (normalized === "false") return false
    }
  }
  return null
}

function readTopLevelInt(data: unknown, keys: string[]): number | null {
  if (!isRecord(data)) return null
  return readNumber(data, keys)
}

function formatWhen(v: string): string {
  if (v === "—") return v
  const t = Date.parse(v)
  if (Number.isNaN(t)) return v
  return new Date(t).toLocaleString()
}

function scalarPreviewRows(data: unknown): Array<{ key: string; value: string }> {
  if (!isRecord(data)) return []
  const out: Array<{ key: string; value: string }> = []
  for (const [key, value] of Object.entries(data)) {
    if (out.length >= 20) break
    if (value == null) {
      out.push({ key, value: "—" })
      continue
    }
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      out.push({ key, value: String(value) })
    }
  }
  return out
}

function isSameLocalDay(iso: string): boolean {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return false
  const d = new Date(t)
  const now = new Date()
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}

const SERVICE_KEYS = ["services", "items", "results", "rows", "data"]
const PREDICTION_KEYS = ["predictions", "items", "results", "rows", "data"]
const ACTIVE_LEARNING_KEYS = ["candidates", "active_learning_candidates", "items", "results", "rows", "data"]

export function AiServicesDashboard() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const [services, setServices] = useState<AnyRecord[]>([])
  const [predictions, setPredictions] = useState<AnyRecord[]>([])
  const [activeLearningCandidates, setActiveLearningCandidates] = useState<AnyRecord[]>([])
  const [modelMonitoring, setModelMonitoring] = useState<unknown>(null)

  const [errServices, setErrServices] = useState("")
  const [errPredictions, setErrPredictions] = useState("")
  const [errActiveLearning, setErrActiveLearning] = useState("")
  const [errMonitoring, setErrMonitoring] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErrServices("")
    setErrPredictions("")
    setErrActiveLearning("")
    setErrMonitoring("")

    await Promise.all([
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/services", { method: "GET" })
          setServices(extractRows(data, SERVICE_KEYS))
        } catch (err) {
          setErrServices(formatErr(err, "Could not load /ai/services."))
          setServices([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/predictions", { method: "GET" })
          setPredictions(extractRows(data, PREDICTION_KEYS))
        } catch (err) {
          setErrPredictions(formatErr(err, "Could not load /ai/predictions."))
          setPredictions([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/active-learning/candidates", { method: "GET" })
          setActiveLearningCandidates(extractRows(data, ACTIVE_LEARNING_KEYS))
        } catch (err) {
          setErrActiveLearning(formatErr(err, "Could not load /ai/active-learning/candidates."))
          setActiveLearningCandidates([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/model-monitoring", { method: "GET" })
          setModelMonitoring(data)
        } catch (err) {
          setErrMonitoring(formatErr(err, "Could not load /ai/model-monitoring."))
          setModelMonitoring(null)
        }
      })(),
    ])

    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const activeServices = useMemo(() => {
    let c = 0
    for (const row of services) {
      const status = readString(row, ["status", "service_status", "state"]).toLowerCase()
      if (status === "active" || status === "serving" || status === "online" || status === "approved") c++
    }
    return c
  }, [services])

  const predictionsToday = useMemo(() => {
    const monitorCount = readTopLevelInt(modelMonitoring, [
      "predictions_today",
      "today_predictions",
      "prediction_count_today",
    ])
    if (monitorCount != null) return monitorCount

    let c = 0
    for (const row of predictions) {
      const created = readString(row, ["created_at", "createdAt", "timestamp", "predicted_at"])
      if (created !== "—" && isSameLocalDay(created)) c++
    }
    return c
  }, [modelMonitoring, predictions])

  const lowConfidencePredictions = useMemo(() => {
    const monitorCount = readTopLevelInt(modelMonitoring, [
      "low_confidence_predictions",
      "low_confidence_count",
      "n_low_confidence_predictions",
    ])
    if (monitorCount != null) return monitorCount

    let c = 0
    for (const row of predictions) {
      const confidence = readNumber(row, ["confidence", "confidence_score", "predicted_confidence"])
      if (confidence != null && confidence < 0.5) c++
    }
    return c
  }, [modelMonitoring, predictions])

  const oodPredictions = useMemo(() => {
    const monitorCount = readTopLevelInt(modelMonitoring, ["ood_predictions", "ood_count", "n_ood_predictions"])
    if (monitorCount != null) return monitorCount

    let c = 0
    for (const row of predictions) {
      const isOod = readBool(row, ["is_ood", "ood", "out_of_domain"])
      if (isOod === true) c++
    }
    return c
  }, [modelMonitoring, predictions])

  const servicesRequiringReview = useMemo(() => {
    let c = 0
    for (const row of services) {
      const status = readString(row, ["status", "review_status", "approval_status"]).toLowerCase()
      if (status.includes("review") || status.includes("pending") || status === "proposed" || status === "draft") c++
    }
    return c
  }, [services])

  const monitoringRows = useMemo(() => scalarPreviewRows(modelMonitoring), [modelMonitoring])

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-teal-ink)" }}
        >
          MolTrace · AI Services
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">AI Services</h1>
        <p className="text-sm text-muted-foreground">
          Controlled prediction services, model routing, active-learning feedback, and inference audit trails.
        </p>
      </div>

      <AlertCard
        variant="warning"
        title="Human review required"
        description="AI predictions are decision support. Scientific and regulatory outputs require human review."
      />

      <div className="flex items-center justify-between">
        <Badge variant="outline">Read-only service overview</Badge>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/predictions">Prediction Playground</Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/active-learning">Active Learning Queue</Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/monitoring">Model Monitoring</Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/shadow-evaluations">Shadow Evaluations</Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/canary">Canary Deployments</Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/ai/services">AI Service Registry</Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setReloadToken((v) => v + 1)}
            disabled={loading}
            className="gap-2"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            Refresh
          </Button>
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Active services</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{activeServices}</CardTitle>
          </CardHeader>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Predictions today</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{predictionsToday}</CardTitle>
          </CardHeader>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Low-confidence predictions</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{lowConfidencePredictions}</CardTitle>
          </CardHeader>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">OOD predictions</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{oodPredictions}</CardTitle>
          </CardHeader>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Active-learning candidates</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{activeLearningCandidates.length}</CardTitle>
          </CardHeader>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="pt-5 pb-5">
            <CardDescription className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Services requiring review</CardDescription>
            <CardTitle className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal-ink)" }}>{servicesRequiringReview}</CardTitle>
          </CardHeader>
        </Card>
      </section>

      <section>
        <ModuleCard
          accent="teal"
          eyebrow="AI · Service Table"
          title="AI service table"
          description="All registered AI/ML services with their model, current status, and version."
        >
          <div className="space-y-2">
            {errServices ? <p className="text-sm" style={{ color: "var(--mt-red)" }}>{errServices}</p> : null}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Service</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Last updated</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {services.slice(0, 20).map((row, idx) => (
                    <TableRow key={`${readString(row, ["id", "service_id", "name"])}-${idx}`}>
                      <TableCell>{readString(row, ["name", "service_name", "endpoint", "id"])}</TableCell>
                      <TableCell>{readString(row, ["model_name", "model", "model_id", "model_artifact_id"])}</TableCell>
                      <TableCell>{readString(row, ["status", "service_status", "approval_status"])}</TableCell>
                      <TableCell>{readString(row, ["version", "model_version", "service_version"])}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["updated_at", "updatedAt", "created_at"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!services.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No services returned.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </ModuleCard>
      </section>

      <section>
        <ModuleCard
          accent="teal"
          eyebrow="AI · Recent Predictions"
          title="Recent predictions"
          description="The most recent inference requests across all AI services with their confidence and review status."
        >
          <div className="space-y-2">
            {errPredictions ? <p className="text-sm" style={{ color: "var(--mt-red)" }}>{errPredictions}</p> : null}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Prediction</TableHead>
                    <TableHead>Service</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Confidence</TableHead>
                    <TableHead>Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {predictions.slice(0, 20).map((row, idx) => (
                    <TableRow key={`${readString(row, ["id", "prediction_id"])}-${idx}`}>
                      <TableCell>{readString(row, ["id", "prediction_id", "request_id"])}</TableCell>
                      <TableCell>{readString(row, ["service_name", "service_id", "endpoint"])}</TableCell>
                      <TableCell>{readString(row, ["status", "result_status", "review_status"])}</TableCell>
                      <TableCell>{readString(row, ["confidence", "confidence_score", "predicted_confidence"])}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["created_at", "createdAt", "timestamp"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!predictions.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No predictions returned.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </ModuleCard>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <ModuleCard
          accent="teal"
          eyebrow="AI · Active Learning"
          title="Active-learning preview"
          description="Predictions queued for human labeling — selected because the model was uncertain or the input was out-of-distribution."
        >
          <div className="space-y-2">
            {errActiveLearning ? <p className="text-sm" style={{ color: "var(--mt-red)" }}>{errActiveLearning}</p> : null}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Candidate</TableHead>
                    <TableHead>Reason</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeLearningCandidates.slice(0, 12).map((row, idx) => (
                    <TableRow key={`${readString(row, ["id", "candidate_id"])}-${idx}`}>
                      <TableCell>{readString(row, ["id", "candidate_id", "prediction_id"])}</TableCell>
                      <TableCell>{readString(row, ["reason", "candidate_reason", "queue_reason"])}</TableCell>
                      <TableCell>{readString(row, ["status", "queue_status", "review_status"])}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["created_at", "createdAt", "queued_at"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!activeLearningCandidates.length ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-muted-foreground">
                        No active-learning candidates returned.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </ModuleCard>

        <ModuleCard
          accent="teal"
          eyebrow="AI · Model Monitoring"
          title="Model monitoring preview"
          description="Live operational metrics — drift, latency, throughput, and out-of-distribution rate — across deployed services."
        >
          <div className="space-y-2">
            {errMonitoring ? <p className="text-sm" style={{ color: "var(--mt-red)" }}>{errMonitoring}</p> : null}
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead>Value</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {monitoringRows.map((row) => (
                    <TableRow key={row.key}>
                      <TableCell>{row.key}</TableCell>
                      <TableCell>{row.value}</TableCell>
                    </TableRow>
                  ))}
                  {!monitoringRows.length ? (
                    <TableRow>
                      <TableCell colSpan={2} className="text-muted-foreground">
                        No scalar monitoring metrics returned.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </ModuleCard>
      </section>
    </div>
  )
}
