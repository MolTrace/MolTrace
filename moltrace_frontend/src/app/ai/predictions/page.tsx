import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiPredictionsWorkspace } from "@/components/ai/ai-predictions-workspace"

export default function AiPredictionsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading predictions...</div>}>
        <AiPredictionsWorkspace />
      </Suspense>
    </AppShell>
  )
}
