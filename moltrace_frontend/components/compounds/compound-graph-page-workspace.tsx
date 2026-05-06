"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { CompoundScientificKnowledgeGraphPanel } from "@/components/compounds/compound-scientific-knowledge-graph-panel"
import { Button } from "@/components/ui/button"

export function CompoundGraphPageWorkspace() {
  const params = useParams()
  const rawId = params?.compoundId
  const compoundId =
    typeof rawId === "string" ? rawId.trim() : Array.isArray(rawId) ? rawId[0]?.trim() ?? "" : ""

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Scientific knowledge graph</h1>
          <p className="text-sm text-muted-foreground">
            compound_id <span className="font-mono">{compoundId || "—"}</span> · GET /compound-registry/graph
          </p>
        </div>
        {compoundId ? (
          <Button variant="outline" size="sm" className="w-fit" asChild>
            <Link href={`/compounds/${encodeURIComponent(compoundId)}`}>← Compound detail</Link>
          </Button>
        ) : null}
      </div>
      {compoundId ? (
        <CompoundScientificKnowledgeGraphPanel compoundId={compoundId} hideFullPageLink />
      ) : (
        <p className="text-sm text-muted-foreground">Missing compound id in the route.</p>
      )}
    </div>
  )
}
