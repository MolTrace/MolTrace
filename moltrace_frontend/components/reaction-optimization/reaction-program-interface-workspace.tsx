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

      {/*
        Tabs row: on narrow viewports the second label "Reaction Studio
        (program-level)" used to push past the right edge of the screen
        because the default TabsList is ``inline-flex w-fit`` (sizes to its
        content) inside a non-scrollable parent.

        Fix:
          - ``max-w-full overflow-x-auto`` lets the list scroll horizontally
            when it can't fit its content into the parent's width.
          - ``[scrollbar-width:none] [&::-webkit-scrollbar]:hidden`` hides the
            scrollbar so the row stays clean (same convention as the
            MobileBottomNav and AppShell mobile tab row).
          - ``shrink-0`` on each trigger prevents the triggers from being
            squeezed below their natural label width — the trigger is sized
            to its content, and the LIST (not the triggers) overflows.
      */}
      <Tabs defaultValue={defaultTab} className="space-y-4">
        <TabsList className="max-w-full overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <TabsTrigger
            value="reaction-overview"
            className="shrink-0 font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
          >
            Reaction Optimization
          </TabsTrigger>
          <TabsTrigger
            value="reaction-studio"
            className="shrink-0 font-mono data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
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
