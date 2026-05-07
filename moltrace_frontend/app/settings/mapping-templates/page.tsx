import { AppShell } from "@/components/app/app-shell"
import { MappingTemplatesWorkspace } from "@/components/settings/mapping-templates-workspace"

/**
 * Settings route mirror (`app/settings/mapping-templates`) — matches `src/app/settings/mapping-templates/page.tsx`.
 */
export default function MappingTemplatesSettingsPageApp() {
  return (
    <AppShell>
      <MappingTemplatesWorkspace />
    </AppShell>
  )
}
