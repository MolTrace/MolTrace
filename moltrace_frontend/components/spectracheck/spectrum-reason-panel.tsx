"use client"

import { useMemo, useState } from "react"
import {
  BookOpenCheck,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Library,
  Loader2,
  Sparkles,
  XCircle,
} from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import type { components } from "@/src/lib/api/schema"

/**
 * Retrieval-augmented structure reasoning (`POST /spectrum/reason`, Prompt 14).
 *
 * Sends the same paired ppm_axis + intensity arrays as `/spectrum/analyze/gsd`,
 * encodes them against the server-configured FAISS similarity index, and asks
 * Anthropic Claude to propose retrieval-grounded candidate structures that the
 * Prompt 7 verifier then arbitrates. Two independent capability flags gate the
 * surface: `index_available` (FAISS index configured), `reasoner_available`
 * (ANTHROPIC_API_KEY set). With neither, the panel shows a calm "not
 * configured" state — this is a server config state, not an error.
 *
 * Score binding: candidate confidence is `posterior_confidence` + `verdict`
 * from the verifier. The model's `self_confidence` is advisory only and is
 * intentionally not presented as the candidate's score.
 */

type SpectrumReasonRequest = components["schemas"]["SpectrumReasonRequest"]
type SpectrumReasonResult = components["schemas"]["SpectrumReasonResult"]
type SpectrumReasonAnalogue = components["schemas"]["SpectrumReasonAnalogue"]
type SpectrumReasonCandidate = components["schemas"]["SpectrumReasonCandidate"]

type ReasonState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: SpectrumReasonResult; error: null }
  | { status: "error"; result: null; error: string }

const DEFAULT_TOP_K = 50
const MIN_TOP_K = 1
const MAX_TOP_K = 1000
const DEFAULT_MAX_CANDIDATES = 5
const MIN_MAX_CANDIDATES = 1
const MAX_MAX_CANDIDATES = 20

// Minimum sample count the backend will accept (matches /spectrum/analyze/gsd).
const MIN_TRACE_SAMPLES = 16

// Cap the retrieved-precedents table — the request still asks for top_k, but
// reviewers read the closest matches; 50 rows of distant precedents is noise.
const MAX_RENDERED_ANALOGUES = 25

/**
 * Verdict → badge colour. The verifier emits a free-form string; we treat
 * "consistent" as the canonical accepted verdict, "borderline" as warning,
 * anything else as muted unknown so we don't pretend to interpret novel verdicts.
 */
function verdictBadge(verdict: string | null | undefined): { label: string; chip: string } {
  if (!verdict) return { label: "—", chip: "border-border bg-muted text-muted-foreground" }
  const v = verdict.toLowerCase()
  if (v === "consistent") {
    return {
      label: "consistent",
      chip:
        "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
    }
  }
  if (v === "borderline" || v.startsWith("partial")) {
    return {
      label: verdict,
      chip:
        "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
    }
  }
  return { label: verdict, chip: "border-border bg-muted text-muted-foreground" }
}

/**
 * Compact warning surface — one card with a capped bulleted list, matching
 * spectrum-retrieve-panel. The /reason endpoint can emit several warnings per
 * call (license drops, truncation, backend-unavailable notes); stacking a card
 * per warning drowns the actual signal.
 */
function WarningList({
  warnings,
  variant,
  title,
  cap = 4,
}: {
  warnings: string[]
  variant: "info" | "warning"
  title: string
  cap?: number
}) {
  if (warnings.length === 0) return null
  const shown = warnings.slice(0, cap)
  const extra = warnings.length - shown.length
  return (
    <AlertCard variant={variant} title={`${title} · ${warnings.length}`}>
      <ul className="ml-4 list-disc space-y-0.5 text-xs text-foreground/90">
        {shown.map((w, idx) => (
          <li key={`warn-${idx}`}>{w}</li>
        ))}
        {extra > 0 ? (
          <li className="list-none text-muted-foreground">+{extra} more…</li>
        ) : null}
      </ul>
    </AlertCard>
  )
}

function AnalogueTable({ analogues }: { analogues: SpectrumReasonAnalogue[] }) {
  if (analogues.length === 0) {
    return (
      <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
        No precedents returned for this spectrum from the similarity index.
      </div>
    )
  }
  const shown = analogues.slice(0, MAX_RENDERED_ANALOGUES)
  return (
    <div className="space-y-2">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {analogues.length} precedent{analogues.length === 1 ? "" : "s"}
        {analogues.length > shown.length ? ` · showing closest ${shown.length}` : ""}
      </p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-right">Rank</th>
              <th className="px-3 py-2">Analogue ID</th>
              <th className="px-3 py-2">SMILES</th>
              <th className="px-3 py-2 text-right">Similarity</th>
              <th className="px-3 py-2">License</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {shown.map((a, idx) => (
              <tr key={`${a.analogue_id}-${idx}`} className="border-t hover:bg-muted/20">
                <td className="px-3 py-1.5 text-right text-muted-foreground">{a.rank + 1}</td>
                <td className="px-3 py-1.5 max-w-[180px] truncate" title={a.analogue_id}>
                  {a.analogue_id}
                </td>
                <td className="px-3 py-1.5 max-w-[280px] truncate" title={a.smiles}>
                  {a.smiles}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <span className="font-bold" style={{ color: "var(--mt-cyan-ink)" }}>
                    {a.similarity.toFixed(3)}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-muted-foreground">{a.license || "unknown"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CandidateRow({ candidate, rank }: { candidate: SpectrumReasonCandidate; rank: number }) {
  const badge = verdictBadge(candidate.verdict)
  const posterior = candidate.posterior_confidence
  const citedIds = candidate.cited_analogue_ids ?? []
  return (
    <div className="rounded-md border bg-card/50 p-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          #{rank + 1}
        </span>
        <code className="break-all font-mono text-xs font-bold text-foreground">
          {candidate.smiles}
        </code>
        <Badge variant="outline" className={cn("gap-1", badge.chip)}>
          <CheckCircle2 className="h-3 w-3" aria-hidden />
          {badge.label}
        </Badge>
        {posterior != null && Number.isFinite(posterior) ? (
          <span className="ml-auto font-mono text-xs tabular-nums">
            <span className="text-muted-foreground">posterior </span>
            <span className="font-bold" style={{ color: "var(--mt-cyan-ink)" }}>
              {posterior.toFixed(2)}
            </span>
          </span>
        ) : null}
      </div>
      {candidate.rationale ? (
        <p className="mt-2 text-xs leading-relaxed text-foreground/85">{candidate.rationale}</p>
      ) : null}
      {citedIds.length > 0 ? (
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          cites{" "}
          {citedIds.map((id, idx) => (
            <span key={`${id}-${idx}`}>
              {idx > 0 ? ", " : ""}
              <span className="text-foreground/70">{id}</span>
            </span>
          ))}
        </p>
      ) : (
        <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          no analogues cited
        </p>
      )}
    </div>
  )
}

function RejectedRow({ candidate }: { candidate: SpectrumReasonCandidate }) {
  const reason = candidate.dropped_reason ?? candidate.verdict ?? "rejected"
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed bg-muted/10 px-3 py-2">
      <XCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
      <code className="break-all font-mono text-[11px] text-foreground/80">{candidate.smiles}</code>
      <Badge variant="outline" className="border-border bg-muted text-[10px] text-muted-foreground">
        {reason}
      </Badge>
    </div>
  )
}

export type SpectrumReasonPanelProps = {
  /** Paired ppm + intensity from the displayed processed spectrum. */
  trace: { x: number[]; y: number[] } | null
  nucleus: "1H" | "13C"
  solvent: string
  fieldMhz: number
  testId?: string
}

export function SpectrumReasonPanel({
  trace,
  nucleus,
  solvent,
  fieldMhz,
  testId = "spectrum-reason-surface",
}: SpectrumReasonPanelProps) {
  const [topK, setTopK] = useState<number>(DEFAULT_TOP_K)
  const [maxCandidates, setMaxCandidates] = useState<number>(DEFAULT_MAX_CANDIDATES)
  const [state, setState] = useState<ReasonState>({ status: "idle", result: null, error: null })
  const [rejectedOpen, setRejectedOpen] = useState(false)

  const clampedTopK = Math.max(MIN_TOP_K, Math.min(MAX_TOP_K, Math.round(topK || DEFAULT_TOP_K)))
  const clampedMaxCandidates = Math.max(
    MIN_MAX_CANDIDATES,
    Math.min(MAX_MAX_CANDIDATES, Math.round(maxCandidates || DEFAULT_MAX_CANDIDATES)),
  )

  const hasTrace = trace != null && trace.x.length >= MIN_TRACE_SAMPLES
  const traceTooShort = trace != null && trace.x.length > 0 && trace.x.length < MIN_TRACE_SAMPLES

  const resetResult = () => setState({ status: "idle", result: null, error: null })

  const runReason = () => {
    if (!hasTrace || !trace) return
    setState({ status: "loading", result: null, error: null })
    const body: SpectrumReasonRequest = {
      ppm_axis: trace.x,
      intensity: trace.y,
      nucleus,
      solvent: solvent.trim(),
      field_mhz: fieldMhz,
      top_k: clampedTopK,
      max_candidates: clampedMaxCandidates,
      allowed_licenses: null,
    }
    apiFetch<SpectrumReasonResult>("/spectrum/reason", { method: "POST", body })
      .then((result) => setState({ status: "ready", result, error: null }))
      .catch((err) =>
        setState({
          status: "error",
          result: null,
          error: formatApiError(err, "Retrieval-augmented reasoning failed"),
        }),
      )
  }

  const result = state.status === "ready" ? state.result : null
  const retrieved = result?.retrieved ?? []
  const candidates = useMemo(() => {
    const list = [...(result?.candidates ?? [])]
    // Backend ranks by posterior desc; defensive sort keeps the rank column honest.
    list.sort((a, b) => (b.posterior_confidence ?? -Infinity) - (a.posterior_confidence ?? -Infinity))
    return list
  }, [result])
  const rejected = result?.rejected ?? []
  const warnings = result?.warnings ?? []
  const audit = result?.audit ?? null

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <label className="inline-flex items-center gap-1.5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Top K
        </span>
        <Input
          type="number"
          inputMode="numeric"
          min={MIN_TOP_K}
          max={MAX_TOP_K}
          step={1}
          aria-label="Number of precedents to retrieve (1–1000)"
          value={topK}
          onChange={(e) => {
            const v = Number.parseInt(e.target.value, 10)
            setTopK(Number.isFinite(v) ? v : DEFAULT_TOP_K)
            resetResult()
          }}
          className="h-8 w-20 font-mono text-xs"
          title="Number of precedent analogues to retrieve before reasoning (1–1000)."
        />
      </label>

      <label className="ml-2 inline-flex items-center gap-1.5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Max candidates
        </span>
        <Input
          type="number"
          inputMode="numeric"
          min={MIN_MAX_CANDIDATES}
          max={MAX_MAX_CANDIDATES}
          step={1}
          aria-label="Maximum candidate structures the reasoner may propose (1–20)"
          value={maxCandidates}
          onChange={(e) => {
            const v = Number.parseInt(e.target.value, 10)
            setMaxCandidates(Number.isFinite(v) ? v : DEFAULT_MAX_CANDIDATES)
            resetResult()
          }}
          className="h-8 w-16 font-mono text-xs"
          title="Upper bound on the number of structures the reasoner proposes (1–20)."
        />
      </label>

      <Button
        type="button"
        size="sm"
        className="ml-2 gap-1.5"
        onClick={runReason}
        disabled={!hasTrace || state.status === "loading"}
      >
        {state.status === "loading" ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Reasoning…
          </>
        ) : (
          <>
            <Brain className="h-3.5 w-3.5" aria-hidden />
            Reason over precedent
          </>
        )}
      </Button>
    </div>
  )

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="cyan"
        eyebrow="Decision-support · Retrieval-augmented reasoning"
        title="Retrieval-augmented structure reasoning"
        icon={Brain}
        description="Encodes the displayed spectrum, retrieves precedent analogues from the server-configured similarity index, then asks the reasoning backend to propose retrieval-grounded structures. Every proposal is verifier-arbitrated against the observed spectrum — decision-support, never a standalone assignment."
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {controls}

          {!hasTrace ? (
            <p className="text-sm text-muted-foreground">
              {traceTooShort
                ? `The displayed trace has ${trace?.x.length ?? 0} samples — at least ${MIN_TRACE_SAMPLES} are required.`
                : "Load a processed spectrum to reason over precedent."}
            </p>
          ) : null}

          {state.status === "error" ? (
            <AlertCard variant="error" title="Retrieval-augmented reasoning failed" description={state.error} />
          ) : null}

          {state.status === "idle" && hasTrace ? (
            <p className="text-sm text-muted-foreground">
              Run the reasoner to retrieve precedent analogues and propose verifier-arbitrated candidate
              structures. The verifier scores each proposal against the displayed spectrum; only
              consistent candidates surface in the accepted list.
            </p>
          ) : null}

          {result ? (
            result.index_available === false ? (
              <div className="space-y-3">
                <div className="flex flex-col items-center gap-2 rounded-md border border-dashed bg-muted/20 px-4 py-8 text-center">
                  <Library className="h-6 w-6 text-muted-foreground" aria-hidden />
                  <p className="text-sm font-medium text-foreground">Reasoning not available</p>
                  <p className="max-w-md text-xs text-muted-foreground">
                    This deployment has no spectral similarity index configured, so retrieval-augmented
                    reasoning has no precedents to ground on. An administrator can configure one
                    server-side (<code className="font-mono">MOLTRACE_SIMILARITY_INDEX</code>) to turn
                    this surface on.
                  </p>
                </div>
                <WarningList warnings={warnings} variant="info" title="Notes" />
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant="outline"
                    className="gap-1 border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-900 dark:bg-cyan-950/40 dark:text-cyan-300"
                    title={`similarity index size: ${result.index_size}`}
                  >
                    <BookOpenCheck className="h-3 w-3" aria-hidden />
                    Index · {result.index_size.toLocaleString()} entries
                  </Badge>
                  {result.reasoner_available ? (
                    <Badge
                      variant="outline"
                      className="gap-1 border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300"
                      title={audit?.model ? `model: ${audit.model}` : "reasoning backend available"}
                    >
                      <Sparkles className="h-3 w-3" aria-hidden />
                      Reasoner · {audit?.model ?? "available"}
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="gap-1 border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
                      title="ANTHROPIC_API_KEY not configured server-side"
                    >
                      <CircleSlash className="h-3 w-3" aria-hidden />
                      Reasoner unavailable
                    </Badge>
                  )}
                  <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                    nucleus {result.query_nucleus === "1H" ? "¹H" : "¹³C"} · top {result.top_k} · max{" "}
                    {result.max_candidates} candidate{result.max_candidates === 1 ? "" : "s"}
                    {result.truncated ? " · context truncated" : ""}
                  </span>
                </div>

                <WarningList warnings={warnings} variant="warning" title="Reasoning warnings" />

                <div className="space-y-2">
                  <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Retrieved precedents
                  </p>
                  <AnalogueTable analogues={retrieved} />
                </div>

                <div className="space-y-2">
                  <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Candidates {candidates.length > 0 ? `· ${candidates.length} accepted` : ""}
                  </p>
                  {result.reasoner_available === false ? (
                    <div className="rounded-md border border-dashed bg-muted/10 px-4 py-6 text-center text-sm text-muted-foreground">
                      Retrieval succeeded, but the reasoning backend is not configured on this
                      deployment. Set <code className="font-mono">ANTHROPIC_API_KEY</code> server-side to
                      enable structure proposals.
                    </div>
                  ) : candidates.length === 0 ? (
                    <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                      No candidate structure passed the verifier for this spectrum.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {candidates.map((c, idx) => (
                        <CandidateRow key={`cand-${idx}-${c.smiles}`} candidate={c} rank={idx} />
                      ))}
                    </div>
                  )}
                </div>

                {rejected.length > 0 ? (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => setRejectedOpen((v) => !v)}
                      className="inline-flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground hover:text-foreground"
                      aria-expanded={rejectedOpen}
                    >
                      {rejectedOpen ? (
                        <ChevronDown className="h-3 w-3" aria-hidden />
                      ) : (
                        <ChevronRight className="h-3 w-3" aria-hidden />
                      )}
                      Dropped · {rejected.length}
                    </button>
                    {rejectedOpen ? (
                      <div className="space-y-1.5">
                        {rejected.map((c, idx) => (
                          <RejectedRow key={`rej-${idx}-${c.smiles}`} candidate={c} />
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {audit ? (
                  <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    Audit · {audit.parsed_candidate_count} parsed · {audit.dropped_candidate_count} dropped ·{" "}
                    {audit.accepted_candidate_count} accepted
                    {audit.retry_used ? " · retry used" : ""}
                    {audit.retrieved_ids && audit.retrieved_ids.length > 0
                      ? ` · ${audit.retrieved_ids.length} analogues cited`
                      : ""}
                  </p>
                ) : null}

                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  Decision-support · candidate score = posterior_confidence × verdict (verifier);
                  self_confidence is advisory only.
                </p>
              </>
            )
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
