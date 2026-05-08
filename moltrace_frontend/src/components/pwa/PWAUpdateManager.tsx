"use client"

import { useEffect } from "react"

const UPDATE_CHECK_INTERVAL_MS = 15_000
const CURRENT_FRONTEND_BUILD_ID = process.env.NEXT_PUBLIC_MOLTRACE_BUILD_ID || "development"

function postSkipWaiting(worker: ServiceWorker | null | undefined) {
  if (!worker) return
  worker.postMessage({ type: "SKIP_WAITING" })
}

function registerUpdateListeners(registration: ServiceWorkerRegistration) {
  const activateWaitingWorker = () => {
    if (navigator.serviceWorker.controller && registration.waiting) {
      postSkipWaiting(registration.waiting)
    }
  }

  activateWaitingWorker()

  registration.addEventListener("updatefound", () => {
    const installingWorker = registration.installing
    if (!installingWorker) return

    installingWorker.addEventListener("statechange", () => {
      if (installingWorker.state === "installed" && navigator.serviceWorker.controller) {
        postSkipWaiting(installingWorker)
      }
    })
  })
}

export function PWAUpdateManager() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return
    if (process.env.NODE_ENV !== "production") {
      void navigator.serviceWorker.getRegistrations().then((registrations) => {
        registrations.forEach((registration) => {
          void registration.unregister()
        })
      })
      if ("caches" in window) {
        void caches.keys().then((keys) => {
          keys.forEach((key) => {
            void caches.delete(key)
          })
        })
      }
      return
    }

    const hadController = Boolean(navigator.serviceWorker.controller)
    let didReloadForUpdate = false
    let disposed = false
    let intervalId: number | undefined
    let registrationRef: ServiceWorkerRegistration | null = null

    const reloadForFreshBuild = () => {
      if (didReloadForUpdate || disposed) return
      didReloadForUpdate = true
      registrationRef?.active?.postMessage({ type: "CLEAR_PWA_CACHES" })
      window.location.reload()
    }

    const checkFrontendBuild = async () => {
      try {
        const response = await fetch("/api/app-version", {
          cache: "no-store",
          headers: { accept: "application/json" },
        })
        if (!response.ok) return

        const payload = (await response.json()) as { frontend_build_id?: unknown }
        const latestBuildId =
          typeof payload.frontend_build_id === "string" ? payload.frontend_build_id : ""

        if (latestBuildId && latestBuildId !== CURRENT_FRONTEND_BUILD_ID) {
          postSkipWaiting(registrationRef?.waiting)
          reloadForFreshBuild()
        }
      } catch {
        // Version checks are best-effort; network recovery/focus will try again.
      }
    }

    const checkForUpdates = () => {
      if (disposed || !registrationRef) return
      void registrationRef.update().catch(() => {
        // Update checks are opportunistic; the next focus/online event will try again.
      })
      void checkFrontendBuild()
    }

    const handleControllerChange = () => {
      if (!hadController || disposed) return
      reloadForFreshBuild()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") checkForUpdates()
    }

    const handleServiceWorkerMessage = (event: MessageEvent) => {
      const data = event.data as { type?: unknown } | null
      if (!data || typeof data.type !== "string") return
      if (data.type === "MOLTRACE_SW_ACTIVATED" && hadController) {
        reloadForFreshBuild()
      }
    }

    const handlePageShow = () => {
      checkForUpdates()
    }

    void navigator.serviceWorker
      .register("/sw.js", {
        scope: "/",
        updateViaCache: "none",
      })
      .then((registration) => {
        if (disposed) return
        registrationRef = registration
        registerUpdateListeners(registration)
        checkForUpdates()
        intervalId = window.setInterval(checkForUpdates, UPDATE_CHECK_INTERVAL_MS)
      })
      .catch(() => {
        // PWA support is optional; the web app remains usable without service worker registration.
      })

    navigator.serviceWorker.addEventListener("controllerchange", handleControllerChange)
    navigator.serviceWorker.addEventListener("message", handleServiceWorkerMessage)
    window.addEventListener("focus", checkForUpdates)
    window.addEventListener("online", checkForUpdates)
    window.addEventListener("pageshow", handlePageShow)
    document.addEventListener("visibilitychange", handleVisibilityChange)

    return () => {
      disposed = true
      if (intervalId != null) window.clearInterval(intervalId)
      navigator.serviceWorker.removeEventListener("controllerchange", handleControllerChange)
      navigator.serviceWorker.removeEventListener("message", handleServiceWorkerMessage)
      window.removeEventListener("focus", checkForUpdates)
      window.removeEventListener("online", checkForUpdates)
      window.removeEventListener("pageshow", handlePageShow)
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [])

  return null
}
