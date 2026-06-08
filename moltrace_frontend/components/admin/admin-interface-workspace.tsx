"use client"

import Link from "next/link"
import { Building2, Flag, PackageCheck } from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SystemStatusWorkspace } from "@/components/admin/system-status-workspace"
import { OpsDashboardWorkspace } from "@/components/admin/ops-dashboard-workspace"
import { SecurityEventsWorkspace } from "@/components/admin/security-events-workspace"
import { AuditSearchWorkspace } from "@/components/admin/audit-search-workspace"
import { DebugBundlesWorkspace } from "@/components/admin/debug-bundles-workspace"
import { FeatureFlagsWorkspace } from "@/components/admin/feature-flags-workspace"
import { FileIngestionNormalizationWorkspace } from "@/components/admin/file-ingestion-normalization-workspace"
import { TenantAdminWorkspace } from "@/components/admin/tenant-admin-workspace"
import { DeploymentSettingsWorkspace } from "@/components/settings/deployment-settings-workspace"
import { useTenant } from "@/src/lib/tenant/tenant-context"

export function AdminInterfaceWorkspace() {
  const { currentTenantId } = useTenant()
  const procurementHref =
    currentTenantId && currentTenantId !== "local-development"
      ? `/admin/tenants/${encodeURIComponent(currentTenantId)}`
      : "/admin/tenants"

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Admin links</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/admin/tenants">
              <Building2 className="mr-2 h-4 w-4" />
              Tenant Admin
            </Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/admin/feature-flags">
              <Flag className="mr-2 h-4 w-4" />
              Feature Flags
            </Link>
          </Button>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href={procurementHref}>
              <PackageCheck className="mr-2 h-4 w-4" />
              Procurement Packages
            </Link>
          </Button>
        </CardContent>
      </Card>

      <Tabs defaultValue="system" className="space-y-6">
        <TabsList className="h-auto w-full flex-wrap justify-start">
          <TabsTrigger value="system">System</TabsTrigger>
          <TabsTrigger value="tenants">Tenant Admin</TabsTrigger>
          <TabsTrigger value="feature_flags">Feature Flags</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
          <TabsTrigger value="debug">Debug</TabsTrigger>
          <TabsTrigger value="ingestion">Ingestion</TabsTrigger>
          <TabsTrigger value="ops">Ops</TabsTrigger>
          <TabsTrigger value="deployment">Deployment</TabsTrigger>
        </TabsList>

        <TabsContent value="system">
          <SystemStatusWorkspace />
        </TabsContent>
        <TabsContent value="tenants">
          <TenantAdminWorkspace />
        </TabsContent>
        <TabsContent value="feature_flags">
          <FeatureFlagsWorkspace />
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
        <TabsContent value="ops">
          <OpsDashboardWorkspace />
        </TabsContent>
        <TabsContent value="deployment">
          <DeploymentSettingsWorkspace />
        </TabsContent>
      </Tabs>
    </div>
  )
}
