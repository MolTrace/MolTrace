import { AppShell } from "@/components/app/app-shell"
import { FeatureFlagsWorkspace } from "@/components/admin/feature-flags-workspace"

/**
 * Feature Flags route (`src/app/admin/feature-flags`) — matches `app/admin/feature-flags/page.tsx`.
 */
export default function FeatureFlagsPage() {
  return (
    <AppShell>
      <FeatureFlagsWorkspace />
    </AppShell>
  )
}
