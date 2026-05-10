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
            <p className="text-muted-foreground">Cross-module summary optimized for quick phone review.</p>
          </div>
          <MobileCommandCenter />
          <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile SpectraCheck review...</div>}>
            <MobileSpectraCheckReview />
          </Suspense>
          <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile report preview...</div>}>
            <MobileReportPreview />
          </Suspense>
          <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile reaction approval board...</div>}>
            <MobileReactionApprovalBoard />
          </Suspense>
          <MobileRegulatoryQueue />
          <MobileDraftQueue />
        </div>
      ) : (
        <div className="mx-auto max-w-xl space-y-4 rounded-lg border bg-card p-6 text-card-foreground shadow-sm">
          <div className="space-y-1">
            <h1 className="text-xl font-semibold tracking-tight">Desktop Workspace</h1>
            <p className="text-sm text-muted-foreground">
              The handheld workflow is hidden while this session is using desktop mode.
            </p>
          </div>
          <Button asChild>
            <Link href="/dashboard">Open dashboard</Link>
          </Button>
        </div>
      )}
    </AppShell>
  )
}
