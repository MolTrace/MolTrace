import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"

export default function SpectraCheckPage({
  searchParams,
}: {
  searchParams?: { [key: string]: string | string[] | undefined }
}) {
  const desktopMode = searchParams?.desktop === "1"
  const sessionIdParam = searchParams?.sessionId
  const sessionId = typeof sessionIdParam === "string" ? sessionIdParam : null
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading SpectraCheck…</div>}>
        <div className="space-y-6">
          {!desktopMode ? (
            <div className="lg:hidden">
              <MobileSpectraCheckReview sessionId={sessionId} />
            </div>
          ) : null}
          <div className={desktopMode ? "" : "hidden lg:block"}>
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
      </Suspense>
    </AppShell>
  )
}
