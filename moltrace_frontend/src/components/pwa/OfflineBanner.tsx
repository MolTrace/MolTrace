"use client"

import { useEffect, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"

export function OfflineBanner() {
  const [mounted, setMounted] = useState(false)
  const [online, setOnline] = useState(true)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    setMounted(true)
    const setFromNavigator = () => {
      setOnline(navigator.onLine)
      if (navigator.onLine) {
        setDismissed(false)
      }
    }
    setFromNavigator()
    window.addEventListener("online", setFromNavigator)
    window.addEventListener("offline", setFromNavigator)
    return () => {
      window.removeEventListener("online", setFromNavigator)
      window.removeEventListener("offline", setFromNavigator)
    }
  }, [])

  if (!mounted) return null
  if (online || dismissed) return null

  return (
    <div className="sticky top-0 z-40 border-b bg-warning/10 text-warning">
      <div className="mx-auto flex min-h-10 max-w-screen-2xl items-center gap-2 px-3 py-2 text-sm">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <p className="min-w-0 flex-1">
          Offline mode: backend-powered scientific analysis and report generation are unavailable.
        </p>
        <Button type="button" size="sm" variant="ghost" className="h-8 px-2 text-warning" onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}
