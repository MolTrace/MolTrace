import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlModelFactoryDashboard } from "@/components/ml/ml-model-factory-dashboard"

export default function MlModelFactoryPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading ML Model Factory…</div>}>
        <MlModelFactoryDashboard />
      </Suspense>
    </AppShell>
  )
}
