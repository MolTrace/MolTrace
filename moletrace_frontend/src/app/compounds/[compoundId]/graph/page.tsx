import { AppShell } from "@/components/app/app-shell"
import { CompoundGraphPageWorkspace } from "@/components/compounds/compound-graph-page-workspace"

/**
 * Mirror route: full-page scientific knowledge graph — GET /compound-registry/graph?compound_id=…
 */
export default function CompoundGraphPage() {
  return (
    <AppShell>
      <CompoundGraphPageWorkspace />
    </AppShell>
  )
}
