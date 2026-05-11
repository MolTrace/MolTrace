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
import { FileCheck2, FileText, Plus } from "lucide-react"

type Row = Record<string, unknown>

const RECORD_TYPE_OPTIONS = [
  "report",
  "validation_protocol",
  "validation_result",
  "regulatory_dossier",
  "ctd_bundle",
  "ai_model_card",
  "workflow_template",
  "sop",
  "release_record",
  "other",
] as const

const RECORD_STATUS_OPTIONS = ["draft", "in_review", "approved", "locked", "archived", "superseded"] as const

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
  for (const key of [...keys, "controlled_record", "record", "data"]) {
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
  return readStr(row?.id ?? row?.record_id)
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function shortHash(value: unknown): string {
  const text = readStr(value)
  if (!text) return "-"
  if (text.length <= 18) return text
  return `${text.slice(0, 12)}...${text.slice(-6)}`
}

function formatDate(value: unknown): string {
  const text = readStr(value)
  if (!text) return "-"
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text
  return date.toLocaleString()
}

function optionalHash(value: string): string | null {
  const trimmed = value.trim()
  return trimmed || null
}

export function ControlledRecordsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [records, setRecords] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedRecord, setSelectedRecord] = useState<Row | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [title, setTitle] = useState("")
  const [recordType, setRecordType] = useState("report")
  const [resourceId, setResourceId] = useState("")
  const [version, setVersion] = useState("1")
  const [status, setStatus] = useState("draft")
  const [contentHash, setContentHash] = useState("")
  const [createBusy, setCreateBusy] = useState(false)

  const [newVersionTitle, setNewVersionTitle] = useState("")
  const [newVersion, setNewVersion] = useState("")
  const [newVersionHash, setNewVersionHash] = useState("")
  const [lockReason, setLockReason] = useState("")
  const [lockedBy, setLockedBy] = useState("")
  const [lockHash, setLockHash] = useState("")
  const [archiveReason, setArchiveReason] = useState("")
  const [actionBusy, setActionBusy] = useState("")

  const loadRecords = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/controlled-records", { method: "GET" })
      const rows = asRows(payload, ["controlled_records", "records"])
      setRecords(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load controlled records."))
      setRecords([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadRecords()
  }, [loadRecords])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return records.find((record) => rowId(record) === selectedId) ?? null
  }, [records, selectedId])

  const detailRecord = selectedRecord ?? selectedSummary
  const detailStatus = readStr(detailRecord?.status)
  const isLocked = detailStatus === "locked"
  const isArchived = detailStatus === "archived"

  async function refreshDetail(id: string) {
    if (!id) return
    const payload = await apiFetch<unknown>(`/controlled-records/${encodeURIComponent(id)}`, { method: "GET" })
    setSelectedRecord(unwrapRecord(payload, ["controlled_record"]))
  }

  async function loadDetail(id: string) {
    if (!id) return
    setSelectedId(id)
    setDetailLoading(true)
    setError("")
    try {
      await refreshDetail(id)
    } catch (err) {
      setError(formatErr(err, "Could not load controlled record."))
      setSelectedRecord(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function createControlledRecord() {
    if (!title.trim()) {
      setError("title is required.")
      return
    }
    if (!version.trim()) {
      setError("version is required.")
      return
    }
    const parsedResourceId = resourceId.trim() ? readInt(resourceId) : null
    if (resourceId.trim() && parsedResourceId == null) {
      setError("resource ID must be a positive integer.")
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/controlled-records", {
        method: "POST",
        body: {
          record_type: recordType,
          resource_id: parsedResourceId,
          title: title.trim(),
          version: version.trim(),
          status,
          content_hash: optionalHash(contentHash),
        },
      })
      const record = unwrapRecord(payload, ["controlled_record"])
      if (record) {
        setSelectedId(rowId(record))
        setSelectedRecord(record)
      }
      setTitle("")
      setRecordType("report")
      setResourceId("")
      setVersion("1")
      setStatus("draft")
      setContentHash("")
      setMessage("Controlled record created.")
      await loadRecords()
    } catch (err) {
      setError(formatErr(err, "Could not create controlled record."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function createNewVersion() {
    const id = rowId(detailRecord)
    if (!id) return
    setActionBusy("new-version")
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/controlled-records/${encodeURIComponent(id)}/new-version`, {
        method: "POST",
        body: {
          title: newVersionTitle.trim() || null,
          version: newVersion.trim() || null,
          content_hash: optionalHash(newVersionHash),
        },
      })
      const record = unwrapRecord(payload, ["controlled_record"])
      if (record) {
        setSelectedId(rowId(record))
        setSelectedRecord(record)
      }
      setNewVersionTitle("")
      setNewVersion("")
      setNewVersionHash("")
      setMessage("New controlled record version created.")
      await loadRecords()
    } catch (err) {
      setError(formatErr(err, "Could not create a new controlled record version."))
    } finally {
      setActionBusy("")
    }
  }

  async function lockRecord() {
    const id = rowId(detailRecord)
    if (!id) return
    if (!lockedBy.trim()) {
      setError("locked by is required.")
      return
    }
    if (!lockReason.trim()) {
      setError("reason is required.")
      return
    }

    setActionBusy("lock")
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/controlled-records/${encodeURIComponent(id)}/lock`, {
        method: "POST",
        body: {
          locked_by: lockedBy.trim(),
          content_hash: optionalHash(lockHash),
          reason: lockReason.trim(),
        },
      })
      setSelectedRecord(unwrapRecord(payload, ["controlled_record"]))
      setLockedBy("")
      setLockReason("")
      setLockHash("")
      setMessage("Controlled record locked.")
      await loadRecords()
    } catch (err) {
      setError(formatErr(err, "Could not lock controlled record."))
    } finally {
      setActionBusy("")
    }
  }

  async function archiveRecord() {
    const id = rowId(detailRecord)
    if (!id) return
    if (!archiveReason.trim()) {
      setError("reason is required.")
      return
    }

    setActionBusy("archive")
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/controlled-records/${encodeURIComponent(id)}/archive`, {
        method: "POST",
        body: {
          reason: archiveReason.trim(),
        },
      })
      setSelectedRecord(unwrapRecord(payload, ["controlled_record"]))
      setArchiveReason("")
      setMessage("Controlled record archived.")
      await loadRecords()
    } catch (err) {
      setError(formatErr(err, "Could not archive controlled record."))
    } finally {
      setActionBusy("")
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
            MolTrace · Controlled Records
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Controlled Records</h1>
          <p className="text-sm text-muted-foreground">
            Create, version, lock, archive, and review controlled records for validation readiness workflows.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <AlertCard
        variant="warning"
        title="Locked records require a new version"
        description="Locked controlled records cannot be edited directly. Create a new version for changes."
      />

      {error ? <AlertCard variant="error" title="Error" description={error} /> : null}

      {message ? <AlertCard variant="success" title="Recorded" description={message} /> : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <ModuleCard
          accent="cyan"
          eyebrow="Create"
          title="Create controlled record"
          icon={Plus}
          description="Register a new controlled document with title, type, version, and responsible owner for GxP audit trail compliance."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="controlled-record-title">title</Label>
                <Input id="controlled-record-title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="controlled-record-type">record type</Label>
                <Select value={recordType} onValueChange={setRecordType}>
                  <SelectTrigger id="controlled-record-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECORD_TYPE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="controlled-record-resource-id">resource ID</Label>
                <Input
                  id="controlled-record-resource-id"
                  inputMode="numeric"
                  value={resourceId}
                  onChange={(event) => setResourceId(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="controlled-record-version">version</Label>
                <Input
                  id="controlled-record-version"
                  value={version}
                  onChange={(event) => setVersion(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="controlled-record-status">status</Label>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger id="controlled-record-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECORD_STATUS_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="controlled-record-content-hash">content hash</Label>
                <Input
                  id="controlled-record-content-hash"
                  value={contentHash}
                  onChange={(event) => setContentHash(event.target.value)}
                />
              </div>
            </div>
            <Button type="button" onClick={createControlledRecord} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create controlled record"}
            </Button>
          </div>
        </ModuleCard>

        <ModuleCard
          accent="cyan"
          eyebrow="Detail"
          title="Selected controlled record"
          icon={FileText}
          description="Selected controlled record details — version, status, owner, and full audit history."
        >
          <div className="space-y-5">
            {detailRecord ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="text-xs text-muted-foreground">title</p>
                    <p className="font-medium">{readStr(detailRecord.title) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">status</p>
                    <Badge variant="secondary">{readStr(detailRecord.status) || "-"}</Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">record type</p>
                    <p className="font-medium">{readStr(detailRecord.record_type) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">version</p>
                    <p className="font-medium">{readStr(detailRecord.version) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">locked by</p>
                    <p className="font-medium">{readStr(detailRecord.locked_by) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">updated date</p>
                    <p className="font-medium">{formatDate(detailRecord.updated_at)}</p>
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-xs text-muted-foreground">content hash</p>
                    <p className="break-all font-mono text-xs">{readStr(detailRecord.content_hash) || "-"}</p>
                  </div>
                </div>

                <div className="space-y-3 rounded-lg border p-3">
                  <div>
                    <h3 className="text-sm font-medium">Create new version</h3>
                    <p className="text-xs text-muted-foreground">Create a new controlled version of this record — specify title, version identifier, and content hash.</p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      aria-label="new version title"
                      placeholder="title"
                      value={newVersionTitle}
                      onChange={(event) => setNewVersionTitle(event.target.value)}
                    />
                    <Input
                      aria-label="new version"
                      placeholder="version"
                      value={newVersion}
                      onChange={(event) => setNewVersion(event.target.value)}
                    />
                    <Input
                      aria-label="new version content hash"
                      className="sm:col-span-2"
                      placeholder="content hash"
                      value={newVersionHash}
                      onChange={(event) => setNewVersionHash(event.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={createNewVersion}
                    disabled={actionBusy === "new-version" || isArchived}
                  >
                    {actionBusy === "new-version" ? "Creating..." : "Create new version"}
                  </Button>
                </div>

                <div className="space-y-3 rounded-lg border p-3">
                  <div>
                    <h3 className="text-sm font-medium">Lock record</h3>
                    <p className="text-xs text-muted-foreground">Lock this record to prevent further edits — specify the reviewer, content hash, and reason for locking.</p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      aria-label="locked by"
                      placeholder="locked by"
                      value={lockedBy}
                      onChange={(event) => setLockedBy(event.target.value)}
                    />
                    <Input
                      aria-label="lock content hash"
                      placeholder="content hash"
                      value={lockHash}
                      onChange={(event) => setLockHash(event.target.value)}
                    />
                    <Textarea
                      aria-label="lock reason"
                      className="sm:col-span-2"
                      placeholder="reason"
                      rows={3}
                      value={lockReason}
                      onChange={(event) => setLockReason(event.target.value)}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={lockRecord}
                    disabled={actionBusy === "lock" || isLocked || isArchived}
                  >
                    {actionBusy === "lock" ? "Locking..." : "Lock record"}
                  </Button>
                </div>

                <div className="space-y-3 rounded-lg border p-3">
                  <div>
                    <h3 className="text-sm font-medium">Archive record</h3>
                    <p className="text-xs text-muted-foreground">Archive this record and remove it from active controlled document workflows — provide a reason for audit trail.</p>
                  </div>
                  <Textarea
                    aria-label="archive reason"
                    placeholder="reason"
                    rows={3}
                    value={archiveReason}
                    onChange={(event) => setArchiveReason(event.target.value)}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    onClick={archiveRecord}
                    disabled={actionBusy === "archive" || isArchived}
                  >
                    {actionBusy === "archive" ? "Archiving..." : "Archive"}
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading controlled record..." : "Select a controlled record to view actions."}
              </p>
            )}
          </div>
        </ModuleCard>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Records"
        title="Controlled records"
        icon={FileCheck2}
        description="All controlled documents across this environment — SOPs, validation plans, analytical methods, and other GxP-controlled records."
      >
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button type="button" variant="outline" size="sm" onClick={() => void loadRecords()} disabled={loading}>
              Refresh
            </Button>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>title</TableHead>
                  <TableHead>record type</TableHead>
                  <TableHead>resource ID</TableHead>
                  <TableHead>version</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>content hash</TableHead>
                  <TableHead>locked by</TableHead>
                  <TableHead>updated date</TableHead>
                  <TableHead className="text-right">actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record) => {
                  const id = rowId(record)
                  return (
                    <TableRow key={id || JSON.stringify(record)}>
                      <TableCell className="font-medium">{readStr(record.title) || "-"}</TableCell>
                      <TableCell>{readStr(record.record_type) || "-"}</TableCell>
                      <TableCell>{readStr(record.resource_id) || "-"}</TableCell>
                      <TableCell>{readStr(record.version) || "-"}</TableCell>
                      <TableCell>{readStr(record.status) || "-"}</TableCell>
                      <TableCell className="font-mono text-xs">{shortHash(record.content_hash)}</TableCell>
                      <TableCell>{readStr(record.locked_by) || "-"}</TableCell>
                      <TableCell>{formatDate(record.updated_at)}</TableCell>
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
                {!records.length ? (
                  <TableRow>
                    <TableCell colSpan={9} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading controlled records..." : "No controlled records found."}
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
