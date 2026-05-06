import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiModelMonitoringWorkspace } from "@/components/ai/ai-model-monitoring-workspace"

export default function AiMonitoringPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading monitoring...</div>}>
        <AiModelMonitoringWorkspace />
      </Suspense>
    </AppShell>
  )
}
