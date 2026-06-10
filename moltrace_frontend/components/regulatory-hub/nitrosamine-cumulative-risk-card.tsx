"use client"

import { useState } from "react"
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, CircleDashed } from "lucide-react"
import { Badge } from "@/components/ui/badge"
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
import type { components } from "@/src/lib/api/schema"

/**
 * Dossier-level nitrosamine cumulative-risk rollup card.
 *
 * The dossier companion to the per-call cumulative risk in the Impurity
 * Assessment panel: it rolls every qualifying nitrosamine watch on the
 * dossier into one FDA-Rev-2 verdict — sum(measured / AI limit) must be < 1.
 *
 * Three distinct states (per the v0.23.5 handoff §4b):
 *   - empty / nothing-qualifying (n_components === 0) → a MUTED "not yet
 *     assessed" state, NOT a green pass (ratio is 0 only because nothing
 *     qualified, not because the dossier cleared the gate).
 *   - included components, ratio < 1 → green "within cumulative limit".
 *   - ratio ≥ 1 → red "exceeds cumulative limit".
 *
 * `excluded` watches (no measured ng/day, or a non-nitrosamine structure)
 * are surfaced — never silently dropped — so a reviewer sees exactly what
 * is and isn't counted. Decision-support only; `disclaimer` and
 * `human_review_required` are always surfaced.
 */

export type NitrosamineCumulativeRisk = components["schemas"]["DossierNitrosamineCumulativeRisk"]

function num(value: number | null | undefined, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "—"
  return value.toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function NitrosamineCumulativeRiskCard({
  data,
  testId = "nitrosamine-cumulative-risk-card",
}: {
  data: NitrosamineCumulativeRisk | null
  testId?: string
}) {
  const [excludedOpen, setExcludedOpen] = useState(false)

  // best-effort fetch upstream: null = unavailable (e.g. transient error / 404).
  if (!data) {
    return (
      <div
        data-testid={`${testId}-unavailable`}
        className="rounded-md border border-dashed bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
      >
        Cumulative-risk rollup unavailable.
      </div>
    )
  }

  const components_ = data.components ?? []
  const excluded = data.excluded ?? []
  const notes = data.notes ?? []
  const isEmpty = data.n_components === 0
  const passes = data.passes === true

  // Headline state — empty is neutral, NOT a green pass.
  const verdict = isEmpty
    ? {
        ratioClass: "text-muted-foreground",
        badge: (
          <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
            <CircleDashed className="h-3 w-3" aria-hidden />
            not yet assessed
          </Badge>
        ),
      }
    : passes
      ? {
          ratioClass: "text-success",
          badge: (
            <Badge variant="outline" className="gap-1 border-success/50 font-normal text-success">
              <CheckCircle2 className="h-3 w-3" aria-hidden />
              within cumulative limit
            </Badge>
          ),
        }
      : {
          ratioClass: "text-destructive",
          badge: (
            <Badge variant="outline" className="gap-1 border-destructive/50 font-normal text-destructive">
              <AlertTriangle className="h-3 w-3" aria-hidden />
              exceeds cumulative limit
            </Badge>
          ),
        }

  return (
    <div
      data-testid={testId}
      className="space-y-3 rounded-md border bg-card p-4"
      style={{ borderTop: "3px solid var(--mt-cyan)" }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          Cumulative nitrosamine risk · must be &lt; 1
          {data.regulatory_basis ? <InfoTooltip content={data.regulatory_basis} label="Regulatory basis" /> : null}
        </p>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {data.n_components} included · {data.n_excluded} excluded
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <p className={cn("font-mono text-3xl font-bold tabular-nums", verdict.ratioClass)}>
          {num(data.total_risk_ratio)}
        </p>
        {verdict.badge}
        {isEmpty ? (
          <span className="max-w-md text-xs text-muted-foreground">
            No nitrosamine watch on this dossier carries both a CPCA AI limit and a measured ng/day — cumulative risk is
            0 by default, not a cleared gate.
          </span>
        ) : null}
      </div>

      {/* Per-component contributions */}
      {components_.length > 0 ? (
        <div className="table-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>structure</TableHead>
                <TableHead className="text-right">CPCA cat.</TableHead>
                <TableHead className="text-right">AI limit (ng/day)</TableHead>
                <TableHead className="text-right">measured (ng/day)</TableHead>
                <TableHead className="text-right">risk ratio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {components_.map((c, i) => (
                <TableRow key={`${c.assessment_id}-${i}`}>
                  <TableCell className="max-w-[16rem] truncate font-mono text-xs" title={c.structure_text ?? undefined}>
                    {c.structure_text ?? "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{c.category}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(c.ai_limit_ng_per_day, 2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(c.measured_ng_per_day, 2)}</TableCell>
                  <TableCell className="text-right font-medium tabular-nums">{num(c.risk_ratio)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}

      {/* Excluded watches — never silently dropped */}
      {excluded.length > 0 ? (
        <div className="space-y-1.5">
          <button
            type="button"
            onClick={() => setExcludedOpen((v) => !v)}
            aria-expanded={excludedOpen}
            className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground"
          >
            {excludedOpen ? <ChevronDown className="h-3 w-3" aria-hidden /> : <ChevronRight className="h-3 w-3" aria-hidden />}
            Excluded · {excluded.length}
          </button>
          {excludedOpen ? (
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-muted-foreground">
              {excluded.map((e, i) => (
                <li key={`${e.assessment_id}-${i}`}>
                  <span className="font-mono">#{e.assessment_id}</span> — {e.reason}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {notes.length > 0 ? (
        <ul className="ml-4 list-disc space-y-0.5 text-[11px] text-muted-foreground">
          {notes.map((n, i) => (
            <li key={`note-${i}`}>{n}</li>
          ))}
        </ul>
      ) : null}

      {/* Decision-support posture — always surfaced */}
      <p className="flex items-start gap-1.5 border-t pt-2 text-[11px] text-muted-foreground">
        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warning" aria-hidden />
        <span>
          {data.disclaimer}
          {data.human_review_required ? " Requires qualified review before any regulatory use." : ""}
        </span>
      </p>
    </div>
  )
}
