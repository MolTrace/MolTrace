const STATIC_CACHE = "moltrace-static-v1"
const OFFLINE_URL = "/offline"

const SHELL_ASSETS = ["/", OFFLINE_URL, "/icon.svg"]

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => Promise.resolve()),
  )
  self.skipWaiting()
})

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== STATIC_CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  )
})

function isSafeStaticRequest(request, url) {
  if (request.method !== "GET") return false
  if (url.origin !== self.location.origin) return false
  if (url.pathname.startsWith("/api/backend/")) return false
  if (url.pathname.startsWith("/api/")) return false
  if (url.pathname.startsWith("/artifacts/")) return false
  if (url.pathname.startsWith("/uploads/")) return false
  if (url.pathname.includes("/reports/")) return false

  return ["style", "script", "font", "image"].includes(request.destination)
}

self.addEventListener("fetch", (event) => {
  const { request } = event
  const url = new URL(request.url)

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cachedOffline = await caches.match(OFFLINE_URL)
        return cachedOffline || Response.error()
      }),
    )
    return
  }

  if (!isSafeStaticRequest(request, url)) {
    return
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone()
            void caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy))
          }
          return response
        })
        .catch(() => cached)

      return cached || networkFetch
    }),
  )
})
