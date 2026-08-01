"use client"

import { Suspense } from "react"
import Link from "next/link"
import { AppShell } from "@/components/app/app-shell"
import { Button } from "@/components/ui/button"
import { useIsMobile } from "@/hooks/use-mobile"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { MobileDraftQueue } from "@/src/components/mobile/MobileDraftQueue"
import { MobileReactionApprovalBoard } from "@/src/components/mobile/MobileReactionApprovalBoard"
import { MobileRegulatoryQueue } from "@/src/components/mobile/MobileRegulatoryQueue"
import { ModuleGate } from "@/src/lib/modules/module-not-included-tile"
import { MobileReportPreview } from "@/src/components/mobile/MobileReportPreview"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"

export default function MobileCommandCenterPage() {
  const isMobile = useIsMobile()

  return (
    <AppShell>
      {isMobile ? (
        <div className="mx-auto min-w-0 max-w-screen-sm space-y-4 px-3 pb-24 sm:px-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Mobile Command Center</h1>
            <p className="text-muted-foreground">Everything awaiting you, across all three modules.</p>
          </div>
          <MobileCommandCenter />
          <Suspense fallback={<div className="text-xs text-muted-foreground">Loading SpectraCheck review…</div>}>
            <MobileSpectraCheckReview />
          </Suspense>
          <Suspense fallback={<div className="text-xs text-muted-foreground">Loading report preview…</div>}>
            <MobileReportPreview />
          </Suspense>
          {/* Both of these belong to a product this deployment may not serve, and /mobile is not
              owned by any module — so nav filtering never reaches them and the page is reachable
              on any phone viewport. Hidden rather than tiled: the phone workflow is a short task
              list, and a card explaining an absent product is noise on a small screen. */}
          <ModuleGate module="reaction_optimization" what="Reaction approvals" fallback="hide">
            <Suspense fallback={<div className="text-xs text-muted-foreground">Loading reaction approval board…</div>}>
              <MobileReactionApprovalBoard />
            </Suspense>
          </ModuleGate>
          <ModuleGate module="regulatory_hub" what="Regulatory queue" fallback="hide">
            <MobileRegulatoryQueue />
          </ModuleGate>
          <MobileDraftQueue />
        </div>
      ) : (
        <div className="mx-auto max-w-xl space-y-4 rounded-lg border bg-card p-6 text-card-foreground shadow-sm">
          <div className="space-y-1">
            <h1 className="text-xl font-semibold tracking-tight">Desktop Workspace</h1>
            <p className="text-sm text-muted-foreground">The phone workflow is hidden on desktop.</p>
          </div>
          <Button asChild>
            <Link href="/dashboard">Open dashboard</Link>
          </Button>
        </div>
      )}
    </AppShell>
  )
}
