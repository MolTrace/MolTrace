"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { readRecordString } from "@/components/projects/project-workspace-utils"
import { trackAliquotCreated, trackBatchCreated } from "@/src/lib/analytics/analytics-client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
  batchMatchesCompound,
  formatBatchUpdated,
  linkedSessionReactionDossier,
  normalizeAliquotList,
  normalizeBatchList,
  pickNum,
  pickStr,
  readBatchId,
} from "@/components/batches/batch-registry-utils"

const SOURCE_TYPES = [
  "synthesized",
  "purchased",
  "isolated",
  "reference_standard",
  "imported",
  "unknown",
] as const

type Props = {
  compoundId: string
}

export function CompoundBatchesAliquotsPanel({ compoundId }: Props) {
  const [allBatches, setAllBatches] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")

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

  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null)
  const [aliquots, setAliquots] = useState<Record<string, unknown>[]>([])
  const [aliquotsLoading, setAliquotsLoading] = useState(false)
  const [aliquotsErr, setAliquotsErr] = useState("")

  const [alSampleId, setAlSampleId] = useState("")
  const [aliquotCode, setAliquotCode] = useState("")
  const [alAmount, setAlAmount] = useState("")
  const [alAmountUnit, setAlAmountUnit] = useState("")
  const [storageLocation, setStorageLocation] = useState("")
  const [alStatus, setAlStatus] = useState("available")
  const [alCreateBusy, setAlCreateBusy] = useState(false)
  const [alCreateErr, setAlCreateErr] = useState("")

  const loadBatches = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const raw = await apiFetch<unknown>("/compound-registry/batches", { method: "GET" })
      setAllBatches(normalizeBatchList(raw))
    } catch (e) {
      setAllBatches([])
      setErr(formatApiError(e, "Could not load batches."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBatches()
  }, [loadBatches])

  const filtered = useMemo(
    () => allBatches.filter((row) => batchMatchesCompound(row, compoundId)),
    [allBatches, compoundId],
  )

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

  async function handleCreateBatch(e: React.FormEvent) {
    e.preventDefault()
    setCreateErr("")
    const bc = batchCode.trim()
    if (!bc) {
      setCreateErr("batch_code is required.")
      return
    }
    const compound_id = Number.parseInt(compoundId, 10)
    if (!Number.isFinite(compound_id)) {
      setCreateErr("compound id in URL is not a valid integer for batch creation.")
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
      }
      if (alStatus.trim()) body.status = alStatus.trim()
      if (alAmount.trim()) {
        const a = Number.parseFloat(alAmount)
        if (Number.isFinite(a)) body.amount = a
      }
      if (alAmountUnit.trim()) body.amount_unit = alAmountUnit.trim()
      if (storageLocation.trim()) body.storage_location = storageLocation.trim()
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
      const cid = Number.parseInt(compoundId, 10)
      trackAliquotCreated({
        compound_id: Number.isFinite(cid) ? Math.trunc(cid) : undefined,
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold">Batches & Aliquots</h3>
          <InfoTooltip content={BATCH_ALIQUOT_TOOLTIP} label="About batches and aliquots" />
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/batches">Open batch registry</Link>
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Batches for compound <span className="font-mono text-xs">{compoundId}</span> from GET /compound-registry/batches
        (filtered client-side).
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Create batch for this compound</CardTitle>
          <CardDescription>compound_id is taken from this page. POST /compound-registry/batches</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleCreateBatch}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label>compound_id</Label>
                <Input value={compoundId} disabled readOnly className="font-mono text-xs" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-bc">batch code</Label>
                <Input id="cba-bc" value={batchCode} onChange={(e) => setBatchCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-lc">lot code optional</Label>
                <Input id="cba-lc" value={lotCode} onChange={(e) => setLotCode(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-st">source type</Label>
                <Select value={sourceType} onValueChange={setSourceType}>
                  <SelectTrigger id="cba-st">
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
                <Label htmlFor="cba-rxn">reaction experiment ID optional</Label>
                <Input id="cba-rxn" value={reactionExperimentId} onChange={(e) => setReactionExperimentId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-sc">SpectraCheck session ID optional</Label>
                <Input id="cba-sc" value={spectracheckSessionId} onChange={(e) => setSpectracheckSessionId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-dos">regulatory dossier ID optional</Label>
                <Input id="cba-dos" value={regulatoryDossierId} onChange={(e) => setRegulatoryDossierId(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-amt">amount</Label>
                <Input id="cba-amt" value={amount} onChange={(e) => setAmount(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-amtu">amount unit</Label>
                <Input id="cba-amtu" value={amountUnit} onChange={(e) => setAmountUnit(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-pu">purity percent</Label>
                <Input id="cba-pu" value={purityPercent} onChange={(e) => setPurityPercent(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-pm">purity method</Label>
                <Input id="cba-pm" value={purityMethod} onChange={(e) => setPurityMethod(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cba-sta">status</Label>
                <Input id="cba-sta" value={status} onChange={(e) => setStatus(e.target.value)} />
              </div>
            </div>
            {createErr ? (
              <Alert variant="destructive" className="mt-2">
                <AlertTitle className="text-sm">Create batch</AlertTitle>
                <AlertDescription className="text-xs">{createErr}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="submit" className="mt-2" disabled={createBusy}>
              {createBusy ? "Creating…" : "Create batch"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Batches for this compound</CardTitle>
          <Button type="button" variant="ghost" size="sm" className="h-8" onClick={() => void loadBatches()}>
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-sm text-muted-foreground">Loading batches…</p> : null}
          {err ? <p className="text-xs text-destructive">{err}</p> : null}
          {!loading && filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">No batches for this compound in the registry list.</p>
          ) : null}
          {filtered.length > 0 ? (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>batch code</TableHead>
                    <TableHead>source type</TableHead>
                    <TableHead>purity</TableHead>
                    <TableHead>amount</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>linked</TableHead>
                    <TableHead>updated</TableHead>
                    <TableHead>select</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((row, i) => {
                    const bid = readBatchId(row)
                    const amt = pickNum(row, ["amount", "total_amount", "totalAmount"])
                    const unit = pickStr(row, ["amount_unit", "amountUnit"])
                    const purity = pickNum(row, ["purity_percent", "purityPercent"])
                    const selected = bid != null && selectedBatchId === bid
                    return (
                      <TableRow key={bid ?? i}>
                        <TableCell className="font-mono text-xs">{pickStr(row, ["batch_code", "batchCode", "code"])}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{pickStr(row, ["source_type", "sourceType"])}</Badge>
                        </TableCell>
                        <TableCell className="text-xs tabular-nums">
                          {purity != null ? `${purity}%` : "—"}
                        </TableCell>
                        <TableCell className="text-xs tabular-nums">
                          {amt != null ? amt.toLocaleString() : "—"} {unit !== "—" ? unit : ""}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{pickStr(row, ["status", "state"])}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[180px] text-[11px] text-muted-foreground">
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Aliquots</CardTitle>
          <CardDescription>
            {selectedBatchId
              ? `GET /compound-registry/batches/${selectedBatchId}/aliquots — POST /compound-registry/batches/${selectedBatchId}/aliquots`
              : "Select a batch above to list or add aliquots."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!selectedBatchId ? null : (
            <>
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={handleCreateAliquot}>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-sid">sample ID optional</Label>
                  <Input id="cba-al-sid" value={alSampleId} onChange={(e) => setAlSampleId(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-code">aliquot code</Label>
                  <Input id="cba-al-code" value={aliquotCode} onChange={(e) => setAliquotCode(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-amt">amount</Label>
                  <Input id="cba-al-amt" value={alAmount} onChange={(e) => setAlAmount(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-unit">amount unit</Label>
                  <Input id="cba-al-unit" value={alAmountUnit} onChange={(e) => setAlAmountUnit(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-loc">storage location</Label>
                  <Input id="cba-al-loc" value={storageLocation} onChange={(e) => setStorageLocation(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cba-al-st">status</Label>
                  <Input id="cba-al-st" value={alStatus} onChange={(e) => setAlStatus(e.target.value)} />
                </div>
                <div className="sm:col-span-2">
                  <Button type="submit" disabled={alCreateBusy}>
                    {alCreateBusy ? "Creating…" : "Create aliquot"}
                  </Button>
                </div>
              </form>
              {alCreateErr ? (
                <Alert variant="destructive">
                  <AlertTitle className="text-sm">Aliquot</AlertTitle>
                  <AlertDescription className="text-xs">{alCreateErr}</AlertDescription>
                </Alert>
              ) : null}
              {aliquotsLoading ? <p className="text-sm text-muted-foreground">Loading aliquots…</p> : null}
              {aliquotsErr ? <p className="text-xs text-destructive">{aliquotsErr}</p> : null}
              {!aliquotsLoading && aliquots.length === 0 ? (
                <p className="text-sm text-muted-foreground">No aliquots for this batch.</p>
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
        </CardContent>
      </Card>
    </div>
  )
}
