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

const SIGNATURE_MEANING_OPTIONS = [
  "reviewed",
  "approved",
  "rejected",
  "authored",
  "verified",
  "released",
  "locked",
  "override",
  "other",
] as const

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
  for (const key of [...keys, "record", "signature", "esignature", "data"]) {
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
  return readStr(row?.id ?? row?.signature_id)
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

export function ESignatureRecordsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [records, setRecords] = useState<Row[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [selectedRecord, setSelectedRecord] = useState<Row | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [signerName, setSignerName] = useState("")
  const [signerEmail, setSignerEmail] = useState("")
  const [signatureMeaning, setSignatureMeaning] = useState("reviewed")
  const [targetType, setTargetType] = useState("")
  const [targetId, setTargetId] = useState("")
  const [reason, setReason] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createdRecord, setCreatedRecord] = useState<Row | null>(null)

  const loadRecords = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/esignatures/records", { method: "GET" })
      const rows = asRows(payload, ["signatures", "signature_records", "e_signature_records", "esignatures"])
      setRecords(rows)
      if (!selectedId && rows.length > 0) setSelectedId(rowId(rows[0]!))
    } catch (err) {
      setError(formatErr(err, "Could not load e-signature records."))
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

  async function loadDetail(id: string) {
    if (!id) return
    setSelectedId(id)
    setDetailLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>(`/esignatures/records/${encodeURIComponent(id)}`, { method: "GET" })
      setSelectedRecord(unwrapRecord(payload, ["signature_record", "e_signature_record"]))
    } catch (err) {
      setError(formatErr(err, "Could not load e-signature record."))
      setSelectedRecord(null)
    } finally {
      setDetailLoading(false)
    }
  }

  async function createSignatureRecord() {
    const parsedTargetId = readInt(targetId)
    if (!signatureMeaning.trim()) {
      setError("signature meaning is required.")
      return
    }
    if (!reason.trim()) {
      setError("reason is required.")
      return
    }
    if (!signerName.trim()) {
      setError("signer name is required.")
      return
    }
    if (!targetType.trim()) {
      setError("target type is required.")
      return
    }
    if (parsedTargetId == null) {
      setError("target ID must be a positive integer.")
      return
    }

    setCreateBusy(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/esignatures/records", {
        method: "POST",
        body: {
          signer_name: signerName.trim(),
          signer_email: signerEmail.trim() || null,
          signature_meaning: signatureMeaning,
          target_type: targetType.trim(),
          target_id: parsedTargetId,
          reason: reason.trim(),
        },
      })
      const record = unwrapRecord(payload, ["signature_record", "e_signature_record"])
      setCreatedRecord(record)
      if (record) {
        const id = rowId(record)
        setSelectedId(id)
        setSelectedRecord(record)
      }
      setSignerName("")
      setSignerEmail("")
      setSignatureMeaning("reviewed")
      setTargetType("")
      setTargetId("")
      setReason("")
      await loadRecords()
    } catch (err) {
      setError(formatErr(err, "Could not create e-signature record."))
    } finally {
      setCreateBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">e-Signatures</h1>
          <p className="text-muted-foreground">
            Create and review e-signature records with server timestamps, target references, reasons, and signature hashes.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {createdRecord ? (
        <Alert>
          <AlertDescription>
            e-signature record created. Server timestamp: {formatDate(createdRecord.signed_at)}.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Create e-signature record</CardTitle>
            <CardDescription>reason and signature meaning are required.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="signature-signer-name">signer name</Label>
                <Input
                  id="signature-signer-name"
                  value={signerName}
                  onChange={(event) => setSignerName(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="signature-signer-email">signer email optional</Label>
                <Input
                  id="signature-signer-email"
                  type="email"
                  value={signerEmail}
                  onChange={(event) => setSignerEmail(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="signature-meaning">signature meaning</Label>
                <Select value={signatureMeaning} onValueChange={setSignatureMeaning}>
                  <SelectTrigger id="signature-meaning">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SIGNATURE_MEANING_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="signature-target-type">target type</Label>
                <Input
                  id="signature-target-type"
                  value={targetType}
                  onChange={(event) => setTargetType(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="signature-target-id">target ID</Label>
                <Input
                  id="signature-target-id"
                  inputMode="numeric"
                  value={targetId}
                  onChange={(event) => setTargetId(event.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="signature-reason">reason</Label>
              <Textarea
                id="signature-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
              />
            </div>
            <Button type="button" onClick={createSignatureRecord} disabled={createBusy}>
              {createBusy ? "Creating..." : "Create e-signature record"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Read-only record</CardTitle>
            <CardDescription>Signature record is read-only after creation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {detailRecord ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-muted-foreground">signer name</p>
                  <p className="font-medium">{readStr(detailRecord.signer_name) || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">signature meaning</p>
                  <Badge variant="secondary">{readStr(detailRecord.signature_meaning) || "-"}</Badge>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">target type</p>
                  <p className="font-medium">{readStr(detailRecord.target_type) || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">target ID</p>
                  <p className="font-medium">{readStr(detailRecord.target_id) || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">server timestamp</p>
                  <p className="font-medium">{formatDate(detailRecord.signed_at)}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">signature hash</p>
                  <p className="break-all font-mono text-xs">{readStr(detailRecord.signature_hash) || "-"}</p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs text-muted-foreground">reason</p>
                  <p className="whitespace-pre-wrap text-sm">{readStr(detailRecord.reason) || "-"}</p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading e-signature record..." : "Select an e-signature record to view details."}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">e-Signature records</CardTitle>
            <CardDescription>Electronic signature records for GxP-critical actions — approval events, reviewer sign-offs, and controlled-record authorizations.</CardDescription>
          </div>
          <Button type="button" variant="outline" onClick={() => void loadRecords()} disabled={loading}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>signer name</TableHead>
                  <TableHead>signature meaning</TableHead>
                  <TableHead>target type</TableHead>
                  <TableHead>target ID</TableHead>
                  <TableHead>server timestamp</TableHead>
                  <TableHead>signature hash</TableHead>
                  <TableHead className="text-right">open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records.map((record) => {
                  const id = rowId(record)
                  return (
                    <TableRow key={id || JSON.stringify(record)}>
                      <TableCell className="font-medium">{readStr(record.signer_name) || "-"}</TableCell>
                      <TableCell>{readStr(record.signature_meaning) || "-"}</TableCell>
                      <TableCell>{readStr(record.target_type) || "-"}</TableCell>
                      <TableCell>{readStr(record.target_id) || "-"}</TableCell>
                      <TableCell>{formatDate(record.signed_at)}</TableCell>
                      <TableCell className="font-mono text-xs">{shortHash(record.signature_hash)}</TableCell>
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
                    <TableCell colSpan={7} className="py-6 text-center text-sm text-muted-foreground">
                      {loading ? "Loading e-signature records..." : "No e-signature records found."}
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
