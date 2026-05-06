"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackCompoundCreated, trackCompoundLinkedToSpectracheck } from "@/src/lib/analytics/analytics-client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  batchMatchesCompound,
  normalizeBatchList,
  readBatchId,
} from "@/components/batches/batch-registry-utils"
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

const BATCH_TOOLTIP =
  "Batches and aliquots connect physical material to analytical evidence, reaction experiments, and regulatory dossiers."

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

function readDerivedCanonical(row: Record<string, unknown>): string | undefined {
  const keys = [
    "derived_canonical_representation",
    "derivedCanonicalRepresentation",
    "canonical_smiles",
    "canonicalSmiles",
    "canonical_structure",
    "canonicalStructure",
  ]
  for (const k of keys) {
    const v = readRecordString(row, k)
    if (v?.trim()) return v.trim()
  }
  return undefined
}

/** Resolve linked compound display from GET /spectracheck/sessions/{id} payload (flexible keys). */
function extractLinkedCompoundRoot(session: unknown): Record<string, unknown> | null {
  if (!isRecord(session)) return null
  const nested =
    session.linked_compound ??
    session.compound_link ??
    session.compound_registry_link ??
    session.registry_compound
  if (isRecord(nested)) return nested
  if (
    readRecordNumber(session, "compound_id") != null ||
    readRecordNumber(session, "linked_compound_id") != null ||
    readRecordString(session, "linked_compound_name")
  ) {
    return session
  }
  return null
}

function parseCandidateLines(text: string): { name?: string; smiles: string; role?: string }[] {
  const out: { name?: string; smiles: string; role?: string }[] = []
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    const parts = t.split("|").map((p) => p.trim())
    if (parts.length >= 2) out.push({ name: parts[0] || undefined, smiles: parts[1], role: parts[2] })
    else out.push({ smiles: parts[0] })
  }
  return out
}

type Props = {
  backendSessionId: string | null
  sessionRecord: unknown
  candidatesText: string
  onSessionRefresh: () => Promise<void>
}

export function SpectraCheckLinkedCompoundCard({
  backendSessionId,
  sessionRecord,
  candidatesText,
  onSessionRefresh,
}: Props) {
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

  const [candidateLineIdx, setCandidateLineIdx] = useState("0")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createResult, setCreateResult] = useState<Record<string, unknown> | null>(null)
  const [lastCreatedOriginalSmiles, setLastCreatedOriginalSmiles] = useState<string | null>(null)

  const linked = useMemo(() => extractLinkedCompoundRoot(sessionRecord), [sessionRecord])

  const candidateLines = useMemo(() => parseCandidateLines(candidatesText), [candidatesText])

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
    if (!backendSessionId?.trim()) return
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
      await apiFetch(`/spectracheck/sessions/${encodeURIComponent(backendSessionId.trim())}/link-compound`, {
        method: "POST",
        body,
      })
      const batchId =
        selectedBatchId !== "__none__" && Number.isFinite(Number.parseInt(selectedBatchId, 10))
          ? Math.trunc(Number.parseInt(selectedBatchId, 10))
          : undefined
      trackCompoundLinkedToSpectracheck({
        compound_id: compound_id,
        batch_id: batchId,
        has_batch: batchId != null,
        linked_resource_type: "spectracheck_session",
        status: "linked",
      })
      await onSessionRefresh()
    } catch (e) {
      setLinkErr(formatApiError(e, "Link compound failed."))
    } finally {
      setLinkBusy(false)
    }
  }

  async function handleCreateFromCandidate() {
    setCreateErr("")
    setCreateResult(null)
    const idx = Number.parseInt(candidateLineIdx, 10)
    if (!Number.isFinite(idx) || idx < 0 || idx >= candidateLines.length) {
      setCreateErr("Select a valid candidate line.")
      return
    }
    const line = candidateLines[idx]!
    const smiles = line.smiles?.trim() ?? ""
    if (!smiles) {
      setCreateErr("Selected line has no SMILES token.")
      return
    }
    setCreateBusy(true)
    try {
      const preferred_name = (line.name?.trim() || `candidate line ${idx + 1}`).slice(0, 512)
      setLastCreatedOriginalSmiles(smiles)
      const created = await apiFetch<Record<string, unknown>>("/compound-registry/compounds", {
        method: "POST",
        body: {
          preferred_name,
          compound_type: "unknown",
          original_structure_input: smiles,
          original_structure_format: "smiles",
          stereochemistry_status: "unknown",
          salt_solvent_status: "unknown",
          status: "draft",
        },
      })
      const rec = isRecord(created) ? created : { response: created }
      setCreateResult(rec)
      const newId = readRecordNumber(rec, "id")
      const createdStatus = readRecordString(rec, "status")
      const createdType = readRecordString(rec, "compound_type") ?? readRecordString(rec, "compoundType")
      trackCompoundCreated({
        compound_id: newId != null && Number.isFinite(newId) ? Math.trunc(newId) : undefined,
        compound_type: (createdType?.trim() || "unknown").slice(0, 64),
        has_structure: true,
        status: createdStatus?.trim() || undefined,
      })
      const nid = compoundRowId(rec)
      if (nid) {
        setSearchHits((prev) => {
          const rest = prev.filter((r) => compoundRowId(r) !== nid)
          return [rec, ...rest]
        })
        setSelectedCompoundId(nid)
      }
    } catch (e) {
      setCreateErr(formatApiError(e, "Create compound failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  const linkedName = linked ? pickStr(linked, ["preferred_name", "preferredName", "linked_compound_name", "name"]) : "—"
  const linkedRegistry = linked ? pickStr(linked, ["registry_id", "registryId"]) : "—"
  const linkedType = linked ? pickStr(linked, ["compound_type", "compoundType"]) : "—"
  const linkedBatch = linked
    ? pickStr(linked, ["batch_code", "batchCode", "linked_batch_code", "linkedBatchCode", "lot_code", "lotCode"])
    : "—"
  const linkedStatus = linked ? pickStr(linked, ["status", "link_status", "linkStatus", "record_status"]) : "—"
  const linkedCompoundIdHref = linked
    ? readRecordNumber(linked, "compound_id") ??
      readRecordNumber(linked, "compoundId") ??
      readRecordNumber(linked, "id") ??
      (readRecordString(linked, "id")?.trim() ? Number.parseInt(readRecordString(linked, "id")!, 10) : undefined)
    : undefined
  const openHref =
    linkedCompoundIdHref != null && Number.isFinite(linkedCompoundIdHref)
      ? `/compounds/${encodeURIComponent(String(linkedCompoundIdHref))}`
      : linked
        ? (() => {
            const sid = readRecordString(linked, "id")?.trim()
            return sid ? `/compounds/${encodeURIComponent(sid)}` : null
          })()
        : null

  if (!backendSessionId?.trim()) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Linked Compound</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Create or load a SpectraCheck session before linking a compound.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Linked Compound</CardTitle>
          <InfoTooltip content={BATCH_TOOLTIP} label="About batches and links" />
        </div>
        <CardDescription>Link a registry compound and optional batch to this SpectraCheck session.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {linked ? (
          <div className="rounded-md border bg-muted/20 p-3 text-sm">
            <dl className="grid gap-2 sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">linked compound name</dt>
                <dd className="font-medium">{linkedName}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">registry ID</dt>
                <dd className="font-mono text-xs">{linkedRegistry}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">compound type</dt>
                <dd>
                  <Badge variant="outline">{linkedType}</Badge>
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">batch if linked</dt>
                <dd className="font-mono text-xs">{linkedBatch}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-muted-foreground">status</dt>
                <dd>
                  <Badge variant="secondary">{linkedStatus}</Badge>
                </dd>
              </div>
            </dl>
            <div className="mt-3">
              {openHref ? (
                <Button variant="outline" size="sm" asChild>
                  <Link href={openHref}>Open compound</Link>
                </Button>
              ) : (
                <span className="text-xs text-muted-foreground">—</span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No linked compound on this session payload yet.</p>
        )}

        <div className="space-y-3 border-t pt-4">
          <p className="text-xs font-medium text-muted-foreground">Link compound to session</p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="sc-lc-search">compound search/select</Label>
              <Input
                id="sc-lc-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="name/alias"
              />
            </div>
            <Button type="button" variant="secondary" size="sm" disabled={searchBusy} onClick={() => void runCompoundSearch()}>
              {searchBusy ? "Searching…" : "Search"}
            </Button>
          </div>
          {searchErr ? <p className="text-xs text-destructive">{searchErr}</p> : null}
          <div className="space-y-2">
            <Label htmlFor="sc-lc-compound">match</Label>
            <Select value={selectedCompoundId || "__none__"} onValueChange={(v) => setSelectedCompoundId(v === "__none__" ? "" : v)}>
              <SelectTrigger id="sc-lc-compound">
                <SelectValue placeholder="Pick from search results" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {searchHits.map((row) => {
                  const id = compoundRowId(row)
                  if (!id) return null
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
            <div className="flex items-center gap-2">
              <Label htmlFor="sc-lc-batch">batch search/select optional</Label>
              <InfoTooltip content={BATCH_TOOLTIP} label="About batches" />
            </div>
            <Select value={selectedBatchId} onValueChange={setSelectedBatchId} disabled={!selectedCompoundId || batchesLoading}>
              <SelectTrigger id="sc-lc-batch">
                <SelectValue placeholder={batchesLoading ? "Loading batches…" : "Optional batch"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {batchesForCompound.map((row) => {
                  const bid = readBatchId(row)
                  if (!bid) return null
                  const code = pickStr(row, ["batch_code", "batchCode", "code"])
                  return (
                    <SelectItem key={bid} value={bid}>
                      {code !== "—" ? code : `batch ${bid}`}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>
          {linkErr ? (
            <Alert variant="destructive">
              <AlertTitle className="text-sm">Link</AlertTitle>
              <AlertDescription className="text-xs">{linkErr}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="button" disabled={linkBusy} onClick={() => void handleLinkCompound()}>
            {linkBusy ? "Linking…" : "Link compound to session"}
          </Button>
        </div>

        <div className="space-y-3 border-t pt-4">
          <p className="text-xs font-medium text-muted-foreground">Create compound from selected candidate</p>
          {candidateLines.length === 0 ? (
            <p className="text-xs text-muted-foreground">Add candidate lines in Shared session inputs (NMR text + candidates tab).</p>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="sc-lc-cand">candidate line</Label>
                <Select value={candidateLineIdx} onValueChange={setCandidateLineIdx}>
                  <SelectTrigger id="sc-lc-cand">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {candidateLines.map((line, i) => (
                      <SelectItem key={i} value={String(i)}>
                        {(line.name ? `${line.name} | ` : "") + line.smiles + (line.role ? ` | ${line.role}` : "")}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {createErr ? (
                <Alert variant="destructive">
                  <AlertTitle className="text-sm">Create compound</AlertTitle>
                  <AlertDescription className="text-xs">{createErr}</AlertDescription>
                </Alert>
              ) : null}
              {createResult ? (
                <div className="rounded-md border bg-muted/20 p-3 text-xs">
                  <p className="font-medium">Compound created</p>
                  <p className="mt-1 break-all font-mono text-[11px] text-muted-foreground">
                    original_structure_input:{" "}
                    {lastCreatedOriginalSmiles ??
                      pickStr(createResult, ["original_structure_input", "originalStructureInput"])}
                  </p>
                  {readDerivedCanonical(createResult) ? (
                    <p className="mt-2">
                      <span className="font-medium">Derived canonical representation.</span>
                      <span className="mt-1 block break-all font-mono text-[11px]">{readDerivedCanonical(createResult)}</span>
                    </p>
                  ) : null}
                </div>
              ) : null}
              <Button type="button" variant="outline" size="sm" disabled={createBusy} onClick={() => void handleCreateFromCandidate()}>
                {createBusy ? "Creating…" : "Create compound from selected candidate"}
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
