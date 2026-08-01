import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { RegulatoryRuleUpdatesWorkspace } from "@/components/regulatory-hub/regulatory-rule-updates-workspace"

export default function RegulatoryRuleUpdatesPage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatoryRuleUpdatesWorkspace />
      </Suspense>
    </AppShell>
  )
}
