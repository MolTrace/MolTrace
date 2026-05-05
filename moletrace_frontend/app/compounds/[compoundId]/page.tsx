import { AppShell } from "@/components/app/app-shell"
import { CompoundDetailWorkspace } from "@/components/compounds/compound-detail-workspace"

/**
 * Compound detail route — dynamic segment `compoundId` maps to GET /compound-registry/compounds/{compound_id}.
 */
export default function CompoundDetailPage() {
  return (
    <AppShell>
      <CompoundDetailWorkspace />
    </AppShell>
  )
}
