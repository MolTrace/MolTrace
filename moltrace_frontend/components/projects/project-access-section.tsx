"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { UserPlus } from "lucide-react"

const PROJECT_ACCESS_TOOLTIP =
  "Project access controls who can view, upload, analyze, review, and approve evidence for this project."

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

function formatApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    if (isRecord(d) && typeof d.message === "string") return d.message
    return err.message
  }
  if (err instanceof Error) return err.message
  return fallback
}

export type ProjectPermissionRow = {
  id: string
  email: string
  role: string
  addedAt: string
}

function normalizePermissionsPayload(data: unknown): ProjectPermissionRow[] {
  const arr = Array.isArray(data)
    ? data
    : isRecord(data) && Array.isArray(data.permissions)
      ? data.permissions
      : isRecord(data) && Array.isArray(data.items)
        ? data.items
        : []
  const out: ProjectPermissionRow[] = []
  for (const item of arr) {
    if (!isRecord(item)) continue
    const id = readStr(item, ["permission_id", "permissionId", "id"])
    const email = readStr(item, ["user_email", "userEmail", "email"])
    const role = readStr(item, ["role"]) || "—"
    const addedAt =
      readStr(item, ["created_at", "createdAt", "added_at", "addedAt", "granted_at", "grantedAt"]) || "—"
    if (id && email) out.push({ id, email, role, addedAt })
  }
  return out
}

type Props = {
  projectId: string
}

export function ProjectAccessSection({ projectId }: Props) {
  const pid = projectId.trim()

  const [rows, setRows] = useState<ProjectPermissionRow[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState("")

  const [addOpen, setAddOpen] = useState(false)
  const [addEmail, setAddEmail] = useState("")
  const [addRole, setAddRole] = useState<string>(ROLE_OPTIONS[2])
  const [addBusy, setAddBusy] = useState(false)
  const [addError, setAddError] = useState("")

  const [roleDraft, setRoleDraft] = useState<Record<string, string>>({})
  const [updateBusyId, setUpdateBusyId] = useState<string | null>(null)
  const [updateError, setUpdateError] = useState("")
  const [removeBusyId, setRemoveBusyId] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState("")

  const loadPermissions = useCallback(async () => {
    if (!pid) {
      setRows([])
      return
    }
    setLoading(true)
    setListError("")
    try {
      const data = await apiFetch<unknown>(`/projects/${encodeURIComponent(pid)}/permissions`, {
        method: "GET",
      })
      const list = normalizePermissionsPayload(data)
      setRows(list)
      const drafts: Record<string, string> = {}
      for (const r of list) drafts[r.id] = r.role
      setRoleDraft(drafts)
    } catch (err) {
      setRows([])
      setListError(formatApiError(err, "Could not load project permissions."))
    } finally {
      setLoading(false)
    }
  }, [pid])

  useEffect(() => {
    void loadPermissions()
  }, [loadPermissions])

  async function submitAddCollaborator() {
    if (!pid) return
    const email = addEmail.trim()
    if (!email) {
      setAddError("Email is required.")
      return
    }
    setAddBusy(true)
    setAddError("")
    try {
      await apiFetch(`/projects/${encodeURIComponent(pid)}/permissions`, {
        method: "POST",
        body: {
          email,
          role: addRole,
        },
      })
      setAddEmail("")
      setAddRole(ROLE_OPTIONS[2])
      setAddOpen(false)
      await loadPermissions()
    } catch (err) {
      setAddError(formatApiError(err, "Add collaborator failed."))
    } finally {
      setAddBusy(false)
    }
  }

  async function submitUpdateRole(row: ProjectPermissionRow) {
    if (!pid) return
    const next = roleDraft[row.id]?.trim()
    if (!next || next === row.role) return
    setUpdateBusyId(row.id)
    setUpdateError("")
    try {
      await apiFetch(`/projects/${encodeURIComponent(pid)}/permissions/${encodeURIComponent(row.id)}`, {
        method: "PATCH",
        body: { role: next },
      })
      await loadPermissions()
    } catch (err) {
      setUpdateError(formatApiError(err, "Update role failed."))
    } finally {
      setUpdateBusyId(null)
    }
  }

  async function submitRemove(row: ProjectPermissionRow) {
    if (!pid) return
    if (!window.confirm(`Remove access for ${row.email}?`)) return
    setRemoveBusyId(row.id)
    setRemoveError("")
    try {
      await apiFetch(`/projects/${encodeURIComponent(pid)}/permissions/${encodeURIComponent(row.id)}`, {
        method: "DELETE",
      })
      await loadPermissions()
    } catch (err) {
      setRemoveError(formatApiError(err, "Remove access failed."))
    } finally {
      setRemoveBusyId(null)
    }
  }

  if (!pid) return null

  return (
    <Card>
      <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <CardTitle className="flex flex-wrap items-center gap-2 text-lg">
            Project access
            <InfoTooltip content={PROJECT_ACCESS_TOOLTIP} label="About project access" />
          </CardTitle>
          <CardDescription>Collaborators and roles for this project.</CardDescription>
        </div>
        <Dialog open={addOpen} onOpenChange={setAddOpen}>
          <DialogTrigger asChild>
            <Button type="button" variant="secondary" size="sm" className="gap-2 self-start sm:self-auto shrink-0">
              <UserPlus className="h-4 w-4" />
              Add collaborator
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Add collaborator</DialogTitle>
              <DialogDescription>Grant access by email. The server must accept the invitation.</DialogDescription>
            </DialogHeader>
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="proj-access-email">Email</Label>
                <Input
                  id="proj-access-email"
                  type="email"
                  value={addEmail}
                  onChange={(e) => setAddEmail(e.target.value)}
                  autoComplete="email"
                />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={addRole} onValueChange={setAddRole}>
                  <SelectTrigger id="proj-access-add-role">
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
              {addError ? <p className="text-sm text-destructive">{addError}</p> : null}
            </div>
            <DialogFooter className="gap-2">
              <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
                Cancel
              </Button>
              <Button type="button" disabled={addBusy} onClick={() => void submitAddCollaborator()}>
                {addBusy ? "Adding…" : "Add collaborator"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="space-y-4">
        {listError ? (
          <Alert variant="destructive">
            <AlertTitle>Permissions</AlertTitle>
            <AlertDescription>{listError}</AlertDescription>
          </Alert>
        ) : null}
        {updateError ? (
          <Alert variant="destructive">
            <AlertTitle>Update role</AlertTitle>
            <AlertDescription>{updateError}</AlertDescription>
          </Alert>
        ) : null}
        {removeError ? (
          <Alert variant="destructive">
            <AlertTitle>Remove access</AlertTitle>
            <AlertDescription>{removeError}</AlertDescription>
          </Alert>
        ) : null}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading permissions…</p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs whitespace-nowrap">User email</TableHead>
                  <TableHead className="text-xs whitespace-nowrap">Role</TableHead>
                  <TableHead className="text-xs whitespace-nowrap">Added</TableHead>
                  <TableHead className="text-xs text-right whitespace-nowrap">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-sm text-muted-foreground">
                      No permissions returned for this project.
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((row) => {
                    const draft = roleDraft[row.id] ?? row.role
                    const dirty = draft.trim() !== row.role.trim()
                    return (
                      <TableRow key={row.id}>
                        <TableCell className="max-w-[14rem] font-mono text-xs break-all">{row.email}</TableCell>
                        <TableCell>
                          <Badge variant="secondary" className="font-normal">
                            {row.role}
                          </Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{row.addedAt}</TableCell>
                        <TableCell className="text-right">
                          <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-end">
                            <Select
                              value={draft}
                              onValueChange={(v) => setRoleDraft((prev) => ({ ...prev, [row.id]: v }))}
                            >
                              <SelectTrigger className="h-8 w-full min-w-[7rem] text-xs sm:w-[9rem]">
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
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="shrink-0"
                              disabled={!dirty || updateBusyId === row.id}
                              onClick={() => void submitUpdateRole(row)}
                            >
                              {updateBusyId === row.id ? "Updating…" : "Update role"}
                            </Button>
                            <Button
                              type="button"
                              variant="destructive"
                              size="sm"
                              className="shrink-0"
                              disabled={removeBusyId === row.id}
                              onClick={() => void submitRemove(row)}
                            >
                              {removeBusyId === row.id ? "Removing…" : "Remove access"}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
