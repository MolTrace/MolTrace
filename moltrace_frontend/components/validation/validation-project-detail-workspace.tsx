"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
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
import { ArrowLeft, Layers3, ServerOff, ShieldCheck } from "lucide-react"
import { ValidationTraceabilityMatrixPanel } from "@/components/validation/validation-traceability-matrix-panel"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"

type Row = Record<string, unknown>

const MODULE_OPTIONS = [
  "spectracheck",
  "regulatory_hub",
  "reaction_optimization",
  "cross_module",
  "system",
  "mobile",
  "ai_ml",
  "connectors",
] as const

const CRITICALITY_OPTIONS = ["low", "medium", "high", "critical"] as const
const GXP_IMPACT_OPTIONS = ["none", "indirect", "direct", "unknown"] as const
const SPEC_STATUS_OPTIONS = ["draft", "approved", "retired"] as const
const RISK_TARGET_TYPE_OPTIONS = [
  "requirement",
  "function",
  "module",
  "workflow",
  "connector",
  "ai_model",
  "report",
  "mobile",
  "system",
] as const
const RISK_LEVEL_OPTIONS = ["low", "medium", "high", "critical"] as const
const PROBABILITY_OPTIONS = ["low", "medium", "high", "unknown"] as const
const TESTING_RIGOR_OPTIONS = [
  "scripted",
  "unscripted",
  "exploratory",
  "automated",
  "supplier_evidence",
] as const
const RISK_STATUS_OPTIONS = ["open", "mitigated", "accepted", "rejected"] as const
const PROTOCOL_TYPE_OPTIONS = [
  "installation",
  "operational",
  "performance",
  "regression",
  "security",
  "data_integrity",
  "electronic_signature",
  "ai_model",
  "connector",
  "mobile",
] as const
const PROTOCOL_STATUS_OPTIONS = ["draft", "approved", "executed", "failed", "archived"] as const
const TEST_CASE_STATUS_OPTIONS = ["draft", "approved", "executed", "retired"] as const
const EXECUTION_STATUS_OPTIONS = ["pass", "fail", "blocked", "not_run", "requires_review"] as const

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
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
  for (const key of [...keys, "project", "validation_project", "record", "data"]) {
    const value = payload[key]
    if (isRecord(value)) return value
  }
  return payload
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  if (typeof v === "boolean") return String(v)
  return ""
}

function readFirst(row: Row | null | undefined, keys: string[]): string {
  if (!row) return ""
  for (const key of keys) {
    const value = readStr(row[key])
    if (value) return value
  }
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.max(0, Math.floor(v))
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.max(0, Math.floor(Number(v)))
  return null
}

function rowId(row: Row | null | undefined): string {
  return readFirst(row, ["id", "protocol_id", "test_case_id", "execution_id"])
}

function countFrom(row: Row | null, keys: string[], fallbackRows: Row[] = []): number {
  if (row) {
    for (const key of keys) {
      const n = readNum(row[key])
      if (n != null) return n
    }
  }
  return fallbackRows.length
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function formatValue(value: unknown, maxLen = 220): string {
  if (value == null || value === "") return "-"
  if (typeof value === "string") return value.trim() || "-"
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  const text = JSON.stringify(value)
  return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text
}

function parseJsonField(raw: string, label: string): unknown {
  const text = raw.trim()
  if (!text) return []
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`${label} must be valid JSON.`)
  }
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s.includes("fail") || s.includes("error") || s.includes("rejected")) return "border-destructive/40 text-destructive"
  if (s.includes("review") || s.includes("warning") || s.includes("open") || s.includes("blocked")) {
    return "border-warning/50 text-warning"
  }
  return "text-muted-foreground"
}

function Field({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm">{formatValue(value)}</p>
    </div>
  )
}

type StatAccent = "cyan" | "amber" | "red" | "green" | "violet"

const STAT_ACCENT_VAR: Record<StatAccent, string> = {
  cyan: "var(--mt-green)",
  amber: "var(--mt-amber)",
  red: "var(--mt-red)",
  green: "var(--mt-green)",
  violet: "var(--mt-violet)",
}

function StatCard({
  title,
  value,
  accent = "cyan",
}: {
  title: string
  value: string | number
  accent?: StatAccent
}) {
  const color = STAT_ACCENT_VAR[accent]
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: `3px solid ${color}` }}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
        <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="pb-5">
        <div
          className="font-mono text-3xl font-bold tabular-nums leading-none"
          style={{ color }}
        >
          {value}
        </div>
      </CardContent>
    </Card>
  )
}

function FormSelect({
  id,
  label,
  value,
  onValueChange,
  options,
}: {
  id: string
  label: string
  value: string
  onValueChange: (value: string) => void
  options: readonly string[]
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
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
            rows.map((row, idx) => (
              <TableRow key={readFirst(row, ["id", "uuid", "code"]) || `row-${idx}`}>
                {columns.map((column) => {
                  const value = readFirst(row, column.keys ?? [column.key]) || formatValue(row[column.key])
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

function extractNestedRows(project: Row | null, keys: string[]): Row[] {
  if (!project) return []
  for (const key of keys) {
    const value = project[key]
    if (Array.isArray(value)) return value.filter(isRecord)
    if (isRecord(value)) return asRows(value)
  }
  return []
}

function executionRowsFromProtocols(protocols: Row[]): Row[] {
  const out: Row[] = []
  for (const protocol of protocols) {
    for (const protocolKey of ["test_cases", "test_cases_json", "cases"]) {
      const cases = asRows(protocol[protocolKey])
      for (const testCase of cases) {
        const executions = asRows(testCase.executions ?? testCase.test_executions ?? testCase.execution_rows)
        if (executions.length === 0) continue
        for (const execution of executions) {
          out.push({
            ...execution,
            protocol_code: protocol.protocol_code,
            test_case_code: testCase.test_case_code,
            title: testCase.title,
          })
        }
      }
    }
  }
  return out
}

function traceabilityRecord(payload: unknown): Row | null {
  if (Array.isArray(payload)) return payload.find(isRecord) ?? null
  return unwrapRecord(payload, ["traceability", "traceability_matrix", "matrix"])
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[36rem] overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[10px] leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function ValidationProjectDetailWorkspace() {
  const params = useParams()
  const rawId = params?.validationProjectId
  const validationProjectId = typeof rawId === "string" ? rawId : Array.isArray(rawId) ? rawId[0] : ""

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [projectRaw, setProjectRaw] = useState<unknown>(null)
  const [ursRaw, setUrsRaw] = useState<unknown>(null)
  const [functionalSpecsRaw, setFunctionalSpecsRaw] = useState<unknown>(null)
  const [riskRaw, setRiskRaw] = useState<unknown>(null)
  const [protocolsRaw, setProtocolsRaw] = useState<unknown>(null)
  const [traceabilityRaw, setTraceabilityRaw] = useState<unknown>(null)

  const [ursRequirementCode, setUrsRequirementCode] = useState("")
  const [ursModule, setUrsModule] = useState<string>("spectracheck")
  const [ursRequirementText, setUrsRequirementText] = useState("")
  const [ursCriticality, setUrsCriticality] = useState<string>("medium")
  const [ursGxpImpact, setUrsGxpImpact] = useState<string>("unknown")
  const [ursStatus, setUrsStatus] = useState<string>("draft")
  const [ursBusy, setUrsBusy] = useState(false)
  const [ursError, setUrsError] = useState("")

  const [fsRequirementId, setFsRequirementId] = useState("__none__")
  const [fsFunctionCode, setFsFunctionCode] = useState("")
  const [fsFunctionName, setFsFunctionName] = useState("")
  const [fsFunctionDescription, setFsFunctionDescription] = useState("")
  const [fsExpectedBehavior, setFsExpectedBehavior] = useState("")
  const [fsModule, setFsModule] = useState<string>("spectracheck")
  const [fsStatus, setFsStatus] = useState<string>("draft")
  const [fsBusy, setFsBusy] = useState(false)
  const [fsError, setFsError] = useState("")

  const [riskTargetType, setRiskTargetType] = useState<string>("requirement")
  const [riskTargetId, setRiskTargetId] = useState("")
  const [riskDescription, setRiskDescription] = useState("")
  const [riskSeverity, setRiskSeverity] = useState<string>("medium")
  const [riskProbability, setRiskProbability] = useState<string>("unknown")
  const [riskDetectability, setRiskDetectability] = useState<string>("unknown")
  const [riskMitigation, setRiskMitigation] = useState("")
  const [riskTestingRigor, setRiskTestingRigor] = useState<string>("scripted")
  const [riskStatus, setRiskStatus] = useState<string>("open")
  const [riskBusy, setRiskBusy] = useState(false)
  const [riskError, setRiskError] = useState("")

  const [protocolCode, setProtocolCode] = useState("")
  const [protocolTitle, setProtocolTitle] = useState("")
  const [protocolModule, setProtocolModule] = useState<string>("spectracheck")
  const [protocolType, setProtocolType] = useState<string>("operational")
  const [protocolStatus, setProtocolStatus] = useState<string>("draft")
  const [protocolBusy, setProtocolBusy] = useState(false)
  const [protocolError, setProtocolError] = useState("")
  const [selectedProtocolId, setSelectedProtocolId] = useState("")
  const [protocolDetailRaw, setProtocolDetailRaw] = useState<unknown>(null)
  const [protocolDetailLoading, setProtocolDetailLoading] = useState(false)
  const [protocolDetailError, setProtocolDetailError] = useState("")

  const [testCasesRaw, setTestCasesRaw] = useState<unknown>(null)
  const [testCasesLoading, setTestCasesLoading] = useState(false)
  const [testCasesError, setTestCasesError] = useState("")
  const [testCaseCode, setTestCaseCode] = useState("")
  const [testCaseTitle, setTestCaseTitle] = useState("")
  const [testCasePreconditions, setTestCasePreconditions] = useState("")
  const [testCaseStepsJson, setTestCaseStepsJson] = useState("[]")
  const [testCaseExpectedResults, setTestCaseExpectedResults] = useState("")
  const [testCaseLinkedRequirementsJson, setTestCaseLinkedRequirementsJson] = useState("[]")
  const [testCaseLinkedRisksJson, setTestCaseLinkedRisksJson] = useState("[]")
  const [testCaseStatus, setTestCaseStatus] = useState<string>("draft")
  const [testCaseBusy, setTestCaseBusy] = useState(false)
  const [testCaseError, setTestCaseError] = useState("")
  const [selectedTestCaseId, setSelectedTestCaseId] = useState("")

  const [executionsRaw, setExecutionsRaw] = useState<unknown>(null)
  const [executionsLoading, setExecutionsLoading] = useState(false)
  const [executionsError, setExecutionsError] = useState("")
  const [selectedExecutionId, setSelectedExecutionId] = useState("")
  const [executionDetailRaw, setExecutionDetailRaw] = useState<unknown>(null)
  const [executionDetailLoading, setExecutionDetailLoading] = useState(false)
  const [executionDetailError, setExecutionDetailError] = useState("")
  const [executedBy, setExecutedBy] = useState("")
  const [executionStatus, setExecutionStatus] = useState<string>("pass")
  const [actualResults, setActualResults] = useState("")
  const [evidenceFileIdsJson, setEvidenceFileIdsJson] = useState("[]")
  const [evidenceArtifactIdsJson, setEvidenceArtifactIdsJson] = useState("[]")
  const [executionBusy, setExecutionBusy] = useState(false)
  const [executionError, setExecutionError] = useState("")

  const load = useCallback(async () => {
    const id = validationProjectId.trim()
    if (!id) {
      setLoading(false)
      setError("Missing validation project id.")
      return
    }
    setLoading(true)
    setError("")
    try {
      const encoded = encodeURIComponent(id)
      const [project, urs, functionalSpecs, risks, protocols, traceability] = await Promise.all([
        apiFetch<unknown>(`/validation-center/projects/${encoded}`, { method: "GET" }),
        apiFetch<unknown>(`/validation-center/projects/${encoded}/urs`, { method: "GET" }),
        apiFetch<unknown>(`/validation-center/projects/${encoded}/functional-specs`, { method: "GET" }),
        apiFetch<unknown>(`/validation-center/projects/${encoded}/risk-assessment`, { method: "GET" }),
        apiFetch<unknown>(`/validation-center/projects/${encoded}/test-protocols`, { method: "GET" }),
        apiFetch<unknown>(`/validation-center/projects/${encoded}/traceability`, { method: "GET" }),
      ])
      setProjectRaw(project)
      setUrsRaw(urs)
      setFunctionalSpecsRaw(functionalSpecs)
      setRiskRaw(risks)
      setProtocolsRaw(protocols)
      setTraceabilityRaw(traceability)
    } catch (e) {
      setError(formatErr(e, "Could not load validation project detail."))
      setProjectRaw(null)
      setUrsRaw(null)
      setFunctionalSpecsRaw(null)
      setRiskRaw(null)
      setProtocolsRaw(null)
      setTraceabilityRaw(null)
    } finally {
      setLoading(false)
    }
  }, [validationProjectId])

  useEffect(() => {
    void load()
  }, [load])

  const loadProtocolDetail = useCallback(async (protocolId: string) => {
    const id = protocolId.trim()
    if (!id) {
      setProtocolDetailRaw(null)
      setProtocolDetailError("")
      return
    }
    setProtocolDetailLoading(true)
    setProtocolDetailError("")
    try {
      const payload = await apiFetch<unknown>(`/validation-center/test-protocols/${encodeURIComponent(id)}`, {
        method: "GET",
      })
      setProtocolDetailRaw(payload)
    } catch (err) {
      setProtocolDetailRaw(null)
      setProtocolDetailError(formatErr(err, "Could not load test protocol detail."))
    } finally {
      setProtocolDetailLoading(false)
    }
  }, [])

  const loadTestCases = useCallback(async (protocolId: string) => {
    const id = protocolId.trim()
    if (!id) {
      setTestCasesRaw(null)
      setTestCasesError("")
      return
    }
    setTestCasesLoading(true)
    setTestCasesError("")
    try {
      const payload = await apiFetch<unknown>(`/validation-center/test-protocols/${encodeURIComponent(id)}/test-cases`, {
        method: "GET",
      })
      setTestCasesRaw(payload)
    } catch (err) {
      setTestCasesRaw(null)
      setTestCasesError(formatErr(err, "Could not load test cases."))
    } finally {
      setTestCasesLoading(false)
    }
  }, [])

  const loadExecutions = useCallback(async () => {
    setExecutionsLoading(true)
    setExecutionsError("")
    try {
      const payload = await apiFetch<unknown>("/validation-center/test-executions", { method: "GET" })
      setExecutionsRaw(payload)
    } catch (err) {
      setExecutionsRaw(null)
      setExecutionsError(formatErr(err, "Could not load test executions."))
    } finally {
      setExecutionsLoading(false)
    }
  }, [])

  const loadExecutionDetail = useCallback(async (executionId: string) => {
    const id = executionId.trim()
    if (!id) {
      setExecutionDetailRaw(null)
      setExecutionDetailError("")
      return
    }
    setExecutionDetailLoading(true)
    setExecutionDetailError("")
    try {
      const payload = await apiFetch<unknown>(`/validation-center/test-executions/${encodeURIComponent(id)}`, {
        method: "GET",
      })
      setExecutionDetailRaw(payload)
    } catch (err) {
      setExecutionDetailRaw(null)
      setExecutionDetailError(formatErr(err, "Could not load test execution detail."))
    } finally {
      setExecutionDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadExecutions()
  }, [loadExecutions])

  const project = useMemo(() => unwrapRecord(projectRaw, ["validation_project", "project"]), [projectRaw])
  const ursRows = useMemo(() => asRows(ursRaw, ["urs", "requirements", "user_requirements"]), [ursRaw])
  const functionalSpecRows = useMemo(
    () => asRows(functionalSpecsRaw, ["functional_specs", "specs", "functional_specifications"]),
    [functionalSpecsRaw],
  )
  const riskRows = useMemo(() => asRows(riskRaw, ["risk_assessments", "risks", "risk_assessment"]), [riskRaw])
  const protocolRows = useMemo(
    () => asRows(protocolsRaw, ["test_protocols", "protocols", "validation_test_protocols"]),
    [protocolsRaw],
  )
  const nestedExecutionRows = useMemo(() => executionRowsFromProtocols(protocolRows), [protocolRows])
  const protocolDetail = useMemo(() => unwrapRecord(protocolDetailRaw, ["test_protocol", "protocol"]), [protocolDetailRaw])
  const testCaseRows = useMemo(() => asRows(testCasesRaw, ["test_cases", "cases", "validation_test_cases"]), [testCasesRaw])
  const executionRows = useMemo(
    () => asRows(executionsRaw, ["test_executions", "executions", "validation_test_executions"]),
    [executionsRaw],
  )
  const displayedExecutionRows = executionRows.length > 0 ? executionRows : nestedExecutionRows
  const executionDetail = useMemo(
    () => unwrapRecord(executionDetailRaw, ["test_execution", "execution"]),
    [executionDetailRaw],
  )
  const traceability = useMemo(() => traceabilityRecord(traceabilityRaw), [traceabilityRaw])

  const signaturesRows = useMemo(
    () => extractNestedRows(project, ["signatures", "signature_records", "e_signature_records", "esignatures"]),
    [project],
  )
  const deviationsRows = useMemo(() => extractNestedRows(project, ["deviations", "deviation_records"]), [project])
  const capaRows = useMemo(() => extractNestedRows(project, ["capa", "capa_records", "capa_items"]), [project])
  const inspectionRows = useMemo(
    () => extractNestedRows(project, ["inspection_packages", "inspection_readiness_packages"]),
    [project],
  )

  useEffect(() => {
    const ids = protocolRows.map(rowId).filter(Boolean)
    if (ids.length === 0) {
      if (selectedProtocolId) setSelectedProtocolId("")
      return
    }
    if (!selectedProtocolId || !ids.includes(selectedProtocolId)) setSelectedProtocolId(ids[0]!)
  }, [protocolRows, selectedProtocolId])

  useEffect(() => {
    void loadProtocolDetail(selectedProtocolId)
    void loadTestCases(selectedProtocolId)
  }, [selectedProtocolId, loadProtocolDetail, loadTestCases])

  useEffect(() => {
    const ids = testCaseRows.map(rowId).filter(Boolean)
    if (ids.length === 0) {
      if (selectedTestCaseId) setSelectedTestCaseId("")
      return
    }
    if (!selectedTestCaseId || !ids.includes(selectedTestCaseId)) setSelectedTestCaseId(ids[0]!)
  }, [testCaseRows, selectedTestCaseId])

  useEffect(() => {
    const ids = displayedExecutionRows.map(rowId).filter(Boolean)
    if (ids.length === 0) {
      if (selectedExecutionId) setSelectedExecutionId("")
      return
    }
    if (!selectedExecutionId || !ids.includes(selectedExecutionId)) setSelectedExecutionId(ids[0]!)
  }, [displayedExecutionRows, selectedExecutionId])

  useEffect(() => {
    void loadExecutionDetail(selectedExecutionId)
  }, [selectedExecutionId, loadExecutionDetail])

  const openRiskRows = useMemo(
    () => riskRows.filter((row) => readFirst(row, ["status"]).toLowerCase() === "open"),
    [riskRows],
  )
  const failedExecutionRows = useMemo(
    () => displayedExecutionRows.filter((row) => readFirst(row, ["execution_status", "status"]).toLowerCase() === "fail"),
    [displayedExecutionRows],
  )

  const coverageSummary =
    traceability?.coverage_summary_json ??
    traceability?.coverage_summary ??
    project?.coverage_summary_json ??
    project?.coverage_summary ??
    "-"

  const summary = {
    coverage: formatValue(coverageSummary, 90),
    openRisks: countFrom(project, ["open_risks_count", "open_risk_count"], openRiskRows),
    failedTests: countFrom(project, ["failed_tests_count", "failed_test_count"], failedExecutionRows),
    signatures: countFrom(project, ["signatures_count", "signature_count", "e_signature_count"], signaturesRows),
    controlledRecords: countFrom(project, ["controlled_records_count", "controlled_record_count"]),
  }

  const developerBundle = {
    project: projectRaw,
    urs: ursRaw,
    functional_specs: functionalSpecsRaw,
    risk_assessment: riskRaw,
    test_protocols: protocolsRaw,
    selected_protocol_detail: protocolDetailRaw,
    selected_protocol_test_cases: testCasesRaw,
    test_executions: executionsRaw,
    selected_execution_detail: executionDetailRaw,
    traceability: traceabilityRaw,
  }

  const requirementOptions = useMemo(
    () =>
      ursRows
        .map((row, index) => ({
          id: readFirst(row, ["id", "requirement_id", "validation_requirement_id"]) || "",
          label:
            readFirst(row, ["requirement_code", "code"]) ||
            readFirst(row, ["requirement_text", "title"]) ||
            `requirement-${index + 1}`,
        }))
        .filter((option) => option.id),
    [ursRows],
  )
  const selectedProtocol = useMemo(
    () => protocolRows.find((row) => rowId(row) === selectedProtocolId) ?? null,
    [protocolRows, selectedProtocolId],
  )
  const selectedTestCase = useMemo(
    () => testCaseRows.find((row) => rowId(row) === selectedTestCaseId) ?? null,
    [testCaseRows, selectedTestCaseId],
  )

  async function createUrsRequirement() {
    const id = validationProjectId.trim()
    if (!id) return
    setUrsBusy(true)
    setUrsError("")
    try {
      await apiFetch(`/validation-center/projects/${encodeURIComponent(id)}/urs`, {
        method: "POST",
        body: {
          requirement_code: ursRequirementCode.trim(),
          module: ursModule,
          requirement_text: ursRequirementText.trim(),
          criticality: ursCriticality,
          gxp_impact: ursGxpImpact,
          status: ursStatus,
        },
      })
      setUrsRequirementCode("")
      setUrsRequirementText("")
      await load()
    } catch (err) {
      setUrsError(formatErr(err, "Create URS requirement failed."))
    } finally {
      setUrsBusy(false)
    }
  }

  async function createFunctionalSpec() {
    const id = validationProjectId.trim()
    if (!id) return
    setFsBusy(true)
    setFsError("")
    try {
      await apiFetch(`/validation-center/projects/${encodeURIComponent(id)}/functional-specs`, {
        method: "POST",
        body: {
          requirement_id: fsRequirementId === "__none__" ? null : fsRequirementId,
          function_code: fsFunctionCode.trim(),
          function_name: fsFunctionName.trim(),
          function_description: fsFunctionDescription.trim(),
          expected_behavior: fsExpectedBehavior.trim(),
          module: fsModule,
          status: fsStatus,
        },
      })
      setFsRequirementId("__none__")
      setFsFunctionCode("")
      setFsFunctionName("")
      setFsFunctionDescription("")
      setFsExpectedBehavior("")
      await load()
    } catch (err) {
      setFsError(formatErr(err, "Create functional spec failed."))
    } finally {
      setFsBusy(false)
    }
  }

  async function createRiskAssessment() {
    const id = validationProjectId.trim()
    if (!id) return
    setRiskBusy(true)
    setRiskError("")
    try {
      await apiFetch(`/validation-center/projects/${encodeURIComponent(id)}/risk-assessment`, {
        method: "POST",
        body: {
          target_type: riskTargetType,
          target_id: riskTargetId.trim() || null,
          risk_description: riskDescription.trim(),
          severity: riskSeverity,
          probability: riskProbability,
          detectability: riskDetectability,
          mitigation: riskMitigation.trim(),
          testing_rigor: riskTestingRigor,
          status: riskStatus,
        },
      })
      setRiskTargetId("")
      setRiskDescription("")
      setRiskMitigation("")
      await load()
    } catch (err) {
      setRiskError(formatErr(err, "Create risk assessment failed."))
    } finally {
      setRiskBusy(false)
    }
  }

  async function createTestProtocol() {
    const id = validationProjectId.trim()
    if (!id) return
    setProtocolBusy(true)
    setProtocolError("")
    try {
      await apiFetch(`/validation-center/projects/${encodeURIComponent(id)}/test-protocols`, {
        method: "POST",
        body: {
          protocol_code: protocolCode.trim(),
          title: protocolTitle.trim(),
          module: protocolModule,
          protocol_type: protocolType,
          status: protocolStatus,
        },
      })
      setProtocolCode("")
      setProtocolTitle("")
      await load()
    } catch (err) {
      setProtocolError(formatErr(err, "Create test protocol failed."))
    } finally {
      setProtocolBusy(false)
    }
  }

  async function createTestCase() {
    const protocolId = selectedProtocolId.trim()
    if (!protocolId) {
      setTestCaseError("Open a protocol before creating test cases.")
      return
    }
    let stepsJson: unknown
    let linkedRequirementIdsJson: unknown
    let linkedRiskIdsJson: unknown
    try {
      stepsJson = parseJsonField(testCaseStepsJson, "steps JSON")
      linkedRequirementIdsJson = parseJsonField(testCaseLinkedRequirementsJson, "linked requirements")
      linkedRiskIdsJson = parseJsonField(testCaseLinkedRisksJson, "linked risks")
    } catch (err) {
      setTestCaseError(err instanceof Error ? err.message : "Invalid test case JSON.")
      return
    }

    setTestCaseBusy(true)
    setTestCaseError("")
    try {
      await apiFetch(`/validation-center/test-protocols/${encodeURIComponent(protocolId)}/test-cases`, {
        method: "POST",
        body: {
          test_case_code: testCaseCode.trim(),
          title: testCaseTitle.trim(),
          preconditions: testCasePreconditions.trim(),
          steps_json: stepsJson,
          expected_results: testCaseExpectedResults.trim(),
          linked_requirement_ids_json: linkedRequirementIdsJson,
          linked_risk_ids_json: linkedRiskIdsJson,
          status: testCaseStatus,
        },
      })
      setTestCaseCode("")
      setTestCaseTitle("")
      setTestCasePreconditions("")
      setTestCaseStepsJson("[]")
      setTestCaseExpectedResults("")
      setTestCaseLinkedRequirementsJson("[]")
      setTestCaseLinkedRisksJson("[]")
      await loadTestCases(protocolId)
    } catch (err) {
      setTestCaseError(formatErr(err, "Create test case failed."))
    } finally {
      setTestCaseBusy(false)
    }
  }

  async function executeTestCase() {
    const testCaseId = selectedTestCaseId.trim()
    if (!testCaseId) {
      setExecutionError("Open a test case before executing.")
      return
    }
    let evidenceFileIds: unknown
    let evidenceArtifactIds: unknown
    try {
      evidenceFileIds = parseJsonField(evidenceFileIdsJson, "evidence file IDs")
      evidenceArtifactIds = parseJsonField(evidenceArtifactIdsJson, "evidence artifact IDs")
    } catch (err) {
      setExecutionError(err instanceof Error ? err.message : "Invalid execution JSON.")
      return
    }

    setExecutionBusy(true)
    setExecutionError("")
    try {
      const payload = await apiFetch<unknown>(`/validation-center/test-cases/${encodeURIComponent(testCaseId)}/execute`, {
        method: "POST",
        body: {
          executed_by: executedBy.trim(),
          execution_status: executionStatus,
          actual_results: actualResults.trim(),
          evidence_file_ids_json: evidenceFileIds,
          evidence_artifact_ids_json: evidenceArtifactIds,
        },
      })
      const execution = unwrapRecord(payload, ["test_execution", "execution"])
      const nextExecutionId = rowId(execution)
      if (nextExecutionId) setSelectedExecutionId(nextExecutionId)
      setActualResults("")
      setEvidenceFileIdsJson("[]")
      setEvidenceArtifactIdsJson("[]")
      await loadExecutions()
      if (selectedProtocolId) await loadTestCases(selectedProtocolId)
    } catch (err) {
      setExecutionError(formatErr(err, "Execute test case failed."))
    } finally {
      setExecutionBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <Button type="button" variant="ghost" size="sm" className="h-8 px-2" asChild>
            <Link href="/validation-center">
              <ArrowLeft className="mr-1 h-3.5 w-3.5" aria-hidden />
              Back
            </Link>
          </Button>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-green)" }}
          >
            MolTrace · Validation Project
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">
            {readFirst(project, ["title", "name"]) || "Validation project"}
          </h1>
          <p className="font-mono text-xs text-muted-foreground break-all">{validationProjectId || "-"}</p>
          <p className="text-sm text-muted-foreground">
            Validation readiness details. Status labels are shown as returned by the API.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading validation project...</p> : null}
      {!loading && error ? (
        <AlertCard variant="error" icon={ServerOff} title="Could not load project" description={error} />
      ) : null}

      {!loading && !error ? (
        <Tabs defaultValue="overview" className="space-y-6">
          <TabsList className="flex h-auto flex-wrap justify-start">
            <TabsTrigger value="overview" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Overview</TabsTrigger>
            <TabsTrigger value="urs" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">URS</TabsTrigger>
            <TabsTrigger value="functional_specs" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Functional Specs</TabsTrigger>
            <TabsTrigger value="risk_assessment" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Risk Assessment</TabsTrigger>
            <TabsTrigger value="test_protocols" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Test Protocols</TabsTrigger>
            <TabsTrigger value="test_executions" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Test Executions</TabsTrigger>
            <TabsTrigger value="traceability" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Traceability</TabsTrigger>
            <TabsTrigger value="esignatures" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">e-Signatures</TabsTrigger>
            <TabsTrigger value="deviations_capa" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Deviations / CAPA</TabsTrigger>
            <TabsTrigger value="inspection_package" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Inspection Package</TabsTrigger>
            <TabsTrigger value="developer_json" className="font-mono data-[state=active]:[background-color:var(--mt-green)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground">Developer JSON</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard title="Coverage summary" value={summary.coverage} accent="cyan" />
              <StatCard title="Open risks" value={summary.openRisks} accent="amber" />
              <StatCard title="Failed tests" value={summary.failedTests} accent="red" />
              <StatCard title="Signatures" value={summary.signatures} accent="green" />
              <StatCard title="Controlled records" value={summary.controlledRecords} accent="cyan" />
            </div>

            <ModuleCard
              accent="cyan"
              eyebrow="Overview"
              title="Project overview"
              icon={ShieldCheck}
              description="Summary of the selected validation project — scope, status, intended use, and regulated context."
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="validation scope" value={readFirst(project, ["scope"])} />
                <Field label="status" value={readFirst(project, ["status"])} />
                <Field label="intended use" value={readFirst(project, ["intended_use"])} />
                <Field label="regulated context" value={readFirst(project, ["regulated_context"])} />
              </div>
            </ModuleCard>

            <ModuleCard
              accent="cyan"
              eyebrow="Module Order"
              title="Module order"
              icon={Layers3}
              description="Global product order for validation readiness views."
            >
              <div className="space-y-2 text-sm">
                <div className="rounded-md border bg-muted/20 px-3 py-2">
                  SpectraCheck {" -> "} Regentry {" -> "} Reaction Optimization
                </div>
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="urs" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Create URS requirement</CardTitle>
                <CardDescription>
                  Add a User Requirement Specification entry — specify requirement code, text, module, criticality, and GxP impact.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {ursError ? <p className="text-xs text-destructive">{ursError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor="urs-requirement-code">requirement code</Label>
                    <Input
                      id="urs-requirement-code"
                      value={ursRequirementCode}
                      onChange={(event) => setUrsRequirementCode(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="urs-module"
                    label="module"
                    value={ursModule}
                    onValueChange={setUrsModule}
                    options={MODULE_OPTIONS}
                  />
                  <FormSelect
                    id="urs-criticality"
                    label="criticality"
                    value={ursCriticality}
                    onValueChange={setUrsCriticality}
                    options={CRITICALITY_OPTIONS}
                  />
                  <FormSelect
                    id="urs-gxp-impact"
                    label="GxP impact"
                    value={ursGxpImpact}
                    onValueChange={setUrsGxpImpact}
                    options={GXP_IMPACT_OPTIONS}
                  />
                  <FormSelect
                    id="urs-status"
                    label="status"
                    value={ursStatus}
                    onValueChange={setUrsStatus}
                    options={SPEC_STATUS_OPTIONS}
                  />
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="urs-requirement-text">requirement text</Label>
                    <Textarea
                      id="urs-requirement-text"
                      value={ursRequirementText}
                      onChange={(event) => setUrsRequirementText(event.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
                <Button type="button" disabled={ursBusy} onClick={() => void createUrsRequirement()}>
                  {ursBusy ? "Creating..." : "Create URS requirement"}
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">URS</CardTitle>
                <CardDescription>
                  URS entries for this validation project — requirement code, module, criticality, GxP impact, and approval status.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={ursRows}
                  empty="No URS rows returned."
                  columns={[
                    { key: "requirement_code", label: "requirement code" },
                    { key: "module", label: "module" },
                    { key: "criticality", label: "criticality" },
                    { key: "gxp_impact", label: "gxp impact" },
                    { key: "status", label: "status" },
                    { key: "requirement_text", label: "requirement text" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="functional_specs" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Create functional spec</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    POST /validation-center/projects/{"{validation_project_id}"}/functional-specs
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {fsError ? <p className="text-xs text-destructive">{fsError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor="fs-linked-requirement">linked requirement</Label>
                    <Select value={fsRequirementId} onValueChange={setFsRequirementId}>
                      <SelectTrigger id="fs-linked-requirement">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">None</SelectItem>
                        {requirementOptions.map((option) => (
                          <SelectItem key={option.id} value={option.id}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="fs-function-code">function code</Label>
                    <Input
                      id="fs-function-code"
                      value={fsFunctionCode}
                      onChange={(event) => setFsFunctionCode(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="fs-function-name">function name</Label>
                    <Input
                      id="fs-function-name"
                      value={fsFunctionName}
                      onChange={(event) => setFsFunctionName(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="fs-module"
                    label="module"
                    value={fsModule}
                    onValueChange={setFsModule}
                    options={MODULE_OPTIONS}
                  />
                  <FormSelect
                    id="fs-status"
                    label="status"
                    value={fsStatus}
                    onValueChange={setFsStatus}
                    options={SPEC_STATUS_OPTIONS}
                  />
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="fs-function-description">function description</Label>
                    <Textarea
                      id="fs-function-description"
                      value={fsFunctionDescription}
                      onChange={(event) => setFsFunctionDescription(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="fs-expected-behavior">expected behavior</Label>
                    <Textarea
                      id="fs-expected-behavior"
                      value={fsExpectedBehavior}
                      onChange={(event) => setFsExpectedBehavior(event.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
                <Button type="button" disabled={fsBusy} onClick={() => void createFunctionalSpec()}>
                  {fsBusy ? "Creating..." : "Create functional spec"}
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Functional Specs</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    GET /validation-center/projects/{"{validation_project_id}"}/functional-specs
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={functionalSpecRows}
                  empty="No functional specs returned."
                  columns={[
                    { key: "requirement_id", label: "linked requirement", keys: ["requirement_id", "linked_requirement_id"] },
                    { key: "function_code", label: "function code" },
                    { key: "function_name", label: "function name" },
                    { key: "function_description", label: "function description" },
                    { key: "module", label: "module" },
                    { key: "status", label: "status" },
                    { key: "expected_behavior", label: "expected behavior" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="risk_assessment" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Create risk assessment</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    POST /validation-center/projects/{"{validation_project_id}"}/risk-assessment
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {riskError ? <p className="text-xs text-destructive">{riskError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <FormSelect
                    id="risk-target-type"
                    label="target type"
                    value={riskTargetType}
                    onValueChange={setRiskTargetType}
                    options={RISK_TARGET_TYPE_OPTIONS}
                  />
                  <div className="space-y-1">
                    <Label htmlFor="risk-target-id">target ID optional</Label>
                    <Input
                      id="risk-target-id"
                      value={riskTargetId}
                      onChange={(event) => setRiskTargetId(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="risk-severity"
                    label="severity"
                    value={riskSeverity}
                    onValueChange={setRiskSeverity}
                    options={RISK_LEVEL_OPTIONS}
                  />
                  <FormSelect
                    id="risk-probability"
                    label="probability"
                    value={riskProbability}
                    onValueChange={setRiskProbability}
                    options={PROBABILITY_OPTIONS}
                  />
                  <FormSelect
                    id="risk-detectability"
                    label="detectability"
                    value={riskDetectability}
                    onValueChange={setRiskDetectability}
                    options={PROBABILITY_OPTIONS}
                  />
                  <FormSelect
                    id="risk-testing-rigor"
                    label="testing rigor"
                    value={riskTestingRigor}
                    onValueChange={setRiskTestingRigor}
                    options={TESTING_RIGOR_OPTIONS}
                  />
                  <FormSelect
                    id="risk-status"
                    label="status"
                    value={riskStatus}
                    onValueChange={setRiskStatus}
                    options={RISK_STATUS_OPTIONS}
                  />
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="risk-description">risk description</Label>
                    <Textarea
                      id="risk-description"
                      value={riskDescription}
                      onChange={(event) => setRiskDescription(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="risk-mitigation">mitigation</Label>
                    <Textarea
                      id="risk-mitigation"
                      value={riskMitigation}
                      onChange={(event) => setRiskMitigation(event.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
                <Button type="button" disabled={riskBusy} onClick={() => void createRiskAssessment()}>
                  {riskBusy ? "Creating..." : "Create risk assessment"}
                </Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Risk Assessment</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    GET /validation-center/projects/{"{validation_project_id}"}/risk-assessment
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={riskRows}
                  empty="No risk assessment rows returned."
                  columns={[
                    { key: "target_type", label: "target type" },
                    { key: "target_id", label: "target ID" },
                    { key: "severity", label: "severity" },
                    { key: "probability", label: "probability" },
                    { key: "detectability", label: "detectability" },
                    { key: "testing_rigor", label: "testing rigor" },
                    { key: "status", label: "status" },
                    { key: "risk_description", label: "risk description" },
                    { key: "mitigation", label: "mitigation" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="test_protocols" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Create test protocol</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    POST /validation-center/projects/{"{validation_project_id}"}/test-protocols
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {protocolError ? <p className="text-xs text-destructive">{protocolError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor="protocol-code">protocol code</Label>
                    <Input
                      id="protocol-code"
                      value={protocolCode}
                      onChange={(event) => setProtocolCode(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="protocol-title">title</Label>
                    <Input
                      id="protocol-title"
                      value={protocolTitle}
                      onChange={(event) => setProtocolTitle(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="protocol-module"
                    label="module"
                    value={protocolModule}
                    onValueChange={setProtocolModule}
                    options={MODULE_OPTIONS}
                  />
                  <FormSelect
                    id="protocol-type"
                    label="protocol type"
                    value={protocolType}
                    onValueChange={setProtocolType}
                    options={PROTOCOL_TYPE_OPTIONS}
                  />
                  <FormSelect
                    id="protocol-status"
                    label="status"
                    value={protocolStatus}
                    onValueChange={setProtocolStatus}
                    options={PROTOCOL_STATUS_OPTIONS}
                  />
                </div>
                <Button type="button" disabled={protocolBusy} onClick={() => void createTestProtocol()}>
                  {protocolBusy ? "Creating..." : "Create test protocol"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Test Protocols</CardTitle>
                <CardDescription>
                  <code className="text-xs">
                    GET /validation-center/projects/{"{validation_project_id}"}/test-protocols
                  </code>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">protocol code</TableHead>
                        <TableHead className="text-xs">title</TableHead>
                        <TableHead className="text-xs">module</TableHead>
                        <TableHead className="text-xs">protocol type</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-xs">open</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {protocolRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-xs text-muted-foreground">
                            No test protocols returned.
                          </TableCell>
                        </TableRow>
                      ) : (
                        protocolRows.map((row, idx) => {
                          const id = rowId(row)
                          const status = readFirst(row, ["status"])
                          return (
                            <TableRow key={id || `protocol-${idx}`}>
                              <TableCell className="text-xs">{readFirst(row, ["protocol_code"]) || "-"}</TableCell>
                              <TableCell className="max-w-[18rem] text-xs">{readFirst(row, ["title"]) || "-"}</TableCell>
                              <TableCell className="text-xs">{readFirst(row, ["module"]) || "-"}</TableCell>
                              <TableCell className="text-xs">{readFirst(row, ["protocol_type"]) || "-"}</TableCell>
                              <TableCell className="text-xs">
                                {status ? (
                                  <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                                    {status}
                                  </Badge>
                                ) : (
                                  "-"
                                )}
                              </TableCell>
                              <TableCell>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={selectedProtocolId === id ? "secondary" : "outline"}
                                  disabled={!id}
                                  onClick={() => setSelectedProtocolId(id)}
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
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Selected protocol detail</CardTitle>
                <CardDescription>
                  Detail for the selected test protocol — protocol code, title, type, module, and status.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {protocolDetailError ? <p className="text-xs text-destructive">{protocolDetailError}</p> : null}
                {protocolDetailLoading ? <p className="text-sm text-muted-foreground">Loading protocol detail...</p> : null}
                {!selectedProtocolId ? (
                  <p className="text-sm text-muted-foreground">Open a protocol to load detail and test cases.</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="protocol id" value={selectedProtocolId} />
                    <Field label="protocol code" value={readFirst(protocolDetail ?? selectedProtocol, ["protocol_code"])} />
                    <Field label="status" value={readFirst(protocolDetail ?? selectedProtocol, ["status"])} />
                    <Field label="title" value={readFirst(protocolDetail ?? selectedProtocol, ["title"])} />
                    <Field label="module" value={readFirst(protocolDetail ?? selectedProtocol, ["module"])} />
                    <Field label="protocol type" value={readFirst(protocolDetail ?? selectedProtocol, ["protocol_type"])} />
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Create test case</CardTitle>
                <CardDescription>
                  Add a test case to this protocol — specify code, title, preconditions, steps, expected results, and linked requirement and risk IDs.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {testCaseError ? <p className="text-xs text-destructive">{testCaseError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor="test-case-code">test case code</Label>
                    <Input
                      id="test-case-code"
                      value={testCaseCode}
                      onChange={(event) => setTestCaseCode(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="test-case-title">title</Label>
                    <Input
                      id="test-case-title"
                      value={testCaseTitle}
                      onChange={(event) => setTestCaseTitle(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="test-case-status"
                    label="status"
                    value={testCaseStatus}
                    onValueChange={setTestCaseStatus}
                    options={TEST_CASE_STATUS_OPTIONS}
                  />
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="test-case-preconditions">preconditions</Label>
                    <Textarea
                      id="test-case-preconditions"
                      value={testCasePreconditions}
                      onChange={(event) => setTestCasePreconditions(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="test-case-steps-json">steps JSON</Label>
                    <Textarea
                      id="test-case-steps-json"
                      value={testCaseStepsJson}
                      onChange={(event) => setTestCaseStepsJson(event.target.value)}
                      rows={4}
                      className="font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="test-case-expected-results">expected results</Label>
                    <Textarea
                      id="test-case-expected-results"
                      value={testCaseExpectedResults}
                      onChange={(event) => setTestCaseExpectedResults(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="test-case-linked-requirements">linked requirements</Label>
                    <Textarea
                      id="test-case-linked-requirements"
                      value={testCaseLinkedRequirementsJson}
                      onChange={(event) => setTestCaseLinkedRequirementsJson(event.target.value)}
                      rows={3}
                      className="font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="test-case-linked-risks">linked risks</Label>
                    <Textarea
                      id="test-case-linked-risks"
                      value={testCaseLinkedRisksJson}
                      onChange={(event) => setTestCaseLinkedRisksJson(event.target.value)}
                      rows={3}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    disabled={testCaseBusy || !selectedProtocolId}
                    onClick={() => void createTestCase()}
                  >
                    {testCaseBusy ? "Creating..." : "Create test case"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={!selectedProtocolId || testCasesLoading}
                    onClick={() => void loadTestCases(selectedProtocolId)}
                  >
                    Refresh test cases
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Test Cases</CardTitle>
                <CardDescription>
                  Test cases associated with the selected protocol — status, linked requirements, and linked risks.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {testCasesError ? <p className="text-xs text-destructive">{testCasesError}</p> : null}
                {testCasesLoading ? <p className="text-sm text-muted-foreground">Loading test cases...</p> : null}
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">test case code</TableHead>
                        <TableHead className="text-xs">title</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-xs">linked requirements</TableHead>
                        <TableHead className="text-xs">linked risks</TableHead>
                        <TableHead className="text-xs">open</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {testCaseRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-xs text-muted-foreground">
                            No test cases returned.
                          </TableCell>
                        </TableRow>
                      ) : (
                        testCaseRows.map((row, idx) => {
                          const id = rowId(row)
                          const status = readFirst(row, ["status"])
                          return (
                            <TableRow key={id || `test-case-${idx}`}>
                              <TableCell className="text-xs">{readFirst(row, ["test_case_code"]) || "-"}</TableCell>
                              <TableCell className="max-w-[18rem] text-xs">{readFirst(row, ["title"]) || "-"}</TableCell>
                              <TableCell className="text-xs">
                                {status ? (
                                  <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                                    {status}
                                  </Badge>
                                ) : (
                                  "-"
                                )}
                              </TableCell>
                              <TableCell className="max-w-[12rem] font-mono text-[10px]">
                                {formatValue(row.linked_requirement_ids_json ?? row.linked_requirement_ids)}
                              </TableCell>
                              <TableCell className="max-w-[12rem] font-mono text-[10px]">
                                {formatValue(row.linked_risk_ids_json ?? row.linked_risk_ids)}
                              </TableCell>
                              <TableCell>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={selectedTestCaseId === id ? "secondary" : "outline"}
                                  disabled={!id}
                                  onClick={() => setSelectedTestCaseId(id)}
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
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="test_executions" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Execute test case</CardTitle>
                <CardDescription>
                  Record a test execution result — executor, execution status, actual results, and evidence file or artifact IDs.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {executionError ? <p className="text-xs text-destructive">{executionError}</p> : null}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  <Field label="selected test case" value={selectedTestCaseId || rowId(selectedTestCase) || "Open a test case in Test Protocols"} />
                  <div className="space-y-1">
                    <Label htmlFor="execution-executed-by">executed by</Label>
                    <Input
                      id="execution-executed-by"
                      value={executedBy}
                      onChange={(event) => setExecutedBy(event.target.value)}
                    />
                  </div>
                  <FormSelect
                    id="execution-status"
                    label="execution status"
                    value={executionStatus}
                    onValueChange={setExecutionStatus}
                    options={EXECUTION_STATUS_OPTIONS}
                  />
                  <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                    <Label htmlFor="execution-actual-results">actual results</Label>
                    <Textarea
                      id="execution-actual-results"
                      value={actualResults}
                      onChange={(event) => setActualResults(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="execution-evidence-file-ids">evidence file IDs</Label>
                    <Textarea
                      id="execution-evidence-file-ids"
                      value={evidenceFileIdsJson}
                      onChange={(event) => setEvidenceFileIdsJson(event.target.value)}
                      rows={3}
                      className="font-mono text-xs"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="execution-evidence-artifact-ids">evidence artifact IDs</Label>
                    <Textarea
                      id="execution-evidence-artifact-ids"
                      value={evidenceArtifactIdsJson}
                      onChange={(event) => setEvidenceArtifactIdsJson(event.target.value)}
                      rows={3}
                      className="font-mono text-xs"
                    />
                  </div>
                </div>
                {executionStatus === "fail" ? (
                  <AlertCard
                    variant="warning"
                    title="Failure path"
                    description="Failed execution path visible: create or link a deviation record before closure."
                  />
                ) : null}
                <Button type="button" disabled={executionBusy || !selectedTestCaseId} onClick={() => void executeTestCase()}>
                  {executionBusy ? "Executing..." : "Execute test case"}
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Test Executions</CardTitle>
                <CardDescription>
                  Test execution records for this project — execution status, executor, timestamp, and linked deviation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {executionsError ? <p className="text-xs text-destructive">{executionsError}</p> : null}
                {executionsLoading ? <p className="text-sm text-muted-foreground">Loading executions...</p> : null}
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">test case</TableHead>
                        <TableHead className="text-xs">execution status</TableHead>
                        <TableHead className="text-xs">executed by</TableHead>
                        <TableHead className="text-xs">executed at</TableHead>
                        <TableHead className="text-xs">deviation id</TableHead>
                        <TableHead className="text-xs">open</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {displayedExecutionRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-xs text-muted-foreground">
                            No test executions returned.
                          </TableCell>
                        </TableRow>
                      ) : (
                        displayedExecutionRows.map((row, idx) => {
                          const id = rowId(row)
                          const status = readFirst(row, ["execution_status", "status"])
                          return (
                            <TableRow key={id || `execution-${idx}`}>
                              <TableCell className="text-xs">
                                {readFirst(row, ["test_case_code", "test_case_id", "title"]) || "-"}
                              </TableCell>
                              <TableCell className="text-xs">
                                {status ? (
                                  <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                                    {status}
                                  </Badge>
                                ) : (
                                  "-"
                                )}
                              </TableCell>
                              <TableCell className="text-xs">{readFirst(row, ["executed_by"]) || "-"}</TableCell>
                              <TableCell className="text-xs">{readFirst(row, ["executed_at"]) || "-"}</TableCell>
                              <TableCell className="text-xs">{readFirst(row, ["deviation_id"]) || "-"}</TableCell>
                              <TableCell>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant={selectedExecutionId === id ? "secondary" : "outline"}
                                  disabled={!id}
                                  onClick={() => setSelectedExecutionId(id)}
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
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Selected execution detail</CardTitle>
                <CardDescription>
                  Detail for the selected test execution — execution status, executor, actual results, and linked deviation.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {executionDetailError ? <p className="text-xs text-destructive">{executionDetailError}</p> : null}
                {executionDetailLoading ? <p className="text-sm text-muted-foreground">Loading execution detail...</p> : null}
                {!selectedExecutionId ? (
                  <p className="text-sm text-muted-foreground">Open an execution to load detail.</p>
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="execution id" value={selectedExecutionId} />
                    <Field label="execution status" value={readFirst(executionDetail, ["execution_status", "status"])} />
                    <Field label="executed by" value={readFirst(executionDetail, ["executed_by"])} />
                    <Field label="executed at" value={readFirst(executionDetail, ["executed_at"])} />
                    <Field label="actual results" value={readFirst(executionDetail, ["actual_results"])} />
                    <Field label="deviation id" value={readFirst(executionDetail, ["deviation_id"])} />
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="traceability" className="space-y-4">
            <ValidationTraceabilityMatrixPanel
              validationProjectId={validationProjectId}
              initialTraceability={traceabilityRaw}
              onTraceabilityChange={setTraceabilityRaw}
            />
          </TabsContent>

          <TabsContent value="esignatures">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">e-Signatures</CardTitle>
                <CardDescription>Signature rows when included in the validation project payload.</CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={signaturesRows}
                  empty="No e-signature records returned in the project payload."
                  columns={[
                    { key: "signer_name", label: "signer name" },
                    { key: "signature_meaning", label: "signature meaning" },
                    { key: "target_type", label: "target type" },
                    { key: "target_id", label: "target id" },
                    { key: "signed_at", label: "signed at" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="deviations_capa" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Deviations</CardTitle>
                <CardDescription>Deviation rows when included in the validation project payload.</CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={deviationsRows}
                  empty="No deviation records returned in the project payload."
                  columns={[
                    { key: "deviation_code", label: "deviation code" },
                    { key: "title", label: "title" },
                    { key: "severity", label: "severity" },
                    { key: "status", label: "status" },
                    { key: "source_type", label: "source type" },
                  ]}
                />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">CAPA</CardTitle>
                <CardDescription>CAPA rows when included in the validation project payload.</CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={capaRows}
                  empty="No CAPA records returned in the project payload."
                  columns={[
                    { key: "capa_code", label: "CAPA code" },
                    { key: "title", label: "title" },
                    { key: "owner", label: "owner" },
                    { key: "due_date", label: "due date" },
                    { key: "status", label: "status" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="inspection_package">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Inspection Package</CardTitle>
                <CardDescription>Inspection package rows when included in the validation project payload.</CardDescription>
              </CardHeader>
              <CardContent>
                <GenericTable
                  rows={inspectionRows}
                  empty="No inspection package rows returned in the project payload."
                  columns={[
                    { key: "title", label: "title" },
                    { key: "scope", label: "scope" },
                    { key: "package_status", label: "package status" },
                    { key: "package_sha256", label: "package sha256" },
                    { key: "created_at", label: "created at" },
                  ]}
                />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="developer_json">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Developer JSON</CardTitle>
                <CardDescription>Raw payloads from the validation project detail endpoints.</CardDescription>
              </CardHeader>
              <CardContent>
                <JsonBlock value={developerBundle} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      ) : null}
    </div>
  )
}
