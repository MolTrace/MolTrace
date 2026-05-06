import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiCanaryDeploymentsWorkspace } from "@/components/ai/ai-canary-deployments-workspace"

export default function AiCanaryPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading canary deployments...</div>}>
        <AiCanaryDeploymentsWorkspace />
      </Suspense>
    </AppShell>
  )
}
