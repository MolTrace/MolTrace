import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlDeploymentCandidatesWorkspace } from "@/components/ml/ml-deployment-candidates-workspace"

export default function MlDeploymentCandidatesPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading deployment candidates…</div>}>
        <MlDeploymentCandidatesWorkspace />
      </Suspense>
    </AppShell>
  )
}
