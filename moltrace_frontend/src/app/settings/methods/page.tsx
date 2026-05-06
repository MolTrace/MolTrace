import { AppShell } from "@/components/app/app-shell"
import { MethodRegistryWorkspace } from "@/components/settings/method-registry-workspace"

/**
 * Settings route mirror (`src/app/settings/methods`) — matches documented path next to `app/settings/methods/page.tsx`.
 */
export default function MethodRegistrySettingsPageSrcApp() {
  return (
    <AppShell>
      <MethodRegistryWorkspace />
    </AppShell>
  )
}
