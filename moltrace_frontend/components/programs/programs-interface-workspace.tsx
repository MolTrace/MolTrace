"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { ReactionProgramInterfaceWorkspace } from "@/components/reaction-optimization/reaction-program-interface-workspace"
import { RegulatoryIntelligenceLanding } from "@/components/regulatory-hub/regulatory-intelligence-landing"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"
import { trackCoreModuleOpened, type CoreAnalyticsModule } from "@/src/lib/analytics/analytics-client"

const PROGRAM_ANALYTICS_MODULES: Record<string, CoreAnalyticsModule> = {
  spectracheck: "spectracheck",
  regulatory_hub: "regulatory_hub",
  reaction_optimization: "reactioniq",
}

const PROGRAM_TABS = ["spectracheck", "regulatory_hub", "reaction_optimization"]
const DEFAULT_PROGRAM = "spectracheck"

export function ProgramsInterfaceWorkspace({
  desktopMode = false,
  sessionId = null,
}: {
  desktopMode?: boolean
  sessionId?: string | null
}) {
  const isMobile = useIsMobile()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  // The active program is mirrored in the URL (?program=…) so deep links and a
  // browser-back return to /spectracheck restore the chosen module instead of
  // snapping to the SpectraCheck default. Local state keeps the tab switch
  // instant; the URL is updated alongside it.
  const [activeProgram, setActiveProgramState] = useState(() => {
    const p = searchParams.get("program")
    return p && PROGRAM_TABS.includes(p) ? p : DEFAULT_PROGRAM
  })

  const setActiveProgram = useCallback(
    (next: string) => {
      setActiveProgramState(next)
      const params = new URLSearchParams(searchParams.toString())
      if (next === DEFAULT_PROGRAM) {
        params.delete("program")
      } else {
        params.set("program", next)
      }
      const query = params.toString()
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
    },
    [router, pathname, searchParams],
  )

  // Keep the tab in sync when ?program changes while this component stays
  // mounted (same-route navigation — e.g. the SpectraCheck "Regulatory Impact"
  // bridge card links to /spectracheck?program=regulatory_hub from within the
  // SpectraCheck tab). A bare URL only resets to the default after a param has
  // been seen, so local tab clicks (which strip the default's param) and test
  // environments without a live router never fight the local state.
  const sawProgramParamRef = useRef(false)
  useEffect(() => {
    const p = searchParams.get("program")
    if (p && PROGRAM_TABS.includes(p)) {
      sawProgramParamRef.current = true
      setActiveProgramState((current) => (current === p ? current : p))
    } else if (sawProgramParamRef.current) {
      setActiveProgramState((current) => (current === DEFAULT_PROGRAM ? current : DEFAULT_PROGRAM))
    }
  }, [searchParams])

  useEffect(() => {
    trackCoreModuleOpened(PROGRAM_ANALYTICS_MODULES[activeProgram] ?? activeProgram, {
      surface: "programs_workspace",
    })
  }, [activeProgram])

  return (
    <Tabs value={activeProgram} onValueChange={setActiveProgram} className="space-y-6">
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
          Regentry
        </TabsTrigger>
        <TabsTrigger
          value="reaction_optimization"
          className="font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
        >
          Repho
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
