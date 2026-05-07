import { AppShell } from "@/components/app/app-shell"
import { ConnectorsCenterWorkspace } from "@/components/settings/connectors-center-workspace"

/**
 * Settings route mirror (`src/app/settings/connectors`) — matches `app/settings/connectors/page.tsx`.
 */
export default function ConnectorsSettingsPageSrcApp() {
  return (
    <AppShell>
      <ConnectorsCenterWorkspace />
    </AppShell>
  )
}
