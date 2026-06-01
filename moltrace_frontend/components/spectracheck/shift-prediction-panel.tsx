"use client"

import { useEffect, useMemo, useState } from "react"
import { Atom, Cpu, FlaskConical, Loader2, Sparkles, Waves } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { parseCandidatesFromText } from "@/components/spectracheck/gsd-jcoupling-panel"
import type { components } from "@/src/lib/api/schema"

/**
 * Per-atom chemical-shift prediction (v0.7.8 / `POST /spectrum/predict/shifts`).
 *
 * Distinct from the GSD observed-spectrum chain (Steps 3b–3e): this is a
 * STRUCTURE-derived tool — SMILES in, predicted ¹H/¹³C shifts out. The
 * active backend is server-configured (NMRNet GPU service when wired,
 * else the HOSE-code / NMRShiftDB2 fallback); the response names which
 * one ran, surfaced here as a badge.
 *
 * Button-triggered (not auto-fired) per the handoff — prediction is a
 * deliberate action on a chosen candidate, and the GPU path can be
 * non-trivial. Candidates are parsed from the same `candidatesText` the
 * J-coupling panel reads.
 */

type SpectrumPredictShiftsRequest = components["schemas"]["SpectrumPredictShiftsRequest"]
type SpectrumPredictShiftsResult = components["schemas"]["SpectrumPredictShiftsResult"]
type AtomShiftPredictionOut = components["schemas"]["AtomShiftPredictionOut"]
type Nucleus = "1H" | "13C"

type PredictState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: SpectrumPredictShiftsResult; error: null }
  | { status: "error"; result: null; error: string }

const NUCLEI_OPTIONS: { value: Nucleus[]; label: string }[] = [
  { value: ["1H", "13C"], label: "¹H + ¹³C" },
  { value: ["1H"], label: "¹H" },
  { value: ["13C"], label: "¹³C" },
]

/** Backend display: HOSE fallback (amber) vs NMRNet ML (teal) vs unknown. */
function backendBadge(backend: string): { label: string; chip: string } {
  if (backend === "nmrnet") {
    return {
      label: "NMRNet (ML)",
      chip: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
    }
  }
  if (backend === "hose_nmrshiftdb2") {
    return {
      label: "HOSE · NMRShiftDB2",
      chip: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
    }
  }
  return { label: backend, chip: "border-border bg-muted text-muted-foreground" }
}

/** Read provenance.hose_sphere (0–6) if present; null otherwise. */
function hoseSphere(p: AtomShiftPredictionOut["provenance"]): number | null {
  if (!p || typeof p !== "object") return null
  const v = (p as Record<string, unknown>).hose_sphere
  return typeof v === "number" && Number.isFinite(v) ? v : null
}

/**
 * HOSE-sphere confidence cue — a 6-segment bar (6 = exact environment
 * match … 0 = element prior). Filled segments tinted by depth; only
 * shown for the fallback backend where the field exists.
 */
function HoseSphereCue({ sphere }: { sphere: number }) {
  const filled = Math.max(0, Math.min(6, sphere))
  const tone =
    sphere >= 5
      ? "bg-emerald-500"
      : sphere >= 3
        ? "bg-sky-500"
        : sphere >= 1
          ? "bg-amber-500"
          : "bg-rose-500"
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={`HOSE sphere ${sphere}/6 — ${
        sphere >= 6
          ? "exact environment match"
          : sphere === 0
            ? "element prior only (weakest)"
            : `${sphere}-sphere environment match`
      }`}
    >
      <span className="inline-flex gap-0.5" aria-hidden>
        {Array.from({ length: 6 }, (_, i) => (
          <span
            key={i}
            className={cn("h-2.5 w-1 rounded-[1px]", i < filled ? tone : "bg-muted")}
          />
        ))}
      </span>
      <span className="font-mono text-[10px] tabular-nums text-muted-foreground">S{sphere}</span>
    </span>
  )
}

function NucleusGroup({
  nucleus,
  shifts,
  showHose,
}: {
  nucleus: Nucleus
  shifts: AtomShiftPredictionOut[]
  showHose: boolean
}) {
  if (shifts.length === 0) return null
  const label = nucleus === "1H" ? "¹H" : "¹³C"
  return (
    <div className="space-y-2">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {label} · {shifts.length} atom{shifts.length === 1 ? "" : "s"}
      </p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-right">Atom #</th>
              <th className="px-3 py-2">Elem</th>
              <th className="px-3 py-2 text-right">δ predicted (ppm)</th>
              <th className="px-3 py-2 text-right">± uncertainty</th>
              <th className="px-3 py-2">Method</th>
              {showHose ? <th className="px-3 py-2">Confidence (HOSE)</th> : null}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {shifts.map((s, idx) => {
              const sphere = hoseSphere(s.provenance)
              return (
                <tr key={`${s.atom_index}-${idx}`} className="border-t hover:bg-muted/20">
                  <td className="px-3 py-1.5 text-right">{s.atom_index}</td>
                  <td className="px-3 py-1.5">{s.element}</td>
                  <td className="px-3 py-1.5 text-right">
                    <span className="font-bold" style={{ color: "var(--mt-teal)" }}>
                      {s.predicted_ppm.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right text-muted-foreground">
                    ± {s.uncertainty_ppm.toFixed(2)}
                  </td>
                  <td className="px-3 py-1.5">
                    <span className="text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
                      {s.method}
                    </span>
                  </td>
                  {showHose ? (
                    <td className="px-3 py-1.5">
                      {sphere != null ? <HoseSphereCue sphere={sphere} /> : <span className="text-muted-foreground">—</span>}
                    </td>
                  ) : null}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export type ShiftPredictionPanelProps = {
  /** Candidate list (same free-text field the J-coupling panel reads). */
  candidatesText: string
  testId?: string
}

export function ShiftPredictionPanel({
  candidatesText,
  testId = "shift-prediction-surface",
}: ShiftPredictionPanelProps) {
  const candidates = useMemo(() => parseCandidatesFromText(candidatesText), [candidatesText])
  const [selectedSmiles, setSelectedSmiles] = useState<string>("")
  const [nucleiIdx, setNucleiIdx] = useState(0)
  const [state, setState] = useState<PredictState>({ status: "idle", result: null, error: null })

  // Keep the selected SMILES valid as the candidate list changes; reset
  // any stale result when the selection or candidate set shifts.
  useEffect(() => {
    const smilesList = candidates.map((c) => c.smiles)
    if (smilesList.length === 0) {
      setSelectedSmiles("")
      return
    }
    if (!smilesList.includes(selectedSmiles)) {
      setSelectedSmiles(smilesList[0])
      setState({ status: "idle", result: null, error: null })
    }
  }, [candidates, selectedSmiles])

  if (candidates.length === 0) return null

  const selectedCandidate = candidates.find((c) => c.smiles === selectedSmiles) ?? candidates[0]
  const nuclei = NUCLEI_OPTIONS[nucleiIdx].value

  const runPrediction = () => {
    const smiles = selectedCandidate?.smiles?.trim()
    if (!smiles) return
    setState({ status: "loading", result: null, error: null })
    const body: SpectrumPredictShiftsRequest = { smiles, nuclei }
    apiFetch<SpectrumPredictShiftsResult>("/spectrum/predict/shifts", { method: "POST", body })
      .then((result) => setState({ status: "ready", result, error: null }))
      .catch((err) =>
        setState({ status: "error", result: null, error: formatApiError(err, "Shift prediction failed") }),
      )
  }

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      {candidates.length > 1 ? (
        <>
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Candidate
          </span>
          <select
            aria-label="Candidate to predict shifts for"
            value={selectedSmiles}
            onChange={(e) => {
              setSelectedSmiles(e.target.value)
              setState({ status: "idle", result: null, error: null })
            }}
            className="h-8 max-w-[220px] rounded-md border bg-card px-2 font-mono text-[11px]"
          >
            {candidates.map((c) => (
              <option key={c.smiles} value={c.smiles}>
                {c.name ? `${c.name} · ${c.smiles}` : c.smiles}
              </option>
            ))}
          </select>
        </>
      ) : (
        <span className="max-w-[260px] truncate font-mono text-[11px] text-muted-foreground" title={selectedCandidate?.smiles}>
          {selectedCandidate?.name ? `${selectedCandidate.name} · ` : ""}
          {selectedCandidate?.smiles}
        </span>
      )}

      <span className="ml-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        Nuclei
      </span>
      <div role="radiogroup" aria-label="Nuclei to predict" className="inline-flex overflow-hidden rounded-md border bg-card">
        {NUCLEI_OPTIONS.map((opt, idx) => (
          <button
            key={opt.label}
            type="button"
            role="radio"
            aria-checked={nucleiIdx === idx}
            onClick={() => {
              setNucleiIdx(idx)
              setState({ status: "idle", result: null, error: null })
            }}
            className={cn(
              "px-2.5 py-1 font-mono text-[11px] tabular-nums transition-colors",
              idx > 0 ? "border-l" : "",
              nucleiIdx === idx ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted/40",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <Button
        type="button"
        size="sm"
        className="ml-2 gap-1.5"
        onClick={runPrediction}
        disabled={state.status === "loading"}
      >
        {state.status === "loading" ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Predicting…
          </>
        ) : (
          <>
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Predict shifts
          </>
        )}
      </Button>
    </div>
  )

  const result = state.status === "ready" ? state.result : null
  const badge = result ? backendBadge(result.backend) : null
  const showHose = result?.backend === "hose_nmrshiftdb2"
  const protonShifts = (result?.shifts ?? []).filter((s) => s.nucleus === "1H")
  const carbonShifts = (result?.shifts ?? []).filter((s) => s.nucleus === "13C")

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Candidate tool · Predicted shifts"
        title="Per-atom ¹H / ¹³C shift prediction"
        icon={Atom}
        description="Structure-derived chemical-shift prediction from a candidate SMILES. The backend is server-configured (NMRNet when wired, else the HOSE-code / NMRShiftDB2 fallback) and named in the response."
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {controls}

          {state.status === "error" ? (
            <AlertCard variant="error" title="Shift prediction failed" description={state.error} />
          ) : null}

          {state.status === "idle" ? (
            <p className="text-sm text-muted-foreground">
              Pick a candidate and nuclei, then run the prediction. Predicted shifts are
              decision-support — compare against the observed spectrum before any assignment.
            </p>
          ) : null}

          {result ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                  Backend
                </span>
                {badge ? (
                  <Badge
                    variant="outline"
                    className={cn("gap-1", badge.chip)}
                    title={`Backend used: ${result.backend}`}
                  >
                    {result.backend === "nmrnet" ? (
                      <Cpu className="h-3 w-3" aria-hidden />
                    ) : (
                      <Waves className="h-3 w-3" aria-hidden />
                    )}
                    {badge.label}
                  </Badge>
                ) : null}
                <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                  {result.shift_count} shift{result.shift_count === 1 ? "" : "s"} ·{" "}
                  {result.nuclei.map((n) => (n === "1H" ? "¹H" : "¹³C")).join(" + ")}
                </span>
              </div>

              {(result.notes ?? []).length > 0
                ? (result.notes ?? []).map((note, idx) => (
                    <AlertCard
                      key={`shift-note-${idx}`}
                      variant="info"
                      title="Prediction note"
                      description={note}
                    />
                  ))
                : null}

              {(result.shifts ?? []).length === 0 ? (
                <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                  No per-atom shifts returned for this structure / nuclei selection.
                </div>
              ) : (
                <div className="space-y-5">
                  <NucleusGroup nucleus="1H" shifts={protonShifts} showHose={showHose} />
                  <NucleusGroup nucleus="13C" shifts={carbonShifts} showHose={showHose} />
                </div>
              )}

              {showHose ? (
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                  <FlaskConical className="mr-1 inline h-3 w-3" aria-hidden />
                  HOSE confidence: 6 = exact spherical environment match · 0 = element prior only.
                  Higher spheres = more literature-grounded prediction.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
