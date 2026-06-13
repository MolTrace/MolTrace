"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Badge } from "@/components/ui/badge"
import { ThemeToggle } from "@/components/theme-toggle"
import { TenantSelector } from "@/components/app/tenant-selector"
import { useIsMobile } from "@/hooks/use-mobile"
import { useOptionalOverviewData } from "@/components/app/overview-data-context"
import { apiFetch, AUTH_TOKEN_STORAGE_KEY } from "@/lib/api/client"
import { fetchAiEvidenceQueue } from "@/lib/api/ai-evidence"
import { useTenant } from "@/src/lib/tenant/tenant-context"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"
import {
  Search,
  Bell,
  Sparkles,
  User,
  LogOut,
  Settings,
  HelpCircle,
  FolderOpen,
  Waves,
  FlaskConical,
  CheckCircle2,
  Loader2,
  Inbox,
  Brain,
  Shield,
} from "lucide-react"

interface AppTopbarProps {
  onToggleEvidenceQueue: () => void
}

// ── Tiny helpers for parsing arbitrary backend rows ──────────────────────────
function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}
function asArray(v: unknown): unknown[] {
  if (Array.isArray(v)) return v
  if (!isRecord(v)) return []
  for (const k of ["items", "results", "rows", "data"]) {
    const inner = v[k]
    if (Array.isArray(inner)) return inner
  }
  return []
}
function readStr(row: unknown, key: string): string | undefined {
  if (!isRecord(row)) return undefined
  const v = row[key]
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return undefined
}
function readNum(row: unknown, key: string): number | undefined {
  if (!isRecord(row)) return undefined
  const v = row[key]
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
  return undefined
}

type SearchProject = { id: number; name: string }
type SearchSession = { id: number | string; sample_id: string | undefined; project_id: number | undefined }
type SearchReaction = { id: number; name: string }

type NotificationItem = {
  id: string
  title: string
  description: string
  href: string
  icon: typeof Bell
  accent: string
}

export function AppTopbar({ onToggleEvidenceQueue }: AppTopbarProps) {
  const [commandOpen, setCommandOpen] = useState(false)
  const router = useRouter()
  const isMobile = useIsMobile()
  const overview = useOptionalOverviewData()
  const tenantContext = useTenant()
  const tenantDisplayName = tenantContext.tenantDisplayName

  // ── Real AI Queue badge count: prefer fetched count, fall back to overview ──
  const [aiQueueCount, setAiQueueCount] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    void fetchAiEvidenceQueue(100)
      .then((rows) => {
        if (!cancelled) setAiQueueCount(rows.length)
      })
      .catch(() => {
        // Leave as null so the fallback (overview metrics) is used
      })
    return () => {
      cancelled = true
    }
  }, [])
  const overviewQueueCount = overview?.metrics?.evidenceQueue
  const badgeCount =
    aiQueueCount != null
      ? aiQueueCount
      : typeof overviewQueueCount === "number" && Number.isFinite(overviewQueueCount)
      ? overviewQueueCount
      : 0
  const badgeLabel = badgeCount > 99 ? "99+" : String(badgeCount)

  // ── Real notifications: pull from regulatory + AI evidence queues ──
  const [notifLoading, setNotifLoading] = useState(false)
  const [notifs, setNotifs] = useState<NotificationItem[]>([])
  const loadNotifications = useCallback(async () => {
    setNotifLoading(true)
    try {
      const [regRaw, aiRows] = await Promise.all([
        apiFetch<unknown>("/regulatory/notifications?limit=20", { method: "GET" }).catch(() => []),
        fetchAiEvidenceQueue(20).catch(() => []),
      ])
      const regItems: NotificationItem[] = asArray(regRaw)
        .filter(isRecord)
        .slice(0, 5)
        .map((row, idx) => {
          const id = readNum(row, "id")
          const changeId = readNum(row, "change_id")
          const title = readStr(row, "title") ?? readStr(row, "kind") ?? "Regulatory notification"
          const description =
            readStr(row, "summary") ??
            readStr(row, "body") ??
            readStr(row, "kind") ??
            "Regulatory signal awaiting review"
          // Prefer linking to the change detail when available; otherwise to the notifications list
          const href =
            changeId != null
              ? `/regulatory/changes/${changeId}`
              : id != null
              ? `/regulatory/notifications`
              : `/regulatory/notifications`
          return {
            id: `reg-${id ?? idx}`,
            title,
            description,
            href,
            icon: Shield,
            accent: "var(--mt-cyan)",
          }
        })
      const aiItems: NotificationItem[] = aiRows.slice(0, 5).map((item) => ({
        id: `ai-${item.id}`,
        title: `AI evidence ${item.id} · ${item.module}`,
        description: item.summary || `${item.entity_type} ${item.entity_id} awaiting review`,
        href: `/spectracheck`, // Open AI Evidence Queue panel via SpectraCheck (where it surfaces)
        icon: Brain,
        accent: "var(--mt-teal)",
      }))
      setNotifs([...regItems, ...aiItems])
    } finally {
      setNotifLoading(false)
    }
  }, [])
  useEffect(() => {
    void loadNotifications()
  }, [loadNotifications])
  const notifBadgeCount = notifs.length
  const notifBadgeLabel = notifBadgeCount > 9 ? "9+" : String(notifBadgeCount)

  // ── Real search: load projects + reaction projects + recent SpectraCheck sessions ──
  const [searchProjects, setSearchProjects] = useState<SearchProject[]>([])
  const [searchReactions, setSearchReactions] = useState<SearchReaction[]>([])
  const [searchSessions, setSearchSessions] = useState<SearchSession[]>([])
  const [searchLoading, setSearchLoading] = useState(false)

  useEffect(() => {
    if (!commandOpen) return
    let cancelled = false
    setSearchLoading(true)
    void Promise.all([
      apiFetch<unknown>("/projects?limit=20", { method: "GET" }).catch(() => []),
      apiFetch<unknown>("/reaction-projects?limit=20", { method: "GET" }).catch(() => []),
      apiFetch<unknown>("/spectracheck/sessions?limit=20", { method: "GET" }).catch(() => []),
    ])
      .then(([pRaw, rRaw, sRaw]) => {
        if (cancelled) return
        const projects: SearchProject[] = asArray(pRaw)
          .filter(isRecord)
          .map((row) => {
            const id = readNum(row, "id")
            const name =
              readStr(row, "name") ?? readStr(row, "project_name") ?? readStr(row, "title") ?? null
            if (id == null || !name) return null
            return { id, name }
          })
          .filter((v): v is SearchProject => v !== null)
        const reactions: SearchReaction[] = asArray(rRaw)
          .filter(isRecord)
          .map((row) => {
            const id = readNum(row, "id")
            const name = readStr(row, "name") ?? readStr(row, "title") ?? null
            if (id == null || !name) return null
            return { id, name }
          })
          .filter((v): v is SearchReaction => v !== null)
        const sessions: SearchSession[] = asArray(sRaw)
          .filter(isRecord)
          .map((row) => {
            const id = readStr(row, "id") ?? readNum(row, "id")
            if (id == null) return null
            return {
              id,
              sample_id: readStr(row, "sample_id"),
              project_id: readNum(row, "project_id"),
            }
          })
          .filter((v): v is SearchSession => v !== null)
        setSearchProjects(projects)
        setSearchReactions(reactions)
        setSearchSessions(sessions)
      })
      .finally(() => {
        if (!cancelled) setSearchLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [commandOpen])

  const hasAnyResults = useMemo(
    () => searchProjects.length + searchReactions.length + searchSessions.length > 0,
    [searchProjects, searchReactions, searchSessions],
  )

  // ── Sign out: clear auth token + tenant id + push to /sign-in ──
  const handleSignOut = useCallback(() => {
    clearSpectraCheckRuntimeState()
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
        window.localStorage.removeItem("moltrace.tenant_id")
        window.sessionStorage.clear()
      } catch {
        // best-effort cleanup
      }
    }
    router.push("/sign-in")
  }, [router])

  return (
    <>
      <header className="flex h-14 items-center justify-between border-b bg-background px-4">
        <div className="flex items-center gap-4">
          {isMobile ? (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open search"
              onClick={() => setCommandOpen(true)}
            >
              <Search className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              variant="outline"
              className="w-64 justify-start gap-2 text-muted-foreground"
              onClick={() => setCommandOpen(true)}
              aria-label="Search projects, samples, or analyses"
            >
              <Search className="h-4 w-4" />
              <span className="flex-1 text-left">Search projects...</span>
              <kbd className="pointer-events-none flex h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100">
                <span className="text-xs">⌘</span>K
              </kbd>
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isMobile ? (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Toggle AI Evidence Queue"
              onClick={onToggleEvidenceQueue}
            >
              <Sparkles className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="gap-2 font-mono text-xs font-semibold uppercase tracking-[0.06em]"
              onClick={onToggleEvidenceQueue}
              aria-label="Toggle AI Evidence Queue"
            >
              <Sparkles className="h-4 w-4" style={{ color: "var(--mt-teal)" }} aria-hidden />
              <span>AI Queue</span>
              <Badge
                variant="secondary"
                className="ml-1 h-5 px-1.5 font-mono"
                style={{ backgroundColor: "var(--mt-teal-soft)", color: "var(--mt-teal)" }}
              >
                {badgeLabel}
              </Badge>
            </Button>
          )}

          <TenantSelector />

          <ThemeToggle />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative" aria-label="Open notifications">
                <Bell className="h-4 w-4" />
                {notifBadgeCount > 0 ? (
                  <span
                    className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full px-1 font-mono text-[10px] font-bold"
                    style={{ backgroundColor: "var(--mt-amber)", color: "#04080F" }}
                  >
                    {notifBadgeLabel}
                  </span>
                ) : null}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-96">
              <DropdownMenuLabel className="flex items-center justify-between">
                <span>Notifications</span>
                {notifLoading ? <Loader2 className="size-3 animate-spin" aria-hidden /> : null}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {!notifLoading && notifs.length === 0 ? (
                <div className="flex flex-col items-center gap-1 px-4 py-6 text-center">
                  <Inbox className="size-5 text-muted-foreground/60" aria-hidden />
                  <p className="text-xs text-muted-foreground">No new notifications.</p>
                </div>
              ) : null}
              {notifs.slice(0, 8).map((n) => {
                const Icon = n.icon
                return (
                  <DropdownMenuItem key={n.id} asChild>
                    <Link
                      href={n.href}
                      className="flex w-full cursor-pointer items-start gap-2"
                    >
                      <Icon className="mt-0.5 size-4 shrink-0" style={{ color: n.accent }} aria-hidden />
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <span className="truncate font-medium">{n.title}</span>
                        <span className="line-clamp-2 text-xs text-muted-foreground">{n.description}</span>
                      </div>
                    </Link>
                  </DropdownMenuItem>
                )
              })}
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/regulatory/notifications" className="flex w-full cursor-pointer items-center gap-2">
                  <Bell className="size-4" aria-hidden />
                  View all notifications
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Open profile menu">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary">
                  <User className="h-4 w-4" />
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex flex-col">
                  <span>{tenantDisplayName || "MolTrace user"}</span>
                  <span className="text-xs font-normal text-muted-foreground">Active workspace</span>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/dashboard/settings" className="flex w-full cursor-pointer items-center">
                  <User className="mr-2 h-4 w-4" />
                  Profile
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/dashboard/settings" className="flex w-full cursor-pointer items-center">
                  <Settings className="mr-2 h-4 w-4" />
                  Settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link
                  href="https://docs.moltrace.co"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex w-full cursor-pointer items-center"
                >
                  <HelpCircle className="mr-2 h-4 w-4" />
                  Help & Support
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive"
                onSelect={(e) => {
                  e.preventDefault()
                  handleSignOut()
                }}
              >
                <LogOut className="mr-2 h-4 w-4" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <CommandDialog open={commandOpen} onOpenChange={setCommandOpen}>
        <CommandInput placeholder="Search projects, samples, or analyses..." />
        <CommandList>
          {searchLoading ? (
            <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
              <Loader2 className="size-3 animate-spin" aria-hidden />
              Loading…
            </div>
          ) : null}
          {!searchLoading && !hasAnyResults ? (
            <CommandEmpty>No results found. Try a different search.</CommandEmpty>
          ) : null}
          {searchProjects.length > 0 ? (
            <CommandGroup heading="Projects">
              {searchProjects.slice(0, 8).map((p) => (
                <CommandItem
                  key={`proj-${p.id}`}
                  value={`project ${p.name}`}
                  onSelect={() => {
                    router.push(`/projects/${p.id}`)
                    setCommandOpen(false)
                  }}
                >
                  <FolderOpen className="mr-2 h-4 w-4" />
                  <span>{p.name}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {searchReactions.length > 0 ? (
            <>
              {searchProjects.length > 0 ? <CommandSeparator /> : null}
              <CommandGroup heading="Reaction projects">
                {searchReactions.slice(0, 8).map((p) => (
                  <CommandItem
                    key={`rxn-${p.id}`}
                    value={`reaction ${p.name}`}
                    onSelect={() => {
                      router.push(`/reactions/${p.id}`)
                      setCommandOpen(false)
                    }}
                  >
                    <FlaskConical className="mr-2 h-4 w-4" />
                    <span>{p.name}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
          {searchSessions.length > 0 ? (
            <>
              {searchProjects.length + searchReactions.length > 0 ? <CommandSeparator /> : null}
              <CommandGroup heading="Recent SpectraCheck sessions">
                {searchSessions.slice(0, 8).map((s) => (
                  <CommandItem
                    key={`sess-${s.id}`}
                    value={`session ${s.sample_id ?? s.id}`}
                    onSelect={() => {
                      const params = new URLSearchParams()
                      if (s.project_id != null) params.set("projectId", String(s.project_id))
                      if (s.sample_id) params.set("sampleId", s.sample_id)
                      const qs = params.toString()
                      router.push(qs ? `/spectracheck?${qs}` : `/spectracheck`)
                      setCommandOpen(false)
                    }}
                  >
                    <Waves className="mr-2 h-4 w-4" />
                    <span>{s.sample_id ?? `Session ${s.id}`}</span>
                    {s.project_id != null ? (
                      <Badge variant="secondary" className="ml-auto">
                        proj {s.project_id}
                      </Badge>
                    ) : null}
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
          <CommandSeparator />
          <CommandGroup heading="Quick navigation">
            <CommandItem
              onSelect={() => {
                router.push("/dashboard")
                setCommandOpen(false)
              }}
            >
              <CheckCircle2 className="mr-2 h-4 w-4" />
              <span>Dashboard</span>
            </CommandItem>
            <CommandItem
              onSelect={() => {
                router.push("/spectracheck")
                setCommandOpen(false)
              }}
            >
              <Waves className="mr-2 h-4 w-4" />
              <span>Open SpectraCheck</span>
            </CommandItem>
            <CommandItem
              onSelect={() => {
                router.push("/regulatory")
                setCommandOpen(false)
              }}
            >
              <Shield className="mr-2 h-4 w-4" />
              <span>Open ComplianceCore</span>
            </CommandItem>
            <CommandItem
              onSelect={() => {
                router.push("/reactions")
                setCommandOpen(false)
              }}
            >
              <FlaskConical className="mr-2 h-4 w-4" />
              <span>Open Reaction Optimization</span>
            </CommandItem>
            <CommandItem
              onSelect={() => {
                router.push("/actions")
                setCommandOpen(false)
              }}
            >
              <Inbox className="mr-2 h-4 w-4" />
              <span>Open Action Queue</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  )
}
