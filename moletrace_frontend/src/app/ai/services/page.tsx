import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiServiceRegistryWorkspace } from "@/components/ai/ai-service-registry-workspace"

export default function AiServiceRegistryPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading AI Service Registry…</div>}>
        <AiServiceRegistryWorkspace />
      </Suspense>
    </AppShell>
  )
}
