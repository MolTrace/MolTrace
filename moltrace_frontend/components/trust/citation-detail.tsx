"use client"

import { useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

export type RegulatoryCitation = components["schemas"]["RegulatoryCitation"]
type SourceDocument = components["schemas"]["RegulatorySourceDocument"]

/**
 * The citation behind a figure, resolved: label -> source -> version -> paragraph,
 * with the quoted sentence inline so a reviewer reads what is being relied on
 * without leaving the page.
 *
 * THE RULE THAT SHAPES THIS COMPONENT: never fabricate a link. If `source_id`
 * resolves to nothing, this says the source is unavailable and stops. It does not
 * fall back to a search page, a Google query, or the citation label rendered as
 * if it were a link — all of which look resolved to a reader and are not. An
 * unresolvable citation is a real state of the data and is shown as one.
 */

type Resolution =
  | { status: "loading" }
  | { status: "resolved"; source: SourceDocument }
  | { status: "unavailable" }

export function CitationDetail({ citation }: { citation: RegulatoryCitation }) {
  const [resolution, setResolution] = useState<Resolution>({ status: "loading" })

  useEffect(() => {
    let active = true
    setResolution({ status: "loading" })
    apiFetch<SourceDocument>(`/regulatory/sources/${citation.source_id}`, { method: "GET" })
      .then((source) => {
        if (active) setResolution({ status: "resolved", source })
      })
      .catch(() => {
        // Any failure — missing, forbidden, offline — resolves to the same honest
        // statement. We do not know that this source exists, so we do not imply it.
        if (active) setResolution({ status: "unavailable" })
      })
    return () => {
      active = false
    }
  }, [citation.source_id])

  const locator = [
    citation.section_title,
    citation.paragraph_number != null ? `Paragraph ${citation.paragraph_number}` : null,
    citation.page_number != null ? `Page ${citation.page_number}` : null,
  ].filter(Boolean)

  return (
    <div className="rounded-lg border bg-muted/30 p-3 text-xs">
      <div className="font-semibold text-foreground">{citation.citation_label}</div>

      {resolution.status === "loading" ? (
        <p className="mt-1 text-muted-foreground">Resolving source…</p>
      ) : resolution.status === "unavailable" ? (
        // Stated, not hidden, and deliberately offering no link to click.
        <p className="mt-1" style={{ color: "var(--mt-amber-ink)" }}>
          Source record unavailable — this citation could not be resolved.
        </p>
      ) : (
        <div className="mt-1 space-y-0.5 text-muted-foreground">
          <div className="text-foreground">{resolution.source.title}</div>
          {resolution.source.version ? <div>Version {resolution.source.version}</div> : null}
          {resolution.source.source_date ? <div>Dated {resolution.source.source_date}</div> : null}
        </div>
      )}

      {locator.length > 0 ? (
        <div className="mt-1 text-muted-foreground">{locator.join(" · ")}</div>
      ) : null}

      {citation.quote_excerpt ? (
        <blockquote
          className="mt-2 border-l-2 pl-3 italic leading-relaxed text-muted-foreground"
          style={{ borderLeftColor: "var(--mt-cyan)" }}
        >
          {citation.quote_excerpt}
        </blockquote>
      ) : null}
    </div>
  )
}
