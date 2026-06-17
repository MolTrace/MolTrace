"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Activity, ListChecks } from "lucide-react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"

type Row = Record<string, unknown>

const EVENT_KEYS = ["events", "items", "results", "rows", "data"]

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

function readNum(data: unknown, keys: string[]): number | null {
  if (!isRecord(data)) return null
  for (const key of keys) {
    const value = data[key]
    if (typeof value === "number" && Number.isFinite(value)) return value
    if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value)
  }
  return null
}

function readStr(row: Row, keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "string" && value.trim()) return value.trim()
    if (typeof value === "number" && Number.isFinite(value)) return String(value)
  }
  return "-"
}

function formatWhen(iso: string): string {
  if (iso === "-") return iso
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

export function AiModelMonitoringWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [monitoring, setMonitoring] = useState<unknown>(null)
  const [events, setEvents] = useState<Row[]>([])
  const [loadErr, setLoadErr] = useState("")
  const [eventsErr, setEventsErr] = useState("")

  const [eventType, setEventType] = useState("monitoring_signal")
  const [serviceKey, setServiceKey] = useState("")
  const [status, setStatus] = useState("")
  const [eventNotes, setEventNotes] = useState("")
  const [postBusy, setPostBusy] = useState(false)
  const [postErr, setPostErr] = useState("")
  const [postOk, setPostOk] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    setEventsErr("")
    await Promise.all([
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/model-monitoring", { method: "GET" })
          setMonitoring(data)
        } catch (err) {
          setLoadErr(formatErr(err, "Could not load /ai/model-monitoring."))
          setMonitoring(null)
        }
      })(),
      (async () => {
        try {
          const data = await apiFetch<unknown>("/ai/model-monitoring/events", { method: "GET" })
          setEvents(extractRows(data, EVENT_KEYS))
        } catch (err) {
          setEventsErr(formatErr(err, "Could not load /ai/model-monitoring/events."))
          setEvents([])
        }
      })(),
    ])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  const predictionVolume = useMemo(
    () => readNum(monitoring, ["prediction_volume", "predictions_today", "prediction_count", "total_predictions"]) ?? 0,
    [monitoring],
  )
  const lowConfidenceCount = useMemo(
    () => readNum(monitoring, ["low_confidence_count", "low_confidence_predictions", "n_low_confidence"]) ?? 0,
    [monitoring],
  )
  const oodCount = useMemo(() => readNum(monitoring, ["ood_count", "ood_predictions", "n_ood"]) ?? 0, [monitoring])
  const fallbackUsedCount = useMemo(
    () => readNum(monitoring, ["fallback_used_count", "fallback_count", "n_fallback_used"]) ?? 0,
    [monitoring],
  )
  const humanRejectionCount = useMemo(
    () => readNum(monitoring, ["human_rejection_count", "rejection_count", "n_human_rejection"]) ?? 0,
    [monitoring],
  )
  const serviceFailureCount = useMemo(
    () => readNum(monitoring, ["service_failure_count", "failure_count", "n_service_failures"]) ?? 0,
    [monitoring],
  )

  async function postEvent() {
    setPostErr("")
    setPostOk("")
    setPostBusy(true)
    try {
      await apiFetch("/ai/model-monitoring/events", {
        method: "POST",
        body: {
          event_type: eventType.trim() || "monitoring_signal",
          service_key: serviceKey.trim() || null,
          status: status.trim() || null,
          notes: eventNotes.trim() || null,
        },
      })
      setPostOk("Monitoring event submitted.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setPostErr(formatErr(err, "Could not submit monitoring event."))
    } finally {
      setPostBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="font-mono text-2xl font-bold tracking-tight">Model Monitoring</h1>
        <p className="text-sm text-muted-foreground">Read monitoring rollups and log monitoring events.</p>
      </div>

      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertTitle>Human review required</AlertTitle>
        <AlertDescription>Monitoring metrics are decision support and require review before deployment decisions.</AlertDescription>
      </Alert>

      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
          Refresh
        </Button>
        <Badge variant="outline">GET /ai/model-monitoring</Badge>
        <Badge variant="outline">GET /ai/model-monitoring/events</Badge>
      </div>

      {loadErr ? <p className="text-sm text-destructive">{loadErr}</p> : null}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[
          { label: "prediction volume", value: predictionVolume, color: "var(--mt-teal-ink)" },
          { label: "low-confidence count", value: lowConfidenceCount, color: "var(--mt-amber)" },
          { label: "OOD count", value: oodCount, color: "var(--mt-amber)" },
          { label: "fallback used count", value: fallbackUsedCount, color: "var(--mt-violet-ink)" },
          { label: "human rejection count", value: humanRejectionCount, color: "var(--mt-amber)" },
          { label: "service failure count", value: serviceFailureCount, color: "var(--mt-red)" },
        ].map((kpi) => (
          <Card
            key={kpi.label}
            className="overflow-hidden rounded-xl py-0"
            style={{ borderTop: `3px solid ${kpi.color}` }}
          >
            <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
              <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                {kpi.label}
              </CardTitle>
            </CardHeader>
            <CardContent className="pb-5">
              <div
                className="font-mono text-3xl font-bold tabular-nums leading-none"
                style={{ color: kpi.color }}
              >
                {kpi.value}
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      <ModuleCard
        accent="teal"
        eyebrow="Event"
        title="Log monitoring event"
        icon={Activity}
        description="Record a drift, latency, failure, or audit event for a deployed AI service."
      >
        <div className="space-y-4">
          {postErr ? <p className="text-sm text-destructive">{postErr}</p> : null}
          {postOk ? <p className="text-sm text-emerald-700">{postOk}</p> : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="mm-event-type">event type</Label><Input id="mm-event-type" value={eventType} onChange={(e) => setEventType(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="mm-service-key">service key</Label><Input id="mm-service-key" value={serviceKey} onChange={(e) => setServiceKey(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="mm-status">status</Label><Input id="mm-status" value={status} onChange={(e) => setStatus(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="mm-notes">notes</Label><Input id="mm-notes" value={eventNotes} onChange={(e) => setEventNotes(e.target.value)} /></div>
          </div>
          <Button type="button" onClick={() => void postEvent()} disabled={postBusy}>
            {postBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Submit event
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Events"
        title="Monitoring events"
        icon={ListChecks}
        description="Recent operational events across all monitored AI services, ordered by timestamp."
      >
        <div className="overflow-x-auto">
          {eventsErr ? <p className="mb-3 text-sm text-destructive">{eventsErr}</p> : null}
          <Table>
            <TableHeader><TableRow><TableHead>event</TableHead><TableHead>service key</TableHead><TableHead>status</TableHead><TableHead>timestamp</TableHead></TableRow></TableHeader>
            <TableBody>
              {events.slice(0, 40).map((row, idx) => (
                <TableRow key={`${readStr(row, ["id", "event_id"])}-${idx}`}>
                  <TableCell>{readStr(row, ["event_type", "event"])}</TableCell>
                  <TableCell>{readStr(row, ["service_key"])}</TableCell>
                  <TableCell><Badge variant="outline">{readStr(row, ["status"])}</Badge></TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatWhen(readStr(row, ["created_at", "timestamp"]))}</TableCell>
                </TableRow>
              ))}
              {events.length === 0 ? <TableRow><TableCell colSpan={4} className="text-muted-foreground">No monitoring events returned.</TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </div>
      </ModuleCard>
    </div>
  )
}
