"use client"

import Link from "next/link"
import type { CSSProperties, ReactNode } from "react"
import { ArrowRight, type LucideIcon } from "lucide-react"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type ModuleCardAccent = "teal" | "cyan" | "violet" | "amber"

const ACCENT_VAR: Record<ModuleCardAccent, string> = {
  teal: "var(--mt-teal)",
  cyan: "var(--mt-cyan)",
  violet: "var(--mt-violet)",
  amber: "var(--mt-amber)",
}

type ModuleCardProps = {
  accent?: ModuleCardAccent
  eyebrow?: string
  title: ReactNode
  icon?: LucideIcon
  description?: ReactNode
  badge?: ReactNode
  href?: string
  ctaLabel?: string
  className?: string
  children?: ReactNode
}

export function ModuleCard({
  accent = "teal",
  eyebrow,
  title,
  icon: Icon,
  description,
  badge,
  href,
  ctaLabel,
  className,
  children,
}: ModuleCardProps) {
  const accentColor = ACCENT_VAR[accent]
  const cardStyle: CSSProperties = {
    borderTop: `3px solid ${accentColor}`,
  }

  return (
    <Card
      className={cn(
        "group relative h-full overflow-hidden rounded-xl py-0 transition-all duration-200",
        href && "hover:-translate-y-px hover:border-foreground/20 hover:shadow-md",
        className,
      )}
      style={cardStyle}
    >
      {badge ? (
        <div className="absolute right-4 top-4 z-10">{badge}</div>
      ) : null}

      <CardHeader className="gap-1 pt-5 pb-2">
        {eyebrow ? (
          <span
            className="font-mono text-[9px] font-bold uppercase tracking-[0.2em]"
            style={{ color: accentColor }}
          >
            {eyebrow}
          </span>
        ) : null}
        <div className="flex items-center gap-2">
          {Icon ? (
            <Icon
              className="h-4 w-4 shrink-0"
              style={{ color: accentColor }}
              aria-hidden
            />
          ) : null}
          <h3 className="font-mono text-base font-bold tracking-tight text-foreground">
            {title}
          </h3>
        </div>
        {description ? (
          <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
        ) : null}
      </CardHeader>

      {children ? (
        <CardContent className="space-y-4 pb-4 text-sm">{children}</CardContent>
      ) : null}

      {href && ctaLabel ? (
        <div className="border-t border-border/60 px-6 py-3">
          <Link
            href={href}
            className="inline-flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.12em] transition-colors"
            style={{ color: accentColor }}
            aria-label={ctaLabel}
          >
            {ctaLabel}
            <ArrowRight
              className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
              aria-hidden
            />
          </Link>
        </div>
      ) : null}
    </Card>
  )
}
