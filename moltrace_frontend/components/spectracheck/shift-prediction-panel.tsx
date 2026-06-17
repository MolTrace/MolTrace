"use client"

import { useEffect, useMemo, useState } from "react"
import { Atom, Cpu, Loader2, MonitorCog, Sparkles, Waves, Zap } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { parseCandidatesFromText } from "@/components/spectracheck/gsd-jcoupling-panel"
import type { components } from "@/src/lib/api/schema"

/**
 * Per-atom chemical-shift prediction (v0.7.9 / `POST /spectrum/predict/shifts`).
 *
 * Structure-derived tool (not part of the GSD observed-spectrum chain):
 * SMILES in, predicted ¹H/¹³C shifts out. The active method is
 * server-configured (NMRNet when wired up, else the HOSE-code /
 * NMRShiftDB2 fallback); the response names the `method` and the
 * `device` it ran on. Conformer count is a caller knob (1–32, default 8)
 * — more conformers = better ensemble averaging, slower.
 *
 * Button-triggered (not auto-fired): prediction is a deliberate action
 * on a chosen candidate and the GPU path can be non-trivial. Candidates
 * are parsed from the same `candidatesText` the J-coupling panel reads.
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

const DEFAULT_N_CONFORMERS = 8
const MIN_N_CONFORMERS = 1
const MAX_N_CONFORMERS = 32

/** Method display: NMRNet ML (teal) vs HOSE fallback (amber) vs unknown. */
function methodBadge(method: string): { label: string; chip: string; ml: boolean } {
  if (method === "nmrnet") {
    return {
      label: "NMRNet (ML)",
      chip: "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
      ml: true,
    }
  }
  if (method === "hose_fallback") {
    return {
      label: "HOSE fallback",
      chip: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
      ml: false,
    }
  }
  return { label: method, chip: "border-border bg-muted text-muted-foreground", ml: false }
}

/** Device display: cuda/mps (accelerated, teal) vs cpu (neutral) vs unknown. */
function deviceBadge(device: string): { label: string; chip: string } {
  const accel = device === "cuda" || device === "mps"
  return {
    label: device.toUpperCase(),
    chip: accel
      ? "border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300"
      : "border-border bg-muted text-muted-foreground",
  }
}

function NucleusGroup({ nucleus, shifts }: { nucleus: Nucleus; shifts: AtomShiftPredictionOut[] }) {
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
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {shifts.map((s, idx) => (
              <tr key={`${s.atom_index}-${idx}`} className="border-t hover:bg-muted/20">
                <td className="px-3 py-1.5 text-right">{s.atom_index}</td>
                <td className="px-3 py-1.5">{s.element}</td>
                <td className="px-3 py-1.5 text-right">
                  <span className="font-bold" style={{ color: "var(--mt-teal-ink)" }}>
                    {s.predicted_ppm.toFixed(2)}
                  </span>
                </td>
                <td className="px-3 py-1.5 text-right text-muted-foreground">
                  {s.uncertainty_ppm != null && Number.isFinite(s.uncertainty_ppm)
                    ? `± ${s.uncertainty_ppm.toFixed(2)}`
                    : "—"}
                </td>
              </tr>
            ))}
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
  const [nConformers, setNConformers] = useState<number>(DEFAULT_N_CONFORMERS)
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
  const clampedConformers = Math.max(MIN_N_CONFORMERS, Math.min(MAX_N_CONFORMERS, Math.round(nConformers || DEFAULT_N_CONFORMERS)))

  const runPrediction = () => {
    const smiles = selectedCandidate?.smiles?.trim()
    if (!smiles) return
    setState({ status: "loading", result: null, error: null })
    const body: SpectrumPredictShiftsRequest = { smiles, nuclei, n_conformers: clampedConformers }
    apiFetch<SpectrumPredictShiftsResult>("/spectrum/predict/shifts", { method: "POST", body })
      .then((result) => setState({ status: "ready", result, error: null }))
      .catch((err) =>
        setState({ status: "error", result: null, error: formatApiError(err, "Shift prediction failed") }),
      )
  }

  const resetResult = () => setState({ status: "idle", result: null, error: null })

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
              resetResult()
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
        <span className="max-w-[240px] truncate font-mono text-[11px] text-muted-foreground" title={selectedCandidate?.smiles}>
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
              resetResult()
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

      <label className="ml-2 inline-flex items-center gap-1.5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Conformers
        </span>
        <Input
          type="number"
          inputMode="numeric"
          min={MIN_N_CONFORMERS}
          max={MAX_N_CONFORMERS}
          step={1}
          aria-label="Number of conformers (1–32)"
          value={nConformers}
          onChange={(e) => {
            const v = Number.parseInt(e.target.value, 10)
            setNConformers(Number.isFinite(v) ? v : DEFAULT_N_CONFORMERS)
            resetResult()
          }}
          className="h-8 w-16 font-mono text-xs"
          title="Conformer ensemble size (1–32). More conformers = better averaging, slower."
        />
      </label>

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
  const mBadge = result ? methodBadge(result.method) : null
  const dBadge = result ? deviceBadge(result.device) : null
  const protonShifts = (result?.shifts ?? []).filter((s) => s.nucleus === "1H")
  const carbonShifts = (result?.shifts ?? []).filter((s) => s.nucleus === "13C")

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="teal"
        eyebrow="Candidate tool · Predicted shifts"
        title="Per-atom ¹H / ¹³C shift prediction"
        icon={Atom}
        description="Structure-derived chemical-shift prediction from a candidate SMILES. The method is server-configured (NMRNet when wired, else the HOSE-code / NMRShiftDB2 fallback) and named in the response, with the compute device it ran on."
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {controls}

          {state.status === "error" ? (
            <AlertCard variant="error" title="Shift prediction failed" description={state.error} />
          ) : null}

          {state.status === "idle" ? (
            <p className="text-sm text-muted-foreground">
              Pick a candidate, nuclei, and conformer count, then run the prediction. Predicted
              shifts are decision-support — compare against the observed spectrum before any
              assignment.
            </p>
          ) : null}

          {result ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                  Method
                </span>
                {mBadge ? (
                  <Badge variant="outline" className={cn("gap-1", mBadge.chip)} title={`method: ${result.method}`}>
                    {mBadge.ml ? <Sparkles className="h-3 w-3" aria-hidden /> : <Waves className="h-3 w-3" aria-hidden />}
                    {mBadge.label}
                  </Badge>
                ) : null}
                {dBadge ? (
                  <Badge variant="outline" className={cn("gap-1", dBadge.chip)} title={`compute device: ${result.device}`}>
                    {result.device === "cuda" || result.device === "mps" ? (
                      <Zap className="h-3 w-3" aria-hidden />
                    ) : (
                      <MonitorCog className="h-3 w-3" aria-hidden />
                    )}
                    {dBadge.label}
                  </Badge>
                ) : null}
                <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                  {result.shift_count} shift{result.shift_count === 1 ? "" : "s"} ·{" "}
                  {result.nuclei.map((n) => (n === "1H" ? "¹H" : "¹³C")).join(" + ")} ·{" "}
                  {result.n_conformers} conformer{result.n_conformers === 1 ? "" : "s"}
                </span>
              </div>

              {(result.warnings ?? []).length > 0
                ? (result.warnings ?? []).map((w, idx) => (
                    <AlertCard
                      key={`shift-warn-${idx}`}
                      variant="warning"
                      title="Prediction warning"
                      description={w}
                    />
                  ))
                : null}

              {(result.shifts ?? []).length === 0 ? (
                <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                  No per-atom shifts returned for this structure / nuclei selection.
                </div>
              ) : (
                <div className="space-y-5">
                  <NucleusGroup nucleus="1H" shifts={protonShifts} />
                  <NucleusGroup nucleus="13C" shifts={carbonShifts} />
                </div>
              )}

              <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                Decision-support · {result.method === "hose_fallback"
                  ? "HOSE-code fallback (NMRNet not available); uncertainty may be unreported per atom."
                  : "compare predicted vs observed before any assignment."}
              </p>
            </>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
