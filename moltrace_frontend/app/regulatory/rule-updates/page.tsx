import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegulatoryRuleUpdatesWorkspace } from "@/components/regulatory-hub/regulatory-rule-updates-workspace"

export default function RegulatoryRuleUpdatesPage() {
  return (
    <AppShell>
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatoryRuleUpdatesWorkspace />
      </Suspense>
    </AppShell>
  )
}
