import { AppShell } from "@/components/app/app-shell"
import { RegentryModuleNav } from "@/components/regulatory-hub/regentry-module-nav"
import { ImpurityAssessmentWorkspace } from "@/components/regulatory-hub/impurity-assessment-workspace"

export default function RegulatoryImpuritiesPage() {
  return (
    <AppShell>
      <RegentryModuleNav />
      <ImpurityAssessmentWorkspace />
    </AppShell>
  )
}
