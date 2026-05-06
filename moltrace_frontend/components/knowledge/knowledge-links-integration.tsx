"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { KNOWLEDGE_LINK_CONFIDENCE_LABELS, KNOWLEDGE_REVIEW_RECORD_TYPES } from "@/components/knowledge/knowledge-constants"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
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
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ChevronDown, Loader2, BookOpen } from "lucide-react"

/** Minimal query token — yields empty token list server-side so catalog rows match broadly (see API `_matches`). */
const BROAD_CATALOG_QUERY = "a"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readIntList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function truncateLabel(s: string | undefined, max = 72): string {
  const t = (s ?? "").trim()
  if (!t) return "—"
  return t.length <= max ? t : `${t.slice(0, max)}…`
}

type KnowledgeSearchPayload = {
  analytical_records?: unknown[]
  reaction_records?: unknown[]
  regulatory_records?: unknown[]
  warnings?: unknown[]
}

async function fetchKnowledgeSearch(queryProbe: string, recordType: string | undefined, limit: number) {
  const params = new URLSearchParams()
  params.set("query", queryProbe)
  params.set("limit", String(limit))
  if (recordType) params.set("record_type", recordType)
  return apiFetch<unknown>(`/knowledge/search?${params.toString()}`, { method: "GET" })
}

async function fetchTrainingCandidates() {
  const params = new URLSearchParams()
  params.set("limit", "120")
  return apiFetch<unknown>(`/knowledge/training-dataset-candidates?${params.toString()}`, { method: "GET" })
}

function asRows(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) return []
  return raw.filter(isRecord) as Record<string, unknown>[]
}

export function KnowledgeLinkMiniForm({
  targetType,
  targetId,
  onLinked,
}: {
  targetType: string
  targetId: string | number
  onLinked?: () => void
}) {
  const [recordType, setRecordType] = useState<string>("analytical")
  const [recordId, setRecordId] = useState("")
  const [relationType, setRelationType] = useState("linked_to")
  const [confidence, setConfidence] = useState<string>("requires_review")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")
  const [ok, setOk] = useState("")

  async function submit() {
    const id = Number.parseInt(recordId.trim(), 10)
    if (!Number.isFinite(id) || id < 1) {
      setErr("record_id must be a positive integer.")
      return
    }
    setErr("")
    setOk("")
    setBusy(true)
    try {
      await apiFetch(`/knowledge/records/${id}/link`, {
        method: "POST",
        body: {
          record_type: recordType,
          target_type: targetType,
          target_id: targetId,
          relation_type: relationType.trim() || "linked_to",
          confidence_label: confidence,
          metadata_json: {},
        },
      })
      setOk("Link created. Accepted records only (per API review rules).")
      onLinked?.()
    } catch (e) {
      setErr(formatApiError(e, "Link failed."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 rounded-md border bg-muted/20 p-3">
      <p className="text-xs font-medium text-muted-foreground">
        <code className="text-[11px]">POST /knowledge/records/</code>
        {"{record_id}"}
        <code className="text-[11px]">/link</code>
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1">
          <Label className="text-xs">record_type</Label>
          <Select value={recordType} onValueChange={setRecordType}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KNOWLEDGE_REVIEW_RECORD_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {t}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label className="text-xs">record_id</Label>
          <Input className="h-8 font-mono text-xs" value={recordId} onChange={(e) => setRecordId(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">relation_type</Label>
          <Input className="h-8 text-xs" value={relationType} onChange={(e) => setRelationType(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">confidence_label</Label>
          <Select value={confidence} onValueChange={setConfidence}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KNOWLEDGE_LINK_CONFIDENCE_LABELS.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <Button type="button" size="sm" className="h-8" disabled={busy} onClick={() => void submit()}>
        {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
        Link record
      </Button>
      {err ? <p className="text-xs text-destructive">{err}</p> : null}
      {ok ? <p className="text-xs text-muted-foreground">{ok}</p> : null}
    </div>
  )
}

const INTEGRATION_TOOLTIP =
  "Uses GET /knowledge/search for compact previews (IDs and metadata only — no raw spectra or full source text). Link with POST /knowledge/records/{record_id}/link after records are accepted."

export function SpectraCheckKnowledgeLinksCard({ backendSessionId }: { backendSessionId: string | null }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState("")
  const [analytical, setAnalytical] = useState<Record<string, unknown>[]>([])
  const [training, setTraining] = useState<Record<string, unknown>[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const [s, tr] = await Promise.all([
        fetchKnowledgeSearch(BROAD_CATALOG_QUERY, "analytical", 18),
        fetchTrainingCandidates(),
      ])
      const sp = s as KnowledgeSearchPayload
      setAnalytical(asRows(sp.analytical_records))
      const trainRows = asRows(tr)
      const sid = backendSessionId?.trim()
      setTraining(
        trainRows.filter((row) => {
          const dt = readRecordString(row, "dataset_type")
          const spectracheckTypes = new Set([
            "nmr_prediction",
            "nmr_structure_elucidation",
            "msms_annotation",
            "lcms_feature",
          ])
          if (!spectracheckTypes.has(dt ?? "")) return false
          if (!sid) return true
          const meta = row["metadata_json"]
          const blob = meta != null ? JSON.stringify(meta) : ""
          return blob.includes(sid)
        }),
      )
    } catch (e) {
      setErr(formatApiError(e, "Could not load knowledge previews."))
      setAnalytical([])
      setTraining([])
    } finally {
      setLoading(false)
    }
  }, [backendSessionId])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const sessionTargetId = backendSessionId?.trim() ?? ""

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="border-muted">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer pb-2 hover:bg-muted/30">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div>
                  <CardTitle className="text-base">Knowledge links</CardTitle>
                  <CardDescription className="text-xs">
                    Analytical / NMR literature / HRMS rows (sanitized) · training candidates for SpectraCheck-related
                    dataset types
                  </CardDescription>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-4 border-t pt-4">
            <div className="flex items-center gap-2">
              <InfoTooltip content={INTEGRATION_TOOLTIP} label="Knowledge integration" />
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" asChild>
                <Link href="/knowledge/analytical">Knowledge Library</Link>
              </Button>
            </div>

            {sessionTargetId ? (
              <KnowledgeLinkMiniForm
                targetType="spectracheck_session"
                targetId={sessionTargetId}
                onLinked={() => void load()}
              />
            ) : (
              <p className="text-xs text-muted-foreground">Load or save a backend session to enable linking to this SpectraCheck session.</p>
            )}

            {err ? (
              <Alert variant="destructive">
                <AlertDescription className="text-xs">{err}</AlertDescription>
              </Alert>
            ) : null}

            {loading ? (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading previews…
              </p>
            ) : (
              <>
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    Extracted analytical records (preview — no NMR/MS full text)
                  </p>
                  <div className="table-scroll max-h-[220px] min-w-0 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[56px] text-xs">id</TableHead>
                          <TableHead className="text-xs">compound_name</TableHead>
                          <TableHead className="text-xs">review_status</TableHead>
                          <TableHead className="text-right text-xs">citation_ids_json</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {analytical.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={4} className="text-xs text-muted-foreground">
                              No rows.
                            </TableCell>
                          </TableRow>
                        ) : (
                          analytical.map((row, idx) => {
                            const id = readRecordNumber(row, "id")
                            return (
                              <TableRow key={id != null ? `a-${id}` : `a-${idx}`}>
                                <TableCell className="font-mono text-[11px]">{id ?? "—"}</TableCell>
                                <TableCell className="max-w-[200px] truncate text-xs">
                                  {truncateLabel(readRecordString(row, "compound_name"), 48)}
                                </TableCell>
                                <TableCell className="text-xs">{readRecordString(row, "review_status") ?? "—"}</TableCell>
                                <TableCell className="text-right font-mono text-[11px]">
                                  {readIntList(row["citation_ids_json"]).length}
                                </TableCell>
                              </TableRow>
                            )
                          })
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Training dataset candidates (session-scoped when metadata matches)</p>
                  <div className="table-scroll max-h-[160px] min-w-0 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[56px] text-xs">id</TableHead>
                          <TableHead className="text-xs">dataset_type</TableHead>
                          <TableHead className="text-xs">status</TableHead>
                          <TableHead className="text-xs">record_id</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {training.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={4} className="text-xs text-muted-foreground">
                              No matching candidates.
                            </TableCell>
                          </TableRow>
                        ) : (
                          training.slice(0, 12).map((row, idx) => {
                            const id = readRecordNumber(row, "id")
                            return (
                              <TableRow key={id != null ? `t-${id}` : `t-${idx}`}>
                                <TableCell className="font-mono text-[11px]">{id ?? "—"}</TableCell>
                                <TableCell className="font-mono text-[11px]">{readRecordString(row, "dataset_type") ?? "—"}</TableCell>
                                <TableCell>
                                  <Badge variant="outline" className="text-[10px]">
                                    {readRecordString(row, "status") ?? "—"}
                                  </Badge>
                                </TableCell>
                                <TableCell className="font-mono text-[11px]">{readRecordNumber(row, "record_id") ?? "—"}</TableCell>
                              </TableRow>
                            )
                          })
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

export function ReactionStudioKnowledgeLinksCard({ reactionProjectId }: { reactionProjectId: number }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState("")
  const [reactions, setReactions] = useState<Record<string, unknown>[]>([])
  const [training, setTraining] = useState<Record<string, unknown>[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const [s, tr] = await Promise.all([
        fetchKnowledgeSearch(BROAD_CATALOG_QUERY, "reaction", 16),
        fetchTrainingCandidates(),
      ])
      const sp = s as KnowledgeSearchPayload
      setReactions(asRows(sp.reaction_records))
      const trainRows = asRows(tr)
      setTraining(trainRows.filter((row) => readRecordString(row, "dataset_type") === "reaction_optimization"))
    } catch (e) {
      setErr(formatApiError(e, "Could not load knowledge previews."))
      setReactions([])
      setTraining([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="border-muted">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer pb-2 hover:bg-muted/30">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div>
                  <CardTitle className="text-base">Knowledge links</CardTitle>
                  <CardDescription className="text-xs">
                    Reaction extraction previews · literature-style summaries (no product_smiles) · reaction_optimization
                    training candidates
                  </CardDescription>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-4 border-t pt-4">
            <div className="flex items-center gap-2">
              <InfoTooltip content={INTEGRATION_TOOLTIP} label="Knowledge integration" />
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" asChild>
                <Link href="/knowledge/reactions">Knowledge Library</Link>
              </Button>
            </div>

            <KnowledgeLinkMiniForm targetType="reaction_project" targetId={reactionProjectId} onLinked={() => void load()} />

            {err ? (
              <Alert variant="destructive">
                <AlertDescription className="text-xs">{err}</AlertDescription>
              </Alert>
            ) : null}

            {loading ? (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading previews…
              </p>
            ) : (
              <>
                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">Extracted reaction records (summary fields only)</p>
                  <div className="table-scroll max-h-[200px] min-w-0 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[56px] text-xs">id</TableHead>
                          <TableHead className="text-xs">reaction_type</TableHead>
                          <TableHead className="text-xs">substrate_summary</TableHead>
                          <TableHead className="text-xs">review_status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {reactions.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={4} className="text-xs text-muted-foreground">
                              No rows.
                            </TableCell>
                          </TableRow>
                        ) : (
                          reactions.map((row, idx) => {
                            const id = readRecordNumber(row, "id")
                            return (
                              <TableRow key={id != null ? `r-${id}` : `r-${idx}`}>
                                <TableCell className="font-mono text-[11px]">{id ?? "—"}</TableCell>
                                <TableCell className="font-mono text-[11px]">{readRecordString(row, "reaction_type") ?? "—"}</TableCell>
                                <TableCell className="max-w-[200px] truncate text-xs">
                                  {truncateLabel(readRecordString(row, "substrate_summary"), 56)}
                                </TableCell>
                                <TableCell className="text-xs">{readRecordString(row, "review_status") ?? "—"}</TableCell>
                              </TableRow>
                            )
                          })
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </div>

                <div>
                  <p className="mb-2 text-xs font-medium text-muted-foreground">reaction_optimization training candidates</p>
                  <div className="table-scroll max-h-[140px] min-w-0 overflow-auto rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-[56px] text-xs">id</TableHead>
                          <TableHead className="text-xs">status</TableHead>
                          <TableHead className="text-xs">record_id</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {training.length === 0 ? (
                          <TableRow>
                            <TableCell colSpan={3} className="text-xs text-muted-foreground">
                              No rows.
                            </TableCell>
                          </TableRow>
                        ) : (
                          training.slice(0, 10).map((row, idx) => {
                            const id = readRecordNumber(row, "id")
                            return (
                              <TableRow key={id != null ? `tr-${id}` : `tr-${idx}`}>
                                <TableCell className="font-mono text-[11px]">{id ?? "—"}</TableCell>
                                <TableCell className="text-xs">{readRecordString(row, "status") ?? "—"}</TableCell>
                                <TableCell className="font-mono text-[11px]">{readRecordNumber(row, "record_id") ?? "—"}</TableCell>
                              </TableRow>
                            )
                          })
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

export function RegulatoryDossierKnowledgeLinksCard({ dossierId }: { dossierId: number }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState("")
  const [regs, setRegs] = useState<Record<string, unknown>[]>([])
  const [warnList, setWarnList] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const s = await fetchKnowledgeSearch(BROAD_CATALOG_QUERY, "regulatory", 16)
      const sp = s as KnowledgeSearchPayload & { warnings?: unknown }
      setRegs(asRows(sp.regulatory_records))
      const w = sp.warnings
      setWarnList(Array.isArray(w) ? w.filter((x): x is string => typeof x === "string") : [])
    } catch (e) {
      setErr(formatApiError(e, "Could not load knowledge previews."))
      setRegs([])
      setWarnList([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="border-muted">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer pb-2 hover:bg-muted/30">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div>
                  <CardTitle className="text-base">Knowledge links</CardTitle>
                  <CardDescription className="text-xs">
                    Regulatory extraction previews (topic only — no requirement_text) · JSON fields shown as present/absent
                  </CardDescription>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-4 border-t pt-4">
            <div className="flex items-center gap-2">
              <InfoTooltip content={INTEGRATION_TOOLTIP} label="Knowledge integration" />
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" asChild>
                <Link href="/knowledge/regulatory">Knowledge Library</Link>
              </Button>
            </div>

            <KnowledgeLinkMiniForm targetType="regulatory_dossier" targetId={dossierId} onLinked={() => void load()} />

            {warnList.length > 0 ? (
              <Alert>
                <AlertDescription className="text-xs">
                  <span className="font-medium">warnings</span>
                  <ul className="mt-1 list-inside list-disc">
                    {warnList.slice(0, 6).map((w, i) => (
                      <li key={`${i}-${w.slice(0, 40)}`}>{truncateLabel(w, 160)}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}

            {err ? (
              <Alert variant="destructive">
                <AlertDescription className="text-xs">{err}</AlertDescription>
              </Alert>
            ) : null}

            {loading ? (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading previews…
              </p>
            ) : (
              <div className="table-scroll max-h-[240px] min-w-0 overflow-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[56px] text-xs">id</TableHead>
                      <TableHead className="text-xs">topic</TableHead>
                      <TableHead className="text-xs">review_status</TableHead>
                      <TableHead className="text-xs">citations</TableHead>
                      <TableHead className="text-xs">rule_candidate_json</TableHead>
                      <TableHead className="text-xs">action_candidate_json</TableHead>
                      <TableHead className="text-xs">threshold_summary_json</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {regs.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="text-xs text-muted-foreground">
                          No rows.
                        </TableCell>
                      </TableRow>
                    ) : (
                      regs.map((row, idx) => {
                        const id = readRecordNumber(row, "id")
                        const ruleKeys =
                          row["rule_candidate_json"] && typeof row["rule_candidate_json"] === "object"
                            ? Object.keys(row["rule_candidate_json"] as object).length
                            : 0
                        const actionKeys =
                          row["action_candidate_json"] && typeof row["action_candidate_json"] === "object"
                            ? Object.keys(row["action_candidate_json"] as object).length
                            : 0
                        const thrKeys =
                          row["threshold_summary_json"] && typeof row["threshold_summary_json"] === "object"
                            ? Object.keys(row["threshold_summary_json"] as object).length
                            : 0
                        return (
                          <TableRow key={id != null ? `g-${id}` : `g-${idx}`}>
                            <TableCell className="font-mono text-[11px]">{id ?? "—"}</TableCell>
                            <TableCell className="max-w-[140px] truncate font-mono text-[11px]">
                              {truncateLabel(readRecordString(row, "topic"), 40)}
                            </TableCell>
                            <TableCell className="text-xs">{readRecordString(row, "review_status") ?? "—"}</TableCell>
                            <TableCell className="text-right font-mono text-[11px]">
                              {readIntList(row["citation_ids_json"]).length}
                            </TableCell>
                            <TableCell className="text-xs">{ruleKeys > 0 ? `${ruleKeys} keys` : "—"}</TableCell>
                            <TableCell className="text-xs">{actionKeys > 0 ? `${actionKeys} keys` : "—"}</TableCell>
                            <TableCell className="text-xs">{thrKeys > 0 ? `${thrKeys} keys` : "—"}</TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}

export function CompoundDetailKnowledgeLinksCard({
  compoundId,
  searchHint,
}: {
  compoundId: string
  searchHint?: string
}) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState("")
  const [analytical, setAnalytical] = useState<Record<string, unknown>[]>([])
  const [reactions, setReactions] = useState<Record<string, unknown>[]>([])
  const [regs, setRegs] = useState<Record<string, unknown>[]>([])

  const probe = useMemo(() => {
    const t = (searchHint ?? "").trim()
    return t.length >= 2 ? t.slice(0, 80) : BROAD_CATALOG_QUERY
  }, [searchHint])

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const [a, r, g] = await Promise.all([
        fetchKnowledgeSearch(probe, "analytical", 12),
        fetchKnowledgeSearch(probe, "reaction", 10),
        fetchKnowledgeSearch(probe, "regulatory", 8),
      ])
      setAnalytical(asRows((a as KnowledgeSearchPayload).analytical_records))
      setReactions(asRows((r as KnowledgeSearchPayload).reaction_records))
      setRegs(asRows((g as KnowledgeSearchPayload).regulatory_records))
    } catch (e) {
      setErr(formatApiError(e, "Could not load knowledge previews."))
      setAnalytical([])
      setReactions([])
      setRegs([])
    } finally {
      setLoading(false)
    }
  }, [probe])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const tid = compoundId.trim()

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <Card className="border-muted">
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer pb-2 hover:bg-muted/30">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div>
                  <CardTitle className="text-base">Knowledge links</CardTitle>
                  <CardDescription className="text-xs">
                    Search previews scoped by compound hint when available · source provenance via citation counts and IDs
                    only
                  </CardDescription>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
            </div>
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="space-y-4 border-t pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <InfoTooltip content={INTEGRATION_TOOLTIP} label="Knowledge integration" />
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" asChild>
                <Link href="/knowledge">Knowledge Library</Link>
              </Button>
            </div>

            {tid ? (
              <KnowledgeLinkMiniForm targetType="compound" targetId={tid} onLinked={() => void load()} />
            ) : null}

            {err ? (
              <Alert variant="destructive">
                <AlertDescription className="text-xs">{err}</AlertDescription>
              </Alert>
            ) : null}

            {loading ? (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading previews…
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">analytical_records</p>
                  <ul className="space-y-1 text-[11px] text-muted-foreground">
                    {analytical.length === 0 ? (
                      <li>—</li>
                    ) : (
                      analytical.slice(0, 5).map((row, i) => (
                        <li key={readRecordNumber(row, "id") ?? i} className="font-mono">
                          id {readRecordNumber(row, "id") ?? "—"} · {readRecordString(row, "review_status") ?? "—"} · cit{" "}
                          {readIntList(row["citation_ids_json"]).length}
                        </li>
                      ))
                    )}
                  </ul>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">reaction_records</p>
                  <ul className="space-y-1 text-[11px] text-muted-foreground">
                    {reactions.length === 0 ? (
                      <li>—</li>
                    ) : (
                      reactions.slice(0, 5).map((row, i) => (
                        <li key={readRecordNumber(row, "id") ?? i} className="font-mono">
                          id {readRecordNumber(row, "id") ?? "—"} · {readRecordString(row, "review_status") ?? "—"}
                        </li>
                      ))
                    )}
                  </ul>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">regulatory_records</p>
                  <ul className="space-y-1 text-[11px] text-muted-foreground">
                    {regs.length === 0 ? (
                      <li>—</li>
                    ) : (
                      regs.slice(0, 5).map((row, i) => (
                        <li key={readRecordNumber(row, "id") ?? i} className="font-mono">
                          id {readRecordNumber(row, "id") ?? "—"} · {truncateLabel(readRecordString(row, "topic"), 32)}
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
