import { AppShell } from "@/components/app/app-shell"
import { CompoundGraphPageWorkspace } from "@/components/compounds/compound-graph-page-workspace"

/**
 * Full-page scientific knowledge graph for a compound — GET /compound-registry/graph?compound_id=…
 */
export default function CompoundGraphPage() {
  return (
    <AppShell>
      <CompoundGraphPageWorkspace />
    </AppShell>
  )
}
