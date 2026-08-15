"use client"

import dynamic from "next/dynamic"
import { useEffect } from "react"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"
import { trackCoreModuleOpened } from "@/src/lib/analytics/analytics-client"

// The desktop workspace is the app's heaviest client graph. Loaded on demand so
// the mobile branch never fetches its chunk; ssr:false keeps the two branches
// out of the prerendered HTML, so the branch swap cannot hydrate-mismatch.
const SpectraCheckWorkspace = dynamic(
  () =>
    import("@/components/spectracheck/spectracheck-workspace").then(
      (m) => m.SpectraCheckWorkspace,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="h-64 animate-pulse rounded-lg border bg-muted/20" aria-hidden />
    ),
  },
)

/**
 * SpectraCheck route content. After the nav reorg, the three modules (SpectraCheck,
 * Regentry, Repho) live as dedicated sidebar entries with their own routes
 * (`/spectracheck`, `/regulatory`, `/reactions`), so the in-page module tab switcher
 * is redundant — this workspace renders only SpectraCheck.
 */
export function ProgramsInterfaceWorkspace({
  desktopMode = false,
  sessionId = null,
}: {
  desktopMode?: boolean
  sessionId?: string | null
}) {
  const isMobile = useIsMobile()

  useEffect(() => {
    trackCoreModuleOpened("spectracheck", { surface: "programs_workspace" })
  }, [])

  return (
    <div className="space-y-6">
      {/* One tree, never both: the old CSS-`hidden` desktop copy stayed fully
          mounted on phones — effects, workspace fetches, DOM — behind
          display:none, on exactly the devices least able to absorb it. */}
      {!desktopMode && isMobile ? (
        <MobileSpectraCheckReview sessionId={sessionId} />
      ) : (
        <SpectraCheckWorkspace />
      )}
      <AiModulePredictionAugmentation
        moduleKey="spectracheck"
        moduleTitle="SpectraCheck"
        serviceOptions={[
          {
            id: "nmr-candidate-ranking",
            label: "NMR candidate ranking",
            serviceKey: "spectracheck_nmr_candidate_ranking",
            taskKey: "nmr_candidate_ranking",
          },
          {
            id: "nmr-shift-prediction",
            label: "NMR shift prediction",
            serviceKey: "spectracheck_nmr_shift_prediction",
            taskKey: "nmr_shift_prediction",
          },
          {
            id: "msms-annotation-score",
            label: "MS/MS annotation score",
            serviceKey: "spectracheck_msms_annotation_score",
            taskKey: "msms_annotation_score",
          },
          {
            id: "lcms-feature-classification",
            label: "LC-MS feature classification",
            serviceKey: "spectracheck_lcms_feature_classification",
            taskKey: "lcms_feature_classification",
          },
        ]}
        summarySeed={{ module_scope: "spectracheck", summary_type: "analysis_request" }}
      />
    </div>
  )
}
