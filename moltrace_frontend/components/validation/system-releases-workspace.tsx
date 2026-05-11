"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { Textarea } from "@/components/ui/textarea"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { FileText, GitBranch, Plus } from "lucide-react"

type Row = Record<string, unknown>

const RELEASE_TYPE_OPTIONS = [
  "frontend",
  "backend",
  "full_platform",
  "model_update",
  "connector_update",
  "regulatory_rule_update",
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
  for (const key of [...keys, "system_release", "release", "record", "data"]) {
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
  return readStr(row?.id ?? row?.release_id)
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

function sanitizeForDeveloperJson(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY_PATTERN.test(key)) return "[redacted]"
  if (Array.isArray(value)) return value.map((item) => sanitizeForDeveloperJson(item))
  if (!isRecord(value)) return value
  return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [entryKey, sanitizeForDeveloperJson(entryValue, entryKey)]))
}

function parseJsonObject(value: string, label: string): Row | null {
  const trimmed = value.trim()
  if (!trimmed) return {}
  try {
    const parsed = JSON.parse(trimmed)
    if (isRecord(parsed)) return parsed
    throw new Error(`${label} must be a JSON object.`)
  } catch (err) {
    if (err instanceof Error) throw err
    throw new Error(`${label} must be valid JSON.`, { cause: err })
  }
}

function statusVariant(value: unknown): "default" | "secondary" | "destructive" | "outline" {
  const status = readStr(value)
  if (status === "rejected") return "destructive"
  if (status === "approved" || status === "released") return "default"
  if (status === "ready_for_qa") return "secondary"
  return "outline"
}

export function SystemReleasesWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [releases, setReleases] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedRelease, setSelectedRelease] = useState<Row | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [releaseVersion, setReleaseVersion] = useState("")
  const [releaseType, setReleaseType] = useState("frontend")
  const [changeSummary, setChangeSummary] = useState("")
  const [validationProjectId, setValidationProjectId] = useState("")
  const [testSummary, setTestSummary] = useState("")
  const [riskSummary, setRiskSummary] = useState("")
  const [createBusy, setCreateBusy] = useState(false)

  const [reviewerName, setReviewerName] = useState("")
  const [approvalRationale, setApprovalRationale] = useState("")
  const [signatureReason, setSignatureReason] = useState("")
  const [approveBusy, setApproveBusy] = useState(false)

  const loadReleases = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/system-releases", { method: "GET" })
      const rows = asRows(payload, ["system_releases", "releases"])
      setReleases(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load system releases."))
      setReleases([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadReleases()
  }, [loadReleases])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return releases.find((release) => rowId(release) === selectedId) ?? null
  }, [releases, selectedId])

  const detailRelease = selectedRelease ?? selectedSummary
  const sanitizedTestSummary = useMemo(() => sanitizeForDeveloperJson(detailRelease?.test_summary_json), [detailRelease])
  const sanitizedRiskSummary = useMemo(() => sanitizeForDeveloperJson(detailRelease?.risk_summary_json), [detailRelease])

  async function loadDetail(id: string) {
    if (!id) return
    setSelectedId(id)
    setDetailLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/system-releases/${encodeURIComponent(id)}`, { method: "GET" })
      setSelectedRelease(unwrapRecord(payload, ["system_release"]))
    } catch (err) {
      setError(formatErr(err, "Could not load system release."))
      setSelectedRelease(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function createRelease() {
    if (!releaseVersion.trim()) {
      setError("release version is required.")
      return
    }
    if (!changeSummary.trim()) {
      setError("change summary is required.")
      return
    }
    const parsedValidationProjectId = validationProjectId.trim() ? readInt(validationProjectId) : null
    if (validationProjectId.trim() && parsedValidationProjectId == null) {
      setError("validation project ID must be a positive integer.")
      return
    }

    let parsedTestSummary: Row
    let parsedRiskSummary: Row
    try {
      parsedTestSummary = parseJsonObject(testSummary, "test summary") ?? {}
      parsedRiskSummary = parseJsonObject(riskSummary, "risk summary") ?? {}
    } catch (err) {
      setError(formatErr(err, "Summary JSON is invalid."))
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/system-releases", {
        method: "POST",
        body: {
          release_version: releaseVersion.trim(),
          release_type: releaseType,
          change_summary: changeSummary.trim(),
          validation_project_id: parsedValidationProjectId,
          test_summary_json: parsedTestSummary,
          risk_summary_json: parsedRiskSummary,
        },
      })
      const record = unwrapRecord(payload, ["system_release"])
      if (record) {
        setSelectedId(rowId(record))
        setSelectedRelease(record)
      }
      setReleaseVersion("")
      setReleaseType("frontend")
      setChangeSummary("")
      setValidationProjectId("")
      setTestSummary("")
      setRiskSummary("")
      setMessage("System release record created.")
      await loadReleases()
    } catch (err) {
      setError(formatErr(err, "Could not create system release."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function approveRelease() {
    const id = rowId(detailRelease)
    if (!id) return
    if (!reviewerName.trim()) {
      setError("reviewer name is required.")
      return
    }
    if (!approvalRationale.trim()) {
      setError("approval rationale is required.")
      return
    }
    if (!signatureReason.trim()) {
      setError("e-signature reason is required.")
      return
    }

    setApproveBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/system-releases/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        body: {
          signer_name: reviewerName.trim(),
          reason: signatureReason.trim(),
          metadata_json: {
            approval_rationale: approvalRationale.trim(),
          },
        },
      })
      setSelectedRelease(unwrapRecord(payload, ["system_release"]))
      setReviewerName("")
      setApprovalRationale("")
      setSignatureReason("")
      setMessage("System release approval recorded.")
      await loadReleases()
    } catch (err) {
      setError(formatErr(err, "Could not approve system release."))
    } finally {
      setApproveBusy(false)
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
            MolTrace · System Releases
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">System Releases</h1>
          <p className="text-sm text-muted-foreground">
            Create and review system release records with validation summaries, risk summaries, and e-signature approval.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {error ? <AlertCard variant="error" title="Error" description={error} /> : null}

      {message ? <AlertCard variant="success" title="Recorded" description={message} /> : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <ModuleCard
          accent="cyan"
          eyebrow="Create"
          title="Create system release"
          icon={Plus}
          description="Create a system release record documenting a validated software version with qualification evidence and release approval status."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="system-release-version">release version</Label>
                <Input
                  id="system-release-version"
                  value={releaseVersion}
                  onChange={(event) => setReleaseVersion(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="system-release-type">release type</Label>
                <Select value={releaseType} onValueChange={setReleaseType}>
                  <SelectTrigger id="system-release-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RELEASE_TYPE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="system-release-validation-project-id">validation project ID</Label>
                <Input
                  id="system-release-validation-project-id"
                  inputMode="numeric"
                  value={validationProjectId}
                  onChange={(event) => setValidationProjectId(event.target.value)}
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="system-release-change-summary">change summary</Label>
                <Textarea
                  id="system-release-change-summary"
                  value={changeSummary}
                  onChange={(event) => setChangeSummary(event.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="system-release-test-summary">test summary</Label>
                <Textarea
                  id="system-release-test-summary"
                  placeholder='{"summary":"", "passed":0, "failed":0}'
                  value={testSummary}
                  onChange={(event) => setTestSummary(event.target.value)}
                  rows={5}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="system-release-risk-summary">risk summary</Label>
                <Textarea
                  id="system-release-risk-summary"
                  placeholder='{"summary":"", "open_risks":0}'
                  value={riskSummary}
                  onChange={(event) => setRiskSummary(event.target.value)}
                  rows={5}
                />
              </div>
            </div>
            <Button type="button" onClick={createRelease} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create system release"}
            </Button>
          </div>
        </ModuleCard>

        <ModuleCard
          accent="cyan"
          eyebrow="Detail"
          title="Release detail"
          icon={FileText}
          description="Selected release detail — version, release notes, qualification status, and linked validation artefacts."
        >
          <div className="space-y-5">
            {detailRelease ? (
              <>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-muted-foreground">release version</p>
                    <p className="font-medium">{readStr(detailRelease.release_version) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">release type</p>
                    <p className="font-medium">{readStr(detailRelease.release_type) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">approval status</p>
                    <Badge variant={statusVariant(detailRelease.approval_status)}>
                      {readStr(detailRelease.approval_status) || "-"}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">validation project ID</p>
                    <p className="font-medium">{readStr(detailRelease.validation_project_id) || "-"}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <h3 className="text-sm font-medium">change summary</h3>
                  <p className="whitespace-pre-wrap rounded-lg border p-3 text-sm">
                    {readStr(detailRelease.change_summary) || "-"}
                  </p>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <details className="rounded-lg border p-3">
                    <summary className="cursor-pointer text-sm font-medium">test summary</summary>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(sanitizedTestSummary, null, 2)}
                    </pre>
                  </details>
                  <details className="rounded-lg border p-3">
                    <summary className="cursor-pointer text-sm font-medium">risk summary</summary>
                    <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(sanitizedRiskSummary, null, 2)}
                    </pre>
                  </details>
                </div>

                <div className="space-y-3 rounded-lg border p-3">
                  <div>
                    <h3 className="text-sm font-medium">Approval</h3>
                    <p className="text-xs text-muted-foreground">Record the reviewer name and approval decision to advance this release to approved status.</p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label htmlFor="system-release-reviewer-name">reviewer name</Label>
                      <Input
                        id="system-release-reviewer-name"
                        value={reviewerName}
                        onChange={(event) => setReviewerName(event.target.value)}
                      />
                    </div>
                    <div className="space-y-1 sm:col-span-2">
                      <Label htmlFor="system-release-approval-rationale">approval rationale</Label>
                      <Textarea
                        id="system-release-approval-rationale"
                        value={approvalRationale}
                        onChange={(event) => setApprovalRationale(event.target.value)}
                        rows={3}
                      />
                    </div>
                    <div className="space-y-1 sm:col-span-2">
                      <Label htmlFor="system-release-signature-reason">e-signature reason</Label>
                      <Textarea
                        id="system-release-signature-reason"
                        value={signatureReason}
                        onChange={(event) => setSignatureReason(event.target.value)}
                        rows={3}
                      />
                    </div>
                  </div>
                  <Button type="button" variant="outline" onClick={approveRelease} disabled={approveBusy}>
                    {approveBusy ? "Recording..." : "Approve system release"}
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading system release..." : "Select a system release to view approval controls."}
              </p>
            )}
          </div>
        </ModuleCard>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="History"
        title="System releases"
        icon={GitBranch}
        description="All system release records — version history, qualification status, and release approval audit trail."
      >
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={() => void loadReleases()} disabled={loading}>
              Refresh
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>release version</TableHead>
                  <TableHead>release type</TableHead>
                  <TableHead>approval status</TableHead>
                  <TableHead>validation project ID</TableHead>
                  <TableHead>created date</TableHead>
                  <TableHead>released date</TableHead>
                  <TableHead className="text-right">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {releases.map((release) => {
                  const id = rowId(release)
                  return (
                    <TableRow key={id || JSON.stringify(release)}>
                      <TableCell className="font-medium">{readStr(release.release_version) || "-"}</TableCell>
                      <TableCell>{readStr(release.release_type) || "-"}</TableCell>
                      <TableCell>{readStr(release.approval_status) || "-"}</TableCell>
                      <TableCell>{readStr(release.validation_project_id) || "-"}</TableCell>
                      <TableCell>{formatDate(release.created_at)}</TableCell>
                      <TableCell>{formatDate(release.released_at)}</TableCell>
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
                {!releases.length ? (
                  <TableRow>
                    <TableCell colSpan={7} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading system releases..." : "No system releases found."}
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
