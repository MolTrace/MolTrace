import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiShadowEvaluationsWorkspace } from "@/components/ai/ai-shadow-evaluations-workspace"

export default function AiShadowEvaluationsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading shadow evaluations...</div>}>
        <AiShadowEvaluationsWorkspace />
      </Suspense>
    </AppShell>
  )
}
