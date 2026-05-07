"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch, buildApiPath, readStoredAuthToken } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
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

type Row = Record<string, unknown>

const PACKAGE_SCOPE_OPTIONS = ["project", "dossier", "report", "validation_project", "full_platform"] as const
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
  for (const key of [...keys, "inspection_package", "package", "record", "data"]) {
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
  return readStr(row?.id ?? row?.package_id)
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

function shortHash(value: unknown): string {
  const text = readStr(value)
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 12)}...${text.slice(-6)}`
}

function listFrom(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  if (typeof value === "string" && value.trim()) return [value]
  return []
}

function parseIdList(value: string): number[] | null {
  const parts = value
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter(Boolean)
  const ids: number[] = []
  for (const part of parts) {
    const parsed = readInt(part)
    if (parsed == null) return null
    if (!ids.includes(parsed)) ids.push(parsed)
  }
  return ids
}

function sanitizeForDeveloperJson(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY_PATTERN.test(key)) return "[redacted]"
  if (Array.isArray(value)) return value.map((item) => sanitizeForDeveloperJson(item))
  if (!isRecord(value)) return value
  return Object.fromEntries(Object.entries(value).map(([entryKey, entryValue]) => [entryKey, sanitizeForDeveloperJson(entryValue, entryKey)]))
}

function formatJsonItem(value: unknown): string {
  if (typeof value === "string") return value
  if (!isRecord(value)) return JSON.stringify(value)
  const title = readStr(value.title ?? value.code ?? value.event_type ?? value.status ?? value.record_type)
  const message = readStr(value.message ?? value.description ?? value.warning ?? value.reason)
  if (title && message) return `${title}: ${message}`
  if (title) return title
  if (message) return message
  return JSON.stringify(sanitizeForDeveloperJson(value))
}

export function InspectionPackageWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [packages, setPackages] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedPackage, setSelectedPackage] = useState<Row | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [downloadBusy, setDownloadBusy] = useState(false)

  const [title, setTitle] = useState("")
  const [scope, setScope] = useState("project")
  const [scopeId, setScopeId] = useState("")
  const [validationProjectIds, setValidationProjectIds] = useState("")
  const [signatureIds, setSignatureIds] = useState("")
  const [auditEventIds, setAuditEventIds] = useState("")
  const [controlledRecordIds, setControlledRecordIds] = useState("")
  const [includeReleaseRecords, setIncludeReleaseRecords] = useState(true)
  const [includeHashes, setIncludeHashes] = useState(true)
  const [createBusy, setCreateBusy] = useState(false)

  const loadPackages = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/inspection-packages", { method: "GET" })
      const rows = asRows(payload, ["inspection_packages", "packages"])
      setPackages(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load inspection packages."))
      setPackages([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadPackages()
  }, [loadPackages])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return packages.find((pkg) => rowId(pkg) === selectedId) ?? null
  }, [packages, selectedId])

  const detailPackage = selectedPackage ?? selectedSummary
  const manifest = useMemo(
    () => (isRecord(detailPackage?.package_manifest_json) ? detailPackage.package_manifest_json : {}),
    [detailPackage],
  )
  const developerManifest = useMemo(() => sanitizeForDeveloperJson(manifest), [manifest])
  const includedRecordIds = listFrom(detailPackage?.included_record_ids_json)
  const manifestRecords = asRows(manifest.controlled_records)
  const warnings = [
    ...listFrom(manifest.warnings),
    ...listFrom(isRecord(detailPackage?.metadata_json) ? detailPackage.metadata_json.warnings : undefined),
  ]

  async function loadDetail(id: string) {
    if (!id) return
    setSelectedId(id)
    setDetailLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/inspection-packages/${encodeURIComponent(id)}`, { method: "GET" })
      setSelectedPackage(unwrapRecord(payload, ["inspection_package"]))
    } catch (err) {
      setError(formatErr(err, "Could not load inspection package."))
      setSelectedPackage(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function createPackage() {
    const parsedScopeId = scopeId.trim() ? readInt(scopeId) : null
    if (!title.trim()) {
      setError("title is required.")
      return
    }
    if (scopeId.trim() && parsedScopeId == null) {
      setError("scope ID must be a positive integer.")
      return
    }
    const parsedValidationProjects = parseIdList(validationProjectIds)
    const parsedSignatures = parseIdList(signatureIds)
    const parsedAuditEvents = parseIdList(auditEventIds)
    const parsedControlledRecords = parseIdList(controlledRecordIds)
    if (!parsedValidationProjects || !parsedSignatures || !parsedAuditEvents || !parsedControlledRecords) {
      setError("included IDs must be positive integers separated by commas or spaces.")
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/inspection-packages", {
        method: "POST",
        body: {
          title: title.trim(),
          scope,
          scope_id: parsedScopeId,
          included_validation_project_ids_json: parsedValidationProjects,
          included_signature_ids_json: parsedSignatures,
          included_audit_event_ids_json: parsedAuditEvents,
          included_record_ids_json: parsedControlledRecords,
          metadata_json: {
            include_release_records: includeReleaseRecords,
            include_hashes: includeHashes,
          },
        },
      })
      const record = unwrapRecord(payload, ["inspection_package"])
      if (record) {
        setSelectedId(rowId(record))
        setSelectedPackage(record)
      }
      setTitle("")
      setScope("project")
      setScopeId("")
      setValidationProjectIds("")
      setSignatureIds("")
      setAuditEventIds("")
      setControlledRecordIds("")
      setIncludeReleaseRecords(true)
      setIncludeHashes(true)
      setMessage("Inspection-ready package created.")
      await loadPackages()
    } catch (err) {
      setError(formatErr(err, "Could not create inspection package."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function downloadPackage(id: string) {
    if (!id || typeof window === "undefined") return
    setDownloadBusy(true)
    setError("")
    try {
      const headers = new Headers()
      const token = readStoredAuthToken()
      if (token) headers.set("authorization", `Bearer ${token}`)
      const response = await fetch(buildApiPath(`/inspection-packages/${encodeURIComponent(id)}/download`), {
        headers,
        cache: "no-store",
      })
      if (!response.ok) throw new Error(`Download failed with status ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `inspection-ready-package-${id}.json`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setError(formatErr(err, "Could not download inspection package."))
    } finally {
      setDownloadBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inspection Readiness Package</h1>
          <p className="text-muted-foreground">
            Create and review inspection-ready packages with manifests, package hashes, included records, and warnings.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {message ? (
        <Alert>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Create inspection package</CardTitle>
            <CardDescription>POST /inspection-packages</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="inspection-package-title">title</Label>
                <Input id="inspection-package-title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-scope">scope</Label>
                <Select value={scope} onValueChange={setScope}>
                  <SelectTrigger id="inspection-package-scope">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PACKAGE_SCOPE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-scope-id">scope ID optional</Label>
                <Input
                  id="inspection-package-scope-id"
                  inputMode="numeric"
                  value={scopeId}
                  onChange={(event) => setScopeId(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-validation-projects">include validation projects</Label>
                <Input
                  id="inspection-package-validation-projects"
                  placeholder="1, 2, 3"
                  value={validationProjectIds}
                  onChange={(event) => setValidationProjectIds(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-signatures">include signatures</Label>
                <Input
                  id="inspection-package-signatures"
                  placeholder="1, 2, 3"
                  value={signatureIds}
                  onChange={(event) => setSignatureIds(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-audit-events">include audit events</Label>
                <Input
                  id="inspection-package-audit-events"
                  placeholder="1, 2, 3"
                  value={auditEventIds}
                  onChange={(event) => setAuditEventIds(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="inspection-package-controlled-records">include controlled records</Label>
                <Input
                  id="inspection-package-controlled-records"
                  placeholder="1, 2, 3"
                  value={controlledRecordIds}
                  onChange={(event) => setControlledRecordIds(event.target.value)}
                />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={includeReleaseRecords}
                  onCheckedChange={(checked) => setIncludeReleaseRecords(Boolean(checked))}
                />
                include release records
              </label>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={includeHashes} onCheckedChange={(checked) => setIncludeHashes(Boolean(checked))} />
                include hashes
              </label>
            </div>
            <Button type="button" onClick={createPackage} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create inspection package"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Package detail</CardTitle>
            <CardDescription>GET /inspection-packages/{"{package_id}"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {detailPackage ? (
              <>
                <div className="grid gap-3 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-muted-foreground">package status</p>
                    <Badge variant="secondary">{readStr(detailPackage.package_status) || "-"}</Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">scope</p>
                    <p className="font-medium">{readStr(detailPackage.scope) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">scope ID</p>
                    <p className="font-medium">{readStr(detailPackage.scope_id) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">created date</p>
                    <p className="font-medium">{formatDate(detailPackage.created_at)}</p>
                  </div>
                  <div className="sm:col-span-4">
                    <p className="text-xs text-muted-foreground">package SHA-256</p>
                    <p className="break-all font-mono text-xs">{readStr(detailPackage.package_sha256) || "-"}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => void downloadPackage(rowId(detailPackage))}
                    disabled={downloadBusy}
                  >
                    {downloadBusy ? "Downloading..." : "Download"}
                  </Button>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">included records</h3>
                    <div className="space-y-2">
                      {includedRecordIds.map((recordId, index) => (
                        <div key={`${recordId}-${index}`} className="rounded-lg border p-3 text-sm">
                          record ID: {readStr(recordId)}
                        </div>
                      ))}
                      {manifestRecords.map((record, index) => (
                        <div key={`${rowId(record)}-${index}`} className="rounded-lg border p-3 text-sm">
                          <p>record ID: {readStr(record.record_id) || "-"}</p>
                          <p className="text-muted-foreground">content hash: {shortHash(record.content_hash)}</p>
                        </div>
                      ))}
                      {!includedRecordIds.length && !manifestRecords.length ? (
                        <p className="text-sm text-muted-foreground">No included records found.</p>
                      ) : null}
                    </div>
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium">warnings</h3>
                    <div className="space-y-2">
                      {warnings.map((warning, index) => (
                        <div key={index} className="rounded-lg border p-3 text-sm">
                          {formatJsonItem(warning)}
                        </div>
                      ))}
                      {!warnings.length ? <p className="text-sm text-muted-foreground">No warnings recorded.</p> : null}
                    </div>
                  </div>
                </div>

                <details open className="rounded-lg border p-3">
                  <summary className="cursor-pointer text-sm font-medium">manifest</summary>
                  <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(developerManifest, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading inspection package..." : "Select an inspection package to view its manifest."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">Inspection packages</CardTitle>
            <CardDescription>GET /inspection-packages</CardDescription>
          </div>
          <Button type="button" variant="outline" onClick={() => void loadPackages()} disabled={loading}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>title</TableHead>
                  <TableHead>scope</TableHead>
                  <TableHead>package status</TableHead>
                  <TableHead>package SHA-256</TableHead>
                  <TableHead>created date</TableHead>
                  <TableHead className="text-right">actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {packages.map((pkg) => {
                  const id = rowId(pkg)
                  return (
                    <TableRow key={id || JSON.stringify(pkg)}>
                      <TableCell className="font-medium">{readStr(pkg.title) || "-"}</TableCell>
                      <TableCell>{readStr(pkg.scope) || "-"}</TableCell>
                      <TableCell>{readStr(pkg.package_status) || "-"}</TableCell>
                      <TableCell className="font-mono text-xs">{shortHash(pkg.package_sha256)}</TableCell>
                      <TableCell>{formatDate(pkg.created_at)}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            variant={selectedId === id ? "secondary" : "outline"}
                            size="sm"
                            onClick={() => void loadDetail(id)}
                            disabled={!id || detailLoading}
                          >
                            Open
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => void downloadPackage(id)}
                            disabled={!id || downloadBusy}
                          >
                            Download
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!packages.length ? (
                  <TableRow>
                    <TableCell colSpan={6} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading inspection packages..." : "No inspection packages found."}
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
