"use client"

import { useMemo } from "react"
import { summarizeResult, type Summary } from "@/components/spectracheck/spectracheck-summary"
import { Button } from "@/components/ui/button"
import {
  buildEvidenceItemInput,
  type SpectraCheckUnifiedEvidenceMeta,
} from "@/src/lib/spectracheck/evidence-enqueue"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

export function SpectraCheckUseUnifiedEvidenceButton({
  response,
  summary: summaryProp,
  meta,
}: {
  response: unknown
  summary?: Summary
  meta: SpectraCheckUnifiedEvidenceMeta
}) {
  const { addEvidenceItem } = useSpectraCheckEvidence()
  const summary = useMemo(
    () => summaryProp ?? summarizeResult(response),
    [summaryProp, response],
  )

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      className="w-full shrink-0 sm:w-auto"
      onClick={() =>
        addEvidenceItem(
          buildEvidenceItemInput({
            ...meta,
            response,
            summary,
          }),
        )
      }
    >
      Use in Unified Evidence
    </Button>
  )
}
