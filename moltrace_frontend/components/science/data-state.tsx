"use client"

import type { ReactNode } from "react"
import { AlertCircle, CircleDashed, Database, FlaskConical } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export type DataStateKind = "live" | "loading" | "empty" | "unavailable" | "demo"

function stateLabel(state: DataStateKind): string {
  switch (state) {
    case "live":
      return "Live data"
    case "loading":
      return "Loading"
    case "empty":
      return "No data"
    case "unavailable":
      return "Unavailable"
    case "demo":
      return "Demo data."
    default:
      return state
  }
}

function stateClass(state: DataStateKind): string {
  switch (state) {
    case "live":
      return "border-success/50 bg-success/10 text-success"
    case "loading":
      return "border-primary/40 bg-primary/10 text-primary"
    case "empty":
      return "border-muted-foreground/30 text-muted-foreground"
    case "unavailable":
      return "border-warning/60 bg-warning/10 text-warning-foreground"
    case "demo":
      return "border-accent/50 bg-accent/10 text-accent"
    default:
      return ""
  }
}

function stateIcon(state: DataStateKind) {
  switch (state) {
    case "live":
      return <Database className="h-3.5 w-3.5" aria-hidden />
    case "loading":
      return <CircleDashed className="h-3.5 w-3.5 animate-spin" aria-hidden />
    case "empty":
      return <FlaskConical className="h-3.5 w-3.5" aria-hidden />
    case "unavailable":
      return <AlertCircle className="h-3.5 w-3.5" aria-hidden />
    case "demo":
      return <FlaskConical className="h-3.5 w-3.5" aria-hidden />
    default:
      return null
  }
}

export function DataStateBadge({ state, className }: { state: DataStateKind; className?: string }) {
  return (
    <Badge variant="outline" className={cn("gap-1 font-normal", stateClass(state), className)}>
      {stateIcon(state)}
      {stateLabel(state)}
    </Badge>
  )
}

export function DataState({
  state,
  title,
  description,
  children,
  className,
}: {
  state: DataStateKind
  title: ReactNode
  description?: ReactNode
  children?: ReactNode
  className?: string
}) {
  return (
    <Card className={cn("border-dashed bg-muted/20", className)}>
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{title}</CardTitle>
          <DataStateBadge state={state} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        {description ? <p>{description}</p> : null}
        {children}
      </CardContent>
    </Card>
  )
}
