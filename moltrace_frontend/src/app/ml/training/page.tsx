import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlTrainingRunLauncher } from "@/components/ml/ml-training-run-launcher"

export default function MlTrainingPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading ML Training…</div>}>
        <MlTrainingRunLauncher />
      </Suspense>
    </AppShell>
  )
}
