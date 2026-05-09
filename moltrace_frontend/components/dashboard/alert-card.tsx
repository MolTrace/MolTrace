"use client"

import type { CSSProperties, ReactNode } from "react"
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

export type AlertCardVariant = "info" | "success" | "warning" | "error"

const VARIANT_COLOR: Record<AlertCardVariant, string> = {
  info: "var(--mt-cyan)",
  success: "var(--mt-green)",
  warning: "var(--mt-amber)",
  error: "var(--mt-red)",
}

const VARIANT_BG: Record<AlertCardVariant, string> = {
  info: "var(--mt-cyan-soft)",
  success: "var(--mt-green-soft)",
  warning: "var(--mt-amber-soft)",
  error: "var(--mt-red-soft)",
}

const VARIANT_ICON: Record<AlertCardVariant, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: AlertCircle,
}

type AlertCardProps = {
  variant?: AlertCardVariant
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
  role?: "alert" | "status"
  children?: ReactNode
}

export function AlertCard({
  variant = "info",
  icon,
  title,
  description,
  action,
  className,
  role = "status",
  children,
}: AlertCardProps) {
  const color = VARIANT_COLOR[variant]
  const bg = VARIANT_BG[variant]
  const Icon = icon ?? VARIANT_ICON[variant]

  const style: CSSProperties = {
    borderLeft: `4px solid ${color}`,
    background: bg,
  }

  return (
    <div
      role={role}
      className={cn(
        "rounded-r-lg border border-border/40 px-4 py-3 text-sm",
        className,
      )}
      style={style}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <Icon
            className="h-4 w-4 shrink-0 translate-y-0.5"
            style={{ color }}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <p
              className="font-mono text-xs font-bold uppercase tracking-[0.12em]"
              style={{ color }}
            >
              {title}
            </p>
            {description ? (
              <p className="mt-1 leading-relaxed text-foreground/90">{description}</p>
            ) : null}
          </div>
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children ? <div className="mt-3 pl-7">{children}</div> : null}
    </div>
  )
}
