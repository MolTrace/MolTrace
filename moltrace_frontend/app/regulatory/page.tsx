import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { RegulatoryIntelligenceLanding } from "@/components/regulatory-hub/regulatory-intelligence-landing"

export default function RegulatoryPage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatoryIntelligenceLanding />
      </Suspense>
    </AppShell>
  )
}
