import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { MobileDraftQueue } from "@/src/components/mobile/MobileDraftQueue"
import { MobileReactionApprovalBoard } from "@/src/components/mobile/MobileReactionApprovalBoard"
import { MobileRegulatoryQueue } from "@/src/components/mobile/MobileRegulatoryQueue"
import { MobileReportPreview } from "@/src/components/mobile/MobileReportPreview"
import { MobileSpectraCheckReview } from "@/src/components/mobile/MobileSpectraCheckReview"

export default function MobileCommandCenterPage() {
  return (
    <AppShell>
      <div className="mx-auto min-w-0 max-w-screen-sm space-y-4 px-3 pb-24 sm:px-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mobile Command Center</h1>
          <p className="text-muted-foreground">Cross-module summary optimized for quick phone review.</p>
        </div>
        <MobileCommandCenter />
        <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile SpectraCheck review…</div>}>
          <MobileSpectraCheckReview />
        </Suspense>
        <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile report preview…</div>}>
          <MobileReportPreview />
        </Suspense>
        <Suspense fallback={<div className="text-xs text-muted-foreground">Loading mobile reaction approval board…</div>}>
          <MobileReactionApprovalBoard />
        </Suspense>
        <MobileRegulatoryQueue />
        <MobileDraftQueue />
      </div>
    </AppShell>
  )
}
