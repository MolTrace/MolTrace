import { AppShell } from "@/components/app/app-shell"
import { FileIngestionNormalizationWorkspace } from "@/components/admin/file-ingestion-normalization-workspace"

/**
 * Admin route mirror (`app/admin/ingestion`) — matches `src/app/admin/ingestion/page.tsx`.
 */
export default function AdminIngestionPageApp() {
  return (
    <AppShell>
      <FileIngestionNormalizationWorkspace />
    </AppShell>
  )
}
