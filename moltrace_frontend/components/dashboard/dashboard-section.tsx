"use client"

import { useState, type ReactNode } from "react"
import { ChevronDown, type LucideIcon } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

type DashboardSectionProps = {
  title: string
  description?: string
  icon?: LucideIcon
  defaultOpen?: boolean
  badge?: ReactNode
  children: ReactNode
}

export function DashboardSection({
  title,
  description,
  icon: Icon,
  defaultOpen = false,
  badge,
  children,
}: DashboardSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-4">
      <CollapsibleTrigger
        className="group flex w-full items-center justify-between gap-3 rounded-md border-b border-border/60 px-1 pb-2 pt-1 text-left transition-colors hover:bg-muted/30"
        aria-label={`${open ? "Collapse" : "Expand"} ${title} section`}
      >
        <div className="flex min-w-0 items-center gap-2">
          {Icon ? <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden /> : null}
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </h2>
          {badge ? <span className="ml-1">{badge}</span> : null}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {description ? (
            <p className="hidden text-xs text-muted-foreground sm:block">{description}</p>
          ) : null}
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
              open && "rotate-180",
            )}
            aria-hidden
          />
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4">{children}</CollapsibleContent>
    </Collapsible>
  )
}
