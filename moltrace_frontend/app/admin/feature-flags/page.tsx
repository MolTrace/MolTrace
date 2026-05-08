import { AppShell } from "@/components/app/app-shell"
import { FeatureFlagsWorkspace } from "@/components/admin/feature-flags-workspace"

export default function FeatureFlagsPage() {
  return (
    <AppShell>
      <FeatureFlagsWorkspace />
    </AppShell>
  )
}
