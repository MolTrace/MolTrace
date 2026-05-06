import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlEvaluationDashboard } from "@/components/ml/ml-evaluation-dashboard"

export default function MlEvaluationsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading ML Evaluation…</div>}>
        <MlEvaluationDashboard />
      </Suspense>
    </AppShell>
  )
}
