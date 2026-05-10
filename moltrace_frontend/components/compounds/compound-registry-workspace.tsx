"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { Boxes, Database, Link2, ListFilter, Microscope, Plus, Search } from "lucide-react"
import { trackCompoundCreated } from "@/src/lib/analytics/analytics-client"

const COMPOUND_TYPES = [
  "target",
  "product",
  "starting_material",
  "reagent",
  "impurity",
  "intermediate",
  "metabolite",
  "unknown",
  "reference_standard",
  "other",
] as const

const STRUCTURE_FORMATS = ["smiles", "mol", "sdf", "inchi", "name_only", "unknown"] as const

const STEREO_STATUSES = ["specified", "partial", "unspecified", "ambiguous", "unknown"] as const

const SALT_SOLVENT_STATUSES = ["parent", "salt", "solvate", "mixture", "unknown"] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeCompoundsList(data: unknown): Record<string, unknown>[] {
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

function pickNum(row: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const n = readRecordNumber(row, k)
    if (n != null && Number.isFinite(n)) return n
  }
  return undefined
}

function formatUpdated(row: Record<string, unknown>): string {
  const raw = pickStr(row, ["updated_at", "updatedAt", "modified_at", "modifiedAt"])
  if (raw === "—") return "—"
  const t = Date.parse(raw)
  if (!Number.isNaN(t)) return new Date(t).toLocaleString()
  return raw
}

function rowNeedsReview(row: Record<string, unknown>): boolean {
  const s = pickStr(row, ["status", "review_status", "reviewStatus"]).toLowerCase().replace(/\s+/g, "_")
  if (
    s.includes("needs_review") ||
    s.includes("review_required") ||
    s.includes("pending_review") ||
    s.includes("human_review")
  )
    return true
  const flag = row.requires_review ?? row.needs_review ?? row.needsReview
  if (flag === true) return true
  return false
}

function rowEvidenceLinked(row: Record<string, unknown>): boolean {
  const n =
    pickNum(row, ["evidence_link_count", "evidenceLinkCount", "linked_evidence_count", "linkedEvidenceCount"]) ?? 0
  if (n > 0) return true
  const b = row.evidence_linked ?? row.evidenceLinked
  return b === true || b === 1
}

export function CompoundRegistryWorkspace() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [listErr, setListErr] = useState("")
  const [searchActive, setSearchActive] = useState(false)
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchErr, setSearchErr] = useState("")

  const [preferredName, setPreferredName] = useState("")
  const [compoundType, setCompoundType] = useState<string>(COMPOUND_TYPES[0])
  const [originalStructureInput, setOriginalStructureInput] = useState("")
  const [originalStructureFormat, setOriginalStructureFormat] = useState<string>(STRUCTURE_FORMATS[0])
  const [registryId, setRegistryId] = useState("")
  const [stereochemistryStatus, setStereochemistryStatus] = useState<string>(STEREO_STATUSES[0])
  const [saltSolventStatus, setSaltSolventStatus] = useState<string>(SALT_SOLVENT_STATUSES[0])
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState(false)

  const [sfNameAlias, setSfNameAlias] = useState("")
  const [sfFormula, setSfFormula] = useState("")
  const [sfInchiKey, setSfInchiKey] = useState("")
  const [sfMassMin, setSfMassMin] = useState("")
  const [sfMassMax, setSfMassMax] = useState("")
  const [sfCompoundType, setSfCompoundType] = useState<string>("__any__")

  const loadCompounds = useCallback(async () => {
    setLoading(true)
    setListErr("")
    try {
      const raw = await apiFetch<unknown>("/compound-registry/compounds", { method: "GET" })
      setRows(normalizeCompoundsList(raw))
      setSearchActive(false)
    } catch (e) {
      setRows([])
      setListErr(formatApiError(e, "Could not load compounds."))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadCompounds()
  }, [loadCompounds])

  const summary = useMemo(() => {
    const compounds = rows.length
    let activeBatches = 0
    let batchesKnown = false
    for (const r of rows) {
      const n = pickNum(r, ["active_batch_count", "activeBatchCount", "batch_count", "batchCount"])
      if (n != null) {
        activeBatches += n
        batchesKnown = true
      }
    }
    const evidenceLinked = rows.filter(rowEvidenceLinked).length
    const needingReview = rows.filter(rowNeedsReview).length
    return {
      compounds,
      activeBatches: batchesKnown ? activeBatches : null,
      evidenceLinked,
      needingReview,
    }
  }, [rows])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setCreateErr("")
    setCreateOk(false)
    const pn = preferredName.trim()
    if (!pn) {
      setCreateErr("preferred name is required.")
      return
    }
    setCreateBusy(true)
    try {
      const body: Record<string, unknown> = {
        preferred_name: pn,
        compound_type: compoundType,
        original_structure_input: originalStructureInput.trim(),
        original_structure_format: originalStructureFormat,
        stereochemistry_status: stereochemistryStatus,
        salt_solvent_status: saltSolventStatus,
      }
      const rid = registryId.trim()
      if (rid) body.registry_id = rid
      const hasStructureInput = Boolean(originalStructureInput.trim())
      const created = await apiFetch<Record<string, unknown>>("/compound-registry/compounds", { method: "POST", body })
      const newId = readRecordNumber(created, "id")
      const createdStatus = readRecordString(created, "status")
      const createdType = readRecordString(created, "compound_type") ?? readRecordString(created, "compoundType")
      trackCompoundCreated({
        compound_id: newId != null && Number.isFinite(newId) ? Math.trunc(newId) : undefined,
        compound_type: (createdType?.trim() || compoundType).slice(0, 64),
        has_structure: hasStructureInput,
        status: createdStatus?.trim() || undefined,
      })
      setCreateOk(true)
      setPreferredName("")
      setOriginalStructureInput("")
      setRegistryId("")
      await loadCompounds()
    } catch (err) {
      setCreateErr(formatApiError(err, "Create compound failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setSearchErr("")
    setSearchBusy(true)
    try {
      const body: Record<string, unknown> = {}
      const na = sfNameAlias.trim()
      if (na) body.name_alias = na
      const f = sfFormula.trim()
      if (f) body.formula = f
      const ik = sfInchiKey.trim()
      if (ik) body.inchi_key = ik
      if (sfCompoundType !== "__any__") body.compound_type = sfCompoundType
      const minRaw = sfMassMin.trim()
      const maxRaw = sfMassMax.trim()
      if (minRaw) {
        const n = Number.parseFloat(minRaw)
        if (Number.isFinite(n)) body.exact_mass_min = n
      }
      if (maxRaw) {
        const n = Number.parseFloat(maxRaw)
        if (Number.isFinite(n)) body.exact_mass_max = n
      }
      const raw = await apiFetch<unknown>("/compound-registry/search", { method: "POST", body })
      setRows(normalizeCompoundsList(raw))
      setSearchActive(true)
    } catch (err) {
      setSearchErr(formatApiError(err, "Search failed."))
    } finally {
      setSearchBusy(false)
    }
  }

  function clearSearch() {
    setSfNameAlias("")
    setSfFormula("")
    setSfInchiKey("")
    setSfMassMin("")
    setSfMassMax("")
    setSfCompoundType("__any__")
    void loadCompounds()
  }

  function compoundDetailHref(row: Record<string, unknown>): string | null {
    const sid = readRecordString(row, "id")?.trim()
    if (sid) return `/compounds/${encodeURIComponent(sid)}`
    const n = readRecordNumber(row, "id")
    if (n != null) return `/compounds/${encodeURIComponent(String(n))}`
    return null
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            MolTrace · Compound Registry
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Compound Registry</h1>
          <p className="text-sm text-muted-foreground">
            Track compounds, batches, samples, analytical evidence, reactions, reports, and regulatory dossiers in one
            connected registry.
          </p>
          {listErr && !loading ? <p className="mt-1 text-xs text-destructive">{listErr}</p> : null}
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Compounds</CardTitle>
            <Boxes className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>{summary.compounds}</div>
            <p className="mt-2 text-xs text-muted-foreground">Listed compounds</p>
          </CardContent>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-teal)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Active batches</CardTitle>
            <ListFilter className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-teal)" }}>
              {summary.activeBatches == null ? "—" : summary.activeBatches}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">When per-row batch counts are present</p>
          </CardContent>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-green)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Evidence-linked compounds</CardTitle>
            <Link2 className="h-4 w-4" style={{ color: "var(--mt-green)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-green)" }}>{summary.evidenceLinked}</div>
            <p className="mt-2 text-xs text-muted-foreground">Linked evidence indicators</p>
          </CardContent>
        </Card>
        <Card
          className="overflow-hidden rounded-xl py-0"
          style={{ borderTop: "3px solid var(--mt-amber)" }}
        >
          <CardHeader className="flex flex-row items-center justify-between gap-2 pt-5 pb-2">
            <CardTitle className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">Compounds needing review</CardTitle>
            <Microscope className="h-4 w-4" style={{ color: "var(--mt-amber)" }} aria-hidden />
          </CardHeader>
          <CardContent className="pb-5">
            <div className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-amber)" }}>{summary.needingReview}</div>
            <p className="mt-2 text-xs text-muted-foreground">Status-based when returned</p>
          </CardContent>
        </Card>
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="Form"
        title="Create compound"
        icon={Plus}
        description="Add a compound record to the registry."
      >
        <div>
          <form className="space-y-4" onSubmit={handleCreate}>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="cr-preferred-name">preferred name</Label>
                <Input
                  id="cr-preferred-name"
                  value={preferredName}
                  onChange={(e) => setPreferredName(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cr-compound-type">compound type</Label>
                <Select value={compoundType} onValueChange={setCompoundType}>
                  <SelectTrigger id="cr-compound-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COMPOUND_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="cr-original-input">original structure input</Label>
                <Input
                  id="cr-original-input"
                  value={originalStructureInput}
                  onChange={(e) => setOriginalStructureInput(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cr-original-format">original structure format</Label>
                <Select value={originalStructureFormat} onValueChange={setOriginalStructureFormat}>
                  <SelectTrigger id="cr-original-format">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STRUCTURE_FORMATS.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cr-registry-id">registry ID optional</Label>
                <Input
                  id="cr-registry-id"
                  value={registryId}
                  onChange={(e) => setRegistryId(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cr-stereo">stereochemistry status</Label>
                <Select value={stereochemistryStatus} onValueChange={setStereochemistryStatus}>
                  <SelectTrigger id="cr-stereo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STEREO_STATUSES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cr-salt">salt/solvent status</Label>
                <Select value={saltSolventStatus} onValueChange={setSaltSolventStatus}>
                  <SelectTrigger id="cr-salt">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SALT_SOLVENT_STATUSES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {createErr ? (
              <AlertCard variant="error" title="Could not create" description={createErr} />
            ) : null}
            {createOk ? (
              <p className="text-sm text-muted-foreground">Compound created.</p>
            ) : null}
            <Button type="submit" disabled={createBusy}>
              {createBusy ? "Creating…" : "Create compound"}
            </Button>
          </form>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Catalog"
        title="Search"
        icon={Search}
        description="Filter the registry by identifiers and mass range."
        badge={
          searchActive ? (
            <Button type="button" variant="outline" size="sm" onClick={clearSearch}>
              Clear search
            </Button>
          ) : undefined
        }
      >
        <div className="space-y-4">
          <form className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" onSubmit={handleSearch}>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-name">name/alias</Label>
              <Input id="cr-sf-name" value={sfNameAlias} onChange={(e) => setSfNameAlias(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-formula">formula</Label>
              <Input id="cr-sf-formula" value={sfFormula} onChange={(e) => setSfFormula(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-inchi">InChIKey</Label>
              <Input id="cr-sf-inchi" value={sfInchiKey} onChange={(e) => setSfInchiKey(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-min">exact mass min</Label>
              <Input id="cr-sf-min" value={sfMassMin} onChange={(e) => setSfMassMin(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-max">exact mass max</Label>
              <Input id="cr-sf-max" value={sfMassMax} onChange={(e) => setSfMassMax(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cr-sf-ctype">compound type</Label>
              <Select value={sfCompoundType} onValueChange={setSfCompoundType}>
                <SelectTrigger id="cr-sf-ctype">
                  <SelectValue placeholder="Any" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__any__">Any</SelectItem>
                  {COMPOUND_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
                </Select>
            </div>
            <div className="flex items-end gap-2 md:col-span-2 lg:col-span-3">
              <Button type="submit" disabled={searchBusy}>
                {searchBusy ? "Searching…" : "Search"}
              </Button>
            </div>
          </form>
          {searchErr ? (
            <AlertCard variant="error" title="Search error" description={searchErr} />
          ) : null}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Registry"
        title={searchActive ? "Search results" : "Compounds"}
        icon={Database}
        description="List from the registry, or results after search."
      >
        <div>
          {loading ? <p className="text-sm text-muted-foreground">Loading compounds…</p> : null}
          {!loading && rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No compounds returned.</p>
          ) : null}
          {!loading && rows.length > 0 ? (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>preferred name</TableHead>
                    <TableHead>registry ID</TableHead>
                    <TableHead>compound type</TableHead>
                    <TableHead>formula</TableHead>
                    <TableHead>exact mass</TableHead>
                    <TableHead>stereochemistry status</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>updated date</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row, idx) => {
                    const id = pickStr(row, ["id", "compound_id", "compoundId"])
                    const key = `${id}-${idx}`
                    return (
                      <TableRow key={key}>
                        <TableCell className="max-w-[200px] font-medium">
                          {pickStr(row, ["preferred_name", "preferredName", "name"])}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {pickStr(row, ["registry_id", "registryId", "registry_code", "registryCode"])}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{pickStr(row, ["compound_type", "compoundType"])}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{pickStr(row, ["formula", "molecular_formula", "molecularFormula"])}</TableCell>
                        <TableCell className="tabular-nums text-sm">
                          {(() => {
                            const m = pickNum(row, ["exact_mass", "exactMass", "mono_mass", "monoMass"])
                            return m != null ? m.toLocaleString(undefined, { maximumFractionDigits: 6 }) : "—"
                          })()}
                        </TableCell>
                        <TableCell className="text-xs">
                          {pickStr(row, ["stereochemistry_status", "stereochemistryStatus"])}
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{pickStr(row, ["status", "record_status", "recordStatus"])}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">{formatUpdated(row)}</TableCell>
                        <TableCell>
                          {compoundDetailHref(row) ? (
                            <Button variant="outline" size="sm" className="h-8" asChild>
                              <Link href={compoundDetailHref(row)!}>Open</Link>
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
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

    </div>
  )
}
