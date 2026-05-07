"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SystemStatusWorkspace } from "@/components/admin/system-status-workspace"
import { SecurityEventsWorkspace } from "@/components/admin/security-events-workspace"
import { AuditSearchWorkspace } from "@/components/admin/audit-search-workspace"
import { DebugBundlesWorkspace } from "@/components/admin/debug-bundles-workspace"
import { FileIngestionNormalizationWorkspace } from "@/components/admin/file-ingestion-normalization-workspace"
import { DeploymentSettingsWorkspace } from "@/components/settings/deployment-settings-workspace"

export function AdminInterfaceWorkspace() {
  return (
    <div className="space-y-6">
      <Tabs defaultValue="system" className="space-y-6">
        <TabsList>
          <TabsTrigger value="system">System</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
          <TabsTrigger value="debug">Debug</TabsTrigger>
          <TabsTrigger value="ingestion">Ingestion</TabsTrigger>
          <TabsTrigger value="deployment">Deployment</TabsTrigger>
        </TabsList>

        <TabsContent value="system">
          <SystemStatusWorkspace />
        </TabsContent>
        <TabsContent value="security">
          <SecurityEventsWorkspace />
        </TabsContent>
        <TabsContent value="audit">
          <AuditSearchWorkspace />
        </TabsContent>
        <TabsContent value="debug">
          <DebugBundlesWorkspace />
        </TabsContent>
        <TabsContent value="ingestion">
          <FileIngestionNormalizationWorkspace />
        </TabsContent>
        <TabsContent value="deployment">
          <DeploymentSettingsWorkspace />
        </TabsContent>
      </Tabs>
    </div>
  )
}
