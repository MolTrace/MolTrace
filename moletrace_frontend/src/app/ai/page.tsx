import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { AiServicesDashboard } from "@/components/ai/ai-services-dashboard"

export default function AiServicesPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading AI Services…</div>}>
        <AiServicesDashboard />
      </Suspense>
    </AppShell>
  )
}
