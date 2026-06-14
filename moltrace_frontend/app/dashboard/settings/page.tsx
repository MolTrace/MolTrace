import Link from "next/link"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ConnectorsCenterWorkspace } from "@/components/settings/connectors-center-workspace"
import { MfaManagementWorkspace } from "@/components/settings/mfa-management-workspace"
import { InstrumentWatchFolderWorkspace } from "@/components/settings/instrument-watch-folder-workspace"
import { MappingTemplatesWorkspace } from "@/components/settings/mapping-templates-workspace"
import { User, Bell, Shield, Key, Building2, Plug, FolderSearch, Link2 } from "lucide-react"

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-slate)" }}
        >
          MolTrace · Dashboard · Settings
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Settings</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Manage your account, application preferences, security, API keys, and connector configuration.
        </p>
      </div>

      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList>
          <TabsTrigger value="profile" className="gap-2">
            <User className="h-4 w-4" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="h-4 w-4" />
            Security
          </TabsTrigger>
          <TabsTrigger value="api" className="gap-2">
            <Key className="h-4 w-4" />
            API
          </TabsTrigger>
          <TabsTrigger value="organization" className="gap-2">
            <Building2 className="h-4 w-4" />
            Organization
          </TabsTrigger>
          <TabsTrigger value="connectors" className="gap-2">
            <Plug className="h-4 w-4" />
            Connectors
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
              <CardDescription>Update your personal information and preferences.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="firstName">First Name</Label>
                  <Input id="firstName" defaultValue="Sarah" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lastName">Last Name</Label>
                  <Input id="lastName" defaultValue="Chen" />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" defaultValue="sarah.chen@pharma.com" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="role">Role</Label>
                <Input id="role" defaultValue="Senior Research Scientist" />
              </div>
              <Separator />
              <Button>Save Changes</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle>Notification Preferences</CardTitle>
              <CardDescription>Control how and when you receive notifications.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Analysis Complete</div>
                  <div className="text-sm text-muted-foreground">Notify when analyses finish processing</div>
                </div>
                <Switch defaultChecked />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Review Required</div>
                  <div className="text-sm text-muted-foreground">Alert when human review is needed</div>
                </div>
                <Switch defaultChecked />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Contradictions Detected</div>
                  <div className="text-sm text-muted-foreground">Immediate alerts for AI contradictions</div>
                </div>
                <Switch defaultChecked />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Weekly Digest</div>
                  <div className="text-sm text-muted-foreground">Summary of platform activity</div>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle>Security Settings</CardTitle>
              <CardDescription>Manage your account security and authentication.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <MfaManagementWorkspace />
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Session Timeout</div>
                  <div className="text-sm text-muted-foreground">Automatically log out after inactivity</div>
                </div>
                <Badge variant="outline">30 minutes</Badge>
              </div>
              <Separator />
              <div>
                <Button variant="outline">Change Password</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="api">
          <Card>
            <CardHeader>
              <CardTitle>API Access</CardTitle>
              <CardDescription>Manage API keys for programmatic access.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">Production Key</div>
                    <div className="font-mono text-sm text-muted-foreground">moltrace_prod_****************************3f7a</div>
                  </div>
                  <Button variant="outline" size="sm">Regenerate</Button>
                </div>
              </div>
              <div className="rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">Development Key</div>
                    <div className="font-mono text-sm text-muted-foreground">moltrace_dev_****************************8c2b</div>
                  </div>
                  <Button variant="outline" size="sm">Regenerate</Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="organization">
          <Card>
            <CardHeader>
              <CardTitle>Organization Settings</CardTitle>
              <CardDescription>Manage your organization and team members.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>Organization Name</Label>
                <Input defaultValue="Pharma Research Inc." />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Team Members</div>
                  <div className="text-sm text-muted-foreground">12 active users</div>
                </div>
                <Button variant="outline" asChild>
                  <Link href="/settings/team">Manage Team</Link>
                </Button>
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Subscription</div>
                  <div className="text-sm text-muted-foreground">Enterprise Plan</div>
                </div>
                <Badge>Active</Badge>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="connectors">
          <Tabs defaultValue="connector-center" className="space-y-4">
            <TabsList>
              <TabsTrigger value="connector-center" className="gap-2">
                <Plug className="h-4 w-4" />
                Connector Center
              </TabsTrigger>
              <TabsTrigger value="instrument-watch" className="gap-2">
                <FolderSearch className="h-4 w-4" />
                Instrument Watch
              </TabsTrigger>
              <TabsTrigger value="mapping-templates" className="gap-2">
                <Link2 className="h-4 w-4" />
                Mapping Templates
              </TabsTrigger>
            </TabsList>
            <TabsContent value="connector-center">
              <ConnectorsCenterWorkspace />
            </TabsContent>
            <TabsContent value="instrument-watch">
              <InstrumentWatchFolderWorkspace />
            </TabsContent>
            <TabsContent value="mapping-templates">
              <MappingTemplatesWorkspace />
            </TabsContent>
          </Tabs>
        </TabsContent>

      </Tabs>
    </div>
  )
}
