"use client"

import Link from "next/link"
import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type KpiCardSeverity = "neutral" | "warning" | "critical" | "success"

type KpiCardProps = {
  title: string
  icon: LucideIcon
  value: ReactNode
  sub?: ReactNode
  href?: string
  severity?: KpiCardSeverity
}

const SEVERITY_CARD_CLASS: Record<KpiCardSeverity, string> = {
  neutral: "",
  warning: "border-warning/40 bg-warning/5",
  critical: "border-destructive/40 bg-destructive/5",
  success: "border-success/40 bg-success/5",
}

const SEVERITY_ICON_CLASS: Record<KpiCardSeverity, string> = {
  neutral: "text-muted-foreground",
  warning: "text-warning",
  critical: "text-destructive",
  success: "text-success",
}

export function KpiCard({
  title,
  icon: Icon,
  value,
  sub,
  href,
  severity = "neutral",
}: KpiCardProps) {
  const card = (
    <Card
      className={cn(
        "h-full",
        SEVERITY_CARD_CLASS[severity],
        href && "transition-colors hover:border-foreground/20 hover:bg-muted/40",
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={cn("h-4 w-4", SEVERITY_ICON_CLASS[severity])} aria-hidden />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub}
      </CardContent>
    </Card>
  )
  if (href) {
    return (
      <Link
        href={href}
        className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        aria-label={`${title} — open detail`}
      >
        {card}
      </Link>
    )
  }
  return card
}
