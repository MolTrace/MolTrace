import { Suspense } from "react"
import { AppShell } from "@/components/app/app-shell"
import { KnowledgeExtractionRecordsWorkspace } from "@/components/knowledge/knowledge-extraction-records-workspace"

export default function KnowledgeReactionRecordsPage() {
  return (
    <AppShell>
      <Suspense fallback={<div className="p-4 text-sm text-muted-foreground">Loading…</div>}>
        <KnowledgeExtractionRecordsWorkspace recordKind="reaction" />
      </Suspense>
    </AppShell>
  )
}
