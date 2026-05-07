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
    <Tabs defaultValue={defaultTab} className="space-y-4">
      <TabsList>
        <TabsTrigger value="reaction-overview">Reaction Optimization</TabsTrigger>
        <TabsTrigger value="reaction-studio">Reaction Studio (program-level)</TabsTrigger>
      </TabsList>
      <TabsContent value="reaction-overview">
        <ReactionOptimizationLanding />
      </TabsContent>
      <TabsContent value="reaction-studio">
        <ReactionStudioWorkspace />
      </TabsContent>
    </Tabs>
  )
}
