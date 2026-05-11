"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ClipboardList, FileSearch, ShieldCheck } from "lucide-react"

type Row = Record<string, unknown>

const DATA_INTEGRITY_TOOLTIP =
  "Data integrity assessment checks whether records are attributable, legible, contemporaneous, original, accurate, complete, consistent, enduring, and available."

const SCOPE_OPTIONS = [
  "system",
  "project",
  "spectracheck_session",
  "regulatory_dossier",
  "reaction_project",
  "report",
  "connector",
  "ai_model",
  "mobile",
] as const

const ALCOA_STATUS_FIELDS = [
  { key: "attributable_status", label: "attributable" },
  { key: "legible_status", label: "legible" },
  { key: "contemporaneous_status", label: "contemporaneous" },
  { key: "original_status", label: "original" },
  { key: "accurate_status", label: "accurate" },
  { key: "complete_status", label: "complete" },
  { key: "consistent_status", label: "consistent" },
  { key: "enduring_status", label: "enduring" },
  { key: "available_status", label: "available" },
] as const

const SENSITIVE_KEY_PATTERN = /(secret|password|token|credential|authorization|raw|blob|binary|content_json)/i

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
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
  for (const key of [...keys, "assessment", "data_integrity_assessment", "record", "data"]) {
    const value = payload[key]
    if (isRecord(value)) return value
  }
  return payload
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function readInt(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) return value
  if (typeof value === "string" && value.trim() && Number.isInteger(Number(value)) && Number(value) > 0) {
    return Number(value)
  }
  return null
}

function rowId(row: Row | null | undefined): string {
  return readStr(row?.id ?? row?.assessment_id)
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function formatDate(value: unknown): string {
  const text = readStr(value)
  if (!text) return "-"
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return date.toLocaleString()
}

function statusVariant(value: unknown): "default" | "secondary" | "destructive" | "outline" {
  const status = readStr(value)
  if (status === "fail") return "destructive"
  if (status === "warning" || status === "requires_review") return "secondary"
  if (status === "pass") return "default"
  return "outline"
}

function formatJsonItem(value: unknown): string {
  if (typeof value === "string") return value
  if (!isRecord(value)) return JSON.stringify(value)
  const title = readStr(value.title ?? value.code ?? value.status ?? value.type)
  const message = readStr(value.message ?? value.description ?? value.recommendation ?? value.action)
  if (title && message) return `${title}: ${message}`
  if (title) return title
  if (message) return message
  return JSON.stringify(value)
}

function listFrom(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (typeof value === "string" && value.trim()) return [value]
  return []
}

function sanitizeForDeveloperJson(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY_PATTERN.test(key)) return "[redacted]"
  if (Array.isArray(value)) return value.map((item) => sanitizeForDeveloperJson(item))
  if (!isRecord(value)) return value
  return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [entryKey, sanitizeForDeveloperJson(entryValue, entryKey)]))
}

export function DataIntegrityWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [assessments, setAssessments] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedAssessment, setSelectedAssessment] = useState<Row | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [scope, setScope] = useState("system")
  const [scopeId, setScopeId] = useState("")
  const [createBusy, setCreateBusy] = useState(false)

  const loadAssessments = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/data-integrity/assessments", { method: "GET" })
      const rows = asRows(payload, ["assessments", "data_integrity_assessments"])
      setAssessments(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load data integrity assessments."))
      setAssessments([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadAssessments()
  }, [loadAssessments])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return assessments.find((assessment) => rowId(assessment) === selectedId) ?? null
  }, [assessments, selectedId])

  const detailAssessment = selectedAssessment ?? selectedSummary
  const developerJson = useMemo(() => sanitizeForDeveloperJson(detailAssessment), [detailAssessment])

  async function loadDetail(id: string) {
    if (!id) return
    setSelectedId(id)
    setDetailLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/data-integrity/assessments/${encodeURIComponent(id)}`, {
        method: "GET",
      })
      setSelectedAssessment(unwrapRecord(payload, ["data_integrity_assessment"]))
    } catch (err) {
      setError(formatErr(err, "Could not load data integrity assessment."))
      setSelectedAssessment(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function runAssessment() {
    const parsedScopeId = scopeId.trim() ? readInt(scopeId) : null
    if (scopeId.trim() && parsedScopeId == null) {
      setError("scope ID must be a positive integer.")
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/data-integrity/assessments", {
        method: "POST",
        body: {
          scope,
          scope_id: parsedScopeId,
        },
      })
      const assessment = unwrapRecord(payload, ["data_integrity_assessment"])
      if (assessment) {
        setSelectedId(rowId(assessment))
        setSelectedAssessment(assessment)
      }
      setScope("system")
      setScopeId("")
      setMessage("Data integrity assessment created.")
      await loadAssessments()
    } catch (err) {
      setError(formatErr(err, "Could not run data integrity assessment."))
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-green)" }}
          >
            MolTrace · Data Integrity
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Data Integrity Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Run and review ALCOA+ style data integrity assessments for validation readiness records.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {error ? <AlertCard variant="error" title="Error" description={error} /> : null}

      {message ? <AlertCard variant="success" title="Recorded" description={message} /> : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <ModuleCard
          accent="cyan"
          eyebrow="Run"
          title={
            <span className="flex items-center gap-2">
              Run data integrity assessment
              <InfoTooltip content={DATA_INTEGRITY_TOOLTIP} label="About data integrity assessment" />
            </span>
          }
          icon={ShieldCheck}
          description="Run a data integrity assessment across a defined scope — checks ALCOA+ principles, audit trail coverage, and access-control compliance."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="data-integrity-scope">scope</Label>
                <Select value={scope} onValueChange={setScope}>
                  <SelectTrigger id="data-integrity-scope">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SCOPE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="data-integrity-scope-id">scope ID optional</Label>
                <Input
                  id="data-integrity-scope-id"
                  inputMode="numeric"
                  value={scopeId}
                  onChange={(event) => setScopeId(event.target.value)}
                />
              </div>
            </div>
            <Button type="button" onClick={runAssessment} disabled={createBusy}>
              {createBusy ? "Running..." : "Run data integrity assessment"}
            </Button>
          </div>
        </ModuleCard>

        <ModuleCard
          accent="cyan"
          eyebrow="Detail"
          title="Assessment detail"
          icon={FileSearch}
          description="Selected assessment detail — scope, findings, ALCOA+ flags, and recommended remediation actions."
        >
          <div className="space-y-5">
            {detailAssessment ? (
              <>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-muted-foreground">scope</p>
                    <p className="font-medium">{readStr(detailAssessment.scope) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">scope ID</p>
                    <p className="font-medium">{readStr(detailAssessment.scope_id) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">status</p>
                    <Badge variant={statusVariant(detailAssessment.assessment_status)}>
                      {readStr(detailAssessment.assessment_status) || "-"}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">created date</p>
                    <p className="font-medium">{formatDate(detailAssessment.created_at)}</p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {ALCOA_STATUS_FIELDS.map((field) => (
                    <div key={field.key} className="rounded-lg border p-3">
                      <p className="text-xs text-muted-foreground">{field.label}</p>
                      <Badge variant={statusVariant(detailAssessment[field.key])}>
                        {readStr(detailAssessment[field.key]) || "-"}
                      </Badge>
                    </div>
                  ))}
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">findings</h3>
                    <div className="space-y-2">
                      {listFrom(detailAssessment.findings_json).map((item, index) => (
                        <div key={index} className="rounded-lg border p-3 text-sm">
                          {formatJsonItem(item)}
                        </div>
                      ))}
                      {!listFrom(detailAssessment.findings_json).length ? (
                        <p className="text-sm text-muted-foreground">No findings recorded.</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">recommended actions</h3>
                    <div className="space-y-2">
                      {listFrom(detailAssessment.recommended_actions_json).map((item, index) => (
                        <div key={index} className="rounded-lg border p-3 text-sm">
                          {formatJsonItem(item)}
                        </div>
                      ))}
                      {!listFrom(detailAssessment.recommended_actions_json).length ? (
                        <p className="text-sm text-muted-foreground">No recommended actions recorded.</p>
                      ) : null}
                    </div>
                  </div>
                </div>

                <details className="rounded-lg border p-3">
                  <summary className="cursor-pointer text-sm font-medium">Developer JSON</summary>
                  <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(developerJson, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading assessment..." : "Select an assessment to view ALCOA+ statuses."}
              </p>
            )}
          </div>
        </ModuleCard>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Assessments"
        title="Data integrity assessments"
        icon={ClipboardList}
        description="All data integrity assessments — scope, status, and findings summary across all completed and in-progress runs."
      >
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={() => void loadAssessments()} disabled={loading}>
              Refresh
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>scope</TableHead>
                  <TableHead>scope ID</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>created date</TableHead>
                  <TableHead>attributable</TableHead>
                  <TableHead>legible</TableHead>
                  <TableHead>complete</TableHead>
                  <TableHead>available</TableHead>
                  <TableHead className="text-right">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assessments.map((assessment) => {
                  const id = rowId(assessment)
                  return (
                    <TableRow key={id || JSON.stringify(assessment)}>
                      <TableCell className="font-medium">{readStr(assessment.scope) || "-"}</TableCell>
                      <TableCell>{readStr(assessment.scope_id) || "-"}</TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(assessment.assessment_status)}>
                          {readStr(assessment.assessment_status) || "-"}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatDate(assessment.created_at)}</TableCell>
                      <TableCell>{readStr(assessment.attributable_status) || "-"}</TableCell>
                      <TableCell>{readStr(assessment.legible_status) || "-"}</TableCell>
                      <TableCell>{readStr(assessment.complete_status) || "-"}</TableCell>
                      <TableCell>{readStr(assessment.available_status) || "-"}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant={selectedId === id ? "secondary" : "outline"}
                          size="sm"
                          onClick={() => void loadDetail(id)}
                          disabled={!id || detailLoading}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!assessments.length ? (
                  <TableRow>
                    <TableCell colSpan={9} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading data integrity assessments..." : "No data integrity assessments found."}
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </div>
      </ModuleCard>
    </div>
  )
}
