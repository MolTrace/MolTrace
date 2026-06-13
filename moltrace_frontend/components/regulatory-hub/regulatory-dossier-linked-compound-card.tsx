"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import {
  batchMatchesCompound,
  normalizeBatchList,
} from "@/components/batches/batch-registry-utils"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { trackCompoundLinkedToRegulatoryDossier } from "@/src/lib/analytics/analytics-client"

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

function storageKey(dossierId: number) {
  return `moltrace.regDossier.${dossierId}.compoundLink`
}

export type RegulatoryDossierCompoundLink = { compound_id: number; batch_id?: number | null }

export function readRegulatoryDossierCompoundLink(dossierId: number): RegulatoryDossierCompoundLink | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(storageKey(dossierId))
    if (!raw?.trim()) return null
    const o = JSON.parse(raw) as unknown
    if (!isRecord(o)) return null
    const compound_id = readRecordNumber(o, "compound_id")
    if (compound_id == null || !Number.isFinite(compound_id)) return null
    const batch_id = readRecordNumber(o, "batch_id")
    return {
      compound_id: Math.trunc(compound_id),
      batch_id: batch_id != null && Number.isFinite(batch_id) ? Math.trunc(batch_id) : null,
    }
  } catch {
    return null
  }
}

function writePersisted(dossierId: number, payload: RegulatoryDossierCompoundLink) {
  if (typeof window === "undefined") return
  try {
    window.sessionStorage.setItem(storageKey(dossierId), JSON.stringify(payload))
  } catch {
    /* ignore quota */
  }
}

function openEvidenceHref(evidenceType: string | undefined, resourceId: number | undefined): string | null {
  if (!evidenceType) return null
  if (evidenceType === "spectracheck_report" || evidenceType === "unified_evidence" || evidenceType === "qc_assessment") {
    return "/spectracheck"
  }
  if (evidenceType === "analytical_artifact") {
    return "/reports"
  }
  if (
    (evidenceType === "reaction_experiment" || evidenceType === "reaction_report") &&
    resourceId != null &&
    Number.isFinite(resourceId)
  ) {
    return `/reactions/${encodeURIComponent(String(resourceId))}`
  }
  return null
}

const ANALYTICAL_EVIDENCE_TYPES = new Set([
  "unified_evidence",
  "qc_assessment",
  "raw_file_hash",
  "analytical_artifact",
  "reaction_experiment",
])

const REPORT_OR_SESSION_TYPES = new Set(["spectracheck_report", "reaction_report"])

function truncateSummary(s: string, max: number): string {
  const t = s.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

export type RegulatoryDossierLinkedCompoundCardProps = {
  dossierId: number
  evidenceLinks: Record<string, unknown>[]
  onRegistryLinked: () => void | Promise<void>
}

export function RegulatoryDossierLinkedCompoundCard({
  dossierId,
  evidenceLinks,
  onRegistryLinked,
}: RegulatoryDossierLinkedCompoundCardProps) {
  const [searchQuery, setSearchQuery] = useState("")
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchErr, setSearchErr] = useState("")
  const [searchHits, setSearchHits] = useState<Record<string, unknown>[]>([])
  const [selectedCompoundId, setSelectedCompoundId] = useState("")
  const [selectedBatchId, setSelectedBatchId] = useState("__none__")
  const [batchesForCompound, setBatchesForCompound] = useState<Record<string, unknown>[]>([])
  const [batchesLoading, setBatchesLoading] = useState(false)
  const [linkBusy, setLinkBusy] = useState(false)
  const [linkErr, setLinkErr] = useState("")

  const [persisted, setPersisted] = useState<RegulatoryDossierCompoundLink | null>(null)
  const [compoundEntity, setCompoundEntity] = useState<Record<string, unknown> | null>(null)
  const [batchEntity, setBatchEntity] = useState<Record<string, unknown> | null>(null)
  const [hydrateErr, setHydrateErr] = useState("")

  useEffect(() => {
    setPersisted(readRegulatoryDossierCompoundLink(dossierId))
  }, [dossierId])

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
    if (!persisted?.compound_id) {
      setCompoundEntity(null)
      setBatchEntity(null)
      return
    }
    let cancelled = false
    setHydrateErr("")
    ;(async () => {
      try {
        const c = await apiFetch<Record<string, unknown>>(
          `/compound-registry/compounds/${encodeURIComponent(String(persisted.compound_id))}`,
          { method: "GET" },
        )
        if (!cancelled) setCompoundEntity(isRecord(c) ? c : null)
      } catch (e) {
        if (!cancelled) {
          setCompoundEntity(null)
          setHydrateErr(formatApiError(e, "Could not load linked compound from registry."))
        }
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
  }, [persisted])

  const analyticalRows = useMemo(() => {
    return evidenceLinks.filter((row) => {
      const t = readRecordString(row, "evidence_type") ?? ""
      return ANALYTICAL_EVIDENCE_TYPES.has(t)
    })
  }, [evidenceLinks])

  const reportRows = useMemo(() => {
    return evidenceLinks.filter((row) => {
      const t = readRecordString(row, "evidence_type") ?? ""
      return REPORT_OR_SESSION_TYPES.has(t)
    })
  }, [evidenceLinks])

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
      const res = await apiFetch<Record<string, unknown>>(
        `/regulatory/dossiers/${encodeURIComponent(String(dossierId))}/link-compound`,
        { method: "POST", body },
      )
      const ev = isRecord(res.evidence_link) ? res.evidence_link : null
      const evCompoundId = ev ? readRecordNumber(ev, "compound_id") : null
      const evBatchId = ev ? readRecordNumber(ev, "batch_id") : null
      const next: RegulatoryDossierCompoundLink = {
        compound_id:
          evCompoundId != null && Number.isFinite(evCompoundId) ? Math.trunc(evCompoundId) : Math.trunc(compound_id),
        batch_id: evBatchId != null && Number.isFinite(evBatchId) ? Math.trunc(evBatchId) : null,
      }
      trackCompoundLinkedToRegulatoryDossier({
        compound_id: next.compound_id,
        batch_id: next.batch_id ?? undefined,
        has_batch: next.batch_id != null,
        linked_resource_type: "regulatory_dossier",
        status: ev ? readRecordString(ev, "status") ?? undefined : undefined,
      })
      writePersisted(dossierId, next)
      setPersisted(next)
      await onRegistryLinked()
    } catch (e) {
      setLinkErr(formatApiError(e, "Link compound failed."))
    } finally {
      setLinkBusy(false)
    }
  }

  const displayName = compoundEntity
    ? pickStr(compoundEntity, ["preferred_name", "preferredName", "name"])
    : persisted
      ? `compound_id ${persisted.compound_id}`
      : "—"
  const registryId = compoundEntity
    ? pickStr(compoundEntity, ["registry_id", "registryId"])
    : "—"
  const batchLabel =
    batchEntity != null
      ? pickStr(batchEntity, ["batch_code", "batchCode", "lot_code", "lotCode", "label"])
      : persisted?.batch_id != null
        ? `batch_id ${persisted.batch_id}`
        : "—"

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Linked Compound</CardTitle>
        <CardDescription>
          Registry provenance link — identifies which compound is associated with this dossier for traceability. Does not indicate dossier approval or regulatory sign-off.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <AlertTitle className="text-sm">Provenance note</AlertTitle>
          <AlertDescription className="text-xs leading-relaxed">
            This card records which compound registry row is associated with this dossier for traceability. It does not
            substitute cited sources, requirements, or human review outcomes shown elsewhere in ComplianceCore.
          </AlertDescription>
        </Alert>

        {hydrateErr ? (
          <p className="text-xs text-destructive">{hydrateErr}</p>
        ) : null}

        <div className="rounded-md border bg-muted/20 p-3 text-sm">
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Linked registry row</h3>
          <dl className="mt-2 grid gap-2 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">compound name</dt>
              <dd className="font-medium">{displayName}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">registry ID</dt>
              <dd className="font-mono text-xs">{registryId}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs text-muted-foreground">batch / lot (if linked)</dt>
              <dd className="font-mono text-xs">{batchLabel}</dd>
            </div>
          </dl>
          {persisted?.compound_id != null ? (
            <div className="mt-3">
              <Button variant="outline" size="sm" asChild>
                <Link href={`/compounds/${encodeURIComponent(String(persisted.compound_id))}`}>Open compound detail</Link>
              </Button>
            </div>
          ) : (
            <p className="mt-2 text-xs text-muted-foreground">
              No compound link stored in this browser session yet. Use search below, then link — the summary is retained
              here for convenience after a successful POST (GET dossier payload does not echo registry fields).
            </p>
          )}
        </div>

        <div className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Analytical evidence links (dossier index)</h3>
          <p className="text-xs text-muted-foreground">
            Analytical evidence links indexed against this dossier — evidence type, source, and summary. Open the Evidence Links tab for full detail.
          </p>
          {analyticalRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">No matching evidence rows.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {analyticalRows.map((row) => {
                const id = readRecordNumber(row, "id")
                const title = readRecordString(row, "title") ?? "—"
                const summary = readRecordString(row, "summary") ?? ""
                const et = readRecordString(row, "evidence_type")
                const rid = readRecordNumber(row, "resource_id")
                const href = openEvidenceHref(et ?? undefined, rid ?? undefined)
                return (
                  <li key={id ?? `${title}-${et}`} className="rounded border bg-background/60 p-2">
                    <div className="font-medium">{title}</div>
                    <div className="mt-0.5 text-muted-foreground">
                      <span className="font-mono">{et ?? "—"}</span>
                      {rid != null ? <span className="ml-2">resource_id {rid}</span> : null}
                    </div>
                    {summary ? (
                      <p className="mt-1 text-muted-foreground">{truncateSummary(summary, 220)}</p>
                    ) : null}
                    {href ? (
                      <Button variant="link" className="h-auto p-0 text-xs" asChild>
                        <Link href={href}>Open related workspace</Link>
                      </Button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Report links (dossier index)</h3>
          <p className="text-xs text-muted-foreground">
            Evidence rows whose evidence_type maps to SpectraCheck or reaction report navigation (summary only).
          </p>
          {reportRows.length === 0 ? (
            <p className="text-xs text-muted-foreground">No matching evidence rows.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {reportRows.map((row) => {
                const id = readRecordNumber(row, "id")
                const title = readRecordString(row, "title") ?? "—"
                const summary = readRecordString(row, "summary") ?? ""
                const et = readRecordString(row, "evidence_type")
                const rid = readRecordNumber(row, "resource_id")
                const href = openEvidenceHref(et ?? undefined, rid ?? undefined)
                return (
                  <li key={id ?? `${title}-${et}`} className="rounded border bg-background/60 p-2">
                    <div className="font-medium">{title}</div>
                    <div className="mt-0.5 text-muted-foreground">
                      <span className="font-mono">{et ?? "—"}</span>
                      {rid != null ? <span className="ml-2">resource_id {rid}</span> : null}
                    </div>
                    {summary ? (
                      <p className="mt-1 text-muted-foreground">{truncateSummary(summary, 220)}</p>
                    ) : null}
                    {href ? (
                      <Button variant="link" className="h-auto p-0 text-xs" asChild>
                        <Link href={href}>Open related workspace</Link>
                      </Button>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="space-y-3 border-t pt-4">
          <p className="text-xs font-medium text-muted-foreground">Link compound to dossier</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="rd-lc-search">compound search</Label>
              <Input
                id="rd-lc-search"
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
            <Label htmlFor="rd-lc-compound">match</Label>
            <Select
              value={selectedCompoundId || "__none__"}
              onValueChange={(v) => setSelectedCompoundId(v === "__none__" ? "" : v)}
            >
              <SelectTrigger id="rd-lc-compound">
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
          {linkErr ? <p className="text-xs text-destructive">{linkErr}</p> : null}
          <Button type="button" size="sm" disabled={linkBusy} onClick={() => void handleLinkCompound()}>
            {linkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Link compound to dossier
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
