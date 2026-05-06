import { AppShell } from "@/components/app/app-shell"
import AutomationRoiDashboard from "@/components/automation-roi/automation-roi-dashboard"

/**
 * Automation ROI route (mirror of `app/roi/page.tsx`).
 * Next.js resolves `app/` at the project root for routing; this file matches the requested
 * `src/app/roi` path for documentation and future migration to `src/app` only.
 */
export default function RoiPage() {
  return (
    <AppShell>
      <AutomationRoiDashboard />
    </AppShell>
  )
}
