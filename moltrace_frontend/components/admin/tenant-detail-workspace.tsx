"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ArrowLeft, BarChart3, FileText, Hash } from "lucide-react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { GsdReadinessVerdictCard } from "@/components/spectracheck/gsd-telemetry-panel"
import {
  trackDataBoundaryCreated,
  trackEntitlementUpdated,
  trackOnboardingProjectCreated,
  trackOnboardingTaskCompleted,
  trackPilotProgramCreated,
  trackProcurementPackageCreated,
  trackSecurityProfileUpdated,
  trackTenantAuditExportRequested,
  trackValidationProfileUpdated,
} from "@/src/lib/analytics/analytics-client"

type Row = Record<string, unknown>

type SectionKey =
  | "tenant"
  | "environments"
  | "entitlements"
  | "pilotPrograms"
  | "onboarding"
  | "dataBoundary"
  | "securityProfile"
  | "validationProfile"
  | "usageSummary"
  | "roi"
  | "healthScore"
  | "procurementPackages"

type SectionState = {
  payload: unknown
  error: string
}

const EMPTY_SECTION: SectionState = { payload: null, error: "" }

const PROGRAM_ORDER = ["SpectraCheck", "Regentry", "Reaction Optimization"] as const
const ENTITLEMENT_PROGRAM_ORDER = [
  { label: "SpectraCheck", values: ["spectracheck"] },
  { label: "Regentry", values: ["regulatory_hub"] },
  { label: "Reaction Optimization", values: ["reaction_optimization"] },
  { label: "Validation Center", values: ["validation_center"] },
  { label: "Connectors", values: ["connectors"] },
  { label: "ML / AI", values: ["ml_ai"] },
  { label: "Mobile", values: ["mobile"] },
  { label: "Admin / Cross-module", values: ["admin", "cross_module"] },
] as const
const ENTITLEMENT_PROGRAM_OPTIONS = [
  "spectracheck",
  "regulatory_hub",
  "reaction_optimization",
  "validation_center",
  "connectors",
  "ml_ai",
  "mobile",
  "admin",
  "cross_module",
] as const

const DEFAULT_PROGRAM_KEYS = ["spectracheck", "regulatory_hub", "reaction_optimization"] as const
const PILOT_STATUS_OPTIONS = ["planned", "active", "completed", "paused", "failed", "archived"] as const
const ONBOARDING_STAGE_OPTIONS = [
  "discovery",
  "security_review",
  "data_setup",
  "spectracheck_rollout",
  "regulatory_rollout",
  "reaction_rollout",
  "validation",
  "go_live",
  "renewal_review",
] as const
const ONBOARDING_STATUS_OPTIONS = [
  "not_started",
  "in_progress",
  "blocked",
  "ready_for_go_live",
  "completed",
  "archived",
] as const
const TASK_BOARD_COLUMNS = [
  { label: "open", value: "open" },
  { label: "in progress", value: "in_progress" },
  { label: "blocked", value: "blocked" },
  { label: "completed", value: "completed" },
] as const
const IMPLEMENTATION_TASK_TYPE_OPTIONS = [
  "security",
  "data_ingestion",
  "connector_setup",
  "spectracheck_configuration",
  "regulatory_configuration",
  "reaction_configuration",
  "validation",
  "training",
  "mobile_setup",
  "roi",
  "procurement",
  "other",
] as const
const IMPLEMENTATION_TASK_PROGRAM_OPTIONS = [
  "spectracheck",
  "regulatory_hub",
  "reaction_optimization",
  "cross_module",
  "system",
] as const
const DEFAULT_TASK_DISPLAY_ORDER = [
  "SpectraCheck setup",
  "Regentry setup",
  "Reaction Optimization setup",
] as const
const DATA_BOUNDARY_ISOLATION_OPTIONS = [
  "shared_database_tenant_scoped",
  "dedicated_schema",
  "dedicated_database",
  "dedicated_deployment",
] as const
const TENANT_PROFILE_STATUS_OPTIONS = ["draft", "active", "requires_review"] as const
const TENANT_VALIDATION_PROFILE_STATUS_OPTIONS = [
  "draft",
  "in_progress",
  "ready_for_review",
  "approved_internal",
  "not_required",
] as const
const PROCUREMENT_PACKAGE_TYPE_OPTIONS = [
  "security_review",
  "validation_readiness",
  "ai_governance",
  "data_integrity",
  "roi",
  "full_procurement",
] as const
const AUDIT_EXPORT_SCOPE_OPTIONS = [
  "all",
  "security",
  "validation",
  "regulatory",
  "spectracheck",
  "reaction",
  "ai_ml",
  "connectors",
] as const

const SENSITIVE_KEY_PATTERN =
  /(secret|password|token|credential|authorization|api[_-]?key|raw|spectrum|spectra|full_smiles|smiles|molfile|source_text|source_document|document_text|content|blob|binary|model_artifact|private_key)/i

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function asRows(payload: unknown, keys: string[] = []): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  for (const key of [...keys, "items", "results", "rows", "data"]) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }
  return []
}

function unwrapRecord(payload: unknown, keys: string[] = []): Row | null {
  if (!isRecord(payload)) return null
  for (const key of [...keys, "item", "record", "data"]) {
    const value = payload[key]
    if (isRecord(value)) return value
  }
  return payload
}

function readFirst(row: Row | null | undefined, keys: string[]): string {
  if (!row) return ""
  for (const key of keys) {
    const value = readStr(row[key])
    if (value) return value
  }
  return ""
}

function formatErr(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (isRecord(error.data) && typeof error.data.detail === "string") return error.data.detail
    if (isRecord(error.data) && typeof error.data.message === "string") return error.data.message
    return error.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

function parseJsonField(raw: string, label: string): unknown {
  const text = raw.trim()
  if (!text) return {}
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`${label} must be valid JSON.`)
  }
}

function parseJsonArrayField(raw: string, label: string): unknown[] {
  const value = parseJsonField(raw, label)
  if (Array.isArray(value)) return value
  throw new Error(`${label} must be a JSON array.`)
}

function parseJsonObjectField(raw: string, label: string): Row {
  const value = parseJsonField(raw, label)
  if (isRecord(value)) return value
  throw new Error(`${label} must be a JSON object.`)
}

function parseIdArrayField(raw: string, label: string): number[] {
  return parseJsonArrayField(raw, label).map((item) => {
    const numeric = typeof item === "number" ? item : Number(item)
    if (!Number.isInteger(numeric) || numeric < 1) {
      throw new Error(`${label} must contain positive numeric IDs.`)
    }
    return numeric
  })
}

function redactDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redactDeep)
  if (!isRecord(value)) return value
  const out: Row = {}
  for (const [key, item] of Object.entries(value)) {
    out[key] = SENSITIVE_KEY_PATTERN.test(key) ? "[redacted]" : redactDeep(item)
  }
  return out
}

function safeFormatValue(key: string, value: unknown, maxLength = 220): string {
  if (SENSITIVE_KEY_PATTERN.test(key)) return "[redacted]"
  if (value == null || value === "") return "-"
  if (typeof value === "string") return value.trim() || "-"
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  const text = JSON.stringify(redactDeep(value))
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

function statusBadgeClass(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized.includes("risk") || normalized.includes("error") || normalized.includes("failed")) {
    return "border-destructive/40 text-destructive"
  }
  if (normalized.includes("review") || normalized.includes("warning") || normalized.includes("blocked")) {
    return "border-warning/50 text-warning"
  }
  return "text-muted-foreground"
}

function Field({ label, value, valueKey }: { label: string; value: unknown; valueKey?: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm">{safeFormatValue(valueKey ?? label, value)}</p>
    </div>
  )
}

function StatCard({ title, value }: { title: string; value: string | number }) {
  return (
    <ModuleCard accent="slate" eyebrow="Stat" title={title} icon={Hash}>
      <div className="text-2xl font-semibold">{value}</div>
    </ModuleCard>
  )
}

function GenericTable({
  rows,
  columns,
  empty,
}: {
  rows: Row[]
  columns: { key: string; label: string; keys?: string[] }[]
  empty: string
}) {
  return (
    <div className="overflow-x-auto rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.key} className="text-xs">
                {column.label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={columns.length} className="text-xs text-muted-foreground">
                {empty}
              </TableCell>
            </TableRow>
          ) : (
            rows.map((row, index) => (
              <TableRow key={readFirst(row, ["id", "tenant_id", "feature_key", "title"]) || `row-${index}`}>
                {columns.map((column) => {
                  const value =
                    readFirst(row, column.keys ?? [column.key]) || safeFormatValue(column.key, row[column.key])
                  const statusLike = column.key.includes("status") || column.label.toLowerCase().includes("status")
                  return (
                    <TableCell key={column.key} className="max-w-[24rem] text-xs">
                      {statusLike && value !== "-" ? (
                        <Badge variant="outline" className={`font-normal ${statusBadgeClass(value)}`}>
                          {value}
                        </Badge>
                      ) : (
                        value
                      )}
                    </TableCell>
                  )
                })}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}

function SectionCard({
  title,
  description,
  error,
  children,
}: {
  title: string
  description?: string
  error?: string
  children: React.ReactNode
}) {
  return (
    <ModuleCard
      accent="slate"
      eyebrow="Section"
      title={title}
      icon={FileText}
      description={description}
    >
      <div className="space-y-3">
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        {children}
      </div>
    </ModuleCard>
  )
}

function RecordFields({
  row,
  fields,
  empty,
}: {
  row: Row | null
  fields: { label: string; key: string; keys?: string[] }[]
  empty: string
}) {
  if (!row) return <p className="text-sm text-muted-foreground">{empty}</p>
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {fields.map((field) => (
        <Field
          key={field.key}
          label={field.label}
          value={readFirst(row, field.keys ?? [field.key]) || row[field.key]}
          valueKey={field.key}
        />
      ))}
    </div>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[36rem] overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[10px] leading-relaxed">
      {JSON.stringify(redactDeep(value), null, 2)}
    </pre>
  )
}

function programSortIndex(program: string): number {
  const normalized = program.trim().toLowerCase()
  const index = ENTITLEMENT_PROGRAM_ORDER.findIndex((item) => (item.values as readonly string[]).includes(normalized))
  return index === -1 ? ENTITLEMENT_PROGRAM_ORDER.length : index
}

function EntitlementsPanel({
  tenantId,
  rows,
  error,
  onReload,
}: {
  tenantId: string
  rows: Row[]
  error: string
  onReload: () => Promise<void>
}) {
  const [featureKey, setFeatureKey] = useState("")
  const [program, setProgram] = useState<(typeof ENTITLEMENT_PROGRAM_OPTIONS)[number]>("spectracheck")
  const [enabled, setEnabled] = useState("true")
  const [limitsJson, setLimitsJson] = useState("{}")
  const [effectiveStart, setEffectiveStart] = useState("")
  const [effectiveEnd, setEffectiveEnd] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [actionBusyId, setActionBusyId] = useState("")
  const [formError, setFormError] = useState("")

  const sortedRows = useMemo(
    () =>
      [...rows].sort((a, b) => {
        const byProgram =
          programSortIndex(readFirst(a, ["program"])) - programSortIndex(readFirst(b, ["program"]))
        if (byProgram !== 0) return byProgram
        return readFirst(a, ["feature_key"]).localeCompare(readFirst(b, ["feature_key"]))
      }),
    [rows],
  )

  async function createEntitlement() {
    const id = tenantId.trim()
    if (!id) return
    setCreateBusy(true)
    setFormError("")
    try {
      await apiFetch(`/tenants/${encodeURIComponent(id)}/entitlements`, {
        method: "POST",
        body: {
          feature_key: featureKey.trim(),
          program,
          enabled: enabled === "true",
          limit_json: parseJsonField(limitsJson, "limits JSON"),
          effective_start: effectiveStart.trim() || null,
          effective_end: effectiveEnd.trim() || null,
        },
      })
      trackEntitlementUpdated({
        feature_key: featureKey.trim(),
        program,
        status: enabled === "true" ? "enabled" : "disabled",
      })
      setFeatureKey("")
      setProgram("spectracheck")
      setEnabled("true")
      setLimitsJson("{}")
      setEffectiveStart("")
      setEffectiveEnd("")
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not create entitlement."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function patchEntitlement(row: Row, nextEnabled: boolean) {
    const entitlementId = readFirst(row, ["id", "entitlement_id"])
    if (!entitlementId) return
    setActionBusyId(entitlementId)
    setFormError("")
    try {
      await apiFetch(`/tenant-entitlements/${encodeURIComponent(entitlementId)}`, {
        method: "PATCH",
        body: { enabled: nextEnabled },
      })
      trackEntitlementUpdated({
        feature_key: readFirst(row, ["feature_key"]),
        program: readFirst(row, ["program"]),
        status: nextEnabled ? "enabled" : "disabled",
      })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not update entitlement."))
    } finally {
      setActionBusyId("")
    }
  }

  return (
    <div className="space-y-6">
      <Alert className="border-warning/40 bg-warning/10">
        <AlertDescription className="text-xs text-warning">
          Entitlements enable or disable features; they do not change MolTrace’s core product sequence.
        </AlertDescription>
      </Alert>

      <SectionCard
        title="Entitlements"
        description="Module feature entitlements for this tenant — enabled/disabled state, program, and effective date range for each feature key."
        error={error || formError}
      >
        <div className="space-y-2 text-sm">
          {ENTITLEMENT_PROGRAM_ORDER.map((item, index) => (
            <div key={item.label} className="rounded-md border bg-muted/20 px-3 py-2">
              {index + 1}. {item.label}
            </div>
          ))}
        </div>
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">feature key</TableHead>
                <TableHead className="text-xs">program</TableHead>
                <TableHead className="text-xs">enabled</TableHead>
                <TableHead className="text-xs">limits JSON</TableHead>
                <TableHead className="text-xs">effective start</TableHead>
                <TableHead className="text-xs">effective end</TableHead>
                <TableHead className="text-xs">action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-xs text-muted-foreground">
                    No entitlements returned.
                  </TableCell>
                </TableRow>
              ) : (
                sortedRows.map((row, index) => {
                  const entitlementId = readFirst(row, ["id", "entitlement_id"]) || `entitlement-${index}`
                  const enabledValue = readFirst(row, ["enabled"]).toLowerCase() === "true"
                  return (
                    <TableRow key={entitlementId}>
                      <TableCell className="text-xs">{readFirst(row, ["feature_key"]) || "-"}</TableCell>
                      <TableCell className="text-xs">{readFirst(row, ["program"]) || "-"}</TableCell>
                      <TableCell className="text-xs">{safeFormatValue("enabled", row.enabled)}</TableCell>
                      <TableCell className="max-w-[24rem] text-xs">{safeFormatValue("limit_json", row.limit_json)}</TableCell>
                      <TableCell className="text-xs">{readFirst(row, ["effective_start"]) || "-"}</TableCell>
                      <TableCell className="text-xs">{readFirst(row, ["effective_end"]) || "-"}</TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={actionBusyId === entitlementId}
                          onClick={() => void patchEntitlement(row, !enabledValue)}
                        >
                          {enabledValue ? "Disable" : "Enable"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </div>
      </SectionCard>

      <SectionCard
        title="Create entitlement"
        description="Grant a new entitlement to this tenant — specify feature key, program, enabled state, and effective date range."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-entitlement-feature-key">feature key</Label>
            <Input
              id="tenant-entitlement-feature-key"
              value={featureKey}
              onChange={(event) => setFeatureKey(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-entitlement-program">program</Label>
            <Select value={program} onValueChange={(value) => setProgram(value as typeof program)}>
              <SelectTrigger id="tenant-entitlement-program">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ENTITLEMENT_PROGRAM_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-entitlement-enabled">enabled</Label>
            <Select value={enabled} onValueChange={setEnabled}>
              <SelectTrigger id="tenant-entitlement-enabled">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">true</SelectItem>
                <SelectItem value="false">false</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-entitlement-effective-start">effective start</Label>
            <Input
              id="tenant-entitlement-effective-start"
              value={effectiveStart}
              onChange={(event) => setEffectiveStart(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-entitlement-effective-end">effective end</Label>
            <Input
              id="tenant-entitlement-effective-end"
              value={effectiveEnd}
              onChange={(event) => setEffectiveEnd(event.target.value)}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-entitlement-limits-json">limits JSON</Label>
            <Textarea
              id="tenant-entitlement-limits-json"
              value={limitsJson}
              onChange={(event) => setLimitsJson(event.target.value)}
              rows={4}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={createBusy} onClick={() => void createEntitlement()}>
            {createBusy ? "Creating..." : "Create entitlement"}
          </Button>
          <Button type="button" variant="outline" disabled={createBusy} onClick={() => void onReload()}>
            Refresh entitlements
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function pilotProgramSortIndex(program: string): number {
  const normalized = program.trim().toLowerCase()
  const index = DEFAULT_PROGRAM_KEYS.findIndex((item) => item === normalized)
  return index === -1 ? DEFAULT_PROGRAM_KEYS.length : index
}

function defaultTaskSortIndex(row: Row): number {
  const title = readFirst(row, ["title"])
  const exact = DEFAULT_TASK_DISPLAY_ORDER.findIndex((item) => item === title)
  if (exact !== -1) return exact
  const program = readFirst(row, ["program"])
  return DEFAULT_TASK_DISPLAY_ORDER.length + pilotProgramSortIndex(program)
}

function PilotProgramsPanel({
  tenantId,
  rows,
  error,
  onReload,
}: {
  tenantId: string
  rows: Row[]
  error: string
  onReload: () => Promise<void>
}) {
  const [title, setTitle] = useState("")
  const [objective, setObjective] = useState("")
  const [status, setStatus] = useState<(typeof PILOT_STATUS_OPTIONS)[number]>("planned")
  const [startDate, setStartDate] = useState("")
  const [endDate, setEndDate] = useState("")
  const [targetPrograms, setTargetPrograms] = useState(JSON.stringify([...DEFAULT_PROGRAM_KEYS], null, 2))
  const [successCriteriaJson, setSuccessCriteriaJson] = useState("[]")
  const [risksJson, setRisksJson] = useState("[]")
  const [selectedPilot, setSelectedPilot] = useState<Row | null>(null)
  const [selectedPilotError, setSelectedPilotError] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [actionBusyId, setActionBusyId] = useState("")
  const [formError, setFormError] = useState("")

  async function createPilotProgram() {
    const id = tenantId.trim()
    if (!id) return
    setCreateBusy(true)
    setFormError("")
    try {
      await apiFetch(`/tenants/${encodeURIComponent(id)}/pilot-programs`, {
        method: "POST",
        body: {
          title: title.trim(),
          objective: objective.trim(),
          status,
          start_date: startDate.trim() || null,
          end_date: endDate.trim() || null,
          target_programs_json: parseJsonArrayField(targetPrograms, "target programs").map((item) => String(item)),
          success_criteria_json: parseJsonArrayField(successCriteriaJson, "success criteria JSON"),
          risks_json: parseJsonArrayField(risksJson, "risks JSON"),
        },
      })
      trackPilotProgramCreated({ status })
      setTitle("")
      setObjective("")
      setStatus("planned")
      setStartDate("")
      setEndDate("")
      setTargetPrograms(JSON.stringify([...DEFAULT_PROGRAM_KEYS], null, 2))
      setSuccessCriteriaJson("[]")
      setRisksJson("[]")
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not create pilot program."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function loadPilotDetail(row: Row) {
    const pilotId = readFirst(row, ["id", "pilot_id"])
    if (!pilotId) return
    setActionBusyId(pilotId)
    setSelectedPilotError("")
    try {
      const payload = await apiFetch<unknown>(`/pilot-programs/${encodeURIComponent(pilotId)}`, { method: "GET" })
      setSelectedPilot(unwrapRecord(payload, ["pilot_program", "pilot"]))
    } catch (err) {
      setSelectedPilot(null)
      setSelectedPilotError(formatErr(err, "Could not load pilot program detail."))
    } finally {
      setActionBusyId("")
    }
  }

  async function patchPilotStatus(row: Row, nextStatus: string) {
    const pilotId = readFirst(row, ["id", "pilot_id"])
    if (!pilotId) return
    setActionBusyId(pilotId)
    setFormError("")
    try {
      await apiFetch(`/pilot-programs/${encodeURIComponent(pilotId)}`, {
        method: "PATCH",
        body: { status: nextStatus },
      })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not update pilot program."))
    } finally {
      setActionBusyId("")
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Pilot Programs"
        description="Pilot programs active for this tenant — objectives, status, target modules, and start/end timeline."
        error={error || formError}
      >
        <GenericTable
          rows={rows}
          empty="No pilot programs returned."
          columns={[
            { key: "title", label: "title" },
            { key: "objective", label: "objective" },
            { key: "status", label: "status" },
            { key: "start_date", label: "start date" },
            { key: "end_date", label: "end date" },
            { key: "target_programs_json", label: "target programs" },
            { key: "updated_at", label: "updated date", keys: ["updated_at", "updated_date"] },
          ]}
        />
        {rows.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {rows.map((row, index) => {
              const pilotId = readFirst(row, ["id", "pilot_id"]) || `pilot-${index}`
              const currentStatus = readFirst(row, ["status"])
              return (
                <div key={pilotId} className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={actionBusyId === pilotId}
                    onClick={() => void loadPilotDetail(row)}
                  >
                    Load detail
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={actionBusyId === pilotId || currentStatus === "active"}
                    onClick={() => void patchPilotStatus(row, "active")}
                  >
                    active
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={actionBusyId === pilotId || currentStatus === "paused"}
                    onClick={() => void patchPilotStatus(row, "paused")}
                  >
                    paused
                  </Button>
                </div>
              )
            })}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Pilot program detail" description="Detail view of the selected pilot program — objectives, success criteria, risks, and current status." error={selectedPilotError}>
        <RecordFields
          row={selectedPilot}
          empty="Select Load detail from a pilot program row."
          fields={[
            { label: "title", key: "title" },
            { label: "objective", key: "objective" },
            { label: "status", key: "status" },
            { label: "start date", key: "start_date" },
            { label: "end date", key: "end_date" },
            { label: "target programs", key: "target_programs_json" },
            { label: "success criteria JSON", key: "success_criteria_json" },
            { label: "risks JSON", key: "risks_json" },
          ]}
        />
      </SectionCard>

      <SectionCard title="Create pilot program" description="Create a new pilot program for this tenant — title, objective, start/end dates, and target modules.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-pilot-title">title</Label>
            <Input id="tenant-pilot-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-pilot-status">status</Label>
            <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
              <SelectTrigger id="tenant-pilot-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PILOT_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-pilot-start-date">start date</Label>
            <Input id="tenant-pilot-start-date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-pilot-end-date">end date</Label>
            <Input id="tenant-pilot-end-date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-pilot-objective">objective</Label>
            <Textarea id="tenant-pilot-objective" value={objective} onChange={(event) => setObjective(event.target.value)} rows={3} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-pilot-target-programs">target programs</Label>
            <Textarea id="tenant-pilot-target-programs" value={targetPrograms} onChange={(event) => setTargetPrograms(event.target.value)} rows={4} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-pilot-success-criteria-json">success criteria JSON</Label>
            <Textarea id="tenant-pilot-success-criteria-json" value={successCriteriaJson} onChange={(event) => setSuccessCriteriaJson(event.target.value)} rows={4} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-pilot-risks-json">risks JSON</Label>
            <Textarea id="tenant-pilot-risks-json" value={risksJson} onChange={(event) => setRisksJson(event.target.value)} rows={4} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={createBusy} onClick={() => void createPilotProgram()}>
            {createBusy ? "Creating..." : "Create pilot program"}
          </Button>
          <Button type="button" variant="outline" disabled={createBusy} onClick={() => void onReload()}>
            Refresh pilot programs
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function OnboardingPanel({
  tenantId,
  rows,
  error,
  onReload,
}: {
  tenantId: string
  rows: Row[]
  error: string
  onReload: () => Promise<void>
}) {
  const [title, setTitle] = useState("")
  const [ownerName, setOwnerName] = useState("")
  const [customerContact, setCustomerContact] = useState("")
  const [implementationStage, setImplementationStage] =
    useState<(typeof ONBOARDING_STAGE_OPTIONS)[number]>("discovery")
  const [selectedProjectId, setSelectedProjectId] = useState("")
  const [selectedProjectDetail, setSelectedProjectDetail] = useState<Row | null>(null)
  const [tasks, setTasks] = useState<Row[]>([])
  const [tasksError, setTasksError] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [actionBusyId, setActionBusyId] = useState("")
  const [formError, setFormError] = useState("")

  const [taskTitle, setTaskTitle] = useState("")
  const [taskDescription, setTaskDescription] = useState("")
  const [taskType, setTaskType] =
    useState<(typeof IMPLEMENTATION_TASK_TYPE_OPTIONS)[number]>("spectracheck_configuration")
  const [taskProgram, setTaskProgram] =
    useState<(typeof IMPLEMENTATION_TASK_PROGRAM_OPTIONS)[number]>("spectracheck")
  const [taskStatus, setTaskStatus] = useState("open")
  const [taskOwner, setTaskOwner] = useState("")
  const [taskDueDate, setTaskDueDate] = useState("")
  const [taskBusy, setTaskBusy] = useState(false)

  useEffect(() => {
    const ids = rows.map((row) => readFirst(row, ["id", "project_id", "onboarding_project_id"])).filter(Boolean)
    if (ids.length === 0) {
      setSelectedProjectId("")
      setSelectedProjectDetail(null)
      setTasks([])
      return
    }
    if (!selectedProjectId || !ids.includes(selectedProjectId)) setSelectedProjectId(ids[0]!)
  }, [rows, selectedProjectId])

  const loadProjectDetail = useCallback(async (projectId: string) => {
    const id = projectId.trim()
    if (!id) {
      setSelectedProjectDetail(null)
      return
    }
    setActionBusyId(id)
    setTasksError("")
    try {
      const payload = await apiFetch<unknown>(`/onboarding-projects/${encodeURIComponent(id)}`, { method: "GET" })
      setSelectedProjectDetail(unwrapRecord(payload, ["onboarding_project", "project"]))
    } catch (err) {
      setSelectedProjectDetail(null)
      setTasksError(formatErr(err, "Could not load onboarding project detail."))
    } finally {
      setActionBusyId("")
    }
  }, [])

  const loadTasks = useCallback(async (projectId: string) => {
    const id = projectId.trim()
    if (!id) {
      setTasks([])
      return
    }
    setTasksError("")
    try {
      const payload = await apiFetch<unknown>(`/onboarding-projects/${encodeURIComponent(id)}/tasks`, { method: "GET" })
      setTasks(asRows(payload, ["tasks", "implementation_tasks"]))
    } catch (err) {
      setTasks([])
      setTasksError(formatErr(err, "Could not load implementation tasks."))
    }
  }, [])

  useEffect(() => {
    void loadProjectDetail(selectedProjectId)
    void loadTasks(selectedProjectId)
  }, [selectedProjectId, loadProjectDetail, loadTasks])

  const orderedTasks = useMemo(
    () =>
      [...tasks].sort((a, b) => {
        const byDefault = defaultTaskSortIndex(a) - defaultTaskSortIndex(b)
        if (byDefault !== 0) return byDefault
        return readFirst(a, ["title"]).localeCompare(readFirst(b, ["title"]))
      }),
    [tasks],
  )

  async function createOnboardingProject() {
    const id = tenantId.trim()
    if (!id) return
    setCreateBusy(true)
    setFormError("")
    try {
      await apiFetch(`/tenants/${encodeURIComponent(id)}/onboarding-projects`, {
        method: "POST",
        body: {
          title: title.trim(),
          status: "not_started",
          owner_name: ownerName.trim() || null,
          customer_contact: customerContact.trim() || null,
          implementation_stage: implementationStage,
        },
      })
      trackOnboardingProjectCreated({ implementation_stage: implementationStage, status: "not_started" })
      setTitle("")
      setOwnerName("")
      setCustomerContact("")
      setImplementationStage("discovery")
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not create onboarding project."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function patchOnboardingProject(projectId: string, body: Row) {
    if (!projectId) return
    setActionBusyId(projectId)
    setFormError("")
    try {
      await apiFetch(`/onboarding-projects/${encodeURIComponent(projectId)}`, {
        method: "PATCH",
        body,
      })
      await onReload()
      await loadProjectDetail(projectId)
    } catch (err) {
      setFormError(formatErr(err, "Could not update onboarding project."))
    } finally {
      setActionBusyId("")
    }
  }

  async function createImplementationTask() {
    const projectId = selectedProjectId.trim()
    if (!projectId) return
    setTaskBusy(true)
    setTasksError("")
    try {
      await apiFetch(`/onboarding-projects/${encodeURIComponent(projectId)}/tasks`, {
        method: "POST",
        body: {
          title: taskTitle.trim(),
          description: taskDescription.trim() || null,
          task_type: taskType,
          program: taskProgram,
          status: taskStatus,
          owner: taskOwner.trim() || null,
          due_date: taskDueDate.trim() || null,
        },
      })
      if (taskStatus === "completed") {
        trackOnboardingTaskCompleted({
          task_type: taskType,
          program: taskProgram,
          status: taskStatus,
        })
      }
      setTaskTitle("")
      setTaskDescription("")
      setTaskType("spectracheck_configuration")
      setTaskProgram("spectracheck")
      setTaskStatus("open")
      setTaskOwner("")
      setTaskDueDate("")
      await loadTasks(projectId)
    } catch (err) {
      setTasksError(formatErr(err, "Could not create implementation task."))
    } finally {
      setTaskBusy(false)
    }
  }

  async function patchImplementationTask(row: Row, nextStatus: string) {
    const taskId = readFirst(row, ["id", "task_id"])
    if (!taskId) return
    setActionBusyId(taskId)
    setTasksError("")
    try {
      await apiFetch(`/implementation-tasks/${encodeURIComponent(taskId)}`, {
        method: "PATCH",
        body: { status: nextStatus },
      })
      if (nextStatus === "completed") {
        trackOnboardingTaskCompleted({
          task_type: readFirst(row, ["task_type"]),
          program: readFirst(row, ["program"]),
          status: nextStatus,
        })
      }
      await loadTasks(selectedProjectId)
    } catch (err) {
      setTasksError(formatErr(err, "Could not update implementation task."))
    } finally {
      setActionBusyId("")
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Onboarding"
        description="Onboarding projects for this tenant — implementation stage, owner, status, and customer contact."
        error={error || formError}
      >
        <GenericTable
          rows={rows}
          empty="No onboarding projects returned."
          columns={[
            { key: "title", label: "title" },
            { key: "status", label: "status" },
            { key: "owner_name", label: "owner" },
            { key: "customer_contact", label: "customer contact" },
            { key: "implementation_stage", label: "implementation stage" },
            { key: "updated_at", label: "updated date", keys: ["updated_at", "updated_date"] },
          ]}
        />
        {rows.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {rows.map((row, index) => {
              const projectId = readFirst(row, ["id", "project_id", "onboarding_project_id"]) || `project-${index}`
              return (
                <Button
                  key={projectId}
                  type="button"
                  size="sm"
                  variant={selectedProjectId === projectId ? "secondary" : "outline"}
                  disabled={actionBusyId === projectId}
                  onClick={() => setSelectedProjectId(projectId)}
                >
                  {readFirst(row, ["title"]) || projectId}
                </Button>
              )
            })}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Create onboarding project" description="Create a new onboarding project — specify title, owner, customer contact, and implementation stage.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-onboarding-title">title</Label>
            <Input id="tenant-onboarding-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-onboarding-owner-name">owner name</Label>
            <Input id="tenant-onboarding-owner-name" value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-onboarding-customer-contact">customer contact</Label>
            <Input id="tenant-onboarding-customer-contact" value={customerContact} onChange={(event) => setCustomerContact(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-onboarding-implementation-stage">implementation stage</Label>
            <Select value={implementationStage} onValueChange={(value) => setImplementationStage(value as typeof implementationStage)}>
              <SelectTrigger id="tenant-onboarding-implementation-stage">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ONBOARDING_STAGE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={createBusy} onClick={() => void createOnboardingProject()}>
            {createBusy ? "Creating..." : "Create onboarding project"}
          </Button>
          <Button type="button" variant="outline" disabled={createBusy} onClick={() => void onReload()}>
            Refresh onboarding
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Selected onboarding project" description="Detail and status management for the selected onboarding project." error={tasksError}>
        <RecordFields
          row={selectedProjectDetail}
          empty="Select an onboarding project."
          fields={[
            { label: "title", key: "title" },
            { label: "status", key: "status" },
            { label: "owner name", key: "owner_name" },
            { label: "customer contact", key: "customer_contact" },
            { label: "implementation stage", key: "implementation_stage" },
          ]}
        />
        {selectedProjectId ? (
          <div className="flex flex-wrap gap-2">
            {ONBOARDING_STATUS_OPTIONS.map((option) => (
              <Button
                key={option}
                type="button"
                size="sm"
                variant="outline"
                disabled={actionBusyId === selectedProjectId}
                onClick={() => void patchOnboardingProject(selectedProjectId, { status: option })}
              >
                {option}
              </Button>
            ))}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard title="Default task display order">
        <div className="space-y-2 text-sm">
          {DEFAULT_TASK_DISPLAY_ORDER.map((item, index) => (
            <div key={item} className="rounded-md border bg-muted/20 px-3 py-2">
              {index + 1}. {item}
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Task board" description="Implementation task board for the selected onboarding project — move tasks across planned, in-progress, and complete columns.">
        <div className="grid gap-4 lg:grid-cols-4">
          {TASK_BOARD_COLUMNS.map((column) => {
            const columnTasks = orderedTasks.filter((task) => readFirst(task, ["status"]) === column.value)
            return (
              <div key={column.value} className="space-y-3 rounded-md border bg-muted/20 p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-medium">{column.label}</h3>
                  <Badge variant="outline">{columnTasks.length}</Badge>
                </div>
                {columnTasks.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No tasks.</p>
                ) : (
                  columnTasks.map((task, index) => {
                    const taskId = readFirst(task, ["id", "task_id"]) || `task-${index}`
                    return (
                      <div key={taskId} className="space-y-2 rounded-md border bg-background p-3">
                        <p className="text-sm font-medium">{readFirst(task, ["title"]) || "-"}</p>
                        <p className="text-xs text-muted-foreground">{readFirst(task, ["program"]) || "-"}</p>
                        <p className="text-xs text-muted-foreground">{readFirst(task, ["owner"]) || "Unassigned"}</p>
                        <div className="flex flex-wrap gap-1">
                          {TASK_BOARD_COLUMNS.map((nextColumn) => (
                            <Button
                              key={nextColumn.value}
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={actionBusyId === taskId || nextColumn.value === column.value}
                              onClick={() => void patchImplementationTask(task, nextColumn.value)}
                            >
                              {nextColumn.label}
                            </Button>
                          ))}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )
          })}
        </div>
      </SectionCard>

      <SectionCard title="Create implementation task" description="Add an implementation task to the selected onboarding project — specify title, owner, type, and initial status.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-task-title">title</Label>
            <Input id="tenant-task-title" value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-task-owner">owner</Label>
            <Input id="tenant-task-owner" value={taskOwner} onChange={(event) => setTaskOwner(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-task-type">task type</Label>
            <Select value={taskType} onValueChange={(value) => setTaskType(value as typeof taskType)}>
              <SelectTrigger id="tenant-task-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {IMPLEMENTATION_TASK_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-task-program">program</Label>
            <Select value={taskProgram} onValueChange={(value) => setTaskProgram(value as typeof taskProgram)}>
              <SelectTrigger id="tenant-task-program">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {IMPLEMENTATION_TASK_PROGRAM_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-task-status">status</Label>
            <Select value={taskStatus} onValueChange={setTaskStatus}>
              <SelectTrigger id="tenant-task-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TASK_BOARD_COLUMNS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-task-due-date">due date</Label>
            <Input id="tenant-task-due-date" value={taskDueDate} onChange={(event) => setTaskDueDate(event.target.value)} />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-task-description">description</Label>
            <Textarea id="tenant-task-description" value={taskDescription} onChange={(event) => setTaskDescription(event.target.value)} rows={3} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={taskBusy || !selectedProjectId} onClick={() => void createImplementationTask()}>
            {taskBusy ? "Creating..." : "Create implementation task"}
          </Button>
          <Button type="button" variant="outline" disabled={!selectedProjectId} onClick={() => void loadTasks(selectedProjectId)}>
            Refresh tasks
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function NoSecretsWarning() {
  return (
    <Alert className="border-warning/40 bg-warning/10">
      <AlertDescription className="text-xs text-warning">
        Do not enter raw secrets here. Store credentials only through approved secret-reference workflows.
      </AlertDescription>
    </Alert>
  )
}

function DataBoundaryPanel({
  tenantId,
  row,
  error,
  onReload,
}: {
  tenantId: string
  row: Row | null
  error: string
  onReload: () => Promise<void>
}) {
  const [isolationMode, setIsolationMode] =
    useState<(typeof DATA_BOUNDARY_ISOLATION_OPTIONS)[number]>("shared_database_tenant_scoped")
  const [encryptionProfile, setEncryptionProfile] = useState("")
  const [storagePrefix, setStoragePrefix] = useState("")
  const [allowedRegionsJson, setAllowedRegionsJson] = useState("[]")
  const [dataResidencyNotes, setDataResidencyNotes] = useState("")
  const [status, setStatus] = useState<(typeof TENANT_PROFILE_STATUS_OPTIONS)[number]>("draft")
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState("")

  const boundaryId = readFirst(row, ["id", "boundary_id"])

  useEffect(() => {
    if (!row) return
    const nextIsolationMode = readFirst(row, ["isolation_mode"])
    if ((DATA_BOUNDARY_ISOLATION_OPTIONS as readonly string[]).includes(nextIsolationMode)) {
      setIsolationMode(nextIsolationMode as typeof isolationMode)
    }
    setEncryptionProfile(readFirst(row, ["encryption_profile"]))
    setStoragePrefix(readFirst(row, ["storage_prefix"]))
    setAllowedRegionsJson(JSON.stringify(row.allowed_regions_json ?? [], null, 2))
    setDataResidencyNotes(readFirst(row, ["data_residency_notes"]))
    const nextStatus = readFirst(row, ["status"])
    if ((TENANT_PROFILE_STATUS_OPTIONS as readonly string[]).includes(nextStatus)) {
      setStatus(nextStatus as typeof status)
    }
  }, [row])

  async function saveDataBoundary() {
    const body = {
      isolation_mode: isolationMode,
      encryption_profile: encryptionProfile.trim() || null,
      storage_prefix: storagePrefix.trim() || null,
      allowed_regions_json: parseJsonArrayField(allowedRegionsJson, "allowed regions").map((item) => String(item)),
      data_residency_notes: dataResidencyNotes.trim() || null,
      status,
    }
    setBusy(true)
    setFormError("")
    try {
      const isCreate = !boundaryId
      if (boundaryId) {
        await apiFetch(`/tenant-data-boundaries/${encodeURIComponent(boundaryId)}`, {
          method: "PATCH",
          body,
        })
      } else {
        await apiFetch(`/tenants/${encodeURIComponent(tenantId)}/data-boundary`, {
          method: "POST",
          body,
        })
      }
      if (isCreate) trackDataBoundaryCreated({ status })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not save data boundary."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <NoSecretsWarning />

      <SectionCard
        title="Data Boundary"
        description="Data boundary configuration for this tenant — isolation mode, encryption profile, storage prefix, allowed regions, and data residency policy."
        error={error || formError}
      >
        <RecordFields
          row={row}
          empty="No data boundary returned."
          fields={[
            { label: "isolation mode", key: "isolation_mode" },
            { label: "encryption profile", key: "encryption_profile" },
            { label: "storage prefix", key: "storage_prefix" },
            { label: "allowed regions", key: "allowed_regions_json" },
            { label: "data residency notes", key: "data_residency_notes" },
            { label: "status", key: "status" },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Configure data boundary"
        description="Set or update the data boundary — isolation mode, encryption profile, storage prefix, allowed regions, and residency notes."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-boundary-isolation-mode">isolation mode</Label>
            <Select value={isolationMode} onValueChange={(value) => setIsolationMode(value as typeof isolationMode)}>
              <SelectTrigger id="tenant-boundary-isolation-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DATA_BOUNDARY_ISOLATION_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-boundary-status">status</Label>
            <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
              <SelectTrigger id="tenant-boundary-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TENANT_PROFILE_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-boundary-encryption-profile">encryption profile</Label>
            <Input
              id="tenant-boundary-encryption-profile"
              value={encryptionProfile}
              onChange={(event) => setEncryptionProfile(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-boundary-storage-prefix">storage prefix</Label>
            <Input
              id="tenant-boundary-storage-prefix"
              value={storagePrefix}
              onChange={(event) => setStoragePrefix(event.target.value)}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-boundary-allowed-regions">allowed regions</Label>
            <Textarea
              id="tenant-boundary-allowed-regions"
              value={allowedRegionsJson}
              onChange={(event) => setAllowedRegionsJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-boundary-data-residency-notes">data residency notes</Label>
            <Textarea
              id="tenant-boundary-data-residency-notes"
              value={dataResidencyNotes}
              onChange={(event) => setDataResidencyNotes(event.target.value)}
              rows={3}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void saveDataBoundary()}>
            {busy ? "Saving..." : boundaryId ? "Update data boundary" : "Create data boundary"}
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void onReload()}>
            Refresh data boundary
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function SecurityProfilePanel({
  tenantId,
  row,
  error,
  onReload,
}: {
  tenantId: string
  row: Row | null
  error: string
  onReload: () => Promise<void>
}) {
  const [ssoEnabled, setSsoEnabled] = useState("false")
  const [mfaRequired, setMfaRequired] = useState("false")
  const [allowedDomainsJson, setAllowedDomainsJson] = useState("[]")
  const [sessionTimeoutMinutes, setSessionTimeoutMinutes] = useState("")
  const [ipAllowlistJson, setIpAllowlistJson] = useState("[]")
  const [securityFrameworksJson, setSecurityFrameworksJson] = useState("[]")
  const [riskSummaryJson, setRiskSummaryJson] = useState("{}")
  const [status, setStatus] = useState<(typeof TENANT_PROFILE_STATUS_OPTIONS)[number]>("draft")
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState("")

  const profileId = readFirst(row, ["id", "profile_id"])

  useEffect(() => {
    if (!row) return
    setSsoEnabled(readFirst(row, ["sso_enabled"]).toLowerCase() === "true" ? "true" : "false")
    setMfaRequired(readFirst(row, ["mfa_required"]).toLowerCase() === "true" ? "true" : "false")
    setAllowedDomainsJson(JSON.stringify(row.allowed_domains_json ?? [], null, 2))
    setSessionTimeoutMinutes(readFirst(row, ["session_timeout_minutes"]))
    setIpAllowlistJson(JSON.stringify(row.ip_allowlist_json ?? [], null, 2))
    setSecurityFrameworksJson(JSON.stringify(row.security_frameworks_json ?? [], null, 2))
    setRiskSummaryJson(JSON.stringify(row.risk_summary_json ?? {}, null, 2))
    const nextStatus = readFirst(row, ["status"])
    if ((TENANT_PROFILE_STATUS_OPTIONS as readonly string[]).includes(nextStatus)) {
      setStatus(nextStatus as typeof status)
    }
  }, [row])

  async function saveSecurityProfile() {
    const timeoutValue = sessionTimeoutMinutes.trim()
    const body = {
      sso_enabled: ssoEnabled === "true",
      mfa_required: mfaRequired === "true",
      allowed_domains_json: parseJsonArrayField(allowedDomainsJson, "allowed domains").map((item) => String(item)),
      session_timeout_minutes: timeoutValue ? Number(timeoutValue) : null,
      ip_allowlist_json: parseJsonArrayField(ipAllowlistJson, "IP allowlist").map((item) => String(item)),
      security_frameworks_json: parseJsonArrayField(securityFrameworksJson, "security frameworks").map((item) =>
        String(item),
      ),
      risk_summary_json: parseJsonObjectField(riskSummaryJson, "risk summary"),
      status,
    }
    setBusy(true)
    setFormError("")
    try {
      if (profileId) {
        await apiFetch(`/tenant-security-profiles/${encodeURIComponent(profileId)}`, {
          method: "PATCH",
          body,
        })
      } else {
        await apiFetch(`/tenants/${encodeURIComponent(tenantId)}/security-profile`, {
          method: "POST",
          body,
        })
      }
      trackSecurityProfileUpdated({ status })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not save security profile."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <NoSecretsWarning />

      <SectionCard
        title="Security Profile"
        description="Security profile for this tenant — SSO, MFA, allowed domains, session timeout, IP allowlist, and security frameworks."
        error={error || formError}
      >
        <RecordFields
          row={row}
          empty="No security profile returned."
          fields={[
            { label: "SSO enabled", key: "sso_enabled" },
            { label: "MFA required", key: "mfa_required" },
            { label: "allowed domains", key: "allowed_domains_json" },
            { label: "session timeout", key: "session_timeout_minutes" },
            { label: "IP allowlist", key: "ip_allowlist_json" },
            { label: "security frameworks", key: "security_frameworks_json" },
            { label: "risk summary", key: "risk_summary_json" },
            { label: "status", key: "status" },
          ]}
        />
      </SectionCard>

      <SectionCard
        title="Configure security profile"
        description="Set or update the security profile — SSO, MFA, session timeout, allowed domains, IP allowlist, security frameworks, and risk summary."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-security-sso-enabled">SSO enabled</Label>
            <Select value={ssoEnabled} onValueChange={setSsoEnabled}>
              <SelectTrigger id="tenant-security-sso-enabled">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">true</SelectItem>
                <SelectItem value="false">false</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-security-mfa-required">MFA required</Label>
            <Select value={mfaRequired} onValueChange={setMfaRequired}>
              <SelectTrigger id="tenant-security-mfa-required">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">true</SelectItem>
                <SelectItem value="false">false</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-security-session-timeout">session timeout</Label>
            <Input
              id="tenant-security-session-timeout"
              value={sessionTimeoutMinutes}
              onChange={(event) => setSessionTimeoutMinutes(event.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-security-status">status</Label>
            <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
              <SelectTrigger id="tenant-security-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TENANT_PROFILE_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-security-allowed-domains">allowed domains</Label>
            <Textarea
              id="tenant-security-allowed-domains"
              value={allowedDomainsJson}
              onChange={(event) => setAllowedDomainsJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-security-ip-allowlist">IP allowlist</Label>
            <Textarea
              id="tenant-security-ip-allowlist"
              value={ipAllowlistJson}
              onChange={(event) => setIpAllowlistJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-security-frameworks">security frameworks</Label>
            <Textarea
              id="tenant-security-frameworks"
              value={securityFrameworksJson}
              onChange={(event) => setSecurityFrameworksJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-security-risk-summary">risk summary</Label>
            <Textarea
              id="tenant-security-risk-summary"
              value={riskSummaryJson}
              onChange={(event) => setRiskSummaryJson(event.target.value)}
              rows={4}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void saveSecurityProfile()}>
            {busy ? "Saving..." : profileId ? "Update security profile" : "Create security profile"}
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void onReload()}>
            Refresh security profile
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function ValidationProfilePanel({
  tenantId,
  row,
  error,
  onReload,
}: {
  tenantId: string
  row: Row | null
  error: string
  onReload: () => Promise<void>
}) {
  const [validationRequired, setValidationRequired] = useState("false")
  const [validationProjectIdsJson, setValidationProjectIdsJson] = useState("[]")
  const [controlledRecordPolicy, setControlledRecordPolicy] = useState("")
  const [esignatureRequired, setEsignatureRequired] = useState("false")
  const [dataIntegrityAssessmentIdsJson, setDataIntegrityAssessmentIdsJson] = useState("[]")
  const [inspectionPackageIdsJson, setInspectionPackageIdsJson] = useState("[]")
  const [status, setStatus] = useState<(typeof TENANT_VALIDATION_PROFILE_STATUS_OPTIONS)[number]>("draft")
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState("")

  const profileId = readFirst(row, ["id", "profile_id"])
  const validationProjectIds = row?.validation_project_ids_json ?? []
  const dataIntegrityAssessmentIds = row?.data_integrity_assessment_ids_json ?? []
  const inspectionPackageIds = row?.inspection_package_ids_json ?? []
  const esignatureSetting = readFirst(row, ["esignature_required"]).toLowerCase() === "true" ? "required" : "not required"
  const readinessStatus = readFirst(row, ["status"]) || "-"

  useEffect(() => {
    if (!row) return
    setValidationRequired(readFirst(row, ["validation_required"]).toLowerCase() === "true" ? "true" : "false")
    setValidationProjectIdsJson(JSON.stringify(row.validation_project_ids_json ?? [], null, 2))
    setControlledRecordPolicy(readFirst(row, ["controlled_record_policy"]))
    setEsignatureRequired(readFirst(row, ["esignature_required"]).toLowerCase() === "true" ? "true" : "false")
    setDataIntegrityAssessmentIdsJson(JSON.stringify(row.data_integrity_assessment_ids_json ?? [], null, 2))
    setInspectionPackageIdsJson(JSON.stringify(row.inspection_package_ids_json ?? [], null, 2))
    const nextStatus = readFirst(row, ["status"])
    if ((TENANT_VALIDATION_PROFILE_STATUS_OPTIONS as readonly string[]).includes(nextStatus)) {
      setStatus(nextStatus as typeof status)
    }
  }, [row])

  async function saveValidationProfile() {
    const body = {
      validation_required: validationRequired === "true",
      validation_project_ids_json: parseIdArrayField(validationProjectIdsJson, "validation project IDs"),
      controlled_record_policy: controlledRecordPolicy.trim() || null,
      esignature_required: esignatureRequired === "true",
      data_integrity_assessment_ids_json: parseIdArrayField(
        dataIntegrityAssessmentIdsJson,
        "data integrity assessment IDs",
      ),
      inspection_package_ids_json: parseIdArrayField(inspectionPackageIdsJson, "inspection package IDs"),
      status,
    }
    setBusy(true)
    setFormError("")
    try {
      if (profileId) {
        await apiFetch(`/tenant-validation-profiles/${encodeURIComponent(profileId)}`, {
          method: "PATCH",
          body,
        })
      } else {
        await apiFetch(`/tenants/${encodeURIComponent(tenantId)}/validation-profile`, {
          method: "POST",
          body,
        })
      }
      trackValidationProfileUpdated({ status })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not save validation profile."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Alert className="border-warning/40 bg-warning/10">
        <AlertDescription className="text-xs text-warning">
          Validation profile indicates internal validation readiness. It does not represent external regulatory
          certification.
        </AlertDescription>
      </Alert>

      <SectionCard
        title="Validation Profile"
        description="Validation profile for this tenant — validation requirements, linked projects, controlled record policy, e-signature requirements, and readiness status."
        error={error || formError}
      >
        <RecordFields
          row={row}
          empty="No validation profile returned."
          fields={[
            { label: "validation required", key: "validation_required" },
            { label: "validation project IDs", key: "validation_project_ids_json" },
            { label: "controlled record policy", key: "controlled_record_policy" },
            { label: "e-signature required", key: "esignature_required" },
            { label: "data integrity assessment IDs", key: "data_integrity_assessment_ids_json" },
            { label: "inspection package IDs", key: "inspection_package_ids_json" },
            { label: "status", key: "status" },
          ]}
        />
      </SectionCard>

      <SectionCard title="Linked validation artifacts">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="linked validation projects" value={validationProjectIds} valueKey="validation_project_ids_json" />
          <Field label="controlled record policy" value={row?.controlled_record_policy} valueKey="controlled_record_policy" />
          <Field label="e-signature setting" value={esignatureSetting} valueKey="esignature_required" />
          <Field
            label="data integrity assessments"
            value={dataIntegrityAssessmentIds}
            valueKey="data_integrity_assessment_ids_json"
          />
          <Field label="inspection packages" value={inspectionPackageIds} valueKey="inspection_package_ids_json" />
          <div>
            <p className="text-xs font-medium text-muted-foreground">readiness status</p>
            <div className="mt-1">
              <Badge variant="outline" className={`font-normal ${statusBadgeClass(readinessStatus)}`}>
                {readinessStatus}
              </Badge>
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Configure validation profile"
        description="Set or update the validation profile — validation requirements, linked projects, controlled record policy, e-signature setting, and linked assessment/package IDs."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-validation-required">validation required</Label>
            <Select value={validationRequired} onValueChange={setValidationRequired}>
              <SelectTrigger id="tenant-validation-required">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">true</SelectItem>
                <SelectItem value="false">false</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-validation-esignature-required">e-signature required</Label>
            <Select value={esignatureRequired} onValueChange={setEsignatureRequired}>
              <SelectTrigger id="tenant-validation-esignature-required">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">true</SelectItem>
                <SelectItem value="false">false</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-validation-status">status</Label>
            <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
              <SelectTrigger id="tenant-validation-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TENANT_VALIDATION_PROFILE_STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-validation-controlled-record-policy">controlled record policy</Label>
            <Textarea
              id="tenant-validation-controlled-record-policy"
              value={controlledRecordPolicy}
              onChange={(event) => setControlledRecordPolicy(event.target.value)}
              rows={3}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-validation-project-ids">validation project IDs</Label>
            <Textarea
              id="tenant-validation-project-ids"
              value={validationProjectIdsJson}
              onChange={(event) => setValidationProjectIdsJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-validation-data-integrity-assessment-ids">data integrity assessment IDs</Label>
            <Textarea
              id="tenant-validation-data-integrity-assessment-ids"
              value={dataIntegrityAssessmentIdsJson}
              onChange={(event) => setDataIntegrityAssessmentIdsJson(event.target.value)}
              rows={4}
            />
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="tenant-validation-inspection-package-ids">inspection package IDs</Label>
            <Textarea
              id="tenant-validation-inspection-package-ids"
              value={inspectionPackageIdsJson}
              onChange={(event) => setInspectionPackageIdsJson(event.target.value)}
              rows={4}
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void saveValidationProfile()}>
            {busy ? "Saving..." : profileId ? "Update validation profile" : "Create validation profile"}
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void onReload()}>
            Refresh validation profile
          </Button>
        </div>
      </SectionCard>
    </div>
  )
}

function recordValue(value: unknown): Row | null {
  return isRecord(value) ? value : null
}

function metricValue(row: Row | null | undefined, keys: string[]): string {
  if (!row) return "-"
  for (const key of keys) {
    const value = row[key]
    if (value != null && value !== "") return safeFormatValue(key, value, 120)
  }
  return "-"
}

function MetricCard({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-lg font-semibold">{safeFormatValue(label, value, 120)}</p>
    </div>
  )
}

function UsageProgramCard({
  order,
  title,
  usage,
  metrics,
}: {
  order: number
  title: string
  usage: Row | null
  metrics: { label: string; value: unknown }[]
}) {
  return (
    <ModuleCard
      accent="slate"
      eyebrow="Usage"
      title={`${order}. ${title}`}
      icon={BarChart3}
      description="Aggregate tenant usage only."
    >
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} label={metric.label} value={metric.value} />
          ))}
        </div>
        {usage ? (
          <details className="rounded-md border bg-muted/20 p-3">
            <summary className="cursor-pointer text-sm font-medium">Aggregate JSON</summary>
            <div className="mt-3">
              <JsonBlock value={usage} />
            </div>
          </details>
        ) : null}
      </div>
    </ModuleCard>
  )
}

function UsageRoiPanel({
  usageSummary,
  roi,
  usageError,
  roiError,
  onReload,
}: {
  usageSummary: Row | null
  roi: Row | null
  usageError: string
  roiError: string
  onReload: () => Promise<void>
}) {
  const spectracheckUsage = recordValue(usageSummary?.spectracheck_usage_json)
  const regulatoryUsage = recordValue(usageSummary?.regulatory_usage_json)
  const reactionUsage = recordValue(usageSummary?.reaction_usage_json)

  return (
    <div className="space-y-6">
      <SectionCard
        title="Usage / ROI Summary"
        description="Usage and ROI summary for this tenant — reports generated, tasks automated, hours saved, and regulatory and reaction optimization activity metrics."
        error={usageError || roiError}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="reports generated" value={roi?.reports_generated ?? usageSummary?.reports_generated} />
          <MetricCard label="tasks automated" value={roi?.tasks_automated ?? usageSummary?.actions_completed} />
          <MetricCard label="hours saved" value={roi?.total_hours_saved ?? usageSummary?.hours_saved} />
          <MetricCard label="regulatory actions created" value={roi?.regulatory_actions_created} />
          <MetricCard label="regulatory actions completed" value={usageSummary?.actions_completed} />
          <MetricCard
            label="reaction recommendations approved"
            value={roi?.reaction_recommendations_approved}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void onReload()}>
            Refresh usage and ROI
          </Button>
        </div>
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-3">
        <UsageProgramCard
          order={1}
          title="SpectraCheck usage"
          usage={spectracheckUsage}
          metrics={[
            {
              label: "sessions created",
              value: metricValue(spectracheckUsage, ["sessions_created", "sessions", "session_count"]),
            },
            {
              label: "reports generated",
              value: metricValue(spectracheckUsage, ["reports_generated", "reports", "report_count"]),
            },
          ]}
        />
        <UsageProgramCard
          order={2}
          title="Regentry usage"
          usage={regulatoryUsage}
          metrics={[
            {
              label: "regulatory actions created",
              value: metricValue(regulatoryUsage, ["regulatory_actions_created", "actions_created", "created"]),
            },
            {
              label: "regulatory actions completed",
              value: metricValue(regulatoryUsage, ["regulatory_actions_completed", "actions_completed", "completed"]),
            },
          ]}
        />
        <UsageProgramCard
          order={3}
          title="Reaction Optimization usage"
          usage={reactionUsage}
          metrics={[
            {
              label: "reaction recommendations approved",
              value: metricValue(reactionUsage, [
                "reaction_recommendations_approved",
                "recommendations_approved",
                "approved_recommendations",
              ]),
            },
            {
              label: "tasks automated",
              value: metricValue(reactionUsage, ["tasks_automated", "automated_tasks"]),
            },
          ]}
        />
      </div>

      <SectionCard title="Warnings">
        {usageSummary?.warnings_json ? <JsonBlock value={usageSummary.warnings_json} /> : <p className="text-sm text-muted-foreground">No warnings returned.</p>}
      </SectionCard>
    </div>
  )
}

function HealthScorePanel({
  healthScore,
  error,
  onReload,
}: {
  healthScore: Row | null
  error: string
  onReload: () => Promise<void>
}) {
  const status = readFirst(healthScore, ["status"]) || "unknown"

  return (
    <div className="space-y-6">
      <SectionCard title="Health Score" description="Computed health score for this tenant — overall score, status, onboarding progress, usage trends, ROI indicators, blockers, and recommended actions." error={error}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="score" value={healthScore?.score ?? "-"} />
          <div className="rounded-md border bg-muted/20 p-3">
            <p className="text-xs font-medium text-muted-foreground">healthy/watch/at risk/unknown</p>
            <div className="mt-2">
              <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                {status}
              </Badge>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void onReload()}>
            Refresh health score
          </Button>
        </div>
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Onboarding summary">
          {healthScore?.onboarding_summary_json ? (
            <JsonBlock value={healthScore.onboarding_summary_json} />
          ) : (
            <p className="text-sm text-muted-foreground">No onboarding summary returned.</p>
          )}
        </SectionCard>
        <SectionCard title="Usage summary">
          {healthScore?.usage_summary_json ? (
            <JsonBlock value={healthScore.usage_summary_json} />
          ) : (
            <p className="text-sm text-muted-foreground">No usage summary returned.</p>
          )}
        </SectionCard>
        <SectionCard title="ROI summary">
          {healthScore?.roi_summary_json ? (
            <JsonBlock value={healthScore.roi_summary_json} />
          ) : (
            <p className="text-sm text-muted-foreground">No ROI summary returned.</p>
          )}
        </SectionCard>
        <SectionCard title="Blockers">
          {healthScore?.blockers_json ? (
            <JsonBlock value={healthScore.blockers_json} />
          ) : (
            <p className="text-sm text-muted-foreground">No blockers returned.</p>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Recommended actions">
        {healthScore?.recommended_actions_json ? (
          <JsonBlock value={healthScore.recommended_actions_json} />
        ) : (
          <p className="text-sm text-muted-foreground">No recommended actions returned.</p>
        )}
      </SectionCard>
    </div>
  )
}

function IncludeCheckbox({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string
  label: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center gap-2 rounded-md border bg-muted/20 px-3 py-2">
      <Checkbox id={id} checked={checked} onCheckedChange={(value) => onCheckedChange(Boolean(value))} />
      <Label htmlFor={id} className="text-sm font-normal">
        {label}
      </Label>
    </div>
  )
}

function ProcurementPackagesPanel({
  tenantId,
  rows,
  error,
  onReload,
}: {
  tenantId: string
  rows: Row[]
  error: string
  onReload: () => Promise<void>
}) {
  const [title, setTitle] = useState("")
  const [packageType, setPackageType] =
    useState<(typeof PROCUREMENT_PACKAGE_TYPE_OPTIONS)[number]>("security_review")
  const [includeSecurityProfile, setIncludeSecurityProfile] = useState(true)
  const [includeDataBoundary, setIncludeDataBoundary] = useState(true)
  const [includeValidationProfile, setIncludeValidationProfile] = useState(true)
  const [includeAiGovernanceSummary, setIncludeAiGovernanceSummary] = useState(true)
  const [includeAuditSummary, setIncludeAuditSummary] = useState(true)
  const [includeMobileOfflineSafetySummary, setIncludeMobileOfflineSafetySummary] = useState(true)
  const [includeConnectorSafetySummary, setIncludeConnectorSafetySummary] = useState(true)
  const [includeRoiSummary, setIncludeRoiSummary] = useState(true)
  const [selectedPackage, setSelectedPackage] = useState<Row | null>(null)
  const [selectedPackageError, setSelectedPackageError] = useState("")
  const [busy, setBusy] = useState(false)
  const [actionBusyId, setActionBusyId] = useState("")
  const [formError, setFormError] = useState("")

  const selectedPackageJson = recordValue(selectedPackage?.package_json)
  const warningValue =
    selectedPackageJson?.warnings_json ??
    selectedPackageJson?.warnings ??
    selectedPackageJson?.language_notice ??
    selectedPackage?.warnings_json ??
    selectedPackage?.warnings
  const openHref =
    typeof selectedPackage?.package_html === "string" && selectedPackage.package_html.trim()
      ? `data:text/html;charset=utf-8,${encodeURIComponent(selectedPackage.package_html)}`
      : ""
  const developerJson = selectedPackage
    ? {
        ...selectedPackage,
        package_html: selectedPackage.package_html ? "[available]" : null,
      }
    : null

  async function createProcurementPackage() {
    setBusy(true)
    setFormError("")
    try {
      const payload = await apiFetch<unknown>(`/tenants/${encodeURIComponent(tenantId)}/procurement-package`, {
        method: "POST",
        body: {
          title: title.trim(),
          package_type: packageType,
          status: "ready_for_review",
          metadata_json: {
            include_security_profile: includeSecurityProfile,
            include_data_boundary: includeDataBoundary,
            include_validation_profile: includeValidationProfile,
            include_ai_governance_summary: includeAiGovernanceSummary,
            include_audit_summary: includeAuditSummary,
            include_mobile_offline_safety_summary: includeMobileOfflineSafetySummary,
            include_connector_safety_summary: includeConnectorSafetySummary,
            include_roi_summary: includeRoiSummary,
          },
        },
      })
      setTitle("")
      setPackageType("security_review")
      setSelectedPackage(unwrapRecord(payload, ["procurement_package", "package"]))
      trackProcurementPackageCreated({ package_type: packageType, status: "ready_for_review" })
      await onReload()
    } catch (err) {
      setFormError(formatErr(err, "Could not create procurement evidence package."))
    } finally {
      setBusy(false)
    }
  }

  async function loadProcurementPackage(row: Row) {
    const packageId = readFirst(row, ["id", "package_id"])
    if (!packageId) return
    setActionBusyId(packageId)
    setSelectedPackageError("")
    try {
      const payload = await apiFetch<unknown>(`/procurement-packages/${encodeURIComponent(packageId)}`, {
        method: "GET",
      })
      setSelectedPackage(unwrapRecord(payload, ["procurement_package", "package"]))
    } catch (err) {
      setSelectedPackage(null)
      setSelectedPackageError(formatErr(err, "Could not load procurement evidence package."))
    } finally {
      setActionBusyId("")
    }
  }

  return (
    <div className="space-y-6">
      <Alert className="border-warning/40 bg-warning/10">
        <AlertDescription className="text-xs text-warning">
          Procurement evidence packages summarize readiness and controls. They do not represent third-party certification
          unless separately documented.
        </AlertDescription>
      </Alert>

      <SectionCard
        title="Procurement Packages"
        description="Procurement evidence packages generated for this tenant — type, status, SHA-256 integrity hash, and creation date."
        error={error || formError}
      >
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">title</TableHead>
                <TableHead className="text-xs">package type</TableHead>
                <TableHead className="text-xs">package status</TableHead>
                <TableHead className="text-xs">package SHA-256</TableHead>
                <TableHead className="text-xs">created date</TableHead>
                <TableHead className="text-xs">action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-xs text-muted-foreground">
                    No procurement packages returned.
                  </TableCell>
                </TableRow>
              ) : (
                rows.map((row, index) => {
                  const packageId = readFirst(row, ["id", "package_id"]) || `package-${index}`
                  const status = readFirst(row, ["status"])
                  return (
                    <TableRow key={packageId}>
                      <TableCell className="text-xs">{readFirst(row, ["title"]) || "-"}</TableCell>
                      <TableCell className="text-xs">{readFirst(row, ["package_type"]) || "-"}</TableCell>
                      <TableCell className="text-xs">
                        {status ? (
                          <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                            {status}
                          </Badge>
                        ) : (
                          "-"
                        )}
                      </TableCell>
                      <TableCell className="max-w-[24rem] text-xs">{readFirst(row, ["package_sha256"]) || "-"}</TableCell>
                      <TableCell className="text-xs">{readFirst(row, ["created_at"]) || "-"}</TableCell>
                      <TableCell>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={actionBusyId === packageId}
                          onClick={() => void loadProcurementPackage(row)}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </div>
      </SectionCard>

      <SectionCard title="Create procurement evidence package" description="Generate a procurement evidence package — specify type and choose which summaries to include: security profile, data boundary, validation, AI governance, audit, mobile safety, connectors, and ROI.">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-procurement-title">title</Label>
            <Input id="tenant-procurement-title" value={title} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-procurement-package-type">package type</Label>
            <Select value={packageType} onValueChange={(value) => setPackageType(value as typeof packageType)}>
              <SelectTrigger id="tenant-procurement-package-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROCUREMENT_PACKAGE_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <IncludeCheckbox
            id="tenant-procurement-include-security-profile"
            label="include security profile"
            checked={includeSecurityProfile}
            onCheckedChange={setIncludeSecurityProfile}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-data-boundary"
            label="include data boundary"
            checked={includeDataBoundary}
            onCheckedChange={setIncludeDataBoundary}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-validation-profile"
            label="include validation profile"
            checked={includeValidationProfile}
            onCheckedChange={setIncludeValidationProfile}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-ai-governance-summary"
            label="include AI governance summary"
            checked={includeAiGovernanceSummary}
            onCheckedChange={setIncludeAiGovernanceSummary}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-audit-summary"
            label="include audit summary"
            checked={includeAuditSummary}
            onCheckedChange={setIncludeAuditSummary}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-mobile-offline-safety-summary"
            label="include mobile/offline safety summary"
            checked={includeMobileOfflineSafetySummary}
            onCheckedChange={setIncludeMobileOfflineSafetySummary}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-connector-safety-summary"
            label="include connector safety summary"
            checked={includeConnectorSafetySummary}
            onCheckedChange={setIncludeConnectorSafetySummary}
          />
          <IncludeCheckbox
            id="tenant-procurement-include-roi-summary"
            label="include ROI summary"
            checked={includeRoiSummary}
            onCheckedChange={setIncludeRoiSummary}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void createProcurementPackage()}>
            {busy ? "Generating..." : "Generate procurement evidence package"}
          </Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => void onReload()}>
            Refresh packages
          </Button>
        </div>
      </SectionCard>

      <SectionCard
        title="Selected procurement package"
        description="Detail for the selected procurement package — status, SHA-256 integrity hash, type, and included summaries."
        error={selectedPackageError}
      >
        <RecordFields
          row={selectedPackage}
          empty="Open a procurement package to view safe summaries."
          fields={[
            { label: "package status", key: "status" },
            { label: "package SHA-256", key: "package_sha256" },
            { label: "package type", key: "package_type" },
            { label: "created date", key: "created_at" },
          ]}
        />
        {openHref ? (
          <Button type="button" variant="outline" asChild>
            <a href={openHref} target="_blank" rel="noreferrer">
              Open package
            </a>
          </Button>
        ) : null}
      </SectionCard>

      <SectionCard title="Included summaries">
        {selectedPackageJson ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <SectionCard title="Security profile">
              <JsonBlock value={selectedPackageJson.security_profile ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="Data boundary">
              <JsonBlock value={selectedPackageJson.data_boundary ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="Validation profile">
              <JsonBlock value={selectedPackageJson.validation_profile ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="AI governance summary">
              <JsonBlock value={selectedPackageJson.ai_governance_summary ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="Audit summary">
              <JsonBlock value={selectedPackageJson.audit_summary ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="Mobile/offline safety summary">
              <JsonBlock value={selectedPackageJson.mobile_offline_safety_summary ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="Connector safety summary">
              <JsonBlock value={selectedPackageJson.connector_safety_summary ?? { status: "not included" }} />
            </SectionCard>
            <SectionCard title="ROI summary">
              <JsonBlock value={selectedPackageJson.roi_summary ?? { status: "not included" }} />
            </SectionCard>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Open a package to view included summaries.</p>
        )}
      </SectionCard>

      <SectionCard title="Warnings">
        {warningValue ? <JsonBlock value={warningValue} /> : <p className="text-sm text-muted-foreground">No warnings returned.</p>}
      </SectionCard>

      <SectionCard title="Developer JSON">
        <details className="rounded-md border bg-muted/20 p-3">
          <summary className="cursor-pointer text-sm font-medium">Developer JSON</summary>
          <div className="mt-3">
            <JsonBlock value={developerJson ?? { status: "No procurement package selected." }} />
          </div>
        </details>
      </SectionCard>
    </div>
  )
}

function AuditExportPanel({ tenantId }: { tenantId: string }) {
  const [exportScope, setExportScope] = useState<(typeof AUDIT_EXPORT_SCOPE_OPTIONS)[number]>("all")
  const [dateRangeStart, setDateRangeStart] = useState("")
  const [dateRangeEnd, setDateRangeEnd] = useState("")
  const [includeMetadata, setIncludeMetadata] = useState(true)
  const [includeHashes, setIncludeHashes] = useState(true)
  const [exportId, setExportId] = useState("")
  const [selectedExport, setSelectedExport] = useState<Row | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const selectedExportId = readFirst(selectedExport, ["id", "export_id"])
  const selectedExportStatus = readFirst(selectedExport, ["status"]) || "-"
  const selectedExportSha = readFirst(selectedExport, ["export_sha256"]) || "-"
  const metadata = recordValue(selectedExport?.metadata_json)
  const warnings = selectedExport?.warnings_json ?? metadata?.warnings_json ?? metadata?.warnings
  const downloadPayload = selectedExport
    ? {
        export_status: selectedExport.status,
        export_sha256: selectedExport.export_sha256,
        export_scope: selectedExport.export_scope,
        created_at: selectedExport.created_at,
        metadata_json: selectedExport.metadata_json,
      }
    : null
  const downloadHref = downloadPayload
    ? `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(redactDeep(downloadPayload), null, 2))}`
    : ""

  async function requestAuditExport() {
    setBusy(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/tenants/${encodeURIComponent(tenantId)}/audit-export`, {
        method: "POST",
        body: {
          export_scope: exportScope,
          metadata_json: {
            date_range_start: dateRangeStart.trim() || null,
            date_range_end: dateRangeEnd.trim() || null,
            include_metadata: includeMetadata,
            include_hashes: includeHashes,
          },
        },
      })
      const record = unwrapRecord(payload, ["tenant_audit_export", "audit_export", "export"])
      setSelectedExport(record)
      setExportId(readFirst(record, ["id", "export_id"]))
      trackTenantAuditExportRequested({ status: readFirst(record, ["status"]) || "queued" })
    } catch (err) {
      setError(formatErr(err, "Could not request tenant audit export."))
    } finally {
      setBusy(false)
    }
  }

  async function loadAuditExport() {
    const id = exportId.trim()
    if (!id) return
    setBusy(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/tenant-audit-exports/${encodeURIComponent(id)}`, {
        method: "GET",
      })
      setSelectedExport(unwrapRecord(payload, ["tenant_audit_export", "audit_export", "export"]))
    } catch (err) {
      setSelectedExport(null)
      setError(formatErr(err, "Could not load tenant audit export."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <NoSecretsWarning />

      <SectionCard title="Request tenant audit export" description="Request an audit trail export for this tenant — specify export scope, optional date range, and whether to include metadata and hashes." error={error}>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="tenant-audit-export-scope">export scope</Label>
            <Select value={exportScope} onValueChange={(value) => setExportScope(value as typeof exportScope)}>
              <SelectTrigger id="tenant-audit-export-scope">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUDIT_EXPORT_SCOPE_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tenant-audit-export-start">date range optional</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                id="tenant-audit-export-start"
                placeholder="start"
                value={dateRangeStart}
                onChange={(event) => setDateRangeStart(event.target.value)}
              />
              <Input
                id="tenant-audit-export-end"
                placeholder="end"
                value={dateRangeEnd}
                onChange={(event) => setDateRangeEnd(event.target.value)}
              />
            </div>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <IncludeCheckbox
            id="tenant-audit-export-include-metadata"
            label="include metadata"
            checked={includeMetadata}
            onCheckedChange={setIncludeMetadata}
          />
          <IncludeCheckbox
            id="tenant-audit-export-include-hashes"
            label="include hashes"
            checked={includeHashes}
            onCheckedChange={setIncludeHashes}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} onClick={() => void requestAuditExport()}>
            {busy ? "Requesting..." : "Request audit export"}
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Load audit export" description="Load a completed audit export by ID — view export status, scope, and download link.">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input value={exportId} onChange={(event) => setExportId(event.target.value)} placeholder="export ID" />
          <Button type="button" variant="outline" disabled={busy || !exportId.trim()} onClick={() => void loadAuditExport()}>
            Load export
          </Button>
        </div>
      </SectionCard>

      <SectionCard title="Audit export status">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="export ID" value={selectedExportId || "-"} valueKey="id" />
          <div>
            <p className="text-xs font-medium text-muted-foreground">export status</p>
            <div className="mt-1">
              <Badge variant="outline" className={`font-normal ${statusBadgeClass(selectedExportStatus)}`}>
                {selectedExportStatus}
              </Badge>
            </div>
          </div>
          <Field label="export SHA-256" value={selectedExportSha} valueKey="export_sha256" />
          <Field label="created date" value={selectedExport?.created_at} valueKey="created_at" />
        </div>
        {downloadHref ? (
          <Button type="button" variant="outline" asChild>
            <a href={downloadHref} download={`tenant-audit-export-${selectedExportId || "manifest"}.json`}>
              Download export
            </a>
          </Button>
        ) : null}
      </SectionCard>

      <SectionCard title="Warnings">
        {warnings ? <JsonBlock value={warnings} /> : <p className="text-sm text-muted-foreground">No warnings returned.</p>}
      </SectionCard>

      <SectionCard title="Developer JSON">
        <details className="rounded-md border bg-muted/20 p-3">
          <summary className="cursor-pointer text-sm font-medium">Developer JSON</summary>
          <div className="mt-3">
            <JsonBlock value={selectedExport ?? { status: "No audit export selected." }} />
          </div>
        </details>
      </SectionCard>
    </div>
  )
}

export function TenantDetailWorkspace() {
  const params = useParams()
  const rawTenantId = params?.tenantId
  const tenantId = typeof rawTenantId === "string" ? rawTenantId : Array.isArray(rawTenantId) ? rawTenantId[0] : ""

  const [loading, setLoading] = useState(true)
  const [sections, setSections] = useState<Record<SectionKey, SectionState>>({
    tenant: EMPTY_SECTION,
    environments: EMPTY_SECTION,
    entitlements: EMPTY_SECTION,
    pilotPrograms: EMPTY_SECTION,
    onboarding: EMPTY_SECTION,
    dataBoundary: EMPTY_SECTION,
    securityProfile: EMPTY_SECTION,
    validationProfile: EMPTY_SECTION,
    usageSummary: EMPTY_SECTION,
    roi: EMPTY_SECTION,
    healthScore: EMPTY_SECTION,
    procurementPackages: EMPTY_SECTION,
  })

  const load = useCallback(async () => {
    const id = tenantId.trim()
    if (!id) {
      setLoading(false)
      setSections((prev) => ({
        ...prev,
        tenant: { payload: null, error: "Missing tenant id." },
      }))
      return
    }

    setLoading(true)
    const encoded = encodeURIComponent(id)
    const endpoints: Record<SectionKey, string> = {
      tenant: `/tenants/${encoded}`,
      environments: `/tenants/${encoded}/environments`,
      entitlements: `/tenants/${encoded}/entitlements`,
      pilotPrograms: `/tenants/${encoded}/pilot-programs`,
      onboarding: `/tenants/${encoded}/onboarding-projects`,
      dataBoundary: `/tenants/${encoded}/data-boundary`,
      securityProfile: `/tenants/${encoded}/security-profile`,
      validationProfile: `/tenants/${encoded}/validation-profile`,
      usageSummary: `/tenants/${encoded}/usage-summary`,
      roi: `/tenants/${encoded}/roi`,
      healthScore: `/tenants/${encoded}/health-score`,
      procurementPackages: `/tenants/${encoded}/procurement-packages`,
    }

    const entries = await Promise.all(
      Object.entries(endpoints).map(async ([key, endpoint]) => {
        try {
          const payload = await apiFetch<unknown>(endpoint, { method: "GET" })
          return [key, { payload, error: "" }] as const
        } catch (error) {
          return [key, { payload: null, error: formatErr(error, `Could not load ${key}.`) }] as const
        }
      }),
    )

    setSections(Object.fromEntries(entries) as Record<SectionKey, SectionState>)
    setLoading(false)
  }, [tenantId])

  useEffect(() => {
    void load()
  }, [load])

  const tenant = useMemo(() => unwrapRecord(sections.tenant.payload, ["tenant"]), [sections.tenant.payload])
  const environments = useMemo(
    () => asRows(sections.environments.payload, ["environments", "tenant_environments"]),
    [sections.environments.payload],
  )
  const entitlements = useMemo(
    () => asRows(sections.entitlements.payload, ["entitlements", "tenant_entitlements"]),
    [sections.entitlements.payload],
  )
  const pilotPrograms = useMemo(
    () => asRows(sections.pilotPrograms.payload, ["pilot_programs", "pilots"]),
    [sections.pilotPrograms.payload],
  )
  const onboardingProjects = useMemo(
    () => asRows(sections.onboarding.payload, ["onboarding_projects", "projects"]),
    [sections.onboarding.payload],
  )
  const dataBoundary = useMemo(
    () => unwrapRecord(sections.dataBoundary.payload, ["data_boundary", "tenant_data_boundary", "boundary"]),
    [sections.dataBoundary.payload],
  )
  const securityProfile = useMemo(
    () => unwrapRecord(sections.securityProfile.payload, ["security_profile", "tenant_security_profile", "profile"]),
    [sections.securityProfile.payload],
  )
  const validationProfile = useMemo(
    () =>
      unwrapRecord(sections.validationProfile.payload, [
        "validation_profile",
        "tenant_validation_profile",
        "profile",
      ]),
    [sections.validationProfile.payload],
  )
  const usageSummary = useMemo(
    () => unwrapRecord(sections.usageSummary.payload, ["usage_summary", "tenant_usage_summary", "summary"]),
    [sections.usageSummary.payload],
  )
  const roi = useMemo(
    () => unwrapRecord(sections.roi.payload, ["roi", "tenant_roi", "roi_snapshot", "snapshot"]),
    [sections.roi.payload],
  )
  const healthScore = useMemo(
    () => unwrapRecord(sections.healthScore.payload, ["health_score", "customer_success_health_score", "score"]),
    [sections.healthScore.payload],
  )
  const procurementPackages = useMemo(
    () =>
      asRows(sections.procurementPackages.payload, [
        "procurement_packages",
        "packages",
        "procurement_evidence_packages",
      ]),
    [sections.procurementPackages.payload],
  )

  const title = readFirst(tenant, ["display_name", "name", "title"]) || "Tenant Detail"
  const tenantKey = readFirst(tenant, ["tenant_key"]) || tenantId

  const developerBundle = {
    tenant: sections.tenant.payload,
    environments: sections.environments.payload,
    entitlements: sections.entitlements.payload,
    pilot_programs: sections.pilotPrograms.payload,
    onboarding_projects: sections.onboarding.payload,
    data_boundary: sections.dataBoundary.payload,
    security_profile: sections.securityProfile.payload,
    validation_profile: sections.validationProfile.payload,
    usage_summary: sections.usageSummary.payload,
    roi: sections.roi.payload,
    health_score: sections.healthScore.payload,
    procurement_packages: sections.procurementPackages.payload,
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <Button type="button" variant="ghost" size="sm" asChild className="px-0">
            <Link href="/admin/tenants">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Tenant Admin
            </Link>
          </Button>
          <div>
            <h1 className="font-mono text-2xl font-bold tracking-tight">{title}</h1>
            <p className="text-muted-foreground">Tenant key: {tenantKey}</p>
          </div>
        </div>
        <BackendStatusIndicator />
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading tenant detail…</p> : null}

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="h-auto w-full flex-wrap justify-start">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="environments">Environments</TabsTrigger>
          <TabsTrigger value="entitlements">Entitlements</TabsTrigger>
          <TabsTrigger value="pilot_programs">Pilot Programs</TabsTrigger>
          <TabsTrigger value="onboarding">Onboarding</TabsTrigger>
          <TabsTrigger value="data_boundary">Data Boundary</TabsTrigger>
          <TabsTrigger value="security_profile">Security Profile</TabsTrigger>
          <TabsTrigger value="validation_profile">Validation Profile</TabsTrigger>
          <TabsTrigger value="usage_roi">Usage / ROI</TabsTrigger>
          <TabsTrigger value="health_score">Health Score</TabsTrigger>
          <TabsTrigger value="procurement_packages">Procurement Packages</TabsTrigger>
          <TabsTrigger value="audit_export">Audit Export</TabsTrigger>
          <TabsTrigger value="developer_json">Developer JSON</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          {/*
            GSD per-tenant readiness verdict (Phase 25d). Backend's
            telemetry-summary endpoint now scopes by `actor_user_id`; we
            pass the route's tenant id through as the actor scope per
            the FE handoff packet. Same component as the platform-wide
            admin readiness page; the scope chip + CTA copy adapt.
          */}
          <TenantGsdReadinessCard tenantId={tenantId} tenantLabel={title || tenantKey || `tenant ${tenantId}`} />

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
            <StatCard title="environments" value={environments.length} />
            <StatCard title="entitlements" value={entitlements.length} />
            <StatCard title="pilot programs" value={pilotPrograms.length} />
            <StatCard title="onboarding" value={onboardingProjects.length} />
            <StatCard title="procurement packages" value={procurementPackages.length} />
            <StatCard title="health score" value={readFirst(healthScore, ["score", "status"]) || "-"} />
          </div>

          <SectionCard title="Overview" description="Core tenant record — display name, tenant key, type, status, and primary contact." error={sections.tenant.error}>
            <RecordFields
              row={tenant}
              empty="No tenant detail returned."
              fields={[
                { label: "display name", key: "display_name" },
                { label: "tenant key", key: "tenant_key" },
                { label: "tenant type", key: "tenant_type" },
                { label: "status", key: "status" },
                { label: "primary contact", key: "primary_contact_email", keys: ["primary_contact_email", "primary_contact"] },
                { label: "updated date", key: "updated_at", keys: ["updated_at", "updated_date"] },
              ]}
            />
          </SectionCard>

          <SectionCard title="Programs">
            <div className="space-y-2 text-sm">
              {PROGRAM_ORDER.map((program, index) => (
                <div key={program} className="rounded-md border bg-muted/20 px-3 py-2">
                  {index + 1}. {program}
                </div>
              ))}
            </div>
          </SectionCard>
        </TabsContent>

        <TabsContent value="environments">
          <SectionCard
            title="Environments"
            description="Deployment environments for this tenant — environment type, base URL, status, and data retention policy."
            error={sections.environments.error}
          >
            <GenericTable
              rows={environments}
              empty="No environments returned."
              columns={[
                { key: "environment_type", label: "environment type" },
                { key: "base_url", label: "base url" },
                { key: "status", label: "status" },
                { key: "data_retention_policy_id", label: "data retention policy ID" },
                { key: "updated_at", label: "updated date", keys: ["updated_at", "updated_date"] },
              ]}
            />
          </SectionCard>
        </TabsContent>

        <TabsContent value="entitlements">
          <EntitlementsPanel
            tenantId={tenantId}
            rows={entitlements}
            error={sections.entitlements.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="pilot_programs">
          <PilotProgramsPanel
            tenantId={tenantId}
            rows={pilotPrograms}
            error={sections.pilotPrograms.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="onboarding">
          <OnboardingPanel
            tenantId={tenantId}
            rows={onboardingProjects}
            error={sections.onboarding.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="data_boundary">
          <DataBoundaryPanel
            tenantId={tenantId}
            row={dataBoundary}
            error={sections.dataBoundary.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="security_profile">
          <SecurityProfilePanel
            tenantId={tenantId}
            row={securityProfile}
            error={sections.securityProfile.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="validation_profile">
          <ValidationProfilePanel
            tenantId={tenantId}
            row={validationProfile}
            error={sections.validationProfile.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="usage_roi" className="space-y-6">
          <UsageRoiPanel
            usageSummary={usageSummary}
            roi={roi}
            usageError={sections.usageSummary.error}
            roiError={sections.roi.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="health_score">
          <HealthScorePanel
            healthScore={healthScore}
            error={sections.healthScore.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="procurement_packages">
          <ProcurementPackagesPanel
            tenantId={tenantId}
            rows={procurementPackages}
            error={sections.procurementPackages.error}
            onReload={load}
          />
        </TabsContent>

        <TabsContent value="audit_export">
          <AuditExportPanel tenantId={tenantId} />
        </TabsContent>

        <TabsContent value="developer_json">
          <SectionCard title="Developer JSON">
            <JsonBlock value={developerBundle} />
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  )
}

/**
 * Tenant-scoped GSD readiness verdict.
 *
 * Wraps GsdReadinessVerdictCard with the per-tenant scope mapping the
 * Phase 25d packet specifies. The route's `tenantId` is parsed to a
 * numeric value and passed as the `actor_user_id` query param — the
 * backend echoes it back as `scope_actor_user_id` and computes the
 * verdict against that user's audit-event slice.
 *
 * When the route param isn't numeric (e.g., a tenant slug rather than
 * an integer ID), we render a clarifying placeholder instead of firing
 * a request the backend can't satisfy.
 */
function TenantGsdReadinessCard({
  tenantId,
  tenantLabel,
}: {
  tenantId: string
  tenantLabel: string
}) {
  const numericId = Number.parseInt(tenantId, 10)
  if (!Number.isFinite(numericId) || numericId <= 0 || String(numericId) !== tenantId.trim()) {
    // Non-numeric tenant identifier (likely a slug); the actor_user_id
    // filter needs an integer. Skip the card instead of issuing a
    // request the backend will reject. The platform-wide verdict
    // remains available at /admin/gsd-readiness.
    return null
  }
  return (
    <GsdReadinessVerdictCard
      actorUserId={numericId}
      scopeLabel={tenantLabel}
      testId="tenant-gsd-verdict"
    />
  )
}
