"use client"

// Where in a source a fact actually came from.
//
// The quote is the evidence and the page / section / paragraph is the address.
// Both are optional on the wire, and each absence is stated rather than filled
// in: a locator with no page does not become "page 1", and a record with no
// locators does not become a record whose passage happens to be elsewhere. See
// `lib/knowledge/corpus-governance.ts` §5.

import Link from "next/link"
import { FileText, Quote } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ProvenanceBadge } from "@/components/knowledge/knowledge-governance-badges"
import {
  LOCATOR_ADDRESS_MISSING,
  LOCATOR_MISSING_DESCRIPTION,
  LOCATOR_MISSING_LABEL,
  LOCATOR_QUOTE_MISSING,
  locatorAddress,
  type ProvenanceState,
  type RecordLocator,
} from "@/lib/knowledge/corpus-governance"

/**
 * @param provenanceOfRevision resolves a locator's own `source_revision_id`
 *   against its source. A citation can point at an older revision than the
 *   record does, so the staleness question is asked per locator rather than
 *   inherited from the record.
 */
export function KnowledgeRecordLocators({
  locators,
  provenanceOfRevision,
}: {
  locators: RecordLocator[]
  provenanceOfRevision?: (locator: RecordLocator) => ProvenanceState
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <p className="text-xs font-medium text-muted-foreground">Where this came from</p>
      </div>

      {locators.length === 0 ? (
        <div className="rounded-md border border-dashed p-3">
          <p className="text-sm font-medium">{LOCATOR_MISSING_LABEL}</p>
          <p className="mt-1 text-xs text-muted-foreground">{LOCATOR_MISSING_DESCRIPTION}</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {locators.map((locator) => {
            const address = locatorAddress(locator)
            const provenance = provenanceOfRevision?.(locator)
            return (
              <li key={locator.citation_id} className="rounded-md border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="font-mono text-[11px]">
                    {locator.citation_label || `Citation ${locator.citation_id}`}
                  </Badge>
                  <Link
                    href={`/knowledge/sources?source=${locator.source_id}`}
                    className="text-xs underline underline-offset-4"
                  >
                    Open the source
                  </Link>
                  {provenance ? <ProvenanceBadge state={provenance} hideWhenCurrent /> : null}
                </div>

                <p
                  className={
                    address
                      ? "mt-1.5 text-xs text-muted-foreground"
                      : "mt-1.5 text-xs italic text-muted-foreground"
                  }
                >
                  {address || LOCATOR_ADDRESS_MISSING}
                </p>

                {locator.quote_excerpt ? (
                  <blockquote className="mt-2 flex gap-2 border-l-2 border-muted-foreground/30 pl-3">
                    <Quote className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="text-sm leading-relaxed">{locator.quote_excerpt}</span>
                  </blockquote>
                ) : (
                  <p className="mt-2 text-xs italic text-muted-foreground">{LOCATOR_QUOTE_MISSING}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
