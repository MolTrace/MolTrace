"use client"

// Source history — every change appends a revision and the predecessor stays
// readable forever.
//
// The guarantee this panel exists to make visible: revision 1 still shows the
// OLD value. `publication_date`, `doi` and `reliability_label` are exactly the
// fields a downstream extraction was justified by, so being able to read what
// the source said at extraction time is what makes a stale justification
// checkable at all.

import { useCallback, useEffect, useState } from "react"
import { History, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { knowledgeLabel } from "@/components/knowledge/knowledge-constants"
import {
  changedFieldLabel,
  fetchSourceRevisions,
  type KnowledgeSourceRevision,
} from "@/lib/knowledge/corpus-governance"

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString()
}

function ChangedFields({ fields, isOriginal }: { fields: string[]; isOriginal: boolean }) {
  // The first revision reports every field it captured as "changed" — it is the
  // registration, not an edit. Listing ten badges there reads as ten changes,
  // which is the opposite of what happened, so the original says so instead.
  if (isOriginal || fields.length === 0) {
    return <span className="text-muted-foreground">Original record, as first registered</span>
  }
  return (
    <span className="inline-flex flex-wrap gap-1">
      {fields.map((f) => (
        // Humanized for display only. The wire key is never renamed.
        <Badge key={f} variant="secondary" className="text-[10px]">
          {changedFieldLabel(f)}
        </Badge>
      ))}
    </span>
  )
}

function RevisionRow({ revision }: { revision: KnowledgeSourceRevision }) {
  return (
    <li className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Version {revision.revision_number}</span>
        {revision.is_current ? (
          <Badge variant="outline" className="border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
            Current
          </Badge>
        ) : (
          <Badge variant="outline" className="text-muted-foreground">
            Superseded
          </Badge>
        )}
        <span className="ml-auto text-xs text-muted-foreground">{formatWhen(revision.created_at)}</span>
      </div>

      <dl className="mt-2 grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted-foreground">changed</dt>
        <dd>
          <ChangedFields
            fields={revision.changed_fields ?? []}
            isOriginal={revision.revision_number === 1 || revision.supersedes_revision_id == null}
          />
        </dd>

        <dt className="text-muted-foreground">reason</dt>
        <dd>
          {revision.change_reason ? (
            revision.change_reason
          ) : (
            <span className="text-muted-foreground">No reason was recorded.</span>
          )}
        </dd>

        <dt className="text-muted-foreground">by</dt>
        <dd>{revision.created_by || <span className="text-muted-foreground">Not recorded</span>}</dd>

        {/* What the source said at this version — the readable predecessor. */}
        <dt className="text-muted-foreground">reliability</dt>
        <dd>{knowledgeLabel(revision.reliability_label)}</dd>

        <dt className="text-muted-foreground">published</dt>
        <dd>{revision.publication_date || <span className="text-muted-foreground">—</span>}</dd>

        {revision.doi ? (
          <>
            <dt className="text-muted-foreground">DOI</dt>
            <dd className="break-all font-mono text-[11px]">{revision.doi}</dd>
          </>
        ) : null}
      </dl>
    </li>
  )
}

export function KnowledgeSourceRevisionsPanel({
  sourceId,
  /** Bumped by the parent after a successful save so the history reloads. */
  reloadToken = 0,
}: {
  sourceId: number
  reloadToken?: number
}) {
  const [revisions, setRevisions] = useState<KnowledgeSourceRevision[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      setRevisions(await fetchSourceRevisions(sourceId))
    } catch (e) {
      setError(formatApiError(e, "Could not load the history for this source."))
      setRevisions([])
    } finally {
      setLoading(false)
    }
  }, [sourceId])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Every change appends a version and the previous one stays readable. A record extracted from
        an earlier version keeps pointing at that version, so what justified it can still be read.
      </p>

      {loading ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          Loading history…
        </p>
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : revisions.length === 0 ? (
        <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
          No versions are recorded for this source yet.
        </p>
      ) : (
        <ol className="space-y-2">
          {revisions.map((r) => (
            <RevisionRow key={r.id} revision={r} />
          ))}
        </ol>
      )}
    </div>
  )
}

export { History as KnowledgeSourceRevisionsIcon }
