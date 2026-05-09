"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Loader2 } from "lucide-react"
import { trackCompoundGraphViewed } from "@/src/lib/analytics/analytics-client"

const GRAPH_TOOLTIP =
  "The scientific knowledge graph links compounds, batches, analytical evidence, reactions, reports, and regulatory dossiers for traceable decision-making."

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function normalizeGraphPayload(raw: unknown): {
  nodes: Record<string, unknown>[]
  edges: Record<string, unknown>[]
  warnings: string[]
  notes: string[]
} {
  if (!isRecord(raw)) return { nodes: [], edges: [], warnings: [], notes: [] }
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.filter(isRecord) : []
  const edges = Array.isArray(raw.edges) ? raw.edges.filter(isRecord) : []
  const warnings = Array.isArray(raw.warnings) ? raw.warnings.filter((x): x is string => typeof x === "string") : []
  const notes = Array.isArray(raw.notes) ? raw.notes.filter((x): x is string => typeof x === "string") : []
  return { nodes, edges, warnings, notes }
}

function nodeIdString(row: Record<string, unknown>): string {
  const s = readRecordString(row, "node_id") ?? readRecordString(row, "nodeId")
  if (s?.trim()) return s.trim()
  const n = readRecordNumber(row, "node_id") ?? readRecordNumber(row, "nodeId")
  return n != null ? String(n) : "—"
}

function nodeType(row: Record<string, unknown>): string {
  return readRecordString(row, "node_type") ?? readRecordString(row, "nodeType") ?? "—"
}

function nodeLabel(row: Record<string, unknown>): string {
  const v = readRecordString(row, "label")
  if (v?.trim()) return v.trim()
  return "—"
}

function metadataPreview(row: Record<string, unknown>, max: number): string {
  const m = row.metadata_json ?? row.metadataJson
  if (!isRecord(m) || Object.keys(m).length === 0) return "—"
  try {
    const t = JSON.stringify(m)
    return t.length > max ? `${t.slice(0, max)}…` : t
  } catch {
    return "—"
  }
}

function hrefForNode(nodeType: string, nodeId: string): string | null {
  const t = nodeType.toLowerCase()
  const id = nodeId.trim()
  if (!id || id === "—") return null
  if (t === "compound") return `/compounds/${encodeURIComponent(id)}`
  if (t === "batch") return `/batches`
  if (t === "reaction_project" || t === "reactionexperiment" || t === "reaction_experiment") {
    return `/reactions/${encodeURIComponent(id)}`
  }
  if (t === "regulatory_dossier") return `/regulatory/dossiers/${encodeURIComponent(id)}`
  if (t === "spectracheck_session" || t === "spectrachecksession") return "/spectracheck"
  if (t === "report") return "/reports"
  if (t === "sample" || t.includes("aliquot")) return "/projects"
  if (t.includes("qc") || t.includes("artifact") || t.includes("file") || t === "unified_evidence") {
    return "/spectracheck"
  }
  return null
}

function edgeSourceType(row: Record<string, unknown>): string {
  return readRecordString(row, "source_type") ?? readRecordString(row, "sourceType") ?? "—"
}

function edgeTargetType(row: Record<string, unknown>): string {
  return readRecordString(row, "target_type") ?? readRecordString(row, "targetType") ?? "—"
}

function edgeSourceId(row: Record<string, unknown>): string {
  const s = readRecordString(row, "source_id") ?? readRecordString(row, "sourceId")
  if (s?.trim()) return s.trim()
  const n = readRecordNumber(row, "source_id") ?? readRecordNumber(row, "sourceId")
  return n != null ? String(n) : "—"
}

function edgeTargetId(row: Record<string, unknown>): string {
  const s = readRecordString(row, "target_id") ?? readRecordString(row, "targetId")
  if (s?.trim()) return s.trim()
  const n = readRecordNumber(row, "target_id") ?? readRecordNumber(row, "targetId")
  return n != null ? String(n) : "—"
}

function edgeCreatedAt(row: Record<string, unknown>): string {
  return readRecordString(row, "created_at") ?? readRecordString(row, "createdAt") ?? ""
}

function parseEdgeTime(iso: string): number {
  const d = Date.parse(iso)
  return Number.isNaN(d) ? 0 : d
}

export type CompoundScientificKnowledgeGraphPanelProps = {
  compoundId: string
  /** When true (full-page route), the link to open the same view in a new route is hidden. */
  hideFullPageLink?: boolean
}

export function CompoundScientificKnowledgeGraphPanel({
  compoundId,
  hideFullPageLink = false,
}: CompoundScientificKnowledgeGraphPanelProps) {
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null)
  const graphViewTrackedKey = useRef<string | null>(null)

  const numericId = useMemo(() => {
    const n = Number.parseInt(compoundId, 10)
    return Number.isFinite(n) && n > 0 ? n : null
  }, [compoundId])

  const load = useCallback(async () => {
    if (numericId == null) {
      setPayload(null)
      setErr("A valid compound ID is required to load the knowledge graph.")
      setLoading(false)
      return
    }
    setLoading(true)
    setErr("")
    try {
      const q = new URLSearchParams()
      q.set("compound_id", String(numericId))
      q.set("limit", "500")
      const raw = await apiFetch<unknown>(`/compound-registry/graph?${q.toString()}`, { method: "GET" })
      setPayload(isRecord(raw) ? raw : null)
    } catch (e) {
      setPayload(null)
      setErr(formatApiError(e, "Could not load scientific knowledge graph."))
    } finally {
      setLoading(false)
    }
  }, [numericId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (loading || err || payload == null || numericId == null) return
    const key = String(numericId)
    if (graphViewTrackedKey.current === key) return
    graphViewTrackedKey.current = key
    trackCompoundGraphViewed({ compound_id: numericId, status: "loaded" })
  }, [loading, err, payload, numericId])

  const { nodes, edges, warnings, notes } = useMemo(() => normalizeGraphPayload(payload), [payload])

  const nodesByType = useMemo(() => {
    const m = new Map<string, Record<string, unknown>[]>()
    for (const n of nodes) {
      const t = nodeType(n)
      const list = m.get(t) ?? []
      list.push(n)
      m.set(t, list)
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [nodes])

  const edgesByRelation = useMemo(() => {
    const m = new Map<string, Record<string, unknown>[]>()
    for (const e of edges) {
      const rt = readRecordString(e, "relation_type") ?? readRecordString(e, "relationType") ?? "—"
      const list = m.get(rt) ?? []
      list.push(e)
      m.set(rt, list)
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [edges])

  const timelineEdges = useMemo(() => {
    return [...edges].sort((a, b) => parseEdgeTime(edgeCreatedAt(b)) - parseEdgeTime(edgeCreatedAt(a)))
  }, [edges])

  if (numericId == null) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Invalid compound id</AlertTitle>
        <AlertDescription className="text-sm">{err || "Expected a numeric compound id in the route."}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-base">Scientific knowledge graph</CardTitle>
              <InfoTooltip label="About this graph" content={GRAPH_TOOLTIP} />
            </div>
            {hideFullPageLink ? null : (
              <Button variant="outline" size="sm" className="h-8 shrink-0 text-xs" asChild>
                <Link href={`/compounds/${encodeURIComponent(compoundId)}/graph`}>Open full-page graph</Link>
              </Button>
            )}
          </div>
          <CardDescription>
            GET /compound-registry/graph with compound_id and limit query parameters — nodes and edges are returned as
            stored; labels may be absent for non-compound vertices until expanded server-side.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle className="text-sm">Interpretation</AlertTitle>
            <AlertDescription className="text-xs leading-relaxed">
              This view is for traceability and review context only. Graph edges do not assert chemical identity, purity, or
              regulatory approval on their own.
            </AlertDescription>
          </Alert>

          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading graph…
            </div>
          ) : null}
          {err ? (
            <p className="text-sm text-destructive" role="alert">
              {err}
            </p>
          ) : null}

          {warnings.length > 0 ? (
            <Alert variant="destructive">
              <AlertTitle className="text-sm">warnings (payload)</AlertTitle>
              <AlertDescription>
                <ul className="list-inside list-disc text-xs">
                  {warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          ) : null}

          {notes.length > 0 ? (
            <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">notes (payload)</p>
              <ul className="mt-2 list-inside list-disc space-y-1">
                {notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {!loading && !err ? (
            <p className="text-xs text-muted-foreground">
              {nodes.length} node{nodes.length === 1 ? "" : "s"} · {edges.length} edge{edges.length === 1 ? "" : "s"}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Nodes by type</CardTitle>
          <CardDescription>Grouped by node_type from the API response.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {nodesByType.length === 0 && !loading && !err ? (
            <p className="text-sm text-muted-foreground">No nodes in this graph payload.</p>
          ) : null}
          {nodesByType.map(([type, rows]) => (
            <div key={type} className="rounded-lg border bg-muted/10 p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs">
                  {type}
                </Badge>
                <span className="text-xs text-muted-foreground">{rows.length} row{rows.length === 1 ? "" : "s"}</span>
              </div>
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[120px]">node_id</TableHead>
                      <TableHead>label</TableHead>
                      <TableHead className="min-w-[180px]">metadata_json</TableHead>
                      <TableHead className="w-[100px]">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rows.map((row, i) => {
                      const idStr = nodeIdString(row)
                      const href = hrefForNode(type, idStr)
                      return (
                        <TableRow key={`${type}-${idStr}-${i}`}>
                          <TableCell className="font-mono text-xs">{idStr}</TableCell>
                          <TableCell className="text-sm">{nodeLabel(row)}</TableCell>
                          <TableCell className="max-w-[320px] font-mono text-[11px] text-muted-foreground break-all">
                            {metadataPreview(row, 180)}
                          </TableCell>
                          <TableCell>
                            {href ? (
                              <Button variant="outline" size="sm" className="h-7 text-xs" asChild>
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
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Lineage timeline</CardTitle>
          <CardDescription>Edges ordered by created_at (newest first) when timestamps are present.</CardDescription>
        </CardHeader>
        <CardContent>
          {timelineEdges.length === 0 && !loading && !err ? (
            <p className="text-sm text-muted-foreground">No edges to show.</p>
          ) : (
            <ol className="relative space-y-4 border-l border-muted pl-4">
              {timelineEdges.map((e, idx) => {
                const st = edgeSourceType(e)
                const tt = edgeTargetType(e)
                const sid = edgeSourceId(e)
                const tid = edgeTargetId(e)
                const rel = readRecordString(e, "relation_type") ?? readRecordString(e, "relationType") ?? "—"
                const conf =
                  readRecordString(e, "confidence_label") ?? readRecordString(e, "confidenceLabel") ?? "—"
                const when = edgeCreatedAt(e)
                const elid = readRecordNumber(e, "evidence_link_id") ?? readRecordNumber(e, "evidenceLinkId")
                return (
                  <li key={readRecordNumber(e, "id") ?? idx} className="text-sm">
                    <div className="text-xs text-muted-foreground">{when || "—"}</div>
                    <div className="mt-1 font-mono text-[11px] leading-relaxed">
                      <span className="text-foreground">{st}</span>{" "}
                      <span className="text-muted-foreground">{sid}</span>
                      <span className="mx-1 text-muted-foreground">—</span>
                      <Badge variant="secondary" className="mx-1 align-middle text-[10px]">
                        {rel}
                      </Badge>
                      <span className="text-muted-foreground">→</span>{" "}
                      <span className="text-foreground">{tt}</span>{" "}
                      <span className="text-muted-foreground">{tid}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      confidence_label: <span className="font-mono">{conf}</span>
                      {elid != null ? (
                        <>
                          {" "}
                          · evidence_link_id: <span className="font-mono">{elid}</span>
                        </>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Edges by relation_type</CardTitle>
          <CardDescription>Grouped edge table for review; relation_type values come from the API.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {edgesByRelation.length === 0 && !loading && !err ? (
            <p className="text-sm text-muted-foreground">No edges to show.</p>
          ) : null}
          {edgesByRelation.map(([rel, relEdges], idx) => (
            <div key={rel}>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs">
                  {rel}
                </Badge>
                <span className="text-xs text-muted-foreground">{relEdges.length} edge{relEdges.length === 1 ? "" : "s"}</span>
              </div>
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[70px]">id</TableHead>
                      <TableHead>source</TableHead>
                      <TableHead>target</TableHead>
                      <TableHead>label</TableHead>
                      <TableHead>confidence_label</TableHead>
                      <TableHead>created_at</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {relEdges.map((e, i) => (
                      <TableRow key={readRecordNumber(e, "id") ?? `${rel}-${i}`}>
                        <TableCell className="font-mono text-xs">{readRecordNumber(e, "id") ?? "—"}</TableCell>
                        <TableCell className="max-w-[200px] font-mono text-[11px]">
                          {edgeSourceType(e)} {edgeSourceId(e)}
                        </TableCell>
                        <TableCell className="max-w-[200px] font-mono text-[11px]">
                          {edgeTargetType(e)} {edgeTargetId(e)}
                        </TableCell>
                        <TableCell className="text-xs">{readRecordString(e, "label") ?? "—"}</TableCell>
                        <TableCell className="text-xs">
                          {readRecordString(e, "confidence_label") ?? readRecordString(e, "confidenceLabel") ?? "—"}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">{edgeCreatedAt(e) || "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {idx < edgesByRelation.length - 1 ? <Separator className="mt-4" /> : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
