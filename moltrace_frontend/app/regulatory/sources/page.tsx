import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { RegulatorySourceLibraryWorkspace } from "@/components/regulatory-hub/regulatory-source-library-workspace"

export default function RegulatorySourcesPage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <RegulatorySourceLibraryWorkspace />
    </AppShell>
  )
}
