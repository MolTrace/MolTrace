import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { RegulatorySurveillanceDashboard } from "@/components/regulatory-hub/regulatory-surveillance-dashboard"

export default function RegulatorySurveillancePage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatorySurveillanceDashboard />
      </Suspense>
    </AppShell>
  )
}
