"use client"

import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  GitCompareArrows,
  Loader2,
  Sparkles,
  XCircle,
  ZapOff,
} from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import {
  useGsdMultipletAnalysis,
  type MultipletState,
} from "@/components/spectracheck/gsd-multiplet-panel"
import type { components } from "@/src/lib/api/schema"

/**
 * Multiplet J-coupling → candidate-comparison panel (Phase 26b /
 * v0.7.1). After multiplet analysis recovers observed J couplings, this
 * panel POSTs them — plus a list of candidate SMILES — to
 *   POST /candidates/compare/jcoupling
 * and renders the per-candidate J-agreement label (strong / partial /
 * weak / poor / contradiction / no_data) with matched-pair details.
 *
 * Shares the multiplet hook (and its module-level WeakMap cache) with
 * the multiplet panel, so the underlying /spectrum/analyze/multiplets
 * POST fires exactly once per gsdResult identity even though both
 * panels mount independently.
 *
 * Candidates are parsed from a free-text comma/newline-delimited list
 * (the same `candidatesText` the existing legacy `/nmr/processed/analyze`
 * consumer reads from). Empty / no-candidate state renders a friendly
 * hint rather than firing the call.
 */

type CandidateInput = components["schemas"]["CandidateInput"]
type MultipletJCouplingBridgeRequest =
  components["schemas"]["MultipletJCouplingBridgeRequest"]
type MultipletJCouplingBridgeResult =
  components["schemas"]["MultipletJCouplingBridgeResult"]
type MultipletJCouplingCandidateMatch =
  components["schemas"]["MultipletJCouplingCandidateMatch"]
type SpectrumGSDAnalyzeResult = components["schemas"]["SpectrumGSDAnalyzeResult"]
type CandidateMatchLabel = MultipletJCouplingCandidateMatch["label"]

const LABEL_STYLE: Record<
  CandidateMatchLabel,
  { display: string; chip: string; dot: string; tone: "ok" | "warn" | "bad" | "neutral" }
> = {
  strong_j_agreement: {
    display: "Strong",
    chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
    dot: "bg-emerald-500",
    tone: "ok",
  },
  partial_j_agreement: {
    display: "Partial",
    chip: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
    dot: "bg-sky-500",
    tone: "ok",
  },
  weak_j_agreement: {
    display: "Weak",
    chip: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
    dot: "bg-amber-500",
    tone: "warn",
  },
  poor_j_agreement: {
    display: "Poor",
    chip: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950/40 dark:text-orange-300 dark:border-orange-900",
    dot: "bg-orange-500",
    tone: "warn",
  },
  j_coupling_contradiction: {
    display: "Contradiction",
    chip: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
    dot: "bg-rose-500",
    tone: "bad",
  },
  no_observed_couplings: {
    display: "No observed J",
    chip: "bg-muted text-muted-foreground border-border",
    dot: "bg-muted-foreground/40",
    tone: "neutral",
  },
  no_predicted_couplings: {
    display: "No predicted J",
    chip: "bg-muted text-muted-foreground border-border",
    dot: "bg-muted-foreground/40",
    tone: "neutral",
  },
  candidate_invalid: {
    display: "Invalid SMILES",
    chip: "bg-rose-50/60 text-rose-700 border-rose-200 dark:bg-rose-950/30 dark:text-rose-300 dark:border-rose-900",
    dot: "bg-rose-400",
    tone: "bad",
  },
}

/**
 * Parse a comma/newline/semicolon-delimited SMILES list into the
 * CandidateInput shape the bridge endpoint expects.
 *
 * Accepts either:
 *   - "CC=O" (single SMILES per line / token)
 *   - "ethanol: CCO" or "ethanol\tCCO" (label + SMILES separated by
 *     ":" or tab; label is the display name)
 *
 * Skips blank lines, comment lines starting with "#", and any token
 * lacking a non-empty SMILES.
 */
export function parseCandidatesFromText(text: string): CandidateInput[] {
  if (!text) return []
  const items: CandidateInput[] = []
  for (const raw of text.split(/[\n;,]+/)) {
    const line = raw.trim()
    if (!line || line.startsWith("#")) continue
    const labelMatch = line.match(/^([^:\t]+)[:\t]\s*(.+)$/)
    if (labelMatch) {
      const name = labelMatch[1].trim()
      const smiles = labelMatch[2].trim()
      if (smiles) items.push({ name: name || null, smiles })
    } else {
      items.push({ smiles: line })
    }
  }
  return items
}

/**
 * Karplus 3D-refinement options (v0.7.2 → v0.7.5). All optional on the
 * wire (each defaulted server-side); we always send explicit values so
 * the typed request — where openapi-typescript renders defaulted fields
 * as required — type-checks. `use_karplus=false` reproduces the
 * byte-identical topological-empirical prediction; method + weighting
 * only bite when `use_karplus=true`.
 */
type KarplusMethod = MultipletJCouplingBridgeRequest["karplus_method"]
type KarplusWeighting = MultipletJCouplingBridgeRequest["karplus_conformer_weighting"]
export type KarplusOptions = {
  useKarplus: boolean
  method: KarplusMethod
  weighting: KarplusWeighting
  maxConformers: number
}
const DEFAULT_KARPLUS: KarplusOptions = {
  useKarplus: false,
  method: "generic",
  weighting: "uniform",
  maxConformers: 12,
}

// ── J-coupling bridge hook ─────────────────────────────────────────────
type JCouplingState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: MultipletJCouplingBridgeResult; error: null }
  | { status: "error"; result: null; error: string }

function useJCouplingBridge(
  multipletState: MultipletState,
  candidates: CandidateInput[],
  sampleId: string | null,
  compoundClass: string | null,
  karplus: KarplusOptions,
): JCouplingState {
  const [state, setState] = useState<JCouplingState>({
    status: "idle",
    result: null,
    error: null,
  })
  // Stable key — re-fires only when the multiplet result identity or
  // the candidate list materially changes.
  const candidatesKey = useMemo(
    () => candidates.map((c) => `${c.name ?? ""}|${c.smiles}`).join("\n"),
    [candidates],
  )
  useEffect(() => {
    if (multipletState.status !== "ready") {
      setState({ status: "idle", result: null, error: null })
      return
    }
    if (candidates.length === 0) {
      setState({ status: "idle", result: null, error: null })
      return
    }
    const observedMultiplets = multipletState.result.multiplets ?? []
    if (observedMultiplets.length === 0) {
      setState({ status: "idle", result: null, error: null })
      return
    }
    let cancelled = false
    setState({ status: "loading", result: null, error: null })
    const body: MultipletJCouplingBridgeRequest = {
      sample_id: sampleId,
      compound_class: compoundClass,
      candidates,
      observed_multiplets: observedMultiplets,
      sigma_hz: 1.6,
      contradiction_j_hz: 12.0,
      min_observed_hz: 1.0,
      // Karplus 3D refinement (v0.7.2 → v0.7.5). Sent explicitly so the
      // typed request compiles; `use_karplus=false` is the byte-identical
      // topological-empirical default.
      use_karplus: karplus.useKarplus,
      karplus_max_conformers: karplus.maxConformers,
      karplus_method: karplus.method,
      karplus_conformer_weighting: karplus.weighting,
    }
    apiFetch<MultipletJCouplingBridgeResult>("/candidates/compare/jcoupling", {
      method: "POST",
      body,
    })
      .then((result) => {
        if (cancelled) return
        setState({ status: "ready", result, error: null })
      })
      .catch((err) => {
        if (cancelled) return
        setState({
          status: "error",
          result: null,
          error: formatApiError(err, "J-coupling candidate comparison failed"),
        })
      })
    return () => {
      cancelled = true
    }
    // candidatesKey serialises the candidates list; multipletState's
    // .result identity changes per GSD run via the WeakMap cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    multipletState.status,
    multipletState.status === "ready" ? multipletState.result : null,
    candidatesKey,
    sampleId,
    compoundClass,
    karplus.useKarplus,
    karplus.method,
    karplus.weighting,
    karplus.maxConformers,
  ])
  return state
}

export type GsdJCouplingPanelProps = {
  gsdResult: SpectrumGSDAnalyzeResult | null
  /**
   * Free-text candidate list (same `candidatesText` the legacy
   * processed-analyze surface reads from). Parsed via
   * `parseCandidatesFromText`.
   */
  candidatesText: string
  /** Optional sample id forwarded to the bridge request. */
  sampleId?: string
  /** Optional compound class forwarded to the bridge request. */
  compoundClass?: string
  /** Multiplet analysis tolerance (matches the multiplet panel). */
  toleranceHz?: number
  testId?: string
}

export function GsdJCouplingPanel({
  gsdResult,
  candidatesText,
  sampleId,
  compoundClass,
  toleranceHz = 0.5,
  testId = "gsd-jcoupling-results-surface",
}: GsdJCouplingPanelProps) {
  const candidates = useMemo(() => parseCandidatesFromText(candidatesText), [candidatesText])
  const [karplus, setKarplus] = useState<KarplusOptions>(DEFAULT_KARPLUS)
  const multipletState = useGsdMultipletAnalysis(gsdResult, toleranceHz)
  const bridgeState = useJCouplingBridge(
    multipletState,
    candidates,
    sampleId?.trim() || null,
    compoundClass?.trim() || null,
    karplus,
  )

  if (gsdResult == null) return null

  // Compose the rendered status — we surface clear hints for the cases
  // where the panel is intentionally idle (no candidates, no multiplets,
  // multiplet analysis still pending) so a tenant can see what's missing
  // rather than wondering why the panel never appears.

  if (multipletState.status === "loading") {
    return (
      <PanelShell title="J-coupling vs candidates" hint="Waiting for multiplet analysis to finish before scoring candidates…" testId={`${testId}-waiting`}>
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          POST /spectrum/analyze/multiplets…
        </div>
      </PanelShell>
    )
  }
  if (multipletState.status === "error") {
    return (
      <PanelShell title="J-coupling vs candidates" hint="Multiplet analysis did not complete; J-coupling scoring is blocked." testId={`${testId}-blocked`}>
        <AlertCard variant="error" title="Multiplet input unavailable" description={multipletState.error} />
      </PanelShell>
    )
  }
  if (multipletState.status === "ready" && (multipletState.result.multiplets ?? []).length === 0) {
    return (
      <PanelShell title="J-coupling vs candidates" hint="No multiplets detected — nothing to score against candidate topologies." testId={`${testId}-empty-multiplets`}>
        <p className="text-sm text-muted-foreground">
          The multiplet pass returned zero multiplets, so observed J couplings are an empty set.
          Run GSD at a higher level (4 or 5) for finer resolution if you expect coupling structure.
        </p>
      </PanelShell>
    )
  }
  if (candidates.length === 0) {
    return (
      <PanelShell title="J-coupling vs candidates" hint="Add candidate SMILES to enable per-candidate J-agreement scoring." testId={`${testId}-no-candidates`}>
        <p className="text-sm leading-relaxed text-muted-foreground">
          The candidate list is empty. Add SMILES strings (one per line, optionally with{" "}
          <code className="font-mono text-foreground">name: SMILES</code>) in the NMR text + candidates tab
          and re-run GSD to score them against the recovered J couplings.
        </p>
      </PanelShell>
    )
  }

  if (bridgeState.status === "loading") {
    return (
      <PanelShell title="J-coupling vs candidates" hint={`Scoring ${candidates.length} candidate${candidates.length === 1 ? "" : "s"} against the observed J set…`} testId={`${testId}-loading`}>
        <KarplusControls karplus={karplus} onChange={setKarplus} busy />
        <div className="mt-4 flex items-center gap-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          POST /candidates/compare/jcoupling…
        </div>
      </PanelShell>
    )
  }
  if (bridgeState.status === "error") {
    return (
      <PanelShell title="J-coupling vs candidates" hint="Bridge endpoint returned an error." testId={`${testId}-error`}>
        <KarplusControls karplus={karplus} onChange={setKarplus} />
        <div className="mt-4">
          <AlertCard variant="error" title="J-coupling bridge failed" description={bridgeState.error} />
        </div>
      </PanelShell>
    )
  }
  if (bridgeState.status !== "ready") return null

  const result = bridgeState.result
  const matches = result.matches ?? []
  const best = result.best_match ?? null
  const anyContradiction = matches.some((m) => m.contradiction)

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Step 3d · Candidate J-agreement"
        title="Observed J couplings vs candidate topologies"
        icon={GitCompareArrows}
        description={`${result.candidate_count} candidate${result.candidate_count === 1 ? "" : "s"} scored against ${result.observed_coupling_count} observed J coupling${result.observed_coupling_count === 1 ? "" : "s"} (sigma ${result.sigma_hz} Hz · contradiction ${result.contradiction_j_hz} Hz).`}
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {/* J-prediction model controls (v0.7.2 → v0.7.5) */}
          <KarplusControls karplus={karplus} onChange={setKarplus} />

          {/* Banner row — best match + contradiction summary */}
          <div className="flex flex-wrap items-center gap-2">
            {best ? (
              <BestMatchBanner match={best} />
            ) : (
              <span className="text-xs text-muted-foreground">No candidate matched the observed set.</span>
            )}
            {anyContradiction ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                <AlertTriangle className="h-3 w-3" aria-hidden />
                {matches.filter((m) => m.contradiction).length} contradiction{matches.filter((m) => m.contradiction).length === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>

          {(result.notes ?? []).length > 0
            ? (result.notes ?? []).map((note, idx) => (
                <AlertCard
                  key={`jc-note-${idx}`}
                  variant="info"
                  title="J-coupling note"
                  description={note}
                />
              ))
            : null}

          {(result.warnings ?? []).length > 0
            ? (result.warnings ?? []).map((warning, idx) => (
                <AlertCard
                  key={`jc-warning-${idx}`}
                  variant="warning"
                  title="J-coupling warning"
                  description={warning}
                />
              ))
            : null}

          {/* Match table */}
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-right">Rank</th>
                  <th className="px-3 py-2">Candidate</th>
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2 text-right">Score</th>
                  <th className="px-3 py-2 text-right">Matched / Obs / Pred</th>
                  <th className="px-3 py-2">Matched pairs (Hz)</th>
                </tr>
              </thead>
              <tbody className="font-mono tabular-nums">
                {matches.map((m) => {
                  const style = LABEL_STYLE[m.label]
                  const pairs = m.matched_pairs ?? []
                  const obs = m.observed_j_couplings_hz ?? []
                  const pred = m.predicted_j_couplings_hz ?? []
                  return (
                    <tr key={`${m.rank}-${m.smiles}`} className="border-t align-top hover:bg-muted/20">
                      <td className="px-3 py-2 text-right">{m.rank}</td>
                      <td className="px-3 py-2">
                        <div>
                          <span className="font-semibold">{m.name ?? `Candidate ${m.rank}`}</span>
                          {m.role ? (
                            <span className="ml-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                              · {m.role}
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-0.5 max-w-[260px] truncate text-[10px] text-muted-foreground" title={m.smiles}>
                          {m.smiles}
                        </div>
                        {m.formula ? (
                          <div className="font-mono text-[10px] text-muted-foreground">{m.formula}</div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em]",
                            style.chip,
                          )}
                          title={m.label}
                        >
                          <span className={cn("h-1.5 w-1.5 rounded-full", style.dot)} aria-hidden />
                          {style.display}
                        </span>
                        {m.contradiction ? (
                          <span className="ml-2 inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-1.5 py-0 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                            <ZapOff className="h-2.5 w-2.5" aria-hidden />
                            contradiction
                          </span>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-bold", scoreColorClass(m.score))}>
                          {m.score.toFixed(2)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        {m.matched_count} / {obs.length} / {pred.length}
                      </td>
                      <td className="px-3 py-2">
                        {pairs.length === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          <div className="space-y-0.5">
                            {pairs.slice(0, 4).map((p, idx) => (
                              <div key={idx} className="font-mono text-[10px]">
                                <span className="text-foreground">
                                  {p.observed_hz.toFixed(1)} → {p.predicted_hz.toFixed(1)}
                                </span>
                                <span className="ml-2 text-muted-foreground">
                                  Δ {Math.abs(p.delta_hz).toFixed(2)} · s={p.score.toFixed(2)}
                                </span>
                              </div>
                            ))}
                            {pairs.length > 4 ? (
                              <div className="font-mono text-[10px] text-muted-foreground">
                                + {pairs.length - 4} more
                              </div>
                            ) : null}
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {result.evidence_table_text ? (
            <details className="rounded-md border bg-muted/20 p-3">
              <summary className="cursor-pointer font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Evidence table (human-readable)
              </summary>
              <pre className="mt-3 overflow-x-auto font-mono text-[10px] leading-relaxed text-foreground">
                {result.evidence_table_text}
              </pre>
            </details>
          ) : null}

          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            Decision-support only · audited as confidence.candidates.multiplet_jcoupling_bridge ·
            human review required before any regulatory release.
          </p>
        </div>
      </ModuleCard>
    </div>
  )
}

function scoreColorClass(score: number): string {
  if (score >= 0.75) return "text-emerald-600 dark:text-emerald-400"
  if (score >= 0.5) return "text-sky-600 dark:text-sky-400"
  if (score >= 0.25) return "text-amber-600 dark:text-amber-400"
  return "text-rose-600 dark:text-rose-400"
}

/**
 * J-prediction model controls — opt into Karplus 3D refinement and pick
 * the relation + conformer weighting. Default-off reproduces the
 * byte-identical topological-empirical prediction. Decision-support: the
 * tooltips spell out the measured corpus trade-offs from v0.7.4/v0.7.5
 * so a reviewer chooses deliberately, not blindly.
 */
function KarplusControls({
  karplus,
  onChange,
  busy = false,
}: {
  karplus: KarplusOptions
  onChange: (next: KarplusOptions) => void
  busy?: boolean
}) {
  const seg = (active: boolean) =>
    cn(
      "px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors disabled:cursor-wait disabled:opacity-60",
      active ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
    )
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed bg-muted/20 px-3 py-2 text-sm">
      <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        J prediction model
      </span>
      <div role="radiogroup" aria-label="J prediction model" className="inline-flex overflow-hidden rounded-md border bg-card">
        <button
          type="button"
          role="radio"
          aria-checked={!karplus.useKarplus}
          disabled={busy}
          onClick={() => onChange({ ...karplus, useKarplus: false })}
          className={seg(!karplus.useKarplus)}
          title="Topological-empirical prediction from RDKit bond topology — fast, no 3D geometry. The byte-identical default."
        >
          Topological
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={karplus.useKarplus}
          disabled={busy}
          onClick={() =>
            onChange(
              // Fresh opt-in lands on the v0.7.5 recommended combo
              // (generic + Boltzmann); re-clicking while already on
              // preserves the reviewer's current choices.
              karplus.useKarplus
                ? { ...karplus, useKarplus: true }
                : { ...karplus, useKarplus: true, method: "generic", weighting: "boltzmann" },
            )
          }
          className={cn(seg(karplus.useKarplus), "border-l")}
          title="Karplus 3D refinement — RDKit embeds a conformer ensemble (ETKDGv3 + MMFF) and reads each H–C–C–H dihedral. Sharper for conformationally locked vicinal couplings. Opt-in lands on the recommended Generic + Boltzmann combo."
        >
          Karplus 3D
        </button>
      </div>

      {karplus.useKarplus ? (
        <>
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Relation
          </span>
          <div role="radiogroup" aria-label="Karplus relation" className="inline-flex overflow-hidden rounded-md border bg-card">
            <button
              type="button"
              role="radio"
              aria-checked={karplus.method === "generic"}
              disabled={busy}
              onClick={() => onChange({ ...karplus, method: "generic" })}
              className={seg(karplus.method === "generic")}
              title="Three-term Karplus relation ³J = A·cos²θ + B·cosθ + C. Under Boltzmann weighting (v0.7.5) it discriminates locked-vs-mobile better than HLA."
            >
              Generic
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={karplus.method === "haasnoot_altona"}
              disabled={busy}
              onClick={() => onChange({ ...karplus, method: "haasnoot_altona" })}
              className={cn(seg(karplus.method === "haasnoot_altona"), "border-l")}
              title="Haasnoot–de Leeuw–Altona electronegativity/orientation-corrected generalization. More literature-faithful per individual conformer; wider dynamic range."
            >
              Haasnoot–Altona
            </button>
          </div>

          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Weighting
          </span>
          <div role="radiogroup" aria-label="Conformer weighting" className="inline-flex overflow-hidden rounded-md border bg-card">
            <button
              type="button"
              role="radio"
              aria-checked={karplus.weighting === "uniform"}
              disabled={busy}
              onClick={() => onChange({ ...karplus, weighting: "uniform" })}
              className={seg(karplus.weighting === "uniform")}
              title="Average every embedded conformer equally."
            >
              Uniform
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={karplus.weighting === "boltzmann"}
              disabled={busy}
              onClick={() => onChange({ ...karplus, weighting: "boltzmann" })}
              className={cn(seg(karplus.weighting === "boltzmann"), "border-l")}
              title="Weight each conformer by its MMFF-energy Boltzmann population at 298 K. Fixes the sugar-diaxial blind spot (v0.7.5). Recommended with the Generic relation."
            >
              Boltzmann
              {karplus.method === "generic" ? (
                <span className="ml-1 opacity-70" aria-hidden>★</span>
              ) : null}
            </button>
          </div>
          {karplus.method === "generic" && karplus.weighting === "boltzmann" ? (
            <span
              className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.12em]"
              style={{ color: "var(--mt-teal)" }}
            >
              ✓ recommended combo · slower (3D embed)
            </span>
          ) : (
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              recommended: Generic + Boltzmann · slower (3D embed)
            </span>
          )}
        </>
      ) : (
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          default · byte-identical · fast
        </span>
      )}
    </div>
  )
}

function BestMatchBanner({ match }: { match: MultipletJCouplingCandidateMatch }) {
  const style = LABEL_STYLE[match.label]
  const Icon = style.tone === "ok" ? CheckCircle2 : style.tone === "bad" ? XCircle : Sparkles
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] tabular-nums",
        style.chip,
      )}
      title={`Top-ranked candidate · ${match.label}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      <span className="font-bold uppercase tracking-[0.14em]">Best · {style.display}</span>
      <span>·</span>
      <span className="font-semibold">{match.name ?? `Candidate ${match.rank}`}</span>
      <span className="opacity-70">·</span>
      <span className="opacity-70">score {match.score.toFixed(2)}</span>
    </span>
  )
}

function PanelShell({
  title,
  hint,
  testId,
  children,
}: {
  title: string
  hint: string
  testId: string
  children: React.ReactNode
}) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Step 3d · Candidate J-agreement"
        title={title}
        icon={GitCompareArrows}
        description={hint}
        className="min-w-0 overflow-visible shadow-none"
      >
        {children}
      </ModuleCard>
    </div>
  )
}
