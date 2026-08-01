import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { RegulatoryNotificationsWorkspace } from "@/components/regulatory-hub/regulatory-notifications-workspace"

export default function RegulatoryNotificationsPage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <Suspense fallback={<p className="p-6 text-sm text-muted-foreground">Loading…</p>}>
        <RegulatoryNotificationsWorkspace />
      </Suspense>
    </AppShell>
  )
}
