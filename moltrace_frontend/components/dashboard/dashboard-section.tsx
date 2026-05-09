"use client"

import { useState, type CSSProperties, type ReactNode } from "react"
import { ChevronDown, type LucideIcon } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

export type DashboardSectionAccent = "teal" | "cyan" | "violet"

type DashboardSectionProps = {
  title: string
  description?: string
  icon?: LucideIcon
  defaultOpen?: boolean
  badge?: ReactNode
  accent?: DashboardSectionAccent
  eyebrow?: string
  children: ReactNode
}

const ACCENT_VAR: Record<DashboardSectionAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
}

export function DashboardSection({
  title,
  description,
  icon: Icon,
  defaultOpen = false,
  badge,
  accent,
  eyebrow,
  children,
}: DashboardSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const accentColor = accent ? ACCENT_VAR[accent] : undefined

  const triggerStyle: CSSProperties | undefined = accentColor
    ? { borderLeft: `2px solid ${accentColor}` }
    : undefined

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-4">
      <CollapsibleTrigger
        className={cn(
          "group flex w-full items-center justify-between gap-3 rounded-md border-b border-border/60 pb-2 pt-1 pr-1 text-left transition-colors hover:bg-muted/30",
          accentColor ? "pl-3" : "pl-1",
        )}
        style={triggerStyle}
        aria-label={`${open ? "Collapse" : "Expand"} ${title} section`}
      >
        <div className="flex min-w-0 flex-col gap-0.5">
          {eyebrow ? (
            <span
              className="font-mono text-[9px] font-bold uppercase tracking-[0.22em]"
              style={{ color: accentColor ?? "var(--mt-teal)" }}
            >
              {eyebrow}
            </span>
          ) : null}
          <div className="flex min-w-0 items-center gap-2">
            {Icon ? (
              <Icon
                className="h-4 w-4 shrink-0"
                style={{ color: accentColor ?? "var(--mt-teal)", opacity: 0.9 }}
                aria-hidden
              />
            ) : null}
            <h2 className="font-mono text-sm font-bold uppercase tracking-[0.18em] text-foreground">
              {title}
            </h2>
            {badge ? <span className="ml-1">{badge}</span> : null}
          </div>
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
