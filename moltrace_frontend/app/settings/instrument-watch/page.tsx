import { AppShell } from "@/components/app/app-shell"
import { InstrumentWatchFolderWorkspace } from "@/components/settings/instrument-watch-folder-workspace"

/**
 * Settings route mirror (`app/settings/instrument-watch`) — matches `src/app/settings/instrument-watch/page.tsx`.
 */
export default function InstrumentWatchFolderSettingsPageApp() {
  return (
    <AppShell>
      <InstrumentWatchFolderWorkspace />
    </AppShell>
  )
}
