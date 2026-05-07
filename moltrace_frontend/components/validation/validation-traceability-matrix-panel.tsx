"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

type Row = Record<string, unknown>

const TRACEABILITY_TOOLTIP =
  "Traceability maps user requirements to functions, risks, test cases, execution evidence, and validation coverage gaps."

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(value: unknown): Row[] {
  if (Array.isArray(value)) return value.filter(isRecord)
  if (isRecord(value)) {
    for (const key of ["rows", "items", "results", "data"]) {
      const nested = value[key]
      if (Array.isArray(nested)) return nested.filter(isRecord)
    }
  }
  return []
}

function unwrapRecord(payload: unknown): Row | null {
  if (!isRecord(payload)) return null
  for (const key of ["traceability", "traceability_matrix", "matrix", "record", "data"]) {
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

function readNum(v: unknown): number {
  if (typeof v === "number" && Number.isFinite(v)) return Math.max(0, Math.floor(v))
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.max(0, Math.floor(Number(v)))
  return 0
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function listValue(value: unknown): string {
  if (Array.isArray(value)) return value.length > 0 ? value.map((item) => readStr(item) || JSON.stringify(item)).join(", ") : "-"
  if (value == null || value === "") return "-"
  if (typeof value === "object") return JSON.stringify(value)
  return readStr(value) || "-"
}

function latestExecutionStatus(row: Row): string {
  const statuses = row.execution_statuses ?? row.execution_status ?? row.latest_execution_status
  if (Array.isArray(statuses)) {
    const last = statuses.map(readStr).filter(Boolean).at(-1)
    return last || "-"
  }
  return readStr(statuses) || "-"
}

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase()
  if (s === "covered" || s === "pass" || s === "complete") return "border-success/50 text-success"
  if (s.includes("gap") || s === "fail" || s.includes("missing")) return "border-warning/50 text-warning"
  return "text-muted-foreground"
}

function rowRequirementId(row: Row): string {
  return readStr(row.requirement_id)
}

function rowGapList(row: Row, missingCoverage: Row[]): Row[] {
  const rid = rowRequirementId(row)
  if (!rid) return []
  return missingCoverage.filter((gap) => readStr(gap.requirement_id) === rid)
}

function coverageStatus(row: Row, gaps: Row[]): string {
  if (readStr(row.coverage_status)) return readStr(row.coverage_status)
  if (gaps.length > 0) return "gaps_identified"
  const testCases = asRows(row.test_case_ids).length || (Array.isArray(row.test_case_ids) ? row.test_case_ids.length : 0)
  const statuses = Array.isArray(row.execution_statuses) ? row.execution_statuses.map(readStr).filter(Boolean) : []
  if (testCases > 0 && statuses.some((status) => status === "pass")) return "covered"
  return "not_assessed"
}

function gapText(gaps: Row[]): string {
  if (gaps.length === 0) return "-"
  return gaps.map((gap) => readStr(gap.gap_type) || JSON.stringify(gap)).join(", ")
}

function countMissingCoverageForRequirements(rows: Row[], missingCoverage: Row[]): number {
  const requirementIdsWithGaps = new Set(
    missingCoverage.map((gap) => readStr(gap.requirement_id)).filter(Boolean),
  )
  return rows.filter((row) => requirementIdsWithGaps.has(rowRequirementId(row))).length
}

export function ValidationTraceabilityMatrixPanel({
  validationProjectId,
  initialTraceability,
  onTraceabilityChange,
}: {
  validationProjectId: string
  initialTraceability?: unknown
  onTraceabilityChange?: (payload: unknown) => void
}) {
  const [raw, setRaw] = useState<unknown>(initialTraceability ?? null)
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (initialTraceability !== undefined) setRaw(initialTraceability)
  }, [initialTraceability])

  const loadTraceability = useCallback(async () => {
    const id = validationProjectId.trim()
    if (!id) return
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/validation-center/projects/${encodeURIComponent(id)}/traceability`, {
        method: "GET",
      })
      setRaw(payload)
      onTraceabilityChange?.(payload)
    } catch (err) {
      setError(formatErr(err, "Could not load traceability matrix."))
    } finally {
      setLoading(false)
    }
  }, [onTraceabilityChange, validationProjectId])

  useEffect(() => {
    if (validationProjectId.trim()) void loadTraceability()
  }, [loadTraceability, validationProjectId])

  async function generateTraceabilityMatrix() {
    const id = validationProjectId.trim()
    if (!id) return
    setGenerating(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(
        `/validation-center/projects/${encodeURIComponent(id)}/traceability/generate`,
        { method: "POST" },
      )
      setRaw(payload)
      onTraceabilityChange?.(payload)
    } catch (err) {
      setError(formatErr(err, "Generate traceability matrix failed."))
    } finally {
      setGenerating(false)
    }
  }

  const record = useMemo(() => unwrapRecord(raw), [raw])
  const matrix = useMemo(() => {
    const candidate = record?.matrix_json ?? record?.matrix ?? raw
    return isRecord(candidate) ? candidate : {}
  }, [raw, record])
  const rows = useMemo(() => asRows(matrix.rows ?? matrix), [matrix])
  const coverageSummary = useMemo(() => {
    const candidate = record?.coverage_summary_json ?? record?.coverage_summary
    return isRecord(candidate) ? candidate : {}
  }, [record])
  const missingCoverage = useMemo(
    () => asRows(record?.missing_coverage_json ?? record?.missing_coverage),
    [record],
  )

  const testsPassed = rows.reduce((sum, row) => {
    const statuses = Array.isArray(row.execution_statuses) ? row.execution_statuses.map(readStr) : [latestExecutionStatus(row)]
    return sum + statuses.filter((status) => status === "pass").length
  }, 0)
  const testsFailed = rows.reduce((sum, row) => {
    const statuses = Array.isArray(row.execution_statuses) ? row.execution_statuses.map(readStr) : [latestExecutionStatus(row)]
    return sum + statuses.filter((status) => status === "fail").length
  }, 0)
  const requirementCount = readNum(coverageSummary.requirement_count) || rows.length
  const requirementsCovered = Math.max(0, requirementCount - countMissingCoverageForRequirements(rows, missingCoverage))
  const risksCovered = Math.max(
    0,
    readNum(coverageSummary.risk_count) -
      missingCoverage.filter((gap) => readStr(gap.gap_type) === "risk_missing_test_case").length,
  )
  const missingCoverageCount = readNum(coverageSummary.missing_coverage_count) || missingCoverage.length

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              Traceability Matrix
              <InfoTooltip content={TRACEABILITY_TOOLTIP} label="About Traceability Matrix" />
            </CardTitle>
            <CardDescription>
              <code className="text-xs">GET /validation-center/projects/{"{validation_project_id}"}/traceability</code>
              {" · "}
              <code className="text-xs">POST /validation-center/projects/{"{validation_project_id}"}/traceability/generate</code>
            </CardDescription>
          </div>
          <BackendStatusIndicator />
        </CardHeader>
        <CardContent className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={!validationProjectId.trim() || generating}
              onClick={() => void generateTraceabilityMatrix()}
            >
              {generating ? "Generating..." : "Generate traceability matrix"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!validationProjectId.trim() || loading}
              onClick={() => void loadTraceability()}
            >
              {loading ? "Refreshing..." : "Refresh matrix"}
            </Button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">requirements covered</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{requirementsCovered}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">risks covered</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{risksCovered}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">tests passed</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{testsPassed}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">tests failed</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{testsFailed}</CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">missing coverage</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{missingCoverageCount}</CardContent>
            </Card>
          </div>

          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">requirement code</TableHead>
                  <TableHead className="text-xs">function code</TableHead>
                  <TableHead className="text-xs">risk ID</TableHead>
                  <TableHead className="text-xs">test case ID</TableHead>
                  <TableHead className="text-xs">latest execution status</TableHead>
                  <TableHead className="text-xs">evidence IDs</TableHead>
                  <TableHead className="text-xs">coverage status</TableHead>
                  <TableHead className="text-xs">gaps</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-xs text-muted-foreground">
                      No traceability matrix rows returned.
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((row, index) => {
                    const gaps = rowGapList(row, missingCoverage)
                    const status = coverageStatus(row, gaps)
                    return (
                      <TableRow key={`${rowRequirementId(row) || "row"}-${index}`}>
                        <TableCell className="text-xs">{readStr(row.requirement_code) || "-"}</TableCell>
                        <TableCell className="max-w-[12rem] font-mono text-[10px]">
                          {listValue(row.function_codes ?? row.function_code ?? row.function_ids)}
                        </TableCell>
                        <TableCell className="max-w-[12rem] font-mono text-[10px]">{listValue(row.risk_ids ?? row.risk_id)}</TableCell>
                        <TableCell className="max-w-[12rem] font-mono text-[10px]">
                          {listValue(row.test_case_ids ?? row.test_case_id)}
                        </TableCell>
                        <TableCell className="text-xs">{latestExecutionStatus(row)}</TableCell>
                        <TableCell className="max-w-[16rem] font-mono text-[10px]">
                          files: {listValue(row.evidence_file_ids)}
                          <br />
                          artifacts: {listValue(row.evidence_artifact_ids)}
                        </TableCell>
                        <TableCell className="text-xs">
                          <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                            {status}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[18rem] text-xs">{gapText(gaps)}</TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>

          {missingCoverage.length > 0 ? (
            <Alert className="border-warning/40 bg-warning/10">
              <AlertDescription className="text-xs text-warning">
                Coverage gaps visible: {missingCoverage.map((gap) => readStr(gap.gap_type) || JSON.stringify(gap)).join(", ")}
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
