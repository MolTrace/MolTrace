import { AppShell } from "@/components/app/app-shell"
import { DeploymentSettingsWorkspace } from "@/components/settings/deployment-settings-workspace"

export default function DeploymentSettingsPage() {
  return (
    <AppShell>
      <DeploymentSettingsWorkspace />
    </AppShell>
  )
}
