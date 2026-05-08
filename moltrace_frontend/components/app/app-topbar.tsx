"use client"

import { useState } from "react"
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
} from "@/components/ui/command"
import { Badge } from "@/components/ui/badge"
import { ThemeToggle } from "@/components/theme-toggle"
import { TenantSelector } from "@/components/app/tenant-selector"
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
} from "lucide-react"
import { useRouter } from "next/navigation"

interface AppTopbarProps {
  onToggleEvidenceQueue: () => void
}

export function AppTopbar({ onToggleEvidenceQueue }: AppTopbarProps) {
  const [commandOpen, setCommandOpen] = useState(false)
  const router = useRouter()

  return (
    <>
      <header className="flex h-14 items-center justify-between border-b bg-background px-4">
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            className="hidden w-64 justify-start gap-2 text-muted-foreground sm:flex"
            onClick={() => setCommandOpen(true)}
          >
            <Search className="h-4 w-4" />
            <span className="flex-1 text-left">Search projects...</span>
            <kbd className="pointer-events-none hidden h-5 select-none items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
              <span className="text-xs">⌘</span>K
            </kbd>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="sm:hidden"
            onClick={() => setCommandOpen(true)}
          >
            <Search className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="hidden gap-2 sm:flex"
            onClick={onToggleEvidenceQueue}
          >
            <Sparkles className="h-4 w-4" />
            <span>AI Queue</span>
            <Badge variant="secondary" className="ml-1 h-5 px-1.5">3</Badge>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="sm:hidden"
            onClick={onToggleEvidenceQueue}
          >
            <Sparkles className="h-4 w-4" />
          </Button>

          <TenantSelector />

          <ThemeToggle />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative">
                <Bell className="h-4 w-4" />
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[10px] font-medium text-accent-foreground">
                  2
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80">
              <DropdownMenuLabel>Notifications</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="flex flex-col items-start gap-1">
                <span className="font-medium">Analysis Complete</span>
                <span className="text-xs text-muted-foreground">
                  Sample NMR-2024-0847 ready for review
                </span>
              </DropdownMenuItem>
              <DropdownMenuItem className="flex flex-col items-start gap-1">
                <span className="font-medium">Model Update</span>
                <span className="text-xs text-muted-foreground">
                  Spectroscopy model v2.4.1 deployed
                </span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary">
                  <User className="h-4 w-4" />
                </div>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel>
                <div className="flex flex-col">
                  <span>Dr. Sarah Chen</span>
                  <span className="text-xs font-normal text-muted-foreground">
                    sarah.chen@pharma.com
                  </span>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem>
                <User className="mr-2 h-4 w-4" />
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Settings className="mr-2 h-4 w-4" />
                Settings
              </DropdownMenuItem>
              <DropdownMenuItem>
                <HelpCircle className="mr-2 h-4 w-4" />
                Help & Support
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-destructive">
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
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Recent Projects">
            <CommandItem onSelect={() => { router.push("/dashboard/projects"); setCommandOpen(false) }}>
              <FolderOpen className="mr-2 h-4 w-4" />
              <span>API-2024-Q4-Development</span>
            </CommandItem>
            <CommandItem onSelect={() => { router.push("/dashboard/projects"); setCommandOpen(false) }}>
              <FolderOpen className="mr-2 h-4 w-4" />
              <span>Process-Optimization-Batch-12</span>
            </CommandItem>
          </CommandGroup>
          <CommandGroup heading="Recent Analyses">
            <CommandItem onSelect={() => { router.push("/spectracheck"); setCommandOpen(false) }}>
              <Waves className="mr-2 h-4 w-4" />
              <span>NMR-2024-0847</span>
              <Badge variant="secondary" className="ml-auto">Review</Badge>
            </CommandItem>
            <CommandItem onSelect={() => { router.push("/reactions"); setCommandOpen(false) }}>
              <FlaskConical className="mr-2 h-4 w-4" />
              <span>RXN-OPT-2024-156</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  )
}
