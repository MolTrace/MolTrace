import { AppShell } from "@/components/app/app-shell"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { MobileRegulatoryQueue } from "@/src/components/mobile/MobileRegulatoryQueue"

export default function MobileCommandCenterPage() {
  return (
    <AppShell>
      <div className="space-y-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mobile Command Center</h1>
          <p className="text-muted-foreground">Cross-module summary optimized for quick phone review.</p>
        </div>
        <MobileCommandCenter />
        <MobileRegulatoryQueue />
      </div>
    </AppShell>
  )
}
