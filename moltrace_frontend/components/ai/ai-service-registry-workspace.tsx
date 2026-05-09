"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"

type Row = Record<string, unknown>

const SERVICE_KEYS = ["services", "items", "results", "rows", "data"]
const ARTIFACT_KEYS = ["model_artifacts", "items", "results", "rows", "data"]
const DEPLOYMENT_KEYS = ["deployment_candidates", "candidates", "items", "results", "rows", "data"]
const STATUS_OPTIONS = ["draft", "active", "disabled", "experimental"] as const
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
  if (!iso?.trim()) return "—"
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString()
}

function readBool(v: unknown): boolean | null {
  if (typeof v === "boolean") return v
  if (typeof v !== "string") return null
  const n = v.trim().toLowerCase()
  if (n === "true") return true
  if (n === "false") return false
  return null
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const data = err.data
    if (isRecord(data) && typeof data.detail === "string" && data.detail.trim()) {
      return data.detail
    }
    return `HTTP ${err.status}: ${err.message || fallback}`
  }
  if (err instanceof Error) return err.message
  return fallback
}

function isExplicitlyApprovedForServing(deploymentRows: Row[], artifactId: number): boolean {
  for (const row of deploymentRows) {
    const rowArtifactId = readRecordNumber(row, "model_artifact_id")
    if (rowArtifactId !== artifactId) continue
    const approval = (readRecordString(row, "approval_status") || "").toLowerCase()
    const status = (readRecordString(row, "status") || "").toLowerCase()
    if (approval.startsWith("approved") || status.startsWith("approved")) return true
  }
  return false
}

function artifactOptionLabel(row: Row): string {
  const id = readRecordNumber(row, "id")
  const name = readRecordString(row, "model_name") ?? "model"
  const version = readRecordString(row, "model_version") ?? ""
  if (id == null) return `${name} ${version}`.trim()
  return `#${id} ${name} ${version}`.trim()
}

export function AiServiceRegistryWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [services, setServices] = useState<Row[]>([])
  const [artifacts, setArtifacts] = useState<Row[]>([])
  const [deploymentCandidates, setDeploymentCandidates] = useState<Row[]>([])
  const [loadErr, setLoadErr] = useState("")

  const [selectedServiceId, setSelectedServiceId] = useState<number | null>(null)
  const [serviceDetail, setServiceDetail] = useState<Row | null>(null)
  const [detailErr, setDetailErr] = useState("")

  const [serviceKey, setServiceKey] = useState("")
  const [name, setName] = useState("")
  const [targetModule, setTargetModule] = useState<string>(TARGET_MODULE_OPTIONS[0])
  const [taskKey, setTaskKey] = useState("")
  const [activeModelArtifactId, setActiveModelArtifactId] = useState("")
  const [fallbackModelArtifactId, setFallbackModelArtifactId] = useState("")
  const [status, setStatus] = useState<string>(STATUS_OPTIONS[0])
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")
  const [submitBusy, setSubmitBusy] = useState(false)

  const loadAll = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const [serviceData, artifactData, deploymentData] = await Promise.all([
        apiFetch<unknown>("/ai/services", { method: "GET" }),
        apiFetch<unknown>("/ml/model-artifacts", { method: "GET" }),
        apiFetch<unknown>("/ml/deployment-candidates", { method: "GET" }),
      ])
      setServices(extractRows(serviceData, SERVICE_KEYS))
      setArtifacts(extractRows(artifactData, ARTIFACT_KEYS))
      setDeploymentCandidates(extractRows(deploymentData, DEPLOYMENT_KEYS))
    } catch (err) {
      setLoadErr(formatErr(err, "Could not load service registry data."))
      setServices([])
      setArtifacts([])
      setDeploymentCandidates([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadAll()
  }, [loadAll, reloadToken])

  useEffect(() => {
    if (selectedServiceId == null) {
      setServiceDetail(null)
      setDetailErr("")
      return
    }
    let cancelled = false
    setDetailErr("")
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/ai/services/${selectedServiceId}`, { method: "GET" })
        if (!cancelled && isRecord(raw)) {
          setServiceDetail(raw)
          setServiceKey(readRecordString(raw, "service_key") ?? "")
          setName(readRecordString(raw, "name") ?? "")
          setTargetModule(readRecordString(raw, "target_module") ?? TARGET_MODULE_OPTIONS[0])
          setTaskKey(readRecordString(raw, "task_key") ?? "")
          setActiveModelArtifactId(String(readRecordNumber(raw, "active_model_artifact_id") ?? ""))
          setFallbackModelArtifactId(String(readRecordNumber(raw, "fallback_model_artifact_id") ?? ""))
          setStatus(readRecordString(raw, "status") ?? STATUS_OPTIONS[0])
        }
      } catch (err) {
        if (!cancelled) {
          setServiceDetail(null)
          setDetailErr(formatErr(err, `Could not load /ai/services/${selectedServiceId}.`))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedServiceId])

  const activeArtifactIdNum = Number.parseInt(activeModelArtifactId, 10)
  const fallbackArtifactIdNum = Number.parseInt(fallbackModelArtifactId, 10)

  const activeModelApproved =
    Number.isFinite(activeArtifactIdNum) && activeArtifactIdNum > 0
      ? isExplicitlyApprovedForServing(deploymentCandidates, activeArtifactIdNum)
      : false

  const backendAllowsExperimental = useMemo(() => {
    if (!serviceDetail) return false
    return (
      readBool(serviceDetail["experimental_mode_allowed"]) === true ||
      readBool(serviceDetail["allow_experimental_mode"]) === true ||
      readBool(serviceDetail["experimental_allowed"]) === true
    )
  }, [serviceDetail])

  const blockingActiveStatus =
    status === "active" &&
    Number.isFinite(activeArtifactIdNum) &&
    activeArtifactIdNum > 0 &&
    !activeModelApproved &&
    !backendAllowsExperimental

  async function submitCreate() {
    setFormErr("")
    setFormOk("")
    if (!serviceKey.trim() || !name.trim() || !targetModule.trim() || !taskKey.trim()) {
      setFormErr("service_key, name, target_module, and task_key are required.")
      return
    }
    if (!Number.isFinite(activeArtifactIdNum) || activeArtifactIdNum < 1) {
      setFormErr("active_model_artifact_id is required.")
      return
    }
    if (blockingActiveStatus) {
      setFormErr("Selected active model is not approved; backend experimental mode allowance is required.")
      return
    }
    const body: Record<string, unknown> = {
      service_key: serviceKey.trim(),
      name: name.trim(),
      target_module: targetModule,
      task_key: taskKey.trim(),
      active_model_artifact_id: activeArtifactIdNum,
      fallback_model_artifact_id:
        Number.isFinite(fallbackArtifactIdNum) && fallbackArtifactIdNum > 0 ? fallbackArtifactIdNum : null,
      status,
    }
    setSubmitBusy(true)
    try {
      await apiFetch("/ai/services", { method: "POST", body })
      setFormOk("Service created.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setFormErr(formatErr(err, "Could not create service."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function submitUpdate() {
    setFormErr("")
    setFormOk("")
    if (selectedServiceId == null) {
      setFormErr("Select a service row to update.")
      return
    }
    if (!serviceKey.trim() || !name.trim() || !targetModule.trim() || !taskKey.trim()) {
      setFormErr("service_key, name, target_module, and task_key are required.")
      return
    }
    if (!Number.isFinite(activeArtifactIdNum) || activeArtifactIdNum < 1) {
      setFormErr("active_model_artifact_id is required.")
      return
    }
    if (blockingActiveStatus) {
      setFormErr("Selected active model is not approved; backend experimental mode allowance is required.")
      return
    }
    const body: Record<string, unknown> = {
      service_key: serviceKey.trim(),
      name: name.trim(),
      target_module: targetModule,
      task_key: taskKey.trim(),
      active_model_artifact_id: activeArtifactIdNum,
      fallback_model_artifact_id:
        Number.isFinite(fallbackArtifactIdNum) && fallbackArtifactIdNum > 0 ? fallbackArtifactIdNum : null,
      status,
    }
    setSubmitBusy(true)
    try {
      await apiFetch(`/ai/services/${selectedServiceId}`, { method: "PATCH", body })
      setFormOk("Service updated.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setFormErr(formatErr(err, `Could not update /ai/services/${selectedServiceId}.`))
    } finally {
      setSubmitBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">AI Service Registry</h1>
          <InfoTooltip
            label="About AI Service Registry"
            content="AI services route product requests to approved model artifacts and preserve prediction provenance."
          />
        </div>
        <p className="text-sm text-muted-foreground">Create and update service routing definitions without auto-activating models.</p>
      </div>

      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertTitle>Review and approval safeguards</AlertTitle>
        <AlertDescription>
          Service status changes remain decision support. Backend approval signals and review controls determine serving eligibility.
        </AlertDescription>
      </Alert>

      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
          Refresh
        </Button>
        <Badge variant="outline">GET /ai/services</Badge>
      </div>

      {loadErr ? (
        <Alert variant="destructive">
          <AlertTitle>Load error</AlertTitle>
          <AlertDescription>{loadErr}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Service table</CardTitle>
          <CardDescription>All registered AI/ML services. Click a row to load full configuration and edit.</CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>service key</TableHead>
                <TableHead>name</TableHead>
                <TableHead>target module</TableHead>
                <TableHead>task key</TableHead>
                <TableHead>active model artifact</TableHead>
                <TableHead>fallback model artifact</TableHead>
                <TableHead>status</TableHead>
                <TableHead>updated date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.map((row, idx) => {
                const id = readRecordNumber(row, "service_id") ?? readRecordNumber(row, "id")
                const active = id != null && id === selectedServiceId
                return (
                  <TableRow key={`${id ?? "row"}-${idx}`} data-state={active ? "selected" : undefined} onClick={() => setSelectedServiceId(id ?? null)} className="cursor-pointer">
                    <TableCell>{readRecordString(row, "service_key") ?? "—"}</TableCell>
                    <TableCell>{readRecordString(row, "name") ?? "—"}</TableCell>
                    <TableCell>{readRecordString(row, "target_module") ?? "—"}</TableCell>
                    <TableCell>{readRecordString(row, "task_key") ?? "—"}</TableCell>
                    <TableCell>{readRecordString(row, "active_model_artifact_id") ?? "—"}</TableCell>
                    <TableCell>{readRecordString(row, "fallback_model_artifact_id") ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "created_at"))}
                    </TableCell>
                  </TableRow>
                )
              })}
              {services.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-muted-foreground">
                    No services returned.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Create / update service</CardTitle>
          <CardDescription>
            Register a new AI/ML service or update its active and fallback model artifacts, target module, and lifecycle status.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {detailErr ? (
            <Alert variant="destructive">
              <AlertTitle>Service detail error</AlertTitle>
              <AlertDescription>{detailErr}</AlertDescription>
            </Alert>
          ) : null}

          {!activeModelApproved && Number.isFinite(activeArtifactIdNum) && activeArtifactIdNum > 0 ? (
            <Alert className="border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertTitle>Selected model is not approved</AlertTitle>
              <AlertDescription>
                The selected active model artifact does not have an explicit approved deployment signal. Activation is blocked unless backend explicitly allows experimental mode.
              </AlertDescription>
            </Alert>
          ) : null}

          {blockingActiveStatus ? (
            <Alert variant="destructive">
              <AlertTitle>Active status blocked</AlertTitle>
              <AlertDescription>
                The selected model is not approved. Activate an approved artifact, or have an administrator enable experimental mode before setting this service to active.
              </AlertDescription>
            </Alert>
          ) : null}

          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-emerald-700">{formOk}</p> : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="service-key">service key</Label>
              <Input id="service-key" value={serviceKey} onChange={(e) => setServiceKey(e.target.value)} placeholder="service_key" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="service-name">name</Label>
              <Input id="service-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Service name" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="target-module">target module</Label>
              <Select value={targetModule} onValueChange={setTargetModule}>
                <SelectTrigger id="target-module">
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
              <Label htmlFor="task-key">task key</Label>
              <Input id="task-key" value={taskKey} onChange={(e) => setTaskKey(e.target.value)} placeholder="task_key" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="active-model-artifact">active model artifact</Label>
              <Select value={activeModelArtifactId || "none"} onValueChange={(v) => setActiveModelArtifactId(v === "none" ? "" : v)}>
                <SelectTrigger id="active-model-artifact">
                  <SelectValue placeholder="Select active model artifact" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Select model artifact</SelectItem>
                  {artifacts.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={`active-${id}-${idx}`} value={String(id)}>
                        {artifactOptionLabel(row)}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="fallback-model-artifact">fallback model artifact</Label>
              <Select value={fallbackModelArtifactId || "none"} onValueChange={(v) => setFallbackModelArtifactId(v === "none" ? "" : v)}>
                <SelectTrigger id="fallback-model-artifact">
                  <SelectValue placeholder="Select fallback model artifact" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No fallback</SelectItem>
                  {artifacts.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={`fallback-${id}-${idx}`} value={String(id)}>
                        {artifactOptionLabel(row)}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="service-status">status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="service-status">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void submitCreate()} disabled={submitBusy || blockingActiveStatus}>
              {submitBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              Create service
            </Button>
            <Button type="button" variant="outline" onClick={() => void submitUpdate()} disabled={submitBusy || selectedServiceId == null || blockingActiveStatus}>
              {submitBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
              Update selected service
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
