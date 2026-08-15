"use client"

import dynamic from "next/dynamic"
import { useEffect, useState } from "react"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"
import { trackCoreModuleOpened } from "@/src/lib/analytics/analytics-client"

/** Reserves roughly the workspace's above-the-fold height so the swap-in is not
 *  a full-page layout jump, and announces itself instead of being invisible to
 *  assistive tech (the previous aria-hidden box did neither). */
function WorkspacePlaceholder() {
  return (
    <div
      role="status"
      aria-label="Loading SpectraCheck workspace"
      className="min-h-[70vh] animate-pulse rounded-lg border bg-muted/20"
    />
  )
}

// The desktop workspace is the app's heaviest client graph, so it loads on
// demand. ssr:false because the route is authed and every panel fetches its own
// data — there is no meaningful server-rendered content to lose, and it keeps
// both branches out of the prerendered HTML so the branch swap cannot
// hydrate-mismatch.
const SpectraCheckWorkspace = dynamic(
  () =>
    import("@/components/spectracheck/spectracheck-workspace").then(
      (m) => m.SpectraCheckWorkspace,
    ),
  { ssr: false, loading: WorkspacePlaceholder },
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
  // On a HARD load (shared link, refresh, PWA cold start) useIsMobile must
  // report false during hydration to match the server HTML — so rendering the
  // branch immediately would instantiate the lazy workspace on a phone and
  // fetch + evaluate the heaviest chunk in the app before the viewport is even
  // known. Rendering the placeholder for that one commit defers the branch
  // decision until the answer is real; the mobile path then never requests the
  // chunk at all, which is the whole point. Desktop loses nothing: ssr:false
  // emits no preload, so its fetch begins after hydration either way.
  const [viewportKnown, setViewportKnown] = useState(false)
  useEffect(() => {
    setViewportKnown(true)
  }, [])

  useEffect(() => {
    trackCoreModuleOpened("spectracheck", { surface: "programs_workspace" })
  }, [])

  return (
    <div className="space-y-6">
      {/* One tree, never both: the old CSS-`hidden` desktop copy stayed fully
          mounted on phones — effects, workspace fetches, DOM — behind
          display:none, on exactly the devices least able to absorb it. */}
      {!viewportKnown ? (
        <WorkspacePlaceholder />
      ) : !desktopMode && isMobile ? (
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
