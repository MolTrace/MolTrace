"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CompoundRegistryWorkspace } from "@/components/compounds/compound-registry-workspace"
import { BatchRegistryWorkspace } from "@/components/batches/batch-registry-workspace"

export function CompoundsBatchesInterfaceWorkspace() {
  return (
    <div className="space-y-6">
      <Tabs defaultValue="compounds" className="space-y-6">
        <TabsList>
          <TabsTrigger value="compounds">Compounds</TabsTrigger>
          <TabsTrigger value="batches">Batches</TabsTrigger>
        </TabsList>
        <TabsContent value="compounds">
          <CompoundRegistryWorkspace />
        </TabsContent>
        <TabsContent value="batches">
          <BatchRegistryWorkspace />
        </TabsContent>
      </Tabs>
    </div>
  )
}
