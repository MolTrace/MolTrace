import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlModelCardDetail } from "@/components/ml/ml-model-card-detail"

export default function MlModelCardPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading model card…</div>}>
        <MlModelCardDetail />
      </Suspense>
    </AppShell>
  )
}
