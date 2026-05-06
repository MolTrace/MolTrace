import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { KnowledgeExtractionsWorkspace } from "@/components/knowledge/knowledge-extractions-workspace"

export default function KnowledgeExtractionsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading…</div>}>
        <KnowledgeExtractionsWorkspace />
      </Suspense>
    </AppShell>
  )
}
