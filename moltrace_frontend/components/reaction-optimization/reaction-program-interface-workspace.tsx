"use client"

import { useSearchParams } from "next/navigation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ReactionOptimizationLanding } from "@/components/reaction-optimization/reaction-optimization-landing"
import { ReactionStudioWorkspace } from "@/components/reaction-studio/reaction-studio-workspace"

export function ReactionProgramInterfaceWorkspace() {
  const searchParams = useSearchParams()
  const tab = searchParams.get("tab")
  const defaultTab = tab === "reaction-studio" ? "reaction-studio" : "reaction-overview"

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-violet)" }}
        >
          MolTrace · Reaction Optimization
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Reaction program workspace</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Review next-best-experiment recommendations across campaigns, or open the program-level Reaction Studio for direct experiment authoring.
        </p>
      </div>

      <Tabs defaultValue={defaultTab} className="space-y-4">
        <TabsList>
          <TabsTrigger
            value="reaction-overview"
            className="font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#EBF4F8] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
          >
            Reaction Optimization
          </TabsTrigger>
          <TabsTrigger
            value="reaction-studio"
            className="font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#EBF4F8] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
          >
            Reaction Studio (program-level)
          </TabsTrigger>
        </TabsList>
        <TabsContent value="reaction-overview">
          <ReactionOptimizationLanding />
        </TabsContent>
        <TabsContent value="reaction-studio">
          <ReactionStudioWorkspace />
        </TabsContent>
      </Tabs>
    </div>
  )
}
