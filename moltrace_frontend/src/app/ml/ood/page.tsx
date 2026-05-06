import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlOodAssessmentWorkspace } from "@/components/ml/ml-ood-assessment-workspace"

export default function MlOodPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading out-of-domain…</div>}>
        <MlOodAssessmentWorkspace />
      </Suspense>
    </AppShell>
  )
}
