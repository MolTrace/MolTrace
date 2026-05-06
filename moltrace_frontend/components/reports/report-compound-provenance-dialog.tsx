"use client"

import Link from "next/link"
import type { ReactNode } from "react"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import {
  batchMatchesCompound,
  normalizeBatchList,
} from "@/components/batches/batch-registry-utils"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2 } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeCompoundSearchList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["compounds", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

function pickStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = readRecordString(row, k)
    if (v != null && String(v).trim() !== "") return String(v).trim()
  }
  return "—"
}

function compoundRowId(row: Record<string, unknown>): string | null {
  const n = readRecordNumber(row, "id")
  if (n != null) return String(n)
  const s = readRecordString(row, "id")?.trim()
  return s || null
}

function compoundRowLabel(row: Record<string, unknown>): string {
  const name = pickStr(row, ["preferred_name", "preferredName", "name"])
  const id = compoundRowId(row)
  if (id && name !== "—") return `${name} (${id})`
  return name
}

function storageKey(reportId: number) {
  return `moltrace.report.${reportId}.compoundLink`
}

type PersistedLink = { compound_id: number; batch_id?: number | null; sample_id?: string | null }

function readPersisted(reportId: number): PersistedLink | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(storageKey(reportId))
    if (!raw?.trim()) return null
    const o = JSON.parse(raw) as unknown
    if (!isRecord(o)) return null
    const compound_id = readRecordNumber(o, "compound_id")
    if (compound_id == null || !Number.isFinite(compound_id)) return null
    const batch_id = readRecordNumber(o, "batch_id")
    const sample_id = readRecordString(o, "sample_id")
    return {
      compound_id: Math.trunc(compound_id),
      batch_id: batch_id != null && Number.isFinite(batch_id) ? Math.trunc(batch_id) : null,
      sample_id: sample_id?.trim() || null,
    }
  } catch {
    return null
  }
}

function writePersisted(reportId: number, payload: PersistedLink) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(storageKey(reportId), JSON.stringify(payload))
  } catch {
    /* ignore */
  }
}

function collectHashLikeStrings(value: unknown, out: string[], depth: number) {
  if (depth > 6 || out.length > 24) return
  if (typeof value === "string") {
    const t = value.trim()
    if (t.length >= 16 && (/^[a-f0-9]+$/i.test(t) || t.includes("sha"))) out.push(t)
    return
  }
  if (!value || typeof value !== "object") return
  if (Array.isArray(value)) {
    for (const x of value) collectHashLikeStrings(x, out, depth + 1)
    return
  }
  const o = value as Record<string, unknown>
  for (const [k, v] of Object.entries(o)) {
    const kl = k.toLowerCase()
    if (kl.includes("hash") || kl.includes("sha256") || kl === "sha") {
      collectHashLikeStrings(v, out, depth + 1)
    }
  }
}

export type ReportCompoundProvenanceDialogProps = {
  reportId: number
  sessionNumericId: number | null
  reportTitle: string
  hashPreview: string
  children: ReactNode
}

export function ReportCompoundProvenanceDialog({
  reportId,
  sessionNumericId,
  reportTitle,
  hashPreview,
  children,
}: ReportCompoundProvenanceDialogProps) {
  const [open, setOpen] = useState(false)
  const [loadBusy, setLoadBusy] = useState(false)
  const [loadErr, setLoadErr] = useState("")
  const [record, setRecord] = useState<Record<string, unknown> | null>(null)

  const [persisted, setPersisted] = useState<PersistedLink | null>(null)
  const [compoundEntity, setCompoundEntity] = useState<Record<string, unknown> | null>(null)
  const [batchEntity, setBatchEntity] = useState<Record<string, unknown> | null>(null)

  const [searchQuery, setSearchQuery] = useState("")
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchErr, setSearchErr] = useState("")
  const [searchHits, setSearchHits] = useState<Record<string, unknown>[]>([])
  const [selectedCompoundId, setSelectedCompoundId] = useState("")
  const [selectedBatchId, setSelectedBatchId] = useState("__none__")
  const [optionalSampleId, setOptionalSampleId] = useState("")
  const [batchesForCompound, setBatchesForCompound] = useState<Record<string, unknown>[]>([])
  const [batchesLoading, setBatchesLoading] = useState(false)
  const [linkBusy, setLinkBusy] = useState(false)
  const [linkErr, setLinkErr] = useState("")

  useEffect(() => {
    if (!open) return
    setPersisted(readPersisted(reportId))
  }, [open, reportId])

  const loadBatchesForCompound = useCallback(async (compoundId: string) => {
    if (!compoundId.trim()) {
      setBatchesForCompound([])
      return
    }
    setBatchesLoading(true)
    try {
      const raw = await apiFetch<unknown>("/compound-registry/batches", { method: "GET" })
      const all = normalizeBatchList(raw)
      setBatchesForCompound(all.filter((row) => batchMatchesCompound(row, compoundId)))
    } catch {
      setBatchesForCompound([])
    } finally {
      setBatchesLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedCompoundId) void loadBatchesForCompound(selectedCompoundId)
    else {
      setBatchesForCompound([])
      setSelectedBatchId("__none__")
    }
  }, [selectedCompoundId, loadBatchesForCompound])

  useEffect(() => {
    if (!open || !persisted?.compound_id) {
      if (open && !persisted?.compound_id) {
        setCompoundEntity(null)
        setBatchEntity(null)
      }
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const c = await apiFetch<Record<string, unknown>>(
          `/compound-registry/compounds/${encodeURIComponent(String(persisted.compound_id))}`,
          { method: "GET" },
        )
        if (!cancelled) setCompoundEntity(isRecord(c) ? c : null)
      } catch {
        if (!cancelled) setCompoundEntity(null)
      }
      if (persisted.batch_id != null && Number.isFinite(persisted.batch_id)) {
        try {
          const b = await apiFetch<Record<string, unknown>>(
            `/compound-registry/batches/${encodeURIComponent(String(persisted.batch_id))}`,
            { method: "GET" },
          )
          if (!cancelled) setBatchEntity(isRecord(b) ? b : null)
        } catch {
          if (!cancelled) setBatchEntity(null)
        }
      } else if (!cancelled) setBatchEntity(null)
    })()
    return () => {
      cancelled = true
    }
  }, [open, persisted])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoadErr("")
    setLoadBusy(true)
    setRecord(null)
    ;(async () => {
      try {
        const raw = await apiFetch<Record<string, unknown>>(
          `/reports/${encodeURIComponent(String(reportId))}`,
          { method: "GET" },
        )
        if (!cancelled) setRecord(isRecord(raw) ? raw : null)
      } catch (e) {
        if (!cancelled) setLoadErr(formatApiError(e, "Could not load report record."))
      } finally {
        if (!cancelled) setLoadBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, reportId])

  const innerReport = record && isRecord(record.report) ? (record.report as Record<string, unknown>) : null
  const analysis = innerReport && isRecord(innerReport.analysis) ? (innerReport.analysis as Record<string, unknown>) : null
  const structure = innerReport && isRecord(innerReport.structure) ? (innerReport.structure as Record<string, unknown>) : null

  const reportSampleLabel =
    (analysis && pickStr(analysis, ["sample_id", "sampleId"])) ||
    pickStr(record ?? {}, ["sample_id", "sampleId"]) ||
    "—"

  const structureLines: string[] = []
  if (structure) {
    const smiles = pickStr(structure, ["smiles", "Smiles"])
    const formula = pickStr(structure, ["formula", "Formula"])
    if (smiles !== "—") structureLines.push(`smiles: ${smiles}`)
    if (formula !== "—") structureLines.push(`formula: ${formula}`)
    const mw = readRecordNumber(structure, "molecular_weight")
    if (mw != null) structureLines.push(`molecular_weight: ${mw}`)
  }

  const nmr2d = innerReport && Array.isArray(innerReport.nmr2d_evidence) ? innerReport.nmr2d_evidence.filter(isRecord) : []

  const hashStrings: string[] = []
  collectHashLikeStrings(record, hashStrings, 0)
  const uniqueHashes = [...new Set(hashStrings)].slice(0, 12)

  async function runCompoundSearch() {
    setSearchErr("")
    setSearchBusy(true)
    setSearchHits([])
    try {
      const body: Record<string, unknown> = {}
      const q = searchQuery.trim()
      if (q) body.name_alias = q
      const raw = await apiFetch<unknown>("/compound-registry/search", { method: "POST", body })
      setSearchHits(normalizeCompoundSearchList(raw))
    } catch (e) {
      setSearchErr(formatApiError(e, "Compound search failed."))
    } finally {
      setSearchBusy(false)
    }
  }

  async function handleLinkCompound() {
    const cid = selectedCompoundId.trim()
    if (!cid) {
      setLinkErr("Select a compound from search results.")
      return
    }
    const compound_id = Number.parseInt(cid, 10)
    if (!Number.isFinite(compound_id)) {
      setLinkErr("compound_id must be a positive integer for this link action.")
      return
    }
    setLinkBusy(true)
    setLinkErr("")
    try {
      const body: Record<string, unknown> = { compound_id }
      if (selectedBatchId !== "__none__") {
        const bid = Number.parseInt(selectedBatchId, 10)
        if (Number.isFinite(bid)) body.batch_id = bid
      }
      const sid = optionalSampleId.trim()
      if (sid) body.sample_id = sid
      const res = await apiFetch<Record<string, unknown>>(`/reports/${encodeURIComponent(String(reportId))}/link-compound`, {
        method: "POST",
        body,
      })
      const ev = isRecord(res.evidence_link) ? res.evidence_link : null
      const cid = readRecordNumber(ev, "compound_id")
      const bid = readRecordNumber(ev, "batch_id")
      const next: PersistedLink = {
        compound_id: cid != null && Number.isFinite(cid) ? Math.trunc(cid) : Math.trunc(compound_id),
        batch_id: bid != null && Number.isFinite(bid) ? Math.trunc(bid) : null,
        sample_id: readRecordString(ev, "sample_id")?.trim() || sid || null,
      }
      writePersisted(reportId, next)
      setPersisted(next)
    } catch (e) {
      setLinkErr(formatApiError(e, "Link compound failed."))
    } finally {
      setLinkBusy(false)
    }
  }

  const linkedName = compoundEntity
    ? pickStr(compoundEntity, ["preferred_name", "preferredName", "name"])
    : persisted
      ? `compound_id ${persisted.compound_id}`
      : "—"
  const linkedRegistry = compoundEntity ? pickStr(compoundEntity, ["registry_id", "registryId"]) : "—"
  const linkedBatch =
    batchEntity != null
      ? pickStr(batchEntity, ["batch_code", "batchCode", "lot_code", "lotCode"])
      : persisted?.batch_id != null
        ? `batch_id ${persisted.batch_id}`
        : "—"
  const linkedSample = persisted?.sample_id?.trim() || reportSampleLabel

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Compound provenance</DialogTitle>
          <DialogDescription>
            GET /reports/{"{report_id}"} — POST /reports/{"{report_id}"}/link-compound. Provenance and navigation only;
            does not assert report release approval.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">{reportTitle}</p>
          <p>
            report_id: <span className="font-mono">{reportId}</span>
            {sessionNumericId != null ? (
              <>
                {" "}
                · spectracheck_session_id:{" "}
                <Link className="underline-offset-4 hover:underline" href="/spectracheck">
                  {sessionNumericId}
                </Link>
              </>
            ) : null}
          </p>
          <p>
            list hash preview: <span className="font-mono">{hashPreview}</span>
          </p>
        </div>

        <Alert>
          <AlertTitle className="text-sm">Provenance only</AlertTitle>
          <AlertDescription className="text-xs leading-relaxed">
            Fields below are copied from API payloads for traceability. They are not independent regulatory claims.
          </AlertDescription>
        </Alert>

        {loadBusy ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading report…
          </div>
        ) : null}
        {loadErr ? <p className="text-xs text-destructive">{loadErr}</p> : null}

        <section className="space-y-2 rounded-md border p-3 text-sm">
          <h3 className="text-sm font-semibold">Linked compound (registry)</h3>
          <dl className="grid gap-2 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">linked compound</dt>
              <dd className="font-medium">{linkedName}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">registry ID</dt>
              <dd className="font-mono">{linkedRegistry}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">linked batch</dt>
              <dd className="font-mono">{linkedBatch}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">sample / aliquot id</dt>
              <dd className="font-mono">{linkedSample}</dd>
            </div>
          </dl>
          {persisted?.compound_id != null ? (
            <Button variant="outline" size="sm" className="mt-2" asChild>
              <Link href={`/compounds/${encodeURIComponent(String(persisted.compound_id))}`}>Open compound detail</Link>
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              No link stored in this browser session yet. Linking below records compound_id (and optional batch_id,
              sample_id) after POST; GET /reports/{"{report_id}"} does not echo registry link fields here.
            </p>
          )}
        </section>

        <section className="space-y-2 rounded-md border p-3 text-sm">
          <h3 className="text-sm font-semibold">Structure provenance (from report JSON)</h3>
          {structureLines.length === 0 ? (
            <p className="text-xs text-muted-foreground">No structure block parsed from payload.</p>
          ) : (
            <ul className="space-y-1 font-mono text-xs">
              {structureLines.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="space-y-2 rounded-md border p-3 text-sm">
          <h3 className="text-sm font-semibold">Evidence links (from report JSON)</h3>
          {nmr2d.length === 0 ? (
            <p className="text-xs text-muted-foreground">No nmr2d_evidence entries in payload.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {nmr2d.map((row, i) => {
                const url = readRecordString(row, "report_url") ?? readRecordString(row, "reportUrl")
                const et = readRecordString(row, "experiment_type") ?? readRecordString(row, "experimentType")
                return (
                  <li key={i} className="rounded bg-muted/30 p-2">
                    <div className="font-mono">{et ?? "—"}</div>
                    {url ? (
                      <Button variant="link" className="h-auto p-0 text-xs" asChild>
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          {url}
                        </a>
                      </Button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="space-y-2 rounded-md border p-3 text-sm">
          <h3 className="text-sm font-semibold">Source hashes (payload scan)</h3>
          {uniqueHashes.length === 0 ? (
            <p className="text-xs text-muted-foreground">No hash-like strings collected from this GET payload.</p>
          ) : (
            <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-[11px] break-all">
              {uniqueHashes.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="space-y-3 border-t pt-4">
          <h3 className="text-sm font-semibold">Link compound to report</h3>
          <p className="text-xs text-muted-foreground">POST /reports/{"{report_id}"}/link-compound</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="rp-search">compound search</Label>
              <Input
                id="rp-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="name / alias"
                autoComplete="off"
              />
            </div>
            <Button type="button" variant="secondary" size="sm" disabled={searchBusy} onClick={() => void runCompoundSearch()}>
              {searchBusy ? "Searching…" : "Search"}
            </Button>
          </div>
          {searchErr ? <p className="text-xs text-destructive">{searchErr}</p> : null}
          <div className="space-y-2">
            <Label>match</Label>
            <Select
              value={selectedCompoundId || "__none__"}
              onValueChange={(v) => setSelectedCompoundId(v === "__none__" ? "" : v)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Pick from search results" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {searchHits
                  .filter((row) => compoundRowId(row) != null)
                  .map((row) => {
                    const id = compoundRowId(row)!
                    return (
                      <SelectItem key={id} value={id}>
                        {compoundRowLabel(row)}
                      </SelectItem>
                    )
                  })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>optional batch</Label>
            <Select value={selectedBatchId} onValueChange={setSelectedBatchId} disabled={!selectedCompoundId}>
              <SelectTrigger>
                <SelectValue placeholder={batchesLoading ? "Loading batches…" : "No batch"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">No batch</SelectItem>
                {batchesForCompound.map((b) => {
                  const bid = readRecordNumber(b, "id")
                  if (bid == null) return null
                  const code = pickStr(b, ["batch_code", "batchCode", "lot_code", "lotCode"])
                  return (
                    <SelectItem key={bid} value={String(bid)}>
                      {bid} {code !== "—" ? `· ${code}` : ""}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="rp-sample">optional sample_id (POST body)</Label>
            <Input
              id="rp-sample"
              value={optionalSampleId}
              onChange={(e) => setOptionalSampleId(e.target.value)}
              placeholder="registry sample_id string"
              autoComplete="off"
            />
          </div>
          {linkErr ? <p className="text-xs text-destructive">{linkErr}</p> : null}
          <Button type="button" size="sm" disabled={linkBusy} onClick={() => void handleLinkCompound()}>
            {linkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Link compound to report
          </Button>
        </section>
      </DialogContent>
    </Dialog>
  )
}
