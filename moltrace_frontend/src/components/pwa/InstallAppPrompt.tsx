"use client"

import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

const DISMISS_KEY = "moltrace:pwa-install-prompt-dismissed-at"
const DISMISS_WINDOW_MS = 1000 * 60 * 60 * 24 * 7

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>
}

function dismissedRecently(): boolean {
  if (typeof window === "undefined") return true
  const raw = window.localStorage.getItem(DISMISS_KEY)
  if (!raw) return false
  const ts = Number.parseInt(raw, 10)
  if (!Number.isFinite(ts)) return false
  return Date.now() - ts < DISMISS_WINDOW_MS
}

export function InstallAppPrompt() {
  const [mounted, setMounted] = useState(false)
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null)
  const [hidden, setHidden] = useState(true)
  const [busy, setBusy] = useState(false)
  const [isInstalled, setIsInstalled] = useState(false)

  useEffect(() => {
    setMounted(true)
    const detectInstalled = () => {
      const standalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        (typeof navigator !== "undefined" && "standalone" in navigator && Boolean((navigator as Navigator & { standalone?: boolean }).standalone))
      setIsInstalled(standalone)
      return standalone
    }
    detectInstalled()
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker.register("/sw.js").catch(() => {
        // ignore registration failures
      })
    }
    if (dismissedRecently()) {
      setHidden(true)
    }
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault()
      const installed = detectInstalled()
      if (installed) return
      setDeferredPrompt(event as BeforeInstallPromptEvent)
      if (!dismissedRecently()) {
        setHidden(false)
      }
    }
    const onAppInstalled = () => {
      setDeferredPrompt(null)
      setHidden(true)
      setIsInstalled(true)
      try {
        window.localStorage.removeItem(DISMISS_KEY)
      } catch {
        // ignore storage failures
      }
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt)
    window.addEventListener("appinstalled", onAppInstalled)
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt)
      window.removeEventListener("appinstalled", onAppInstalled)
    }
  }, [])

  const showPrompt = useMemo(() => !hidden && deferredPrompt != null, [hidden, deferredPrompt])

  async function handleInstall() {
    if (!deferredPrompt) return
    setBusy(true)
    try {
      await deferredPrompt.prompt()
      await deferredPrompt.userChoice
    } finally {
      setBusy(false)
      setDeferredPrompt(null)
      setHidden(true)
    }
  }

  function handleDismiss() {
    setHidden(true)
    try {
      window.localStorage.setItem(DISMISS_KEY, String(Date.now()))
    } catch {
      // ignore storage failures
    }
  }

  if (!mounted) return null

  return (
    <>
      {showPrompt && !isInstalled ? (
        <div className="fixed bottom-4 right-4 z-40 w-[min(92vw,24rem)]">
          <Card className="border-muted">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Install MolTrace</CardTitle>
              <CardDescription>Add MolTrace to your device for a faster, app-like experience.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-2">
              <Button type="button" size="sm" disabled={busy} onClick={() => void handleInstall()}>
                {busy ? "Opening prompt..." : "Install app"}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={handleDismiss}>
                Not now
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  )
}
