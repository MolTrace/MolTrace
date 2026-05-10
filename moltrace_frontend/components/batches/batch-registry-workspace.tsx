"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  BATCH_ALIQUOT_TOOLTIP,
  formatBatchUpdated,
  isRecord,
  linkedSessionReactionDossier,
  normalizeAliquotList,
  normalizeBatchList,
  pickNum,
  pickStr,
  readBatchId,
} from "@/components/batches/batch-registry-utils"
import { Boxes, FileText, FlaskConical, Package, Plus } from "lucide-react"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { BatchRegulatoryAssessmentPanel } from "@/components/regulatory-hub/batch-regulatory-assessment-panel"
import { trackAliquotCreated, trackBatchCreated } from "@/src/lib/analytics/analytics-client"

const SOURCE_TYPES = [
  "synthesized",
  "purchased",
  "isolated",
  "reference_standard",
  "imported",
  "unknown",
] as const

function normalizeCompoundsForSelect(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["compounds", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

function compoundOptionLabel(row: Record<string, unknown>): string {
  const name = pickStr(row, ["preferred_name", "preferredName", "name"])
  const id = readBatchId(row)
  if (id && name !== "—") return `${name} (${id})`
  return id ?? name
}

function compoundOptionValue(row: Record<string, unknown>): string | null {
  return readBatchId(row)
}

export function BatchRegistryWorkspace() {
  const [compounds, setCompounds] = useState<Record<string, unknown>[]>([])
  const [batches, setBatches] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [listErr, setListErr] = useState("")

  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [aliquots, setAliquots] = useState<Record<string, unknown>[]>([])
  const [aliquotsLoading, setAliquotsLoading] = useState(false)
  const [aliquotsErr, setAliquotsErr] = useState("")

  const [compoundId, setCompoundId] = useState("")
  const [batchCode, setBatchCode] = useState("")
  const [lotCode, setLotCode] = useState("")
  const [sourceType, setSourceType] = useState<string>(SOURCE_TYPES[0])
  const [reactionExperimentId, setReactionExperimentId] = useState("")
  const [spectracheckSessionId, setSpectracheckSessionId] = useState("")
  const [regulatoryDossierId, setRegulatoryDossierId] = useState("")
  const [amount, setAmount] = useState("")
  const [amountUnit, setAmountUnit] = useState("")
  const [purityPercent, setPurityPercent] = useState("")
  const [purityMethod, setPurityMethod] = useState("")
  const [status, setStatus] = useState("active")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")

  const [alSampleId, setAlSampleId] = useState("")
  const [aliquotCode, setAliquotCode] = useState("")
  const [alAmount, setAlAmount] = useState("")
  const [alAmountUnit, setAlAmountUnit] = useState("")
  const [storageLocation, setStorageLocation] = useState("")
  const [alStatus, setAlStatus] = useState("available")
  const [alCreateBusy, setAlCreateBusy] = useState(false)
  const [alCreateErr, setAlCreateErr] = useState("")

  const [batchAssessmentDossierId, setBatchAssessmentDossierId] = useState("")

  const loadCompounds = useCallback(async () => {
    try {
      const raw = await apiFetch<unknown>("/compound-registry/compounds", { method: "GET" })
      setCompounds(normalizeCompoundsForSelect(raw))
    } catch {
      setCompounds([])
    }
  }, [])

  const loadBatches = useCallback(async () => {
    setLoading(true)
    setListErr("")
    try {
      const raw = await apiFetch<unknown>("/compound-registry/batches", { method: "GET" })
      setBatches(normalizeBatchList(raw))
    } catch (e) {
      setBatches([])
      setListErr(formatApiError(e, "Could not load batches."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCompounds()
    void loadBatches()
  }, [loadCompounds, loadBatches])

  const loadAliquots = useCallback(async (batchId: string) => {
    setAliquotsLoading(true)
    setAliquotsErr("")
    setAliquots([])
    try {
      const raw = await apiFetch<unknown>(`/compound-registry/batches/${encodeURIComponent(batchId)}/aliquots`, {
        method: "GET",
      })
      setAliquots(normalizeAliquotList(raw))
    } catch (e) {
      setAliquots([])
      setAliquotsErr(formatApiError(e, "Could not load aliquots."))
    } finally {
      setAliquotsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedBatchId) void loadAliquots(selectedBatchId)
    else {
      setAliquots([])
      setAliquotsErr("")
    }
  }, [selectedBatchId, loadAliquots])

  const compoundLabelById = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of compounds) {
      const id = compoundOptionValue(c)
      if (id) m.set(id, compoundOptionLabel(c))
    }
    return m
  }, [compounds])

  const selectedBatch = useMemo(() => {
    if (!selectedBatchId) return null
    return batches.find((r) => readBatchId(r) === selectedBatchId) ?? null
  }, [batches, selectedBatchId])

  const dossierOnSelectedBatch = useMemo(() => {
    if (!selectedBatch) return null
    return (
      readRecordNumber(selectedBatch, "regulatory_dossier_id") ??
      readRecordNumber(selectedBatch, "regulatoryDossierId") ??
      null
    )
  }, [selectedBatch])

  useEffect(() => {
    if (dossierOnSelectedBatch != null) {
      setBatchAssessmentDossierId(String(dossierOnSelectedBatch))
    }
  }, [dossierOnSelectedBatch])

  const parsedBatchAssessmentDossierId = Number.parseInt(batchAssessmentDossierId.trim(), 10)
  const validBatchAssessmentDossierId =
    Number.isFinite(parsedBatchAssessmentDossierId) && parsedBatchAssessmentDossierId >= 1
  const contextBatchIdForAssessment =
    validBatchAssessmentDossierId && selectedBatchId
      ? Number.parseInt(selectedBatchId, 10)
      : null
  const contextCompoundIdForAssessment = selectedBatch
    ? readRecordNumber(selectedBatch, "compound_id") ?? readRecordNumber(selectedBatch, "compoundId")
    : null

  async function handleCreateBatch(e: React.FormEvent) {
    e.preventDefault()
    setCreateErr("")
    const cid = compoundId.trim()
    const bc = batchCode.trim()
    if (!cid) {
      setCreateErr("compound_id is required.")
      return
    }
    if (!bc) {
      setCreateErr("batch_code is required.")
      return
    }
    const compound_id = Number.parseInt(cid, 10)
    if (!Number.isFinite(compound_id)) {
      setCreateErr("compound_id must be a positive integer.")
      return
    }
    setCreateBusy(true)
    try {
      const body: Record<string, unknown> = {
        compound_id,
        batch_code: bc,
        source_type: sourceType,
      }
      if (status.trim()) body.status = status.trim()
      if (amount.trim()) {
        const a = Number.parseFloat(amount)
        if (Number.isFinite(a)) body.amount = a
      }
      if (amountUnit.trim()) body.amount_unit = amountUnit.trim()
      if (purityPercent.trim()) {
        const p = Number.parseFloat(purityPercent)
        if (Number.isFinite(p)) body.purity_percent = p
      }
      if (purityMethod.trim()) body.purity_method = purityMethod.trim()
      const lc = lotCode.trim()
      if (lc) body.lot_code = lc
      const re = reactionExperimentId.trim()
      if (re) {
        const n = Number.parseInt(re, 10)
        if (Number.isFinite(n)) body.reaction_experiment_id = n
      }
      const sc = spectracheckSessionId.trim()
      if (sc) {
        const n = Number.parseInt(sc, 10)
        body.spectracheck_session_id = Number.isFinite(n) ? n : sc
      }
      const rd = regulatoryDossierId.trim()
      if (rd) {
        const n = Number.parseInt(rd, 10)
        if (Number.isFinite(n)) body.regulatory_dossier_id = n
      }
      const created = await apiFetch<Record<string, unknown>>("/compound-registry/batches", { method: "POST", body })
      const newBatchId = pickNum(created, ["id", "batch_id", "batchId"])
      trackBatchCreated({
        compound_id,
        batch_id: newBatchId,
        source_type: sourceType,
        status: status.trim() || undefined,
        has_batch: true,
      })
      setBatchCode("")
      setLotCode("")
      setReactionExperimentId("")
      setSpectracheckSessionId("")
      setRegulatoryDossierId("")
      setAmount("")
      setAmountUnit("")
      setPurityPercent("")
      setPurityMethod("")
      await loadBatches()
    } catch (err) {
      setCreateErr(formatApiError(err, "Create batch failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function handleCreateAliquot(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedBatchId) {
      setAlCreateErr("Select a batch first.")
      return
    }
    const code = aliquotCode.trim()
    if (!code) {
      setAlCreateErr("aliquot_code is required.")
      return
    }
    setAlCreateBusy(true)
    setAlCreateErr("")
    try {
      const body: Record<string, unknown> = {
        aliquot_code: code,
        amount: alAmount.trim() === "" ? null : Number.parseFloat(alAmount),
        amount_unit: alAmountUnit.trim() || null,
        storage_location: storageLocation.trim() || null,
        status: alStatus.trim() || null,
      }
      const sid = alSampleId.trim()
      if (sid) body.sample_id = sid
      const createdAl = await apiFetch<Record<string, unknown>>(
        `/compound-registry/batches/${encodeURIComponent(selectedBatchId)}/aliquots`,
        {
          method: "POST",
          body,
        },
      )
      const parentBatchId = Number.parseInt(selectedBatchId, 10)
      const st = alStatus.trim() || readRecordString(createdAl, "status")?.trim() || ""
      trackAliquotCreated({
        batch_id: Number.isFinite(parentBatchId) ? Math.trunc(parentBatchId) : undefined,
        status: st || undefined,
      })
      setAliquotCode("")
      setAlAmount("")
      setAlAmountUnit("")
      setStorageLocation("")
      setAlSampleId("")
      await loadAliquots(selectedBatchId)
    } catch (err) {
      setAlCreateErr(formatApiError(err, "Create aliquot failed."))
    } finally {
      setAlCreateBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            MolTrace · Batch / Lot Registry
          </p>
          <div className="flex items-center gap-2">
            <Package className="h-6 w-6" style={{ color: "var(--mt-teal)" }} aria-hidden />
            <h1 className="font-mono text-2xl font-bold tracking-tight">Batch / Lot Registry</h1>
            <InfoTooltip content={BATCH_ALIQUOT_TOOLTIP} label="About batches and aliquots" />
          </div>
          <p className="text-sm text-muted-foreground">
            Register material lots, link them to compounds and evidence, and track aliquots.
          </p>
          {listErr ? <p className="mt-1 text-xs text-destructive">{listErr}</p> : null}
        </div>
        <BackendStatusIndicator />
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="Form"
        title="Create batch"
        icon={Plus}
        description="Register a new compound batch with synthesis route, purity, mass, and source provenance for compound registry traceability."
      >
        <div>
          <form className="space-y-4" onSubmit={handleCreateBatch}>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <div className="space-y-2 md:col-span-2 lg:col-span-3">
                <Label htmlFor="br-compound">compound selector</Label>
                <Select value={compoundId || "__none__"} onValueChange={(v) => setCompoundId(v === "__none__" ? "" : v)}>
                  <SelectTrigger id="br-compound">
                    <SelectValue placeholder="Select compound" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">—</SelectItem>
                    {compounds.map((c) => {
                      const v = compoundOptionValue(c)
                      if (!v) return null
                      return (
                        <SelectItem key={v} value={v}>
                          {compoundOptionLabel(c)}
                        </SelectItem>
                      )
                    })}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-batch-code">batch code</Label>
                <Input id="br-batch-code" value={batchCode} onChange={(e) => setBatchCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-lot-code">lot code optional</Label>
                <Input id="br-lot-code" value={lotCode} onChange={(e) => setLotCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-source">source type</Label>
                <Select value={sourceType} onValueChange={setSourceType}>
                  <SelectTrigger id="br-source">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-rxn">reaction experiment ID optional</Label>
                <Input id="br-rxn" value={reactionExperimentId} onChange={(e) => setReactionExperimentId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-sc">SpectraCheck session ID optional</Label>
                <Input id="br-sc" value={spectracheckSessionId} onChange={(e) => setSpectracheckSessionId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-dos">regulatory dossier ID optional</Label>
                <Input id="br-dos" value={regulatoryDossierId} onChange={(e) => setRegulatoryDossierId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-amt">amount</Label>
                <Input id="br-amt" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-amt-u">amount unit</Label>
                <Input id="br-amt-u" value={amountUnit} onChange={(e) => setAmountUnit(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-purity">purity percent</Label>
                <Input id="br-purity" value={purityPercent} onChange={(e) => setPurityPercent(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-pm">purity method</Label>
                <Input id="br-pm" value={purityMethod} onChange={(e) => setPurityMethod(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="br-status">status</Label>
                <Input id="br-status" value={status} onChange={(e) => setStatus(e.target.value)} />
              </div>
            </div>
            {createErr ? (
              <AlertCard variant="error" title="Create batch" description={createErr} />
            ) : null}
            <Button type="submit" disabled={createBusy}>
              {createBusy ? "Creating…" : "Create batch"}
            </Button>
          </form>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Registry"
        title="Batches"
        icon={Boxes}
        description="All registered compound batches — synthesis route, purity, mass, status, and compound provenance across the compound registry."
        badge={
          <Button type="button" variant="outline" size="sm" onClick={() => void loadBatches()}>
            Refresh
          </Button>
        }
      >
        <div className="space-y-4">
          {loading ? <p className="text-sm text-muted-foreground">Loading batches…</p> : null}
          {!loading && batches.length === 0 ? (
            <p className="text-sm text-muted-foreground">No batches returned.</p>
          ) : null}
          {!loading && batches.length > 0 ? (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>batch code</TableHead>
                    <TableHead>compound</TableHead>
                    <TableHead>source type</TableHead>
                    <TableHead>purity</TableHead>
                    <TableHead>amount</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>linked session/reaction/dossier</TableHead>
                    <TableHead>updated date</TableHead>
                    <TableHead>select</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {batches.map((row, i) => {
                    const bid = readBatchId(row)
                    const compoundKey = pickStr(row, ["compound_id", "compoundId"])
                    const compoundDisplay =
                      compoundKey !== "—" ? compoundLabelById.get(compoundKey) ?? compoundKey : "—"
                    const amt = pickNum(row, ["amount", "total_amount", "totalAmount"])
                    const unit = pickStr(row, ["amount_unit", "amountUnit"])
                    const purity = pickNum(row, ["purity_percent", "purityPercent"])
                    const selected = bid != null && selectedBatchId === bid
                    return (
                      <TableRow key={bid ?? i} data-state={selected ? "selected" : undefined}>
                        <TableCell className="font-mono text-xs">{pickStr(row, ["batch_code", "batchCode", "code"])}</TableCell>
                        <TableCell className="max-w-[200px] text-sm">{compoundDisplay}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{pickStr(row, ["source_type", "sourceType"])}</Badge>
                        </TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {purity != null ? `${purity}%` : "—"}
                          {purity != null ? (
                            <span className="ml-1 text-xs text-muted-foreground">
                              {pickStr(row, ["purity_method", "purityMethod"]) !== "—"
                                ? pickStr(row, ["purity_method", "purityMethod"])
                                : ""}
                            </span>
                          ) : null}
                        </TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {amt != null ? amt.toLocaleString() : "—"} {unit !== "—" ? unit : ""}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{pickStr(row, ["status", "state"])}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[220px] text-xs text-muted-foreground">
                          {linkedSessionReactionDossier(row)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatBatchUpdated(row)}</TableCell>
                        <TableCell>
                          {bid ? (
                            <Button
                              type="button"
                              variant={selected ? "secondary" : "outline"}
                              size="sm"
                              className="h-8"
                              onClick={() => setSelectedBatchId(selected ? null : bid)}
                            >
                              {selected ? "Selected" : "Select"}
                            </Button>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Samples"
        title="Aliquots"
        icon={FlaskConical}
        description={
          selectedBatchId
            ? `GET /compound-registry/batches/${selectedBatchId}/aliquots`
            : "Select a batch in the table above."
        }
      >
        <div className="space-y-4">
          {!selectedBatchId ? (
            <p className="text-sm text-muted-foreground">Choose a batch to list and add aliquots.</p>
          ) : (
            <>
              <form className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" onSubmit={handleCreateAliquot}>
                <div className="space-y-2">
                  <Label htmlFor="br-al-sid">sample ID optional</Label>
                  <Input id="br-al-sid" value={alSampleId} onChange={(e) => setAlSampleId(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="br-al-code">aliquot code</Label>
                  <Input id="br-al-code" value={aliquotCode} onChange={(e) => setAliquotCode(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="br-al-amt">amount</Label>
                  <Input id="br-al-amt" value={alAmount} onChange={(e) => setAlAmount(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="br-al-unit">amount unit</Label>
                  <Input id="br-al-unit" value={alAmountUnit} onChange={(e) => setAlAmountUnit(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="br-al-loc">storage location</Label>
                  <Input id="br-al-loc" value={storageLocation} onChange={(e) => setStorageLocation(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="br-al-st">status</Label>
                  <Input id="br-al-st" value={alStatus} onChange={(e) => setAlStatus(e.target.value)} />
                </div>
                <div className="md:col-span-2 lg:col-span-3">
                  <Button type="submit" disabled={alCreateBusy}>
                    {alCreateBusy ? "Creating…" : "Create aliquot"}
                  </Button>
                </div>
              </form>
              {alCreateErr ? (
                <AlertCard variant="error" title="Aliquot" description={alCreateErr} />
              ) : null}
              {aliquotsLoading ? <p className="text-sm text-muted-foreground">Loading aliquots…</p> : null}
              {aliquotsErr ? <p className="text-xs text-destructive">{aliquotsErr}</p> : null}
              {!aliquotsLoading && aliquots.length === 0 ? (
                <p className="text-sm text-muted-foreground">No aliquots returned for this batch.</p>
              ) : null}
              {aliquots.length > 0 ? (
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>aliquot code</TableHead>
                        <TableHead>sample ID</TableHead>
                        <TableHead>amount</TableHead>
                        <TableHead>storage location</TableHead>
                        <TableHead>status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {aliquots.map((row, idx) => (
                        <TableRow key={idx}>
                          <TableCell className="font-mono text-xs">{pickStr(row, ["aliquot_code", "aliquotCode", "code"])}</TableCell>
                          <TableCell className="text-xs">{pickStr(row, ["sample_id", "sampleId"])}</TableCell>
                          <TableCell className="text-xs tabular-nums">
                            {pickNum(row, ["amount", "quantity"]) ?? "—"}{" "}
                            {pickStr(row, ["amount_unit", "amountUnit"]) !== "—"
                              ? pickStr(row, ["amount_unit", "amountUnit"])
                              : ""}
                          </TableCell>
                          <TableCell className="text-xs">{pickStr(row, ["storage_location", "storageLocation"])}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{pickStr(row, ["status", "state"])}</Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : null}
            </>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Detail"
        title="Dossier scope for batch assessment"
        icon={FileText}
        description={
          <span>
            Enter a regulatory dossier id. If the selected batch row includes regulatory_dossier_id, it is filled
            automatically. The panel below calls POST/GET /regulatory/dossiers/{"{dossier_id}"}/batch-assessment and includes
            batch_id / compound_id from the selected batch when available.
          </span>
        }
      >
        <div className="space-y-4">
          <div className="max-w-sm space-y-2">
            <Label htmlFor="br-badid">dossier_id</Label>
            <Input
              id="br-badid"
              value={batchAssessmentDossierId}
              onChange={(e) => setBatchAssessmentDossierId(e.target.value)}
              placeholder="Regulatory dossier id"
              autoComplete="off"
            />
          </div>
          {validBatchAssessmentDossierId ? (
            <BatchRegulatoryAssessmentPanel
              dossierId={parsedBatchAssessmentDossierId}
              contextBatchId={
                contextBatchIdForAssessment != null && Number.isFinite(contextBatchIdForAssessment)
                  ? contextBatchIdForAssessment
                  : null
              }
              contextCompoundId={contextCompoundIdForAssessment}
              compact
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Enter a valid dossier id (digits). Selecting a batch that stores regulatory_dossier_id fills this field when
              available.
            </p>
          )}
        </div>
      </ModuleCard>

      <p className="text-xs text-muted-foreground">
        <Link href="/compounds" className="underline underline-offset-4">
          Compound Registry
        </Link>
      </p>
    </div>
  )
}
