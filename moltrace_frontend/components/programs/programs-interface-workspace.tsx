"use client"

import { Suspense } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { ReactionProgramInterfaceWorkspace } from "@/components/reaction-optimization/reaction-program-interface-workspace"
import { RegulatoryIntelligenceLanding } from "@/components/regulatory-hub/regulatory-intelligence-landing"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"

export function ProgramsInterfaceWorkspace({
  desktopMode = false,
  sessionId = null,
}: {
  desktopMode?: boolean
  sessionId?: string | null
}) {
  const isMobile = useIsMobile()

  return (
    <Tabs defaultValue="spectracheck" className="space-y-6">
      <TabsList>
        <TabsTrigger
          value="spectracheck"
          className="font-mono data-[state=active]:[background-color:var(--mt-teal)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
        >
          SpectraCheck
        </TabsTrigger>
        <TabsTrigger
          value="regulatory_hub"
          className="font-mono data-[state=active]:[background-color:var(--mt-cyan)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
        >
          Regulatory Hub
        </TabsTrigger>
        <TabsTrigger
          value="reaction_optimization"
          className="font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
        >
          ReactionIQ
        </TabsTrigger>
      </TabsList>

      <TabsContent value="spectracheck" className="space-y-6">
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
      </TabsContent>

      <TabsContent value="regulatory_hub">
        <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
          <RegulatoryIntelligenceLanding />
        </Suspense>
      </TabsContent>

      <TabsContent value="reaction_optimization">
        <ReactionProgramInterfaceWorkspace />
      </TabsContent>
    </Tabs>
  )
}
