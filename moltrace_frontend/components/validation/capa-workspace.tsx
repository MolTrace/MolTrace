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

const STATUS_OPTIONS = ["open", "in_progress", "effectiveness_check", "closed", "canceled"] as const

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
  for (const key of [...keys, "capa", "capa_record", "record", "data"]) {
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
  return readStr(row?.id ?? row?.capa_id)
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

function toDatetimeInput(value: unknown): string {
  const text = readStr(value)
  if (!text) return ""
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return ""
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 16)
}

function parseDatetimeInput(value: string): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const date = new Date(trimmed)
  if (Number.isNaN(date.getTime())) throw new Error("due date must be valid.")
  return date.toISOString()
}

function statusVariant(value: unknown): "default" | "secondary" | "destructive" | "outline" {
  const status = readStr(value)
  if (status === "closed") return "default"
  if (status === "canceled") return "destructive"
  if (status === "in_progress" || status === "effectiveness_check") return "secondary"
  return "outline"
}

function isOverdue(row: Row | null | undefined): boolean {
  const status = readStr(row?.status)
  if (status === "closed" || status === "canceled") return false
  const dueDate = new Date(readStr(row?.due_date))
  if (Number.isNaN(dueDate.getTime())) return false
  return dueDate.getTime() < Date.now()
}

function deviationSourceLabel(row: Row | null | undefined): string {
  const sourceType = readStr(row?.source_type)
  const sourceId = readStr(row?.source_id)
  if (sourceType && sourceId) return `${sourceType} #${sourceId}`
  if (sourceType) return sourceType
  if (sourceId) return `#${sourceId}`
  return "-"
}

function deviationLabel(row: Row | null | undefined, id: string): string {
  if (!row) return id ? `deviation #${id}` : "-"
  const code = readStr(row.deviation_code) || `deviation #${id}`
  const title = readStr(row.title)
  return title ? `${code}: ${title}` : code
}

export function CapaWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const [capaRecords, setCapaRecords] = useState<Row[]>([])
  const [deviations, setDeviations] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedCapa, setSelectedCapa] = useState<Row | null>(null)

  const [capaCode, setCapaCode] = useState("")
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [sourceDeviationId, setSourceDeviationId] = useState("")
  const [correctiveAction, setCorrectiveAction] = useState("")
  const [preventiveAction, setPreventiveAction] = useState("")
  const [owner, setOwner] = useState("")
  const [dueDate, setDueDate] = useState("")
  const [status, setStatus] = useState("open")
  const [createBusy, setCreateBusy] = useState(false)

  const [editTitle, setEditTitle] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editSourceDeviationId, setEditSourceDeviationId] = useState("")
  const [editCorrectiveAction, setEditCorrectiveAction] = useState("")
  const [editPreventiveAction, setEditPreventiveAction] = useState("")
  const [editOwner, setEditOwner] = useState("")
  const [editDueDate, setEditDueDate] = useState("")
  const [editStatus, setEditStatus] = useState("open")
  const [updateBusy, setUpdateBusy] = useState(false)

  const loadWorkspace = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [capaPayload, deviationPayload] = await Promise.all([
        apiFetch<unknown>("/capa", { method: "GET" }),
        apiFetch<unknown>("/deviations", { method: "GET" }),
      ])
      const capaRows = asRows(capaPayload, ["capa", "capa_records"])
      setCapaRecords(capaRows)
      setDeviations(asRows(deviationPayload, ["deviations", "deviation_records"]))
      if (!selectedId && capaRows.length > 0) setSelectedId(rowId(capaRows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load CAPA workspace."))
      setCapaRecords([])
      setDeviations([])
    } finally {
      setLoading(false)
    }
  }, [selectedId])

  useEffect(() => {
    void loadWorkspace()
  }, [loadWorkspace])

  const selectedSummary = useMemo(() => {
    if (!selectedId) return null
    return capaRecords.find((capa) => rowId(capa) === selectedId) ?? null
  }, [capaRecords, selectedId])

  const detailCapa = selectedCapa ?? selectedSummary
  const deviationById = useMemo(() => {
    const entries = deviations.map((deviation) => [rowId(deviation), deviation] as const)
    return new Map(entries.filter(([id]) => Boolean(id)))
  }, [deviations])
  const detailSourceDeviationId = readStr(detailCapa?.source_deviation_id)
  const detailSourceDeviation = deviationById.get(detailSourceDeviationId) ?? null

  useEffect(() => {
    if (!detailCapa) return
    setEditTitle(readStr(detailCapa.title))
    setEditDescription(readStr(detailCapa.description))
    setEditSourceDeviationId(readStr(detailCapa.source_deviation_id))
    setEditCorrectiveAction(readStr(detailCapa.corrective_action))
    setEditPreventiveAction(readStr(detailCapa.preventive_action))
    setEditOwner(readStr(detailCapa.owner))
    setEditDueDate(toDatetimeInput(detailCapa.due_date))
    setEditStatus(readStr(detailCapa.status) || "open")
  }, [detailCapa])

  async function createCapa() {
    if (!title.trim()) {
      setError("title is required.")
      return
    }
    if (!description.trim()) {
      setError("description is required.")
      return
    }
    if (!correctiveAction.trim()) {
      setError("corrective action is required.")
      return
    }
    if (!preventiveAction.trim()) {
      setError("preventive action is required.")
      return
    }

    const parsedSourceDeviationId = sourceDeviationId.trim() ? readInt(sourceDeviationId) : null
    if (sourceDeviationId.trim() && parsedSourceDeviationId == null) {
      setError("source deviation must be a positive integer.")
      return
    }

    let parsedDueDate: string | null
    try {
      parsedDueDate = parseDatetimeInput(dueDate)
    } catch (err) {
      setError(formatErr(err, "due date is invalid."))
      return
    }

    setCreateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>("/capa", {
        method: "POST",
        body: {
          capa_code: capaCode.trim() || null,
          title: title.trim(),
          description: description.trim(),
          source_deviation_id: parsedSourceDeviationId,
          corrective_action: correctiveAction.trim(),
          preventive_action: preventiveAction.trim(),
          owner: owner.trim() || null,
          due_date: parsedDueDate,
          status,
        },
      })
      const record = unwrapRecord(payload, ["capa", "capa_record"])
      setCapaCode("")
      setTitle("")
      setDescription("")
      setSourceDeviationId("")
      setCorrectiveAction("")
      setPreventiveAction("")
      setOwner("")
      setDueDate("")
      setStatus("open")
      setMessage("CAPA record created.")
      await loadWorkspace()
      if (record) {
        setSelectedId(rowId(record))
        setSelectedCapa(record)
      }
    } catch (err) {
      setError(formatErr(err, "Could not create CAPA record."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function updateCapa() {
    const id = rowId(detailCapa)
    if (!id) return
    if (!editTitle.trim()) {
      setError("title is required.")
      return
    }
    if (!editDescription.trim()) {
      setError("description is required.")
      return
    }
    if (!editCorrectiveAction.trim()) {
      setError("corrective action is required.")
      return
    }
    if (!editPreventiveAction.trim()) {
      setError("preventive action is required.")
      return
    }

    const parsedSourceDeviationId = editSourceDeviationId.trim() ? readInt(editSourceDeviationId) : null
    if (editSourceDeviationId.trim() && parsedSourceDeviationId == null) {
      setError("source deviation must be a positive integer.")
      return
    }

    let parsedDueDate: string | null
    try {
      parsedDueDate = parseDatetimeInput(editDueDate)
    } catch (err) {
      setError(formatErr(err, "due date is invalid."))
      return
    }

    setUpdateBusy(true)
    setError("")
    setMessage("")
    try {
      const payload = await apiFetch<unknown>(`/capa/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: {
          title: editTitle.trim(),
          description: editDescription.trim(),
          source_deviation_id: parsedSourceDeviationId,
          corrective_action: editCorrectiveAction.trim(),
          preventive_action: editPreventiveAction.trim(),
          owner: editOwner.trim() || null,
          due_date: parsedDueDate,
          status: editStatus,
        },
      })
      const record = unwrapRecord(payload, ["capa", "capa_record"])
      setMessage("CAPA record updated.")
      await loadWorkspace()
      if (record) {
        setSelectedId(rowId(record))
        setSelectedCapa(record)
      }
    } catch (err) {
      setError(formatErr(err, "Could not update CAPA record."))
    } finally {
      setUpdateBusy(false)
    }
  }

  function openCapa(row: Row) {
    setSelectedId(rowId(row))
    setSelectedCapa(row)
    setMessage("")
    setError("")
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">CAPA</h1>
          <p className="text-muted-foreground">
            Create, update, and review corrective and preventive action records linked to deviations.
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
            <CardTitle className="text-base">Create CAPA</CardTitle>
            <CardDescription>POST /capa</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="capa-code">CAPA code</Label>
                <Input id="capa-code" value={capaCode} onChange={(event) => setCapaCode(event.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-title">title</Label>
                <Input id="capa-title" value={title} onChange={(event) => setTitle(event.target.value)} />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="capa-description">description</Label>
                <Textarea
                  id="capa-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-source-deviation">source deviation</Label>
                <Input
                  id="capa-source-deviation"
                  inputMode="numeric"
                  value={sourceDeviationId}
                  onChange={(event) => setSourceDeviationId(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-status">status</Label>
                <Select value={status} onValueChange={setStatus}>
                  <SelectTrigger id="capa-status">
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
                <Label htmlFor="capa-owner">owner</Label>
                <Input id="capa-owner" value={owner} onChange={(event) => setOwner(event.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-due-date">due date</Label>
                <Input
                  id="capa-due-date"
                  type="datetime-local"
                  value={dueDate}
                  onChange={(event) => setDueDate(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-corrective-action">corrective action</Label>
                <Textarea
                  id="capa-corrective-action"
                  value={correctiveAction}
                  onChange={(event) => setCorrectiveAction(event.target.value)}
                  rows={3}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="capa-preventive-action">preventive action</Label>
                <Textarea
                  id="capa-preventive-action"
                  value={preventiveAction}
                  onChange={(event) => setPreventiveAction(event.target.value)}
                  rows={3}
                />
              </div>
            </div>
            <Button type="button" onClick={createCapa} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create CAPA"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Selected CAPA</CardTitle>
            <CardDescription>PATCH /capa/{"{capa_id}"}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {detailCapa ? (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <p className="text-xs text-muted-foreground">CAPA code</p>
                    <p className="font-medium">{readStr(detailCapa.capa_code) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">status</p>
                    <Badge variant={statusVariant(detailCapa.status)}>{readStr(detailCapa.status) || "-"}</Badge>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">overdue marker</p>
                    {isOverdue(detailCapa) ? <Badge variant="destructive">overdue</Badge> : <span className="text-sm">-</span>}
                  </div>
                  <div className="sm:col-span-2">
                    <p className="text-xs text-muted-foreground">source deviation</p>
                    <p className="font-medium">{deviationLabel(detailSourceDeviation, detailSourceDeviationId)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">linked validation test/source</p>
                    <p className="font-medium">{deviationSourceLabel(detailSourceDeviation)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">owner</p>
                    <p className="font-medium">{readStr(detailCapa.owner) || "-"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">due date</p>
                    <p className="font-medium">{formatDate(detailCapa.due_date)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">updated date</p>
                    <p className="font-medium">{formatDate(detailCapa.updated_at)}</p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="edit-capa-title">title</Label>
                    <Input id="edit-capa-title" value={editTitle} onChange={(event) => setEditTitle(event.target.value)} />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="edit-capa-description">description</Label>
                    <Textarea
                      id="edit-capa-description"
                      value={editDescription}
                      onChange={(event) => setEditDescription(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-capa-source-deviation">source deviation</Label>
                    <Input
                      id="edit-capa-source-deviation"
                      inputMode="numeric"
                      value={editSourceDeviationId}
                      onChange={(event) => setEditSourceDeviationId(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-capa-status">status</Label>
                    <Select value={editStatus} onValueChange={setEditStatus}>
                      <SelectTrigger id="edit-capa-status">
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
                    <Label htmlFor="edit-capa-owner">owner</Label>
                    <Input id="edit-capa-owner" value={editOwner} onChange={(event) => setEditOwner(event.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-capa-due-date">due date</Label>
                    <Input
                      id="edit-capa-due-date"
                      type="datetime-local"
                      value={editDueDate}
                      onChange={(event) => setEditDueDate(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-capa-corrective-action">corrective action</Label>
                    <Textarea
                      id="edit-capa-corrective-action"
                      value={editCorrectiveAction}
                      onChange={(event) => setEditCorrectiveAction(event.target.value)}
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="edit-capa-preventive-action">preventive action</Label>
                    <Textarea
                      id="edit-capa-preventive-action"
                      value={editPreventiveAction}
                      onChange={(event) => setEditPreventiveAction(event.target.value)}
                      rows={3}
                    />
                  </div>
                </div>
                <Button type="button" variant="outline" onClick={updateCapa} disabled={updateBusy}>
                  {updateBusy ? "Updating..." : "Update CAPA"}
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">
                {loading ? "Loading CAPA records..." : "Select a CAPA record to view update controls."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">CAPA table</CardTitle>
            <CardDescription>GET /capa</CardDescription>
          </div>
          <Button type="button" variant="outline" onClick={() => void loadWorkspace()} disabled={loading}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>CAPA code</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>source deviation</TableHead>
                  <TableHead>linked validation test/source</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>owner</TableHead>
                  <TableHead>due date</TableHead>
                  <TableHead>overdue marker</TableHead>
                  <TableHead className="text-right">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {capaRecords.map((capa) => {
                  const id = rowId(capa)
                  const linkedDeviationId = readStr(capa.source_deviation_id)
                  const linkedDeviation = deviationById.get(linkedDeviationId) ?? null
                  return (
                    <TableRow key={id || JSON.stringify(capa)}>
                      <TableCell className="font-medium">{readStr(capa.capa_code) || "-"}</TableCell>
                      <TableCell>{readStr(capa.title) || "-"}</TableCell>
                      <TableCell>{deviationLabel(linkedDeviation, linkedDeviationId)}</TableCell>
                      <TableCell>{deviationSourceLabel(linkedDeviation)}</TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(capa.status)}>{readStr(capa.status) || "-"}</Badge>
                      </TableCell>
                      <TableCell>{readStr(capa.owner) || "-"}</TableCell>
                      <TableCell>{formatDate(capa.due_date)}</TableCell>
                      <TableCell>
                        {isOverdue(capa) ? <Badge variant="destructive">overdue</Badge> : <span className="text-sm">-</span>}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant={selectedId === id ? "secondary" : "outline"}
                          size="sm"
                          onClick={() => openCapa(capa)}
                          disabled={!id}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!capaRecords.length ? (
                  <TableRow>
                    <TableCell colSpan={9} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading CAPA records..." : "No CAPA records found."}
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
