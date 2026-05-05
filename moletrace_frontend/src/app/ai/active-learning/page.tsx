import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiActiveLearningWorkspace } from "@/components/ai/ai-active-learning-workspace"

export default function AiActiveLearningPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading active learning...</div>}>
        <AiActiveLearningWorkspace />
      </Suspense>
    </AppShell>
  )
}
