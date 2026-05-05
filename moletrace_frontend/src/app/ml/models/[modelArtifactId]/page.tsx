import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlModelArtifactDetail } from "@/components/ml/ml-model-artifact-detail"

export default function MlModelArtifactPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading artifact…</div>}>
        <MlModelArtifactDetail />
      </Suspense>
    </AppShell>
  )
}
