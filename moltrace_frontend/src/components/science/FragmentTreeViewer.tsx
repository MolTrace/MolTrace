"use client"

import React, { useMemo } from "react"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import { Layers } from "lucide-react"

export type FragmentTreeNode = {
  id: string
  mz?: number
  label?: string
  intensity?: number
  status?: string
}

export type FragmentTreeEdge = {
  source: string
  target: string
  loss?: string
  delta_mz?: number
  supported?: boolean
  contradiction?: boolean
}

export type FragmentTreeViewerProps = {
  nodes: FragmentTreeNode[]
  edges: FragmentTreeEdge[]
  title?: string
  className?: string
}

const NODE_W = 92
const NODE_H = 46
const LAYER_V_GAP = 56
const NODE_H_GAP = 14
const PAD = 24

function formatMz(v: number | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—"
  return v.toFixed(4)
}

function maxIntensity(nodes: FragmentTreeNode[]): number {
  let m = 0
  for (const n of nodes) {
    const v = n.intensity
    if (typeof v === "number" && Number.isFinite(v) && v > m) m = v
  }
  return m > 0 ? m : 1
}

function edgeLabel(e: FragmentTreeEdge): string {
  const parts: string[] = []
  if (e.loss != null && String(e.loss).trim() !== "") parts.push(String(e.loss))
  if (typeof e.delta_mz === "number" && Number.isFinite(e.delta_mz)) {
    parts.push(`Δm/z ${e.delta_mz.toFixed(4)}`)
  }
  return parts.length > 0 ? parts.join(" · ") : "loss"
}

type LayoutEdge = FragmentTreeEdge & { sourceId: string; targetId: string }

/** Layered positions: precursor layer at top (minimal depth from roots). */
function computeLayout(
  nodes: FragmentTreeNode[],
  edges: LayoutEdge[]
): {
  positions: Map<string, { x: number; y: number }>
  width: number
  height: number
  warnings: string[]
} {
  const warnings: string[] = []
  const incoming = new Map<string, number>()
  const outgoing = new Map<string, string[]>()

  for (const n of nodes) {
    incoming.set(n.id, 0)
    outgoing.set(n.id, [])
  }

  for (const e of edges) {
    outgoing.get(e.source)?.push(e.target)
    incoming.set(e.target, (incoming.get(e.target) ?? 0) + 1)
  }

  let roots = nodes.filter((n) => (incoming.get(n.id) ?? 0) === 0)

  if (roots.length === 0 && nodes.length > 0) {
    const byMz = [...nodes].sort((a, b) => {
      const ma = typeof a.mz === "number" && Number.isFinite(a.mz) ? a.mz : -Infinity
      const mb = typeof b.mz === "number" && Number.isFinite(b.mz) ? b.mz : -Infinity
      return mb - ma
    })
    roots = [byMz[0]!]
    warnings.push(
      "No unique precursor root was found from edges; the highest m/z node was placed at the top for layout (review connectivity)."
    )
  }

  const depth = new Map<string, number>()
  const queue: { id: string; d: number }[] = []

  for (const r of roots) {
    depth.set(r.id, 0)
    queue.push({ id: r.id, d: 0 })
  }

  while (queue.length > 0) {
    const { id, d } = queue.shift()!
    for (const t of outgoing.get(id) ?? []) {
      const nd = d + 1
      const prev = depth.get(t)
      if (prev == null || nd < prev) {
        depth.set(t, nd)
        queue.push({ id: t, d: nd })
      }
    }
  }

  const maxD = nodes.reduce((m, n) => Math.max(m, depth.get(n.id) ?? 0), 0)

  for (const n of nodes) {
    if (!depth.has(n.id)) {
      depth.set(n.id, maxD + 1)
      warnings.push(
        `Node "${n.id}" is not connected by edges to the precursor subtree; it was placed on an extra row for visibility (review graph consistency).`
      )
    }
  }

  const layers = new Map<number, FragmentTreeNode[]>()
  for (const n of nodes) {
    const d = depth.get(n.id) ?? 0
    const row = layers.get(d) ?? []
    row.push(n)
    layers.set(d, row)
  }

  for (const [, row] of layers) {
    row.sort((a, b) => {
      const ma = typeof a.mz === "number" && Number.isFinite(a.mz) ? a.mz : -Infinity
      const mb = typeof b.mz === "number" && Number.isFinite(b.mz) ? b.mz : -Infinity
      if (mb !== ma) return mb - ma
      return a.id.localeCompare(b.id)
    })
  }

  const sortedDepths = [...layers.keys()].sort((a, b) => a - b)
  let totalW = 0
  const layerWidths: number[] = []

  for (const d of sortedDepths) {
    const row = layers.get(d) ?? []
    const w = row.length * NODE_W + Math.max(0, row.length - 1) * NODE_H_GAP
    layerWidths.push(w)
    totalW = Math.max(totalW, w)
  }

  const width = Math.max(totalW + PAD * 2, 320)
  const positions = new Map<string, { x: number; y: number }>()

  sortedDepths.forEach((d, li) => {
    const row = layers.get(d) ?? []
    const lw = row.length * NODE_W + Math.max(0, row.length - 1) * NODE_H_GAP
    const startX = (width - lw) / 2
    const y = PAD + li * (NODE_H + LAYER_V_GAP)

    row.forEach((n, i) => {
      positions.set(n.id, { x: startX + i * (NODE_W + NODE_H_GAP), y })
    })
  })

  const height =
    PAD * 2 + sortedDepths.length * NODE_H + Math.max(0, sortedDepths.length - 1) * LAYER_V_GAP

  return { positions, width, height, warnings }
}

export function FragmentTreeViewer({ nodes, edges, title, className }: FragmentTreeViewerProps) {
  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])

  const { validEdges, skippedEdges, structuralWarnings } = useMemo(() => {
    const valid: LayoutEdge[] = []
    const skipped: FragmentTreeEdge[] = []
    const sw: string[] = []

    for (const e of edges) {
      const hasS = nodeById.has(e.source)
      const hasT = nodeById.has(e.target)
      if (!hasS || !hasT) {
        skipped.push(e)
        if (!hasS && !hasT) {
          sw.push(`Edge omitted: unknown source "${e.source}" and unknown target "${e.target}".`)
        } else if (!hasS) {
          sw.push(`Edge omitted: unknown source "${e.source}".`)
        } else {
          sw.push(`Edge omitted: unknown target "${e.target}".`)
        }
        continue
      }
      valid.push({ ...e, sourceId: e.source, targetId: e.target })
    }

    return { validEdges: valid, skippedEdges: skipped, structuralWarnings: sw }
  }, [edges, nodeById])

  const layout = useMemo(
    () => computeLayout(nodes, validEdges),
    [nodes, validEdges]
  )

  const allWarnings = useMemo(
    () => [...structuralWarnings, ...layout.warnings],
    [structuralWarnings, layout.warnings]
  )

  const intensityMax = useMemo(() => maxIntensity(nodes), [nodes])

  const diagnosticRows = useMemo(() => {
    return [...nodes].sort((a, b) => {
      const ia = typeof a.intensity === "number" && Number.isFinite(a.intensity) ? a.intensity : 0
      const ib = typeof b.intensity === "number" && Number.isFinite(b.intensity) ? b.intensity : 0
      return ib - ia
    })
  }, [nodes])

  if (nodes.length === 0) {
    return (
      <div
        className={cn(
          "flex min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 p-8 text-center text-sm text-muted-foreground",
          className
        )}
        data-testid="fragment-tree-viewer-root"
      >
        <Layers className="mb-2 h-8 w-8 opacity-40" aria-hidden />
        <p className="font-medium text-foreground">No fragmentation tree data available yet.</p>
      </div>
    )
  }

  return (
    <div
      className={cn("flex min-w-0 max-w-full flex-col gap-4 overflow-x-hidden", className)}
      data-testid="fragment-tree-viewer-root"
      aria-label="MS/MS fragmentation tree viewer"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          {title ? <p className="text-sm font-medium text-foreground">{title}</p> : null}
          <p className="text-xs text-muted-foreground">
            Trees summarize precursor-to-fragment relationships for evidence review; they do not
            confirm compound identity on their own.
          </p>
        </div>
        <InfoTooltip content="Fragmentation trees show precursor-to-fragment relationships and diagnostic neutral losses. They are supporting evidence and require review." />
      </div>

      <div className="w-full min-w-0 overflow-x-auto rounded-lg border bg-card p-3">
        <svg
          width="100%"
          height={layout.height}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          preserveAspectRatio="xMidYMin meet"
          role="img"
          aria-label="Fragmentation tree diagram"
        >
          <title>Fragmentation tree diagram</title>

          {validEdges.map((e, i) => {
            const pa = layout.positions.get(e.source)
            const pb = layout.positions.get(e.target)
            if (!pa || !pb) return null

            const x1 = pa.x + NODE_W / 2
            const y1 = pa.y + NODE_H
            const x2 = pb.x + NODE_W / 2
            const y2 = pb.y

            const mx = (x1 + x2) / 2
            const my = (y1 + y2) / 2
            const contradict = Boolean(e.contradiction)

            return (
              <g key={`${e.source}-${e.target}-${i}`} data-contradiction={contradict ? "1" : "0"}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  fill="none"
                  stroke={contradict ? "#dc2626" : e.supported === true ? "#15803d" : "#64748b"}
                  strokeWidth={contradict ? 2.25 : 1.25}
                  strokeDasharray={contradict ? "6 4" : e.supported === true ? undefined : "4 3"}
                  strokeLinecap="round"
                />
                <rect
                  x={mx - 56}
                  y={my - 9}
                  width={112}
                  height={18}
                  rx={4}
                  fill="hsl(var(--card))"
                  stroke="hsl(var(--border))"
                  className="opacity-95"
                />
                <text
                  x={mx}
                  y={my + 4}
                  textAnchor="middle"
                  className="fill-foreground text-[9px] font-medium"
                  style={{ fontFamily: "inherit" }}
                >
                  {edgeLabel(e)}
                </text>
              </g>
            )
          })}

          {nodes.map((n) => {
            const p = layout.positions.get(n.id)
            if (!p) return null
            return (
              <g key={n.id} data-node-id={n.id}>
                <rect
                  x={p.x}
                  y={p.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={6}
                  fill="hsl(var(--muted))"
                  stroke="hsl(var(--border))"
                  strokeWidth={1}
                />
                <text
                  x={p.x + NODE_W / 2}
                  y={p.y + 18}
                  textAnchor="middle"
                  className="fill-foreground text-[10px] font-semibold"
                  style={{ fontFamily: "inherit" }}
                >
                  {n.label != null && String(n.label).trim() !== ""
                    ? String(n.label).slice(0, 12)
                    : n.id.slice(0, 10)}
                </text>
                <text
                  x={p.x + NODE_W / 2}
                  y={p.y + 34}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[9px] font-mono"
                  style={{ fontFamily: "inherit" }}
                >
                  {formatMz(n.mz)}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">Diagnostic fragment hits</p>
        <p className="text-xs text-muted-foreground">
          Relative intensity is for ranking within this spectrum only (supporting review, not
          identification).
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>m/z</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Rel. intensity</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {diagnosticRows.map((n) => {
              const rel =
                typeof n.intensity === "number" && Number.isFinite(n.intensity)
                  ? `${((n.intensity / intensityMax) * 100).toFixed(1)}%`
                  : "—"
              return (
                <TableRow key={n.id}>
                  <TableCell className="font-mono text-xs">{formatMz(n.mz)}</TableCell>
                  <TableCell className="max-w-[140px] truncate text-xs">{n.label ?? "—"}</TableCell>
                  <TableCell className="text-xs">{rel}</TableCell>
                  <TableCell className="max-w-[180px] truncate text-xs" title={n.status}>
                    {n.status ?? "—"}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {(skippedEdges.length > 0 || allWarnings.length > 0) && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Warnings</p>
          <ul className="list-disc space-y-1 pl-5 text-xs text-amber-900 dark:text-amber-200">
            {allWarnings.map((w, i) => (
              <li key={`w-${i}`}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
