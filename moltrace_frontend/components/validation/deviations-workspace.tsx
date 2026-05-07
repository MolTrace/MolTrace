"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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

type Row = Record<string, unknown>

const SEVERITY_OPTIONS = ["low", "medium", "high", "critical"] as const
const SOURCE_TYPE_OPTIONS = [
  "validation_test",
  "production_issue",
  "data_integrity",
  "audit",
  "report",
  "ai_model",
  "connector",
  "other",
] as const
const STATUS_OPTIONS = ["open", "investigation", "resolved", "closed", "rejected"] as const

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
  for (const key of [...keys, "deviation", "deviation_record", "record", "data"]) {
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
  return readStr(row?.id ?? row?.deviation_id)
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
  if (status === "closed" || status === "resolved") return "default"
  if (status === "rejected") return "destructive"
  if (status === "investigation") return "secondary"
  return "outline"
}

function severityVariant(value: unknown): "default" | "secondary" | "destructive" | "outline" {
  const severity = readStr(value)
  if (severity === "critical" || severity === "high") return "destructive"
  if (severity === "medium") return "secondary"
  return "outline"
}

function sourceLabel(row: Row | null | undefined): string {
  const sourceType = readStr(row?.source_type)
  const sourceId = readStr(row?.source_id)
  if (sourceType && sourceId) return `${sourceType} #${sourceId}`
  if (sourceType) return sourceType
  if (sourceId) return `#${sourceId}`
  return "-"
}

export function DeviationsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [deviations, setDeviations] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedDeviation, setSelectedDeviation] = useState<Row | null>(null)

  const [deviationCode, setDeviationCode] = useState("")
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [severity, setSeverity] = useState("low")
  const [sourceType, setSourceType] = useState("validation_test")
  const [sourceId, setSourceId] = useState("")
  const [status, setStatus] = useState("open")
  const [rootCause, setRootCause] = useState("")
  const [resolution, setResolution] = useState("")
  const [createBusy, setCreateBusy] = useState(false)

  const [editTitle, setEditTitle] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editSeverity, setEditSeverity] = useState("low")
  const [editStatus, setEditStatus] = useState("open")
  const [editRootCause, setEditRootCause] = useState("")
  const [editResolution, setEditResolution] = useState("")
  const [updateBusy, setUpdateBusy] = useState(false)

  const loadDeviations = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/deviations", { method: "GET" })
      const rows = asRows(payload, ["deviations", "deviation_records"])
      setDeviations(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load deviations."))
      setDeviations([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadDeviations()
  }, [loadDeviations])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return deviations.find((deviation) => rowId(deviation) === selectedId) ?? null
  }, [deviations, selectedId])

  const detailDeviation = selectedDeviation ?? selectedSummary

  useEffect(() => {
    if (!detailDeviation) return
    setEditTitle(readStr(detailDeviation.title))
    setEditDescription(readStr(detailDeviation.description))
    setEditSeverity(readStr(detailDeviation.severity) || "low")
    setEditStatus(readStr(detailDeviation.status) || "open")
    setEditRootCause(readStr(detailDeviation.root_cause))
    setEditResolution(readStr(detailDeviation.resolution))
  }, [detailDeviation])

  async function createDeviation() {
    if (!title.trim()) {
      setError("title is required.")
      return
    }
    if (!description.trim()) {
      setError("description is required.")
      return
    }
    const parsedSourceId = sourceId.trim() ? readInt(sourceId) : null
    if (sourceId.trim() && parsedSourceId == null) {
      setError("source ID must be a positive integer.")
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/deviations", {
        method: "POST",
        body: {
          deviation_code: deviationCode.trim() || null,
          title: title.trim(),
          description: description.trim(),
          severity,
          source_type: sourceType,
          source_id: parsedSourceId,
          status,
          root_cause: rootCause.trim() || null,
          resolution: resolution.trim() || null,
        },
      })
      const record = unwrapRecord(payload, ["deviation", "deviation_record"])
      setDeviationCode("")
      setTitle("")
      setDescription("")
      setSeverity("low")
      setSourceType("validation_test")
      setSourceId("")
      setStatus("open")
      setRootCause("")
      setResolution("")
      setMessage("Deviation record created.")
      await loadDeviations()
      if (record) {
        setSelectedId(rowId(record))
        setSelectedDeviation(record)
      }
    } catch (err) {
      setError(formatErr(err, "Could not create deviation record."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function updateDeviation() {
    const id = rowId(detailDeviation)
    if (!id) return
    if (!editTitle.trim()) {
      setError("title is required.")
      return
    }
    if (!editDescription.trim()) {
      setError("description is required.")
      return
    }

    setUpdateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/deviations/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: {
          title: editTitle.trim(),
          description: editDescription.trim(),
          severity: editSeverity,
          status: editStatus,
          root_cause: editRootCause.trim() || null,
          resolution: editResolution.trim() || null,
        },
      })
      const record = unwrapRecord(payload, ["deviation", "deviation_record"])
      setMessage("Deviation record updated.")
      await loadDeviations()
      if (record) {
        setSelectedId(rowId(record))
        setSelectedDeviation(record)
      }
    } catch (err) {
      setError(formatErr(err, "Could not update deviation record."))
    } finally {
      setUpdateBusy(false)
    }
  }

  function openDeviation(row: Row) {
    setSelectedId(rowId(row))
    setSelectedDeviation(row)
    setMessage("")
    setError("")
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Deviations</h1>
          <p className="text-muted-foreground">
            Create, update, and review deviation records with linked validation test/source context.
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Create deviation</CardTitle>
            <CardDescription>POST /deviations</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="deviation-code">deviation code</Label>
                <Input
                  id="deviation-code"
                  value={deviationCode}
                  onChange={(event) => setDeviationCode(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-title">title</Label>
                <Input id="deviation-title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="deviation-description">description</Label>
                <Textarea
                  id="deviation-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-severity">severity</Label>
                <Select value={severity} onValueChange={setSeverity}>
                  <SelectTrigger id="deviation-severity">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-status">status</Label>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger id="deviation-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-source-type">source type</Label>
                <Select value={sourceType} onValueChange={setSourceType}>
                  <SelectTrigger id="deviation-source-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_TYPE_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-source-id">source ID</Label>
                <Input
                  id="deviation-source-id"
                  inputMode="numeric"
                  value={sourceId}
                  onChange={(event) => setSourceId(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-root-cause">root cause</Label>
                <Textarea
                  id="deviation-root-cause"
                  value={rootCause}
                  onChange={(event) => setRootCause(event.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="deviation-resolution">resolution</Label>
                <Textarea
                  id="deviation-resolution"
                  value={resolution}
                  onChange={(event) => setResolution(event.target.value)}
                  rows={3}
                />
              </div>
            </div>
            <Button type="button" onClick={createDeviation} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create deviation"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Selected deviation</CardTitle>
            <CardDescription>PATCH /deviations/{"{deviation_id}"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {detailDeviation ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <p className="text-xs text-muted-foreground">deviation code</p>
                    <p className="font-medium">{readStr(detailDeviation.deviation_code) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">severity</p>
                    <Badge variant={severityVariant(detailDeviation.severity)}>
                      {readStr(detailDeviation.severity) || "-"}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">status</p>
                    <Badge variant={statusVariant(detailDeviation.status)}>{readStr(detailDeviation.status) || "-"}</Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">linked validation test/source</p>
                    <p className="font-medium">{sourceLabel(detailDeviation)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">created date</p>
                    <p className="font-medium">{formatDate(detailDeviation.created_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">updated date</p>
                    <p className="font-medium">{formatDate(detailDeviation.updated_at)}</p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="edit-deviation-title">title</Label>
                    <Input
                      id="edit-deviation-title"
                      value={editTitle}
                      onChange={(event) => setEditTitle(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="edit-deviation-description">description</Label>
                    <Textarea
                      id="edit-deviation-description"
                      value={editDescription}
                      onChange={(event) => setEditDescription(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-deviation-severity">severity</Label>
                    <Select value={editSeverity} onValueChange={setEditSeverity}>
                      <SelectTrigger id="edit-deviation-severity">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SEVERITY_OPTIONS.map((option) => (
                          <SelectItem key={option} value={option}>
                            {option}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-deviation-status">status</Label>
                    <Select value={editStatus} onValueChange={setEditStatus}>
                      <SelectTrigger id="edit-deviation-status">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {STATUS_OPTIONS.map((option) => (
                          <SelectItem key={option} value={option}>
                            {option}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-deviation-root-cause">root cause</Label>
                    <Textarea
                      id="edit-deviation-root-cause"
                      value={editRootCause}
                      onChange={(event) => setEditRootCause(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-deviation-resolution">resolution</Label>
                    <Textarea
                      id="edit-deviation-resolution"
                      value={editResolution}
                      onChange={(event) => setEditResolution(event.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
                <Button type="button" variant="outline" onClick={updateDeviation} disabled={updateBusy}>
                  {updateBusy ? "Updating..." : "Update deviation"}
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {loading ? "Loading deviations..." : "Select a deviation to view update controls."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">Deviation table</CardTitle>
            <CardDescription>GET /deviations</CardDescription>
          </div>
          <Button type="button" variant="outline" onClick={() => void loadDeviations()} disabled={loading}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>deviation code</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>severity</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>linked validation test/source</TableHead>
                  <TableHead>root cause</TableHead>
                  <TableHead>updated date</TableHead>
                  <TableHead className="text-right">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {deviations.map((deviation) => {
                  const id = rowId(deviation)
                  return (
                    <TableRow key={id || JSON.stringify(deviation)}>
                      <TableCell className="font-medium">{readStr(deviation.deviation_code) || "-"}</TableCell>
                      <TableCell>{readStr(deviation.title) || "-"}</TableCell>
                      <TableCell>
                        <Badge variant={severityVariant(deviation.severity)}>{readStr(deviation.severity) || "-"}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(deviation.status)}>{readStr(deviation.status) || "-"}</Badge>
                      </TableCell>
                      <TableCell>{sourceLabel(deviation)}</TableCell>
                      <TableCell className="max-w-[260px] truncate">{readStr(deviation.root_cause) || "-"}</TableCell>
                      <TableCell>{formatDate(deviation.updated_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant={selectedId === id ? "secondary" : "outline"}
                          size="sm"
                          onClick={() => openDeviation(deviation)}
                          disabled={!id}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!deviations.length ? (
                  <TableRow>
                    <TableCell colSpan={8} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading deviations..." : "No deviations found."}
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
