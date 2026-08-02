"use client"

/**
 * The schemes attached to a reaction project.
 *
 * Without this a capture was write-only: you could attach a scheme and never see it again, which
 * makes the attach hard to trust and impossible to correct. Archiving is retained and reversible
 * and carries a required reason, so the list can show why something stopped being current rather
 * than just making it vanish.
 */
import { useCallback, useEffect, useState } from "react"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  archiveReactionScheme,
  listReactionSchemes,
  schemeIsArchived,
  type ReactionStructureScheme,
} from "@/src/lib/chemistry/structure-validation"

function formatWhen(iso: string | null | undefined): string {
  if (typeof iso !== "string" || !iso.trim()) return ""
  const t = Date.parse(iso)
  return Number.isFinite(t) ? new Date(t).toLocaleString() : ""
}

export function ReactionSchemeList({
  reactionProjectId,
  /** Bumped by the panel after an attach, so a new scheme appears without a reload. */
  refreshToken = 0,
}: {
  reactionProjectId: number
  refreshToken?: number
}) {
  const [schemes, setSchemes] = useState<ReactionStructureScheme[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [includeArchived, setIncludeArchived] = useState(false)

  const [archivingId, setArchivingId] = useState<number | null>(null)
  const [reason, setReason] = useState("")
  const [archiveError, setArchiveError] = useState("")
  const [archiveBusy, setArchiveBusy] = useState(false)

  const load = useCallback(async () => {
    if (!Number.isFinite(reactionProjectId)) return
    setLoading(true)
    setError("")
    try {
      setSchemes(await listReactionSchemes(reactionProjectId, includeArchived))
    } catch (err) {
      // A project the reader does not own answers 404, deliberately identical to a missing one,
      // so this is not presented as a permission problem.
      setError(
        err instanceof Error && err.message
          ? `Could not load the schemes for this project. ${err.message}`
          : "Could not load the schemes for this project.",
      )
      setSchemes([])
    } finally {
      setLoading(false)
    }
  }, [reactionProjectId, includeArchived])

  useEffect(() => {
    void load()
  }, [load, refreshToken])

  const submitArchive = useCallback(
    async (schemeId: number) => {
      setArchiveBusy(true)
      setArchiveError("")
      try {
        await archiveReactionScheme(reactionProjectId, schemeId, reason)
        setArchivingId(null)
        setReason("")
        await load()
      } catch (err) {
        setArchiveError(
          err instanceof Error && err.message ? err.message : "Could not archive that scheme.",
        )
      } finally {
        setArchiveBusy(false)
      }
    },
    [reactionProjectId, reason, load],
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          Schemes on this project
        </p>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
            aria-label="Include archived schemes"
          />
          Include archived
        </label>
      </div>

      {error ? <AlertCard variant="error" title="Could not load schemes" description={error} /> : null}
      {loading ? <p className="text-xs text-muted-foreground">Loading schemes…</p> : null}
      {!loading && !error && schemes.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {includeArchived
            ? "No schemes on this project, archived or otherwise."
            : "No schemes attached yet. Capture one above to attach it here."}
        </p>
      ) : null}

      {schemes.map((scheme) => {
        const archived = schemeIsArchived(scheme)
        const warnings = Array.isArray(scheme.warnings) ? scheme.warnings : []
        return (
          <div
            key={scheme.id}
            className="rounded-md border p-3"
            data-testid={`reaction-scheme-${scheme.id}`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {scheme.name?.trim() || "Untitled scheme"}
                  {archived ? (
                    <>
                      {/* The space is load-bearing: a margin separates these visually but not in
                          the text layer, so without it the name and the label run together for a
                          screen reader and for anyone copying the row. */}{" "}
                      <span className="ml-1 font-normal text-xs text-muted-foreground">archived</span>
                    </>
                  ) : null}
                </p>
                <p className="text-xs text-muted-foreground">
                  {scheme.format === "rxn" ? "Reaction" : "Structure"} · {scheme.atom_count} atoms ·{" "}
                  {scheme.bond_count} bonds
                  {formatWhen(scheme.created_at) ? ` · added ${formatWhen(scheme.created_at)}` : ""}
                </p>
              </div>
              {!archived ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setArchivingId(scheme.id)
                    setReason("")
                    setArchiveError("")
                  }}
                >
                  Archive
                </Button>
              ) : null}
            </div>

            {scheme.canonical_smiles ? (
              <p className="mt-2 break-all text-xs">
                <span className="text-muted-foreground">
                  {scheme.format === "rxn" ? "Canonical (components sorted): " : "Canonical SMILES: "}
                </span>
                <span className="font-mono">{scheme.canonical_smiles}</span>
              </p>
            ) : null}

            {warnings.length > 0 ? (
              // Kept visible after the fact, not just at capture: a warning that only appeared
              // once is a warning nobody acts on.
              <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-muted-foreground">
                {warnings.map((w, i) => (
                  <li key={`${w.code}-${i}`}>{w.message}</li>
                ))}
              </ul>
            ) : null}

            {archived && scheme.reason_for_change ? (
              <p className="mt-2 text-xs text-muted-foreground">
                Archived: {scheme.reason_for_change}
                {formatWhen(scheme.deleted_at) ? ` (${formatWhen(scheme.deleted_at)})` : ""}
              </p>
            ) : null}

            {archivingId === scheme.id ? (
              <div className="mt-3 space-y-2 border-t pt-3">
                {archiveError ? (
                  <AlertCard variant="error" title="Could not archive" description={archiveError} />
                ) : null}
                <Label htmlFor={`scheme-archive-reason-${scheme.id}`} className="text-xs">
                  Why is this no longer current?
                </Label>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    id={`scheme-archive-reason-${scheme.id}`}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g. superseded by the revised route"
                    className="max-w-md"
                  />
                  <Button
                    type="button"
                    size="sm"
                    // The server requires a reason and 422s a blank one; asking for it here means
                    // the reader finds out before the request, not after it fails.
                    disabled={!reason.trim() || archiveBusy}
                    onClick={() => void submitArchive(scheme.id)}
                  >
                    {archiveBusy ? "Archiving…" : "Archive scheme"}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setArchivingId(null)}>
                    Cancel
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  The scheme is kept and stays readable under &ldquo;Include archived&rdquo; — this
                  records that it is no longer the current one.
                </p>
              </div>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
