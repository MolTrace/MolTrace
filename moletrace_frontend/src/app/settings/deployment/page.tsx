import { AppShell } from "@/components/app/app-shell"
import { DeploymentSettingsWorkspace } from "@/components/settings/deployment-settings-workspace"

/**
 * Deployment Settings route (`src/app/settings/deployment`) — matches `app/settings/deployment/page.tsx`.
 */
export default function DeploymentSettingsPage() {
  return (
    <AppShell>
      <DeploymentSettingsWorkspace />
    </AppShell>
  )
}
