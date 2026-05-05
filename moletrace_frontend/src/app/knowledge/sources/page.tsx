import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { KnowledgeSourceLibraryWorkspace } from "@/components/knowledge/knowledge-source-library-workspace"

export default function KnowledgeSourcesPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading…</div>}>
        <KnowledgeSourceLibraryWorkspace />
      </Suspense>
    </AppShell>
  )
}
