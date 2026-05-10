"use client"

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch, readStoredAuthToken } from "@/lib/api/client"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { Building2, KeyRound, Mail, ShieldAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Separator } from "@/components/ui/separator"
import { Users } from "lucide-react"

const ROLE_OPTIONS = ["owner", "admin", "scientist", "reviewer", "viewer"] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function pickDetail(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    if (isRecord(d) && typeof d.message === "string") return d.message
    return err.message
  }
  if (err instanceof Error) return err.message
  return "Request failed."
}

export type OrganizationRow = {
  id: string
  name: string
}

export type MemberRow = {
  id: string
  email: string
  nameLabel: string
  role: string
  status: string
  createdAt: string
  raw: Record<string, unknown>
}

function normalizeOrganizations(data: unknown): OrganizationRow[] {
  const arr = Array.isArray(data) ? data : isRecord(data) && Array.isArray(data.organizations) ? data.organizations : isRecord(data) && Array.isArray(data.items) ? data.items : []
  const out: OrganizationRow[] = []
  for (const item of arr) {
    if (!isRecord(item)) continue
    const id = readStr(item, ["id", "organization_id", "organizationId"])
    const name = readStr(item, ["name", "organization_name", "title"]) || "—"
    if (id) out.push({ id, name })
  }
  return out
}

function normalizeMembers(data: unknown): MemberRow[] {
  const arr = Array.isArray(data)
    ? data
    : isRecord(data) && Array.isArray(data.members)
      ? data.members
      : isRecord(data) && Array.isArray(data.items)
        ? data.items
        : []
  const out: MemberRow[] = []
  for (const item of arr) {
    if (!isRecord(item)) continue
    const id = readStr(item, ["id", "member_id", "memberId"])
    const email = readStr(item, ["email", "user_email", "userEmail"])
    const display = readStr(item, ["display_name", "displayName", "name", "full_name", "fullName"])
    const nameLabel = display || email || "—"
    const role = readStr(item, ["role", "member_role", "memberRole"]) || "—"
    const status = readStr(item, ["status", "member_status", "memberStatus"]) || "—"
    const createdAt =
      readStr(item, ["created_at", "createdAt", "joined_at", "joinedAt"]) || "—"
    if (id) out.push({ id, email: email || "—", nameLabel, role, status, createdAt, raw: item })
  }
  return out
}

function formatApiErrorMessage(err: unknown, fallback: string): string {
  try {
    return pickDetail(err)
  } catch {
    return fallback
  }
}

export function TeamSettingsWorkspace() {
  const [hasToken, setHasToken] = useState<boolean | null>(null)
  const [orgs, setOrgs] = useState<OrganizationRow[]>([])
  const [orgsBusy, setOrgsBusy] = useState(true)
  const [orgsError, setOrgsError] = useState("")

  const [activeOrgId, setActiveOrgId] = useState<string>("")

  const [members, setMembers] = useState<MemberRow[]>([])
  const [membersBusy, setMembersBusy] = useState(false)
  const [membersError, setMembersError] = useState("")

  const [createName, setCreateName] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState("")

  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteDisplayName, setInviteDisplayName] = useState("")
  const [inviteRole, setInviteRole] = useState<string>(ROLE_OPTIONS[2])
  const [inviteBusy, setInviteBusy] = useState(false)
  const [inviteError, setInviteError] = useState("")
  const [inviteInfo, setInviteInfo] = useState("")

  const [actionBusyId, setActionBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState("")

  const activeOrg = useMemo(() => orgs.find((o) => o.id === activeOrgId) ?? null, [orgs, activeOrgId])

  const refreshTokenState = useCallback(() => {
    setHasToken(Boolean(readStoredAuthToken()))
  }, [])

  useEffect(() => {
    refreshTokenState()
  }, [refreshTokenState])

  const loadOrganizations = useCallback(async () => {
    setOrgsBusy(true)
    setOrgsError("")
    try {
      const data = await apiFetch<unknown>("/organizations", { method: "GET" })
      const list = normalizeOrganizations(data)
      setOrgs(list)
      setActiveOrgId((prev) => {
        if (prev && list.some((o) => o.id === prev)) return prev
        return list[0]?.id ?? ""
      })
    } catch (err) {
      setOrgs([])
      setOrgsError(formatApiErrorMessage(err, "Could not load organizations."))
    } finally {
      setOrgsBusy(false)
    }
  }, [])

  useEffect(() => {
    void loadOrganizations()
  }, [loadOrganizations])

  const loadMembers = useCallback(async (organizationId: string) => {
    const oid = organizationId.trim()
    if (!oid) {
      setMembers([])
      return
    }
    setMembersBusy(true)
    setMembersError("")
    try {
      const data = await apiFetch<unknown>(`/organizations/${encodeURIComponent(oid)}/members`, {
        method: "GET",
      })
      setMembers(normalizeMembers(data))
    } catch (err) {
      setMembers([])
      setMembersError(formatApiErrorMessage(err, "Could not load members."))
    } finally {
      setMembersBusy(false)
    }
  }, [])

  useEffect(() => {
    void loadMembers(activeOrgId)
  }, [activeOrgId, loadMembers])

  async function submitCreateOrganization(ev: FormEvent) {
    ev.preventDefault()
    const name = createName.trim()
    if (!name) {
      setCreateError("Organization name is required.")
      return
    }
    setCreateBusy(true)
    setCreateError("")
    try {
      await apiFetch("/organizations", {
        method: "POST",
        body: { name },
      })
      setCreateName("")
      await loadOrganizations()
    } catch (err) {
      setCreateError(formatApiErrorMessage(err, "Create organization failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function submitInvite(ev: FormEvent) {
    ev.preventDefault()
    const oid = activeOrgId.trim()
    const email = inviteEmail.trim()
    if (!oid) {
      setInviteError("Select or create an organization first.")
      return
    }
    if (!email) {
      setInviteError("Email is required.")
      return
    }
    setInviteBusy(true)
    setInviteError("")
    setInviteInfo("")
    try {
      const body: Record<string, unknown> = {
        email,
        role: inviteRole,
      }
      const dn = inviteDisplayName.trim()
      if (dn) body.display_name = dn

      await apiFetch(`/organizations/${encodeURIComponent(oid)}/members`, {
        method: "POST",
        body,
      })
      setInviteEmail("")
      setInviteDisplayName("")
      setInviteInfo("Invitation submitted.")
      await loadMembers(oid)
    } catch (err) {
      setInviteError(formatApiErrorMessage(err, "Invite failed."))
    } finally {
      setInviteBusy(false)
    }
  }

  async function patchMemberRole(member: MemberRow, newRole: string) {
    const oid = activeOrgId.trim()
    if (!oid) return
    setActionBusyId(member.id)
    setActionError("")
    try {
      await apiFetch(`/organizations/${encodeURIComponent(oid)}/members/${encodeURIComponent(member.id)}`, {
        method: "PATCH",
        body: { role: newRole },
      })
      await loadMembers(oid)
    } catch (err) {
      setActionError(formatApiErrorMessage(err, "Update member failed."))
    } finally {
      setActionBusyId(null)
    }
  }

  const showLocalDevBanner = hasToken === false

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-slate)" }}
        >
          MolTrace · Settings · Team
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Team Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your organization and team members.</p>
      </div>

      {showLocalDevBanner ? (
        <AlertCard
          variant="info"
          title="Local development mode"
          description="No access token found in this browser session. Sign in to use organization APIs, or continue with backend authentication enabled."
        />
      ) : null}

      {orgsError ? <AlertCard variant="error" title="Organizations" description={orgsError} /> : null}
      {membersError ? <AlertCard variant="error" title="Members" description={membersError} /> : null}
      {createError ? <AlertCard variant="error" title="Create organization" description={createError} /> : null}
      {inviteError ? <AlertCard variant="error" title="Invite" description={inviteError} /> : null}
      {actionError ? <AlertCard variant="error" title="Member action" description={actionError} /> : null}

      {!orgsBusy && orgs.length === 0 ? (
        <ModuleCard
          accent="slate"
          eyebrow="Create"
          title="Create organization"
          icon={Building2}
          description="Create an organization to invite members and assign roles."
        >
          <div>
            <form className="space-y-4" onSubmit={submitCreateOrganization}>
              <div className="space-y-2">
                <Label htmlFor="team-create-org-name">Organization name</Label>
                <Input
                  id="team-create-org-name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  autoComplete="organization"
                />
              </div>
              <Button type="submit" disabled={createBusy}>
                {createBusy ? "Creating…" : "Create organization"}
              </Button>
            </form>
          </div>
        </ModuleCard>
      ) : null}

      {orgs.length > 0 ? (
        <ModuleCard
          accent="slate"
          eyebrow="Organization"
          title="Organization"
          icon={Building2}
          description="Active organization for member listing and invites."
        >
          <div className="space-y-4">
            {orgsBusy ? (
              <p className="text-sm text-muted-foreground">Loading organizations…</p>
            ) : (
              <>
                {orgs.length > 1 ? (
                  <div className="space-y-2">
                    <Label>Organization</Label>
                    <Select value={activeOrgId} onValueChange={setActiveOrgId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select organization" />
                      </SelectTrigger>
                      <SelectContent>
                        {orgs.map((o) => (
                          <SelectItem key={o.id} value={o.id}>
                            {o.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <p className="text-sm font-medium">{activeOrg?.name ?? "—"}</p>
                    <p className="font-mono text-[10px] text-muted-foreground break-all">{activeOrg?.id}</p>
                  </div>
                )}
              </>
            )}
          </div>
        </ModuleCard>
      ) : null}

      {orgs.length > 0 && activeOrgId ? (
        <>
          <ModuleCard
            accent="slate"
            eyebrow="Members"
            title="Team members"
            icon={Users}
            description="People with access to this organization."
          >
            <div className="space-y-2">
              {membersBusy ? (
                <p className="text-sm text-muted-foreground">Loading members…</p>
              ) : (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Name / email</TableHead>
                        <TableHead className="text-xs">Role</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Created</TableHead>
                        <TableHead className="text-xs text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {members.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="text-xs text-muted-foreground">
                            No members returned for this organization.
                          </TableCell>
                        </TableRow>
                      ) : (
                        members.map((m) => (
                          <TableRow key={m.id}>
                            <TableCell className="max-w-[14rem] text-xs">
                              <span className="font-medium">{m.nameLabel}</span>
                              <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground break-all">
                                {m.email}
                              </span>
                            </TableCell>
                            <TableCell className="text-xs">
                              <Badge variant="secondary" className="font-normal">
                                {m.role}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs">{m.status}</TableCell>
                            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{m.createdAt}</TableCell>
                            <TableCell className="text-right">
                              <Select
                                value={m.role}
                                disabled={actionBusyId === m.id}
                                onValueChange={(v) => {
                                  if (v === m.role) return
                                  void patchMemberRole(m, v)
                                }}
                              >
                                <SelectTrigger className="ml-auto h-8 w-[min(100%,9rem)] text-xs">
                                  <SelectValue placeholder="Role" />
                                </SelectTrigger>
                                <SelectContent>
                                  {ROLE_OPTIONS.map((r) => (
                                    <SelectItem key={r} value={r}>
                                      {r}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="slate"
            eyebrow="Invite"
            title="Invite member"
            icon={Mail}
            description="Send an invitation to join this organization."
          >
            <div>
              <form className="space-y-4" onSubmit={submitInvite}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="team-invite-email">Email</Label>
                    <Input
                      id="team-invite-email"
                      type="email"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      autoComplete="email"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="team-invite-display">Display name (optional)</Label>
                    <Input
                      id="team-invite-display"
                      value={inviteDisplayName}
                      onChange={(e) => setInviteDisplayName(e.target.value)}
                      autoComplete="name"
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Role</Label>
                  <Select value={inviteRole} onValueChange={setInviteRole}>
                    <SelectTrigger id="team-invite-role">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLE_OPTIONS.map((r) => (
                        <SelectItem key={r} value={r}>
                          {r}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" disabled={inviteBusy}>
                  {inviteBusy ? "Sending…" : "Invite member"}
                </Button>
                {inviteInfo ? <p className="text-sm text-muted-foreground">{inviteInfo}</p> : null}
              </form>
            </div>
          </ModuleCard>
        </>
      ) : null}

      <ModuleCard
        accent="slate"
        eyebrow="Roles"
        title="Roles"
        icon={KeyRound}
        description="How roles are typically used in MolTrace (exact permissions follow backend policy)."
      >
        <div className="space-y-2 text-sm text-muted-foreground">
          <p>
            <span className="font-medium text-foreground">owner</span> — Full control over organization settings and
            membership.
          </p>
          <p>
            <span className="font-medium text-foreground">admin</span> — Manage members and settings except destructive
            ownership transfers where restricted by policy.
          </p>
          <p>
            <span className="font-medium text-foreground">scientist</span> — Run analyses, manage projects and evidence
            within org scope.
          </p>
          <p>
            <span className="font-medium text-foreground">reviewer</span> — Review and approve workflows and reports per
            policy.
          </p>
          <p>
            <span className="font-medium text-foreground">viewer</span> — Read-only access to shared results where
            permitted.
          </p>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="amber"
        eyebrow="Permissions"
        title="Permissions"
        icon={ShieldAlert}
        description="Permission boundaries are enforced by the API."
      >
        <div className="space-y-3 text-sm text-muted-foreground">
          <p>
            Role changes and invitations only succeed when your account has sufficient privileges. If an action fails, the
            error message from the server explains the reason.
          </p>
          <Separator />
          <p className="text-xs">
            Do not share access tokens or invite links in unsecured channels. Suspend or adjust roles promptly when team
            membership changes.
          </p>
        </div>
      </ModuleCard>
    </div>
  )
}
