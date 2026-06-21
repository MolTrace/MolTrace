"use client"

import { useEffect } from "react"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"
import { trackCoreModuleOpened } from "@/src/lib/analytics/analytics-client"

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
      {!desktopMode && isMobile ? (
        <MobileSpectraCheckReview sessionId={sessionId} />
      ) : null}
      <div className={desktopMode || !isMobile ? "" : "hidden"}>
        <SpectraCheckWorkspace />
      </div>
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
