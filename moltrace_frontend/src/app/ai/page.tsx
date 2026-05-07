import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { MlAiInterfaceWorkspace } from "@/components/ai/ml-ai-interface-workspace"

export default function AiServicesPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading AI Services…</div>}>
        <MlAiInterfaceWorkspace />
      </Suspense>
    </AppShell>
  )
}
