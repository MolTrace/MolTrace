"use client"

import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { apiFetch } from "@/lib/api/client"

type BackendStatus = "checking" | "connected" | "unavailable"

export function BackendStatusIndicator() {
  const [status, setStatus] = useState<BackendStatus>("checking")

  useEffect(() => {
    let active = true

    apiFetch<unknown>("/openapi.json")
      .then(() => {
        if (active) setStatus("connected")
      })
      .catch(() => {
        if (active) setStatus("unavailable")
      })

    return () => {
      active = false
    }
  }, [])

  if (status === "checking") {
    return (
      <Badge variant="outline" className="gap-1 text-muted-foreground">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
        Checking backend
      </Badge>
    )
  }

  if (status === "connected") {
    return (
      <Badge variant="outline" className="gap-1 border-success/50 text-success">
        <span className="h-1.5 w-1.5 rounded-full bg-success" />
        Backend connected
      </Badge>
    )
  }

  return (
    <Badge variant="outline" className="gap-1 border-warning/50 text-warning">
      <span className="h-1.5 w-1.5 rounded-full bg-warning" />
      Backend unavailable
    </Badge>
  )
}
