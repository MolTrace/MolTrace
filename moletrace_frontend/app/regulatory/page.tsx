import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegulatoryIntelligenceLanding } from "@/components/regulatory-hub/regulatory-intelligence-landing"

export default function RegulatoryPage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatoryIntelligenceLanding />
      </Suspense>
    </AppShell>
  )
}
