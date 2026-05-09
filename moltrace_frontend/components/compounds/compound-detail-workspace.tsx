"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { CompoundBatchesAliquotsPanel } from "@/components/batches/compound-batches-aliquots-panel"
import { CompoundScientificKnowledgeGraphPanel } from "@/components/compounds/compound-scientific-knowledge-graph-panel"
import { CompoundDetailKnowledgeLinksCard } from "@/components/knowledge/knowledge-links-integration"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const STRUCTURE_TOOLTIP =
  "Original structures are preserved exactly as entered. Canonical structures are derived metadata and do not replace the original."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeArray(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["items", "results", "data", "rows", "structures", "aliases", "relationships", "evidence_links", "links"]) {
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

function readOriginalStructureInput(row: Record<string, unknown>): string {
  const v = pickStr(row, ["original_structure_input", "originalStructureInput"])
  return v === "—" ? "" : v
}

function readDerivedCanonical(row: Record<string, unknown>): string | undefined {
  const keys = [
    "derived_canonical_representation",
    "derivedCanonicalRepresentation",
    "canonical_smiles",
    "canonicalSmiles",
    "canonical_structure",
    "canonicalStructure",
    "canonical_inchi",
    "canonicalInchi",
  ]
  for (const k of keys) {
    const v = readRecordString(row, k)
    if (v != null && v.trim() !== "") return v.trim()
  }
  return undefined
}

function formatWarnings(row: Record<string, unknown>): string {
  const w = row.normalization_warnings ?? row.normalizationWarnings
  if (Array.isArray(w)) return w.map((x) => String(x)).join("; ") || "—"
  if (typeof w === "string" && w.trim()) return w.trim()
  return "—"
}

function evidenceTypeLabel(row: Record<string, unknown>): string {
  return pickStr(row, ["evidence_type", "evidenceType", "link_type", "linkType", "kind"])
}

function evidenceResourceLabel(row: Record<string, unknown>): string {
  return pickStr(row, [
    "resource_label",
    "resourceLabel",
    "title",
    "name",
    "description",
    "target_label",
    "targetLabel",
  ])
}

function evidenceHref(row: Record<string, unknown>): string | null {
  const t = evidenceTypeLabel(row).toLowerCase().replace(/\s+/g, "_")
  const rid =
    readRecordNumber(row, "resource_id") ??
    readRecordNumber(row, "resourceId") ??
    readRecordNumber(row, "target_id") ??
    readRecordNumber(row, "targetId")

  if (t.includes("spectracheck") && t.includes("session")) {
    const sid = readRecordString(row, "session_id") ?? readRecordString(row, "sessionId") ?? (rid != null ? String(rid) : "")
    if (sid) return `/spectracheck?sessionId=${encodeURIComponent(sid)}`
    return "/spectracheck"
  }
  if (t.includes("unified") && t.includes("evidence")) return "/spectracheck"
  if (t.includes("reaction")) {
    if (rid != null) return `/reactions/${encodeURIComponent(String(rid))}`
    return "/reactions"
  }
  if (t.includes("report")) return "/reports"
  if (t.includes("dossier") || t.includes("regulatory")) {
    if (rid != null) return `/regulatory/dossiers/${encodeURIComponent(String(rid))}`
    return "/regulatory"
  }
  if (t.includes("artifact") || t.includes("file") || t.includes("qc") || t.includes("quality")) {
    return "/spectracheck"
  }
  return null
}

function graphRows(
  compoundId: string,
  compound: Record<string, unknown> | null,
  relationships: Record<string, unknown>[],
  evidenceLinks: Record<string, unknown>[],
): { from: string; label: string; to: string }[] {
  const rows: { from: string; label: string; to: string }[] = []
  const selfLabel = compound ? pickStr(compound, ["preferred_name", "preferredName", "name"]) : `compound ${compoundId}`
  for (const r of relationships) {
    const rel = pickStr(r, ["relationship_type", "relationshipType", "type"])
    const toId = pickStr(r, ["related_compound_id", "relatedCompoundId", "to_compound_id", "toCompoundId", "target_compound_id"])
    const toName = pickStr(r, ["related_preferred_name", "relatedPreferredName", "target_name", "targetName"])
    rows.push({
      from: selfLabel,
      label: rel === "—" ? "relationship" : rel,
      to: toName !== "—" ? `${toName} (${toId})` : toId !== "—" ? `compound ${toId}` : "—",
    })
  }
  for (const e of evidenceLinks) {
    const et = evidenceTypeLabel(e)
    const rl = evidenceResourceLabel(e)
    rows.push({
      from: selfLabel,
      label: et === "—" ? "evidence" : et,
      to: rl,
    })
  }
  return rows
}

export function CompoundDetailWorkspace() {
  const params = useParams()
  const rawId = params?.compoundId
  const compoundId = typeof rawId === "string" ? rawId.trim() : Array.isArray(rawId) ? rawId[0]?.trim() ?? "" : ""

  const [compound, setCompound] = useState<Record<string, unknown> | null>(null)
  const [structures, setStructures] = useState<Record<string, unknown>[]>([])
  const [aliases, setAliases] = useState<Record<string, unknown>[]>([])
  const [relationships, setRelationships] = useState<Record<string, unknown>[]>([])
  const [evidenceLinks, setEvidenceLinks] = useState<Record<string, unknown>[]>([])

  const [loadErr, setLoadErr] = useState("")
  const [loading, setLoading] = useState(true)

  const [aliasInput, setAliasInput] = useState("")
  const [aliasBusy, setAliasBusy] = useState(false)
  const [aliasErr, setAliasErr] = useState("")

  const [relTargetId, setRelTargetId] = useState("")
  const [relType, setRelType] = useState("")
  const [relBusy, setRelBusy] = useState(false)
  const [relErr, setRelErr] = useState("")

  const base = compoundId ? `/compound-registry/compounds/${encodeURIComponent(compoundId)}` : ""

  const reloadAll = useCallback(async () => {
    if (!compoundId) {
      setLoading(false)
      return
    }
    setLoading(true)
    setLoadErr("")
    try {
      const [c, s, a, r, e] = await Promise.all([
        apiFetch<unknown>(`${base}`, { method: "GET" }),
        apiFetch<unknown>(`${base}/structures`, { method: "GET" }),
        apiFetch<unknown>(`${base}/aliases`, { method: "GET" }),
        apiFetch<unknown>(`${base}/relationships`, { method: "GET" }),
        apiFetch<unknown>(`${base}/evidence-links`, { method: "GET" }),
      ])
      setCompound(isRecord(c) ? c : null)
      setStructures(normalizeArray(s))
      setAliases(normalizeArray(a))
      setRelationships(normalizeArray(r))
      setEvidenceLinks(normalizeArray(e))
    } catch (err) {
      setCompound(null)
      setStructures([])
      setAliases([])
      setRelationships([])
      setEvidenceLinks([])
      setLoadErr(formatApiError(err, "Could not load compound."))
    } finally {
      setLoading(false)
    }
  }, [base, compoundId])

  useEffect(() => {
    void reloadAll()
  }, [reloadAll])

  const graphData = useMemo(
    () => graphRows(compoundId, compound, relationships, evidenceLinks),
    [compound, compoundId, evidenceLinks, relationships],
  )

  const devPayload = useMemo(
    () => ({
      compound,
      structures,
      aliases,
      relationships,
      evidence_links: evidenceLinks,
    }),
    [aliases, compound, evidenceLinks, relationships, structures],
  )

  async function submitAlias(e: React.FormEvent) {
    e.preventDefault()
    if (!compoundId) return
    const v = aliasInput.trim()
    if (!v) {
      setAliasErr("alias is required.")
      return
    }
    setAliasBusy(true)
    setAliasErr("")
    try {
      await apiFetch(`${base}/aliases`, { method: "POST", body: { alias: v } })
      setAliasInput("")
      await reloadAll()
    } catch (err) {
      setAliasErr(formatApiError(err, "Add alias failed."))
    } finally {
      setAliasBusy(false)
    }
  }

  async function submitRelationship(e: React.FormEvent) {
    e.preventDefault()
    if (!compoundId) return
    const tid = relTargetId.trim()
    const rt = relType.trim()
    if (!tid || !rt) {
      setRelErr("related compound id and relationship type are required.")
      return
    }
    const n = Number.parseInt(tid, 10)
    if (!Number.isFinite(n)) {
      setRelErr("related compound id must be a positive integer.")
      return
    }
    setRelBusy(true)
    setRelErr("")
    try {
      await apiFetch(`${base}/relationships`, {
        method: "POST",
        body: { related_compound_id: n, relationship_type: rt },
      })
      setRelTargetId("")
      setRelType("")
      await reloadAll()
    } catch (err) {
      setRelErr(formatApiError(err, "Add relationship failed."))
    } finally {
      setRelBusy(false)
    }
  }

  const originalInput = compound ? readOriginalStructureInput(compound) : ""
  const derivedCanonical = compound ? readDerivedCanonical(compound) : undefined

  const evidenceGroups = useMemo(() => {
    const g: Record<string, Record<string, unknown>[]> = {
      spectracheck_sessions: [],
      unified_evidence: [],
      reaction_experiments: [],
      reports: [],
      regulatory_dossiers: [],
      files_artifacts_qc: [],
      other: [],
    }
    for (const row of evidenceLinks) {
      const t = evidenceTypeLabel(row).toLowerCase().replace(/\s+/g, "_")
      if (t.includes("spectracheck") && t.includes("session")) g.spectracheck_sessions.push(row)
      else if (t.includes("unified")) g.unified_evidence.push(row)
      else if (t.includes("reaction")) g.reaction_experiments.push(row)
      else if (t.includes("report")) g.reports.push(row)
      else if (t.includes("dossier") || t.includes("regulatory")) g.regulatory_dossiers.push(row)
      else if (t.includes("artifact") || t.includes("file") || t.includes("qc") || t.includes("quality"))
        g.files_artifacts_qc.push(row)
      else g.other.push(row)
    }
    return g
  }, [evidenceLinks])

  if (!compoundId) {
    return (
      <div className="space-y-4 p-4">
        <Alert variant="destructive">
          <AlertTitle>Missing compound</AlertTitle>
          <AlertDescription>compound id is required in the URL.</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/compounds">← Compounds</Link>
            </Button>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Compound Detail</h1>
          <p className="text-muted-foreground">
            Registry id <span className="font-mono text-xs">{compoundId}</span>
          </p>
          {loadErr ? <p className="mt-1 text-xs text-destructive">{loadErr}</p> : null}
        </div>
        <BackendStatusIndicator />
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}

      {!loading && compound ? (
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="flex h-auto min-h-10 w-full flex-wrap justify-start gap-1">
            <TabsTrigger value="overview" className="text-xs sm:text-sm">
              Overview
            </TabsTrigger>
            <TabsTrigger value="structures" className="text-xs sm:text-sm">
              Structures
            </TabsTrigger>
            <TabsTrigger value="aliases" className="text-xs sm:text-sm">
              Aliases
            </TabsTrigger>
            <TabsTrigger value="batches" className="text-xs sm:text-sm">
              Batches & Aliquots
            </TabsTrigger>
            <TabsTrigger value="evidence" className="text-xs sm:text-sm">
              Evidence Links
            </TabsTrigger>
            <TabsTrigger value="relationships" className="text-xs sm:text-sm">
              Relationships
            </TabsTrigger>
            <TabsTrigger value="graph" className="text-xs sm:text-sm">
              Knowledge Graph
            </TabsTrigger>
            <TabsTrigger value="developer" className="text-xs sm:text-sm">
              Developer JSON
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <CompoundDetailKnowledgeLinksCard
              compoundId={compoundId}
              searchHint={pickStr(compound, ["preferred_name", "preferredName", "name"])}
            />
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Overview</CardTitle>
                <CardDescription>Core registry fields for this compound.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <dl className="space-y-3 text-sm">
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">preferred name</dt>
                      <dd className="mt-1 font-medium">{pickStr(compound, ["preferred_name", "preferredName", "name"])}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">registry ID</dt>
                      <dd className="mt-1 font-mono text-xs">{pickStr(compound, ["registry_id", "registryId"])}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">compound type</dt>
                      <dd className="mt-1">
                        <Badge variant="outline">{pickStr(compound, ["compound_type", "compoundType"])}</Badge>
                      </dd>
                    </div>
                    <div>
                      <dt className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        original structure input
                        <InfoTooltip content={STRUCTURE_TOOLTIP} label="About original and canonical structures" />
                      </dt>
                      <dd className="mt-1 break-all rounded-md border bg-muted/30 p-2 font-mono text-xs">
                        {originalInput || "—"}
                      </dd>
                    </div>
                  </dl>
                  <dl className="space-y-3 text-sm">
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">formula</dt>
                      <dd className="mt-1 font-mono text-xs">{pickStr(compound, ["formula", "molecular_formula", "molecularFormula"])}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">exact mass</dt>
                      <dd className="mt-1 tabular-nums">
                        {(() => {
                          const m = pickNum(compound, ["exact_mass", "exactMass", "mono_mass", "monoMass"])
                          return m != null ? m.toLocaleString(undefined, { maximumFractionDigits: 6 }) : "—"
                        })()}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">stereochemistry status</dt>
                      <dd className="mt-1">{pickStr(compound, ["stereochemistry_status", "stereochemistryStatus"])}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">salt/solvent status</dt>
                      <dd className="mt-1">{pickStr(compound, ["salt_solvent_status", "saltSolventStatus"])}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">review/status</dt>
                      <dd className="mt-1 flex flex-wrap gap-2">
                        <Badge variant="secondary">{pickStr(compound, ["status", "record_status", "recordStatus"])}</Badge>
                        <Badge variant="outline">{pickStr(compound, ["review_status", "reviewStatus"])}</Badge>
                      </dd>
                    </div>
                  </dl>
                </div>
                {derivedCanonical ? (
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Derived canonical representation.
                    </p>
                    <p className="mt-1 break-all rounded-md border bg-muted/30 p-2 font-mono text-xs">{derivedCanonical}</p>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="structures" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Structures</CardTitle>
                <CardDescription>Structure records for this compound.</CardDescription>
              </CardHeader>
              <CardContent>
                {structures.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No structure records returned.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>source</TableHead>
                          <TableHead>validation status</TableHead>
                          <TableHead>reviewer status</TableHead>
                          <TableHead>normalization warnings</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {structures.map((row, i) => (
                          <TableRow key={i}>
                            <TableCell className="max-w-[200px] text-xs">
                              {pickStr(row, ["source", "structure_source", "structureSource", "origin"])}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">
                                {pickStr(row, ["validation_status", "validationStatus", "validity"])}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              <Badge variant="secondary">
                                {pickStr(row, ["reviewer_status", "reviewerStatus", "review_status", "reviewStatus"])}
                              </Badge>
                            </TableCell>
                            <TableCell className="max-w-[280px] text-xs text-muted-foreground">{formatWarnings(row)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="aliases" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Add alias</CardTitle>
              </CardHeader>
              <CardContent>
                <form className="flex flex-col gap-3 sm:flex-row sm:items-end" onSubmit={submitAlias}>
                  <div className="flex-1 space-y-2">
                    <Label htmlFor="cd-alias">alias</Label>
                    <Input id="cd-alias" value={aliasInput} onChange={(e) => setAliasInput(e.target.value)} autoComplete="off" />
                  </div>
                  <Button type="submit" disabled={aliasBusy}>
                    {aliasBusy ? "Adding…" : "Add alias"}
                  </Button>
                </form>
                {aliasErr ? (
                  <Alert variant="destructive" className="mt-3">
                    <AlertTitle className="text-sm">Alias</AlertTitle>
                    <AlertDescription className="text-xs">{aliasErr}</AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Aliases</CardTitle>
                <CardDescription>Registered aliases for this compound.</CardDescription>
              </CardHeader>
              <CardContent>
                {aliases.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No aliases returned.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>alias</TableHead>
                          <TableHead>kind</TableHead>
                          <TableHead>updated</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {aliases.map((row, i) => (
                          <TableRow key={i}>
                            <TableCell className="font-medium">{pickStr(row, ["alias", "alias_text", "aliasText", "name"])}</TableCell>
                            <TableCell className="text-xs">{pickStr(row, ["alias_kind", "aliasKind", "kind", "type"])}</TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {pickStr(row, ["updated_at", "updatedAt", "created_at", "createdAt"])}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="batches" className="space-y-4">
            <Card>
              <CardContent className="pt-6">
                <CompoundBatchesAliquotsPanel compoundId={compoundId} />
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="evidence" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Evidence Links</CardTitle>
                <CardDescription>Linked modules and artifacts for this compound.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {evidenceLinks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No evidence links returned.</p>
                ) : (
                  <>
                    {(
                      [
                        ["Linked SpectraCheck sessions", evidenceGroups.spectracheck_sessions],
                        ["Linked unified evidence", evidenceGroups.unified_evidence],
                        ["Linked reaction experiments", evidenceGroups.reaction_experiments],
                        ["Linked reports", evidenceGroups.reports],
                        ["Linked regulatory dossiers", evidenceGroups.regulatory_dossiers],
                        ["Linked files, artifacts, and QC", evidenceGroups.files_artifacts_qc],
                        ["Other links", evidenceGroups.other],
                      ] as [string, Record<string, unknown>[]][]
                    ).map(([title, list]) =>
                      (list as Record<string, unknown>[]).length === 0 ? null : (
                        <div key={String(title)}>
                          <h3 className="mb-2 text-sm font-medium">{title}</h3>
                          <div className="table-scroll">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>type</TableHead>
                                  <TableHead>resource</TableHead>
                                  <TableHead>link</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {(list as Record<string, unknown>[]).map((row, i) => {
                                  const href = evidenceHref(row)
                                  return (
                                    <TableRow key={i}>
                                      <TableCell className="text-xs">{evidenceTypeLabel(row)}</TableCell>
                                      <TableCell className="max-w-[240px] text-xs">{evidenceResourceLabel(row)}</TableCell>
                                      <TableCell>
                                        {href ? (
                                          <Button variant="link" className="h-auto p-0 text-xs" asChild>
                                            <Link href={href}>Open</Link>
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
                        </div>
                      ),
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="relationships" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Add relationship</CardTitle>
              </CardHeader>
              <CardContent>
                <form className="grid gap-4 sm:grid-cols-2" onSubmit={submitRelationship}>
                  <div className="space-y-2">
                    <Label htmlFor="cd-rel-target">related compound id</Label>
                    <Input id="cd-rel-target" value={relTargetId} onChange={(e) => setRelTargetId(e.target.value)} inputMode="numeric" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="cd-rel-type">relationship type</Label>
                    <Input id="cd-rel-type" value={relType} onChange={(e) => setRelType(e.target.value)} autoComplete="off" />
                  </div>
                  <div className="sm:col-span-2">
                    <Button type="submit" disabled={relBusy}>
                      {relBusy ? "Adding…" : "Add relationship"}
                    </Button>
                  </div>
                </form>
                {relErr ? (
                  <Alert variant="destructive" className="mt-3">
                    <AlertTitle className="text-sm">Relationship</AlertTitle>
                    <AlertDescription className="text-xs">{relErr}</AlertDescription>
                  </Alert>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Relationships</CardTitle>
                <CardDescription>Related compounds.</CardDescription>
              </CardHeader>
              <CardContent>
                {relationships.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No relationships returned.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>relationship type</TableHead>
                          <TableHead>related compound</TableHead>
                          <TableHead>status</TableHead>
                          <TableHead>open</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {relationships.map((row, i) => {
                          const relatedId =
                            readRecordNumber(row, "related_compound_id") ??
                            readRecordNumber(row, "relatedCompoundId") ??
                            readRecordNumber(row, "to_compound_id") ??
                            readRecordNumber(row, "toCompoundId")
                          const href =
                            relatedId != null ? `/compounds/${encodeURIComponent(String(relatedId))}` : null
                          return (
                            <TableRow key={i}>
                              <TableCell className="text-xs">
                                {pickStr(row, ["relationship_type", "relationshipType", "type"])}
                              </TableCell>
                              <TableCell className="font-mono text-xs">
                                {pickStr(row, ["related_compound_id", "relatedCompoundId", "to_compound_id", "toCompoundId"])}
                              </TableCell>
                              <TableCell>
                                <Badge variant="outline">{pickStr(row, ["status", "edge_status", "edgeStatus"])}</Badge>
                              </TableCell>
                              <TableCell>
                                {href ? (
                                  <Button variant="outline" size="sm" className="h-8" asChild>
                                    <Link href={href}>Open</Link>
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
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="graph" className="space-y-4">
            {compoundId ? <CompoundScientificKnowledgeGraphPanel compoundId={compoundId} /> : null}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Knowledge Graph (this page)</CardTitle>
                <CardDescription>
                  Network of relationships and evidence links derived from data already loaded for this compound. For the complete graph across all linked compounds, open the Knowledge Graph view.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {graphData.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No graph edges from loaded relationships or evidence links.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>From</TableHead>
                          <TableHead>Relation</TableHead>
                          <TableHead>To</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {graphData.map((row, i) => (
                          <TableRow key={i}>
                            <TableCell className="max-w-[200px] text-sm">{row.from}</TableCell>
                            <TableCell className="text-xs">{row.label}</TableCell>
                            <TableCell className="max-w-[240px] text-sm">{row.to}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="developer" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Developer JSON</CardTitle>
                <CardDescription>Raw payloads for debugging.</CardDescription>
              </CardHeader>
              <CardContent>
                <DeveloperJsonPanel data={devPayload} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      ) : null}

      {!loading && !compound && !loadErr ? (
        <Alert>
          <AlertTitle>No compound record</AlertTitle>
          <AlertDescription className="text-sm">Nothing returned for this id.</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
