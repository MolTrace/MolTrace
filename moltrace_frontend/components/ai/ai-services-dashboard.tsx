"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { humanizeField, statusLabel } from "@/lib/ui/status"
import {
  Activity,
  ArrowRight,
  ClipboardCheck,
  FlaskConical,
  GitCompare,
  Loader2,
  RefreshCw,
  Rocket,
  ServerCog,
  type LucideIcon,
} from "lucide-react"

type AnyRecord = Record<string, unknown>

function isRecord(v: unknown): v is AnyRecord {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
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
    if (typeof value === "boolean") {
      out.push({ key, value: value ? "Yes" : "No" })
      continue
    }
    if (typeof value === "string" || typeof value === "number") {
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

/**
 * The six destinations, grouped by where they sit in a model's life rather than
 * listed flat: you try a model, you feed it back, you check it against the
 * incumbent, you roll it out carefully, and you watch what is live. A row of six
 * identical buttons showed none of that, and made "AI Service Registry" look
 * like a peer of "Prediction Playground".
 *
 * Descriptions are each workspace's OWN stated purpose, lifted from the page
 * being linked to rather than written fresh here, so this hub cannot drift into
 * describing something its destination does not do.
 *
 * Same accent-per-group scheme as the Knowledge Library, and the same rule about
 * which token goes where: the vivid accent fills the left rule and the icon, the
 * -ink variant colours every piece of type.
 */
const AI_DESTINATIONS: ReadonlyArray<{
  label: string
  accent: string
  ink: string
  items: ReadonlyArray<{ label: string; href: string; desc: string; icon: LucideIcon }>
}> = [
  {
    label: "Try it, and teach it",
    accent: "var(--mt-teal)",
    ink: "var(--mt-teal-ink)",
    items: [
      { label: "Prediction Playground", href: "/ai/predictions", desc: "Run a prediction by hand. Available only where your organization's policy allows it.", icon: FlaskConical },
      { label: "Active Learning Queue", href: "/ai/active-learning", desc: "Submit prediction feedback and manage the active-learning candidate lifecycle.", icon: ClipboardCheck },
    ],
  },
  {
    label: "Check before rollout",
    accent: "var(--mt-violet)",
    ink: "var(--mt-violet-ink)",
    items: [
      { label: "Shadow Evaluations", href: "/ai/shadow-evaluations", desc: "Run side-by-side candidate checks and review results before a deployment decision.", icon: GitCompare },
      { label: "Canary Deployments", href: "/ai/canary", desc: "Propose, review and resolve canary deployments through a human approval workflow.", icon: Rocket },
    ],
  },
  {
    label: "Watch what is live",
    accent: "var(--mt-cyan)",
    ink: "var(--mt-cyan-ink)",
    items: [
      { label: "Model Monitoring", href: "/ai/monitoring", desc: "Read monitoring summaries and log monitoring events.", icon: Activity },
      { label: "AI Service Registry", href: "/ai/services", desc: "Create and update service routing definitions without auto-activating models.", icon: ServerCog },
    ],
  },
]

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
          setErrServices(formatApiError(err, "Could not load AI services."))
          setServices([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/predictions", { method: "GET" })
          setPredictions(extractRows(data, PREDICTION_KEYS))
        } catch (err) {
          setErrPredictions(formatApiError(err, "Could not load predictions."))
          setPredictions([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/active-learning/candidates", { method: "GET" })
          setActiveLearningCandidates(extractRows(data, ACTIVE_LEARNING_KEYS))
        } catch (err) {
          setErrActiveLearning(formatApiError(err, "Could not load active-learning candidates."))
          setActiveLearningCandidates([])
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/model-monitoring", { method: "GET" })
          setModelMonitoring(data)
        } catch (err) {
          setErrMonitoring(formatApiError(err, "Could not load model monitoring."))
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
          Controlled prediction services, model routing, active-learning feedback, and prediction audit trails.
        </p>
      </div>

      <AlertCard
        variant="warning"
        title="Human review required"
        description="AI predictions are decision support. Scientific and regulatory outputs require human review."
      />

      {/* Refresh is an ACTION and sat among six navigation links, so the one
          control that changes nothing about where you are looked exactly like
          the six that do. It sits with the heading now. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Badge variant="outline">Read-only service overview</Badge>
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

      <section aria-labelledby="ai-destinations" className="space-y-5">
        <h2
          id="ai-destinations"
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground"
        >
          Where to go next
        </h2>

        {AI_DESTINATIONS.map((group) => (
          <div key={group.label} className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">{group.label}</p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {group.items.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group relative flex h-full min-w-0 flex-col rounded-xl border bg-card p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0"
                  /* Same signature as the Knowledge Library cards and the home
                     page module row: a 3px rule carrying the group's colour
                     without tinting any text. */
                  style={{ borderLeftWidth: "3px", borderLeftColor: group.accent }}
                >
                  <div className="flex items-center gap-2">
                    {/* Icons keep the vivid accent — shapes, not type. */}
                    <item.icon className="h-5 w-5 shrink-0" style={{ color: group.accent }} aria-hidden />
                    <h3 className="min-w-0 text-sm font-semibold" style={{ color: group.ink }}>
                      {item.label}
                    </h3>
                    <ArrowRight
                      className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none"
                      aria-hidden
                    />
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </section>

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
                      <TableCell>{statusLabel(readString(row, ["status", "service_status", "approval_status"]))}</TableCell>
                      <TableCell>{readString(row, ["version", "model_version", "service_version"])}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["updated_at", "updatedAt", "created_at"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!services.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No services found.
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
          description="The most recent predictions across all AI services with their confidence and review status."
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
                      <TableCell>{statusLabel(readString(row, ["status", "result_status", "review_status"]))}</TableCell>
                      <TableCell>{readString(row, ["confidence", "confidence_score", "predicted_confidence"])}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["created_at", "createdAt", "timestamp"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!predictions.length ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No predictions found.
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
                      <TableCell>{statusLabel(readString(row, ["status", "queue_status", "review_status"]))}</TableCell>
                      <TableCell>{formatWhen(readString(row, ["created_at", "createdAt", "queued_at"]))}</TableCell>
                    </TableRow>
                  ))}
                  {!activeLearningCandidates.length ? (
                    <TableRow>
                      <TableCell colSpan={4} className="text-muted-foreground">
                        No active-learning candidates found.
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
                      <TableCell>{humanizeField(row.key)}</TableCell>
                      <TableCell>{row.value}</TableCell>
                    </TableRow>
                  ))}
                  {!monitoringRows.length ? (
                    <TableRow>
                      <TableCell colSpan={2} className="text-muted-foreground">
                        No monitoring metrics found.
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
