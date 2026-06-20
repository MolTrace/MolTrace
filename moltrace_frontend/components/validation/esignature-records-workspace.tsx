"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { useStepUp } from "@/components/auth/step-up-provider"
import { withStepUp } from "@/lib/auth/with-step-up"
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
import { FileText, PenTool, Printer, ShieldCheck, Signature } from "lucide-react"
import {
  getManifestationJson,
  printManifestation,
  verifySignature,
  verifyStatus,
  type ESignatureManifestation,
  type ESignatureVerification,
} from "@/lib/validation/esignature-verify"
import { cn } from "@/lib/utils"

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

  const [signatureMeaning, setSignatureMeaning] = useState("reviewed")
  const [targetType, setTargetType] = useState("")
  const [targetId, setTargetId] = useState("")
  const [reason, setReason] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const { ensureStepUp } = useStepUp()
  const [createdRecord, setCreatedRecord] = useState<Row | null>(null)

  // Part 11 hardening: §11.70 integrity verify + §11.50 manifestation for the open record.
  const [verification, setVerification] = useState<ESignatureVerification | null>(null)
  const [verifyBusy, setVerifyBusy] = useState(false)
  const [manifestation, setManifestation] = useState<ESignatureManifestation | null>(null)
  const [manifestBusy, setManifestBusy] = useState(false)
  const [printBusy, setPrintBusy] = useState(false)

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
    setVerification(null)
    setManifestation(null)
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

  async function handleVerify(id: string) {
    if (!id) return
    setVerifyBusy(true)
    setError("")
    try {
      setVerification(await verifySignature(id))
    } catch (err) {
      setError(formatErr(err, "Could not verify signature integrity."))
    } finally {
      setVerifyBusy(false)
    }
  }

  async function handleManifest(id: string) {
    if (!id) return
    setManifestBusy(true)
    setError("")
    try {
      setManifestation(await getManifestationJson(id))
    } catch (err) {
      setError(formatErr(err, "Could not load the signature manifestation."))
    } finally {
      setManifestBusy(false)
    }
  }

  async function handlePrint(id: string) {
    if (!id) return
    setPrintBusy(true)
    setError("")
    try {
      const ok = await printManifestation(id)
      if (!ok) setError("Could not open the print view — check that pop-ups are allowed.")
    } catch (err) {
      setError(formatErr(err, "Could not print the signature manifestation."))
    } finally {
      setPrintBusy(false)
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
      // Signing is step-up-gated: on a 401 step_up_required, run the ceremony and
      // retry the create once (also proactively elevated if the user just verified).
      const payload = await withStepUp(
        () =>
          // Signer identity is server-authoritative (§11.100): the backend ignores any
          // signer_name/signer_email in the body and signs as the authenticated user, so
          // we no longer collect or send them.
          apiFetch<unknown>("/esignatures/records", {
            method: "POST",
            body: {
              signature_meaning: signatureMeaning,
              target_type: targetType.trim(),
              target_id: parsedTargetId,
              reason: reason.trim(),
            },
          }),
        ensureStepUp,
      )
      const record = unwrapRecord(payload, ["signature_record", "e_signature_record"])
      setCreatedRecord(record)
      if (record) {
        const id = rowId(record)
        setSelectedId(id)
        setSelectedRecord(record)
        setVerification(null)
        setManifestation(null)
      }
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
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-green)" }}
          >
            MolTrace · e-Signatures
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">e-Signatures</h1>
          <p className="text-sm text-muted-foreground">
            Create and review e-signature records with server timestamps, target references, reasons, and signature hashes.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      {error ? <AlertCard variant="error" title="Error" description={error} /> : null}

      {createdRecord ? (
        <AlertCard
          variant="success"
          title="Signature recorded"
          description={`e-signature record created. Server timestamp: ${formatDate(createdRecord.signed_at)}.`}
        />
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <ModuleCard
          accent="cyan"
          eyebrow="Sign"
          title="Create e-signature record"
          icon={PenTool}
          description="Reason and signature meaning are required."
        >
          <div className="space-y-4">
            <p className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
              You sign as the authenticated user — signer identity is recorded server-side from your
              session (§11.100), not from this form. Provide the meaning and reason for the signature.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
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
          </div>
        </ModuleCard>

        <ModuleCard
          accent="cyan"
          eyebrow="Detail"
          title="Read-only record"
          icon={FileText}
          description="Signature record is read-only after creation."
        >
          <div className="space-y-3">
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
                <div>
                  <p className="text-xs text-muted-foreground">signer_user_id (§11.100)</p>
                  <p className="font-mono text-xs">{readStr(detailRecord.signer_user_id) || "—"}</p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs text-muted-foreground">record content hash (§11.70)</p>
                  <p className="break-all font-mono text-xs">
                    {readStr(detailRecord.record_content_hash) || "— (unbound / legacy)"}
                  </p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs text-muted-foreground">reason</p>
                  <p className="whitespace-pre-wrap text-sm">{readStr(detailRecord.reason) || "-"}</p>
                </div>

                {/* §11.70 integrity verify + §11.50 manifestation */}
                <div className="space-y-3 border-t border-border pt-3 sm:col-span-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void handleVerify(rowId(detailRecord))}
                      disabled={verifyBusy || !rowId(detailRecord)}
                    >
                      <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                      {verifyBusy ? "Verifying…" : "Verify integrity"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void handleManifest(rowId(detailRecord))}
                      disabled={manifestBusy || !rowId(detailRecord)}
                    >
                      <FileText className="h-3.5 w-3.5" aria-hidden />
                      {manifestBusy ? "Loading…" : "View signature"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => void handlePrint(rowId(detailRecord))}
                      disabled={printBusy || !rowId(detailRecord)}
                    >
                      <Printer className="h-3.5 w-3.5" aria-hidden />
                      {printBusy ? "Opening…" : "Print"}
                    </Button>
                  </div>

                  {verification ? (
                    (() => {
                      const status = verifyStatus(verification)
                      const toneClass =
                        status.tone === "success"
                          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200"
                          : status.tone === "error"
                            ? "border-red-500/50 bg-red-500/10 text-red-900 dark:text-red-200"
                            : "border-border bg-muted/40 text-muted-foreground"
                      return (
                        <div className={cn("rounded-md border p-3 text-sm", toneClass)}>
                          <p className="font-medium">{status.label}</p>
                          <p className="mt-0.5 text-xs opacity-90">{status.detail}</p>
                          <p className="mt-1 font-mono text-[11px] opacity-70">reason: {verification.reason}</p>
                        </div>
                      )
                    })()
                  ) : null}

                  {manifestation ? (
                    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3 text-xs">
                      <p className="text-sm font-medium">{manifestation.meaningLabel}</p>
                      <p className="text-muted-foreground">
                        {manifestation.printedName || "—"}
                        {manifestation.signerEmail ? ` <${manifestation.signerEmail}>` : ""}
                        {manifestation.signedAtUtc ? ` · signed (UTC) ${manifestation.signedAtUtc}` : ""}
                      </p>
                      <p className="whitespace-pre-wrap">{manifestation.attestationText}</p>
                      <p className="text-muted-foreground">
                        binding: {manifestation.bindingStatus}
                        {manifestation.authenticationMethod ? ` · auth: ${manifestation.authenticationMethod}` : ""}
                        {manifestation.stepUpAal ? ` · AAL: ${manifestation.stepUpAal}` : ""}
                      </p>
                      {/* §11 grounding: surface the backend compliance notice verbatim. */}
                      <p className="border-t border-border pt-2 italic text-muted-foreground">
                        {manifestation.complianceNotice}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {detailLoading ? "Loading e-signature record..." : "Select an e-signature record to view details."}
              </p>
            )}
          </div>
        </ModuleCard>
      </div>

      <ModuleCard
        accent="cyan"
        eyebrow="Records"
        title="e-Signature records"
        icon={Signature}
        description="Electronic signature records for GxP-critical actions — approval events, reviewer sign-offs, and controlled-record authorizations."
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
        </div>
      </ModuleCard>
    </div>
  )
}
