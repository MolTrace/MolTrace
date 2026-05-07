import { AppShell } from "@/components/app/app-shell"
import { FileIngestionNormalizationWorkspace } from "@/components/admin/file-ingestion-normalization-workspace"

export default function AdminIngestionPageSrcApp() {
  return (
    <AppShell>
      <FileIngestionNormalizationWorkspace />
    </AppShell>
  )
}
