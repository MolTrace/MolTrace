import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiPredictionDetailWorkspace } from "@/components/ai/ai-prediction-detail-workspace"

export default function AiPredictionDetailPage({ params }: { params: { predictionId: string } }) {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading prediction detail...</div>}>
        <AiPredictionDetailWorkspace predictionId={params.predictionId} />
      </Suspense>
    </AppShell>
  )
}
