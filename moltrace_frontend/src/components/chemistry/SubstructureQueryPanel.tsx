"use client"

/**
 * Ask whether a motif appears in a set of structures.
 *
 * The query runs on the same engine as the R6 safety screen, so a motif that flags there flags
 * here — two matchers in one product would drift, and the one with a review gate around it is the
 * one to keep.
 *
 * Scope is narrow on purpose. This matches the structures the reader supplies and nothing else: it
 * is not a search over the registry, and the copy says so, because "no matches" over a corpus that
 * was never consulted is a false negative a chemist would act on.
 */
import { useCallback, useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  matchSmarts,
  parseTargetList,
  readSmartsMatch,
  type SmartsMatchOutcome,
  type SmartsMatchRow,
} from "@/src/lib/chemistry/structure-validation"

const TARGETS_PLACEHOLDER = `One structure per line, as SMILES.

CC(=O)Oc1ccccc1C(=O)O
CCO`

/** One target and what the engine made of it. Three outcomes, kept visibly distinct. */
function MatchRow({ row }: { row: SmartsMatchRow }) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b py-1.5 last:border-b-0">
      <span className="min-w-0 break-all font-mono text-xs">{row.smiles}</span>
      {!row.parsed ? (
        // Never rendered as a miss. An unreadable target is a question that went unanswered, and
        // showing it beside the misses is how it would quietly become one.
        <span className="text-xs font-medium text-foreground">Could not be read</span>
      ) : row.matched ? (
        <span className="text-xs">
          <span className="font-medium" style={{ color: "var(--mt-teal-ink)" }}>
            Contains it
          </span>
          <span className="text-muted-foreground">
            {" "}
            · {row.matchCount} place{row.matchCount === 1 ? "" : "s"}
            {row.atomIndices.length > 0 ? ` · atoms ${row.atomIndices.join(", ")}` : ""}
          </span>
        </span>
      ) : (
        <span className="text-xs text-muted-foreground">Does not contain it</span>
      )}
    </li>
  )
}

export function SubstructureQueryPanel({
  getQueryFromCanvas,
}: {
  /** Reads the current drawing off the canvas as a pattern. Absent until the engine has started. */
  getQueryFromCanvas?: () => Promise<string>
}) {
  const [smarts, setSmarts] = useState("")
  const [targetText, setTargetText] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [outcome, setOutcome] = useState<SmartsMatchOutcome | null>(null)

  const takeFromCanvas = useCallback(async () => {
    if (!getQueryFromCanvas) return
    setError("")
    try {
      const pattern = (await getQueryFromCanvas()).trim()
      if (!pattern) {
        setError("There is nothing on the canvas to search for yet.")
        return
      }
      setSmarts(pattern)
    } catch {
      setError("The drawing could not be read as a query pattern.")
    }
  }, [getQueryFromCanvas])

  const run = useCallback(async () => {
    const targets = parseTargetList(targetText)
    setBusy(true)
    setError("")
    setOutcome(null)
    try {
      const read = readSmartsMatch(await matchSmarts(smarts, targets))
      if (read == null) {
        setError("The search replied with something this page could not read.")
        return
      }
      setOutcome(read)
    } catch (err) {
      // A pattern the engine cannot compile comes back refused, with a message already written for
      // a chemist — shown as sent rather than replaced with our own wording.
      setError(err instanceof Error && err.message ? err.message : "That search could not be run.")
    } finally {
      setBusy(false)
    }
  }, [smarts, targetText])

  const targetCount = parseTargetList(targetText).length

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="space-y-1.5">
        <Label htmlFor="substructure-query-smarts" className="text-xs">
          Motif to search for
        </Label>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            id="substructure-query-smarts"
            value={smarts}
            onChange={(e) => setSmarts(e.target.value)}
            placeholder="A query pattern, e.g. c1ccccc1"
            spellCheck={false}
            className="max-w-md font-mono text-xs"
          />
          {getQueryFromCanvas ? (
            // Drawing the query is the point of having a canvas: a motif is made of query atoms
            // and R-groups, which are exactly what nobody wants to type by hand.
            <Button type="button" size="sm" variant="outline" onClick={() => void takeFromCanvas()}>
              Use the drawing
            </Button>
          ) : null}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="substructure-query-targets" className="text-xs">
          Structures to search
        </Label>
        <Textarea
          id="substructure-query-targets"
          value={targetText}
          onChange={(e) => setTargetText(e.target.value)}
          rows={5}
          spellCheck={false}
          placeholder={TARGETS_PLACEHOLDER}
          className="font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground">
          Single structures, one per line. A whole reaction cannot be searched this way — it is
          matched a molecule at a time, so a reaction pasted here comes back as unreadable rather
          than as a miss.
        </p>
      </div>

      {error ? <AlertCard variant="error" title="Could not run that search" description={error} /> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          size="sm"
          disabled={busy || !smarts.trim() || targetCount === 0}
          onClick={() => void run()}
        >
          {busy ? "Searching…" : "Find matches"}
        </Button>
        <span className="text-xs text-muted-foreground">
          {targetCount === 0
            ? "Add at least one structure to search."
            : `${targetCount} structure${targetCount === 1 ? "" : "s"} to search.`}
        </span>
      </div>

      {outcome ? (
        <div className="space-y-2 rounded-md border bg-muted/20 p-3">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
            What the search found
          </p>
          <p className="text-xs">
            {outcome.matchedCount} of {outcome.rows.length}{" "}
            {outcome.matchedCount === 1 ? "contains" : "contain"} it.
          </p>
          {outcome.unreadableCount > 0 ? (
            <AlertCard
              variant="warning"
              title={`${outcome.unreadableCount} could not be read`}
              description="Those were not searched at all. They are unanswered, not misses — do not read them as structures that lack the motif."
            />
          ) : null}
          {outcome.rows.length > 0 ? (
            <ul className="space-y-0">
              {outcome.rows.map((row, i) => (
                <MatchRow key={`${row.smiles}-${i}`} row={row} />
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted-foreground">
            Only the structures listed above were searched — nothing else in the workspace was
            looked at.
          </p>
        </div>
      ) : null}
    </div>
  )
}
