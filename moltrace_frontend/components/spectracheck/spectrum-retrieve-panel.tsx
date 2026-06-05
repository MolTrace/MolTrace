"use client"

import { useEffect, useMemo, useState } from "react"
import { DatabaseZap, Library, Loader2, Search, Trophy } from "lucide-react"
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
 * Spectral-similarity retrieval (`POST /spectrum/retrieve`).
 *
 * Encodes a candidate SMILES (predicted shifts → Gaussian-smoothed vector)
 * and queries the server-configured FAISS similarity index
 * (`MOLTRACE_SIMILARITY_INDEX`) for the nearest reference spectra. Hits come
 * back ascending by `l2_distance` (lower = closer); the panel re-sorts
 * defensively so that ordering is guaranteed regardless of the backend.
 *
 * The index is optional and server-side: when it isn't configured the
 * response carries `index_available: false` and the panel shows an explicit
 * "no index configured" empty state rather than an error. Structure-derived
 * decision-support — not part of the GSD observed-spectrum chain. Candidates
 * are read from the same free-text field the shift / J-coupling panels use.
 */

type SpectrumRetrieveRequest = components["schemas"]["SpectrumRetrieveRequest"]
type SpectrumRetrieveResult = components["schemas"]["SpectrumRetrieveResult"]

type RetrieveState =
  | { status: "idle"; result: null; error: null }
  | { status: "loading"; result: null; error: null }
  | { status: "ready"; result: SpectrumRetrieveResult; error: null }
  | { status: "error"; result: null; error: string }

const DEFAULT_TOP_K = 100
const MIN_TOP_K = 1
const MAX_TOP_K = 1000
// How many hits to render in the table; the request still asks for top_k, but
// a 1000-row table helps no one — the closest matches are what reviewers read.
const MAX_RENDERED_HITS = 50

/** query_source display: which input the server actually encoded. */
function querySourceLabel(source: string): string {
  if (source === "smiles") return "from SMILES"
  if (source === "shifts") return "from shift list"
  return source
}

/**
 * Compact warning surface — one card with a capped bulleted list, not N
 * stacked cards. The encode step (SMILES → predicted shifts → vector) can
 * emit a per-atom note for every atom, so the raw list is easily 8–10 long;
 * stacking that many cards drowns the actual signal.
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
          <li className="list-none text-muted-foreground">+{extra} more encoding note{extra === 1 ? "" : "s"}…</li>
        ) : null}
      </ul>
    </AlertCard>
  )
}

export type SpectrumRetrievePanelProps = {
  /** Candidate list (same free-text field the shift / J-coupling panels read). */
  candidatesText: string
  testId?: string
}

export function SpectrumRetrievePanel({
  candidatesText,
  testId = "spectrum-retrieve-surface",
}: SpectrumRetrievePanelProps) {
  const candidates = useMemo(() => parseCandidatesFromText(candidatesText), [candidatesText])
  const [selectedSmiles, setSelectedSmiles] = useState<string>("")
  const [topK, setTopK] = useState<number>(DEFAULT_TOP_K)
  const [state, setState] = useState<RetrieveState>({ status: "idle", result: null, error: null })

  // Keep the selected SMILES valid as the candidate list changes; clear any
  // stale result when the selection or candidate set shifts.
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
  const clampedTopK = Math.max(MIN_TOP_K, Math.min(MAX_TOP_K, Math.round(topK || DEFAULT_TOP_K)))

  const runRetrieve = () => {
    const smiles = selectedCandidate?.smiles?.trim()
    if (!smiles) return
    setState({ status: "loading", result: null, error: null })
    const body: SpectrumRetrieveRequest = { smiles, top_k: clampedTopK }
    apiFetch<SpectrumRetrieveResult>("/spectrum/retrieve", { method: "POST", body })
      .then((result) => setState({ status: "ready", result, error: null }))
      .catch((err) =>
        setState({ status: "error", result: null, error: formatApiError(err, "Spectral retrieval failed") }),
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
            aria-label="Candidate to search the similarity index for"
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
        <span
          className="max-w-[240px] truncate font-mono text-[11px] text-muted-foreground"
          title={selectedCandidate?.smiles}
        >
          {selectedCandidate?.name ? `${selectedCandidate.name} · ` : ""}
          {selectedCandidate?.smiles}
        </span>
      )}

      <label className="ml-2 inline-flex items-center gap-1.5">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Top K
        </span>
        <Input
          type="number"
          inputMode="numeric"
          min={MIN_TOP_K}
          max={MAX_TOP_K}
          step={1}
          aria-label="Number of nearest neighbours to retrieve (1–1000)"
          value={topK}
          onChange={(e) => {
            const v = Number.parseInt(e.target.value, 10)
            setTopK(Number.isFinite(v) ? v : DEFAULT_TOP_K)
            resetResult()
          }}
          className="h-8 w-20 font-mono text-xs"
          title="Number of nearest neighbours to ask the index for (1–1000)."
        />
      </label>

      <Button type="button" size="sm" className="ml-2 gap-1.5" onClick={runRetrieve} disabled={state.status === "loading"}>
        {state.status === "loading" ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Searching…
          </>
        ) : (
          <>
            <Search className="h-3.5 w-3.5" aria-hidden />
            Find similar spectra
          </>
        )}
      </Button>
    </div>
  )

  const result = state.status === "ready" ? state.result : null
  // Defensive ascending sort (lower L2 = closer). The backend already returns
  // ascending, but guaranteeing it here keeps the "rank" column honest.
  const hits = [...(result?.results ?? [])].sort((a, b) => a.l2_distance - b.l2_distance)
  const renderedHits = hits.slice(0, MAX_RENDERED_HITS)
  const warnings = result?.warnings ?? []

  return (
    <div className="min-w-0" data-testid={testId}>
      <ModuleCard
        accent="violet"
        eyebrow="Candidate tool · Similarity search"
        title="Spectral-similarity retrieval"
        icon={DatabaseZap}
        description="Encodes a candidate SMILES into the same vector space as the reference library and returns the nearest spectra by L2 distance. The similarity index is server-configured; matches are decision-support, not identity assignments."
        className="min-w-0 overflow-visible shadow-none"
      >
        <div className="space-y-4">
          {controls}

          {state.status === "error" ? (
            <AlertCard variant="error" title="Spectral retrieval failed" description={state.error} />
          ) : null}

          {state.status === "idle" ? (
            <p className="text-sm text-muted-foreground">
              Pick a candidate and a neighbour count, then search the reference library. Nearest
              matches are ranked by L2 distance (lower = closer) — corroborating evidence to weigh
              against the observed spectrum, never a standalone assignment.
            </p>
          ) : null}

          {result ? (
            result.index_available === false ? (
              // Explicit empty state — the server has no similarity index wired
              // up (MOLTRACE_SIMILARITY_INDEX). This is a configuration state,
              // not an error: surface it calmly and pass through any warning.
              <div className="space-y-3">
                <div className="flex flex-col items-center gap-2 rounded-md border border-dashed bg-muted/20 px-4 py-8 text-center">
                  <Library className="h-6 w-6 text-muted-foreground" aria-hidden />
                  <p className="text-sm font-medium text-foreground">Retrieval index not configured</p>
                  <p className="max-w-md text-xs text-muted-foreground">
                    This deployment has no spectral similarity index enabled, so there is nothing to
                    search against. An administrator can configure one server-side
                    (<code className="font-mono">MOLTRACE_SIMILARITY_INDEX</code>) to turn on
                    nearest-neighbour retrieval.
                  </p>
                </div>
                <WarningList warnings={warnings} variant="info" title="Encoding notes" />
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Index
                  </span>
                  <Badge
                    variant="outline"
                    className="gap-1 border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-300"
                    title={`retrieval method: ${result.method}`}
                  >
                    <DatabaseZap className="h-3 w-3" aria-hidden />
                    {result.method === "vector_l2" ? "L2 vector" : result.method}
                  </Badge>
                  <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                    {result.index_size.toLocaleString()} indexed spectr{result.index_size === 1 ? "um" : "a"} ·{" "}
                    query {querySourceLabel(result.query_source)} · top {result.top_k}
                  </span>
                </div>

                <WarningList warnings={warnings} variant="warning" title="Retrieval warnings" />

                {hits.length === 0 ? (
                  <div className="rounded-md border border-dashed bg-muted/20 px-4 py-6 text-center text-sm text-muted-foreground">
                    No matches returned from the similarity index for this candidate.
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      {hits.length} match{hits.length === 1 ? "" : "es"}
                      {hits.length > renderedHits.length ? ` · showing closest ${renderedHits.length}` : ""}
                    </p>
                    <div className="overflow-x-auto rounded-md border">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                          <tr>
                            <th className="px-3 py-2 text-right">Rank</th>
                            <th className="px-3 py-2">Reference ID</th>
                            <th className="px-3 py-2 text-right">L2 distance</th>
                          </tr>
                        </thead>
                        <tbody className="font-mono tabular-nums">
                          {renderedHits.map((hit, idx) => (
                            <tr key={`${hit.id}-${idx}`} className="border-t hover:bg-muted/20">
                              <td className="px-3 py-1.5 text-right text-muted-foreground">
                                <span className="inline-flex items-center justify-end gap-1">
                                  {idx === 0 ? (
                                    <Trophy className="h-3 w-3 text-violet-500" aria-label="closest match" />
                                  ) : null}
                                  {idx + 1}
                                </span>
                              </td>
                              <td className="px-3 py-1.5 max-w-[280px] truncate" title={hit.id}>
                                {hit.id}
                              </td>
                              <td className="px-3 py-1.5 text-right">
                                <span className={cn("font-bold", idx === 0 ? "text-violet-600 dark:text-violet-300" : "")}>
                                  {hit.l2_distance.toFixed(4)}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                      Decision-support · lower L2 = closer; corroborate against the observed spectrum
                      before any assignment.
                    </p>
                  </div>
                )}
              </>
            )
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}
