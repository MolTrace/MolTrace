import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlErrorAnalysisWorkspace } from "@/components/ml/ml-error-analysis-workspace"

export default function MlErrorAnalysisPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading error analysis…</div>}>
        <MlErrorAnalysisWorkspace />
      </Suspense>
    </AppShell>
  )
}
