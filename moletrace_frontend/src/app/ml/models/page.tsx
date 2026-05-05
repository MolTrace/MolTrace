import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlModelArtifactsList } from "@/components/ml/ml-model-artifacts-list"

export default function MlModelsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading model artifacts…</div>}>
        <MlModelArtifactsList />
      </Suspense>
    </AppShell>
  )
}
