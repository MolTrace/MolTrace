var SW_VERSION = "2026-05-08-v2"
var STATIC_CACHE = "moltrace-static-" + SW_VERSION
var RUNTIME_CACHE = "moltrace-runtime-" + SW_VERSION
var OFFLINE_URL = "/offline"
var ICON_VERSION = "v=" + SW_VERSION
var SHELL_ASSETS = [
  OFFLINE_URL,
  "/icons/moltrace-mark.svg?" + ICON_VERSION,
  "/icons/icon-192.png?" + ICON_VERSION,
  "/icons/icon-512.png?" + ICON_VERSION,
  "/icons/maskable-icon-512.png?" + ICON_VERSION,
  "/apple-icon.png?" + ICON_VERSION,
]
var ALLOWED_CACHES = [STATIC_CACHE, RUNTIME_CACHE]

function isAllowedCache(cacheName) {
  return ALLOWED_CACHES.indexOf(cacheName) !== -1
}

function isSameOrigin(url) {
  return url.origin === self.location.origin
}

function isLocalDevelopment() {
  return self.location.hostname === "localhost" || self.location.hostname === "127.0.0.1"
}

function isNeverCached(url) {
  if (!isSameOrigin(url)) return true
  if (isLocalDevelopment() && url.pathname.indexOf("/_next/") === 0) return true
  if (url.pathname === "/sw.js") return true
  if (url.pathname === "/manifest.webmanifest") return true
  if (url.pathname === "/manifest.json") return true
  if (url.pathname.indexOf("/api/backend/") === 0) return true
  if (url.pathname.indexOf("/api/") === 0) return true
  if (url.pathname.indexOf("/artifacts/") === 0) return true
  if (url.pathname.indexOf("/uploads/") === 0) return true
  if (url.pathname.indexOf("/reports/") !== -1) return true
  if (url.pathname.indexOf("/_next/data/") === 0) return true
  return false
}

function isImmutableNextAsset(request, url) {
  if (request.method !== "GET") return false
  if (!isSameOrigin(url)) return false
  if (isLocalDevelopment()) return false
  return url.pathname.indexOf("/_next/static/") === 0
}

function isReusableAsset(request, url) {
  if (request.method !== "GET") return false
  if (isNeverCached(url)) return false
  return request.destination === "font" || request.destination === "image"
}

function networkOnly(request) {
  return fetch(request, { cache: "no-store" })
}

function precacheShell() {
  return caches.open(STATIC_CACHE).then(function (cache) {
    return cache.addAll(SHELL_ASSETS)
  }).catch(function () {
    return Promise.resolve()
  })
}

function networkFirst(request, fallbackUrl) {
  return networkOnly(request).catch(function () {
    if (!fallbackUrl) return Response.error()
    return caches.match(fallbackUrl).then(function (fallback) {
      return fallback || Response.error()
    })
  })
}

function cacheFirst(request) {
  return caches.match(request).then(function (cached) {
    if (cached) return cached
    return fetch(request).then(function (response) {
      if (response && response.ok) {
        var copy = response.clone()
        caches.open(STATIC_CACHE).then(function (cache) {
          cache.put(request, copy)
        })
      }
      return response
    })
  })
}

function networkFirstCachedAsset(request) {
  return fetch(request, { cache: "no-store" }).then(function (response) {
    if (response && response.ok) {
      var copy = response.clone()
      caches.open(RUNTIME_CACHE).then(function (cache) {
        cache.put(request, copy)
      })
    }
    return response
  }).catch(function () {
    return caches.match(request).then(function (cached) {
      return cached || Response.error()
    })
  })
}

function broadcastToWindows(message) {
  return self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clients) {
    clients.forEach(function (client) {
      client.postMessage(message)
    })
  })
}

function clearAllCaches() {
  return caches.keys().then(function (keys) {
    return Promise.all(keys.map(function (key) {
      return caches.delete(key)
    }))
  })
}

self.addEventListener("install", function (event) {
  event.waitUntil(precacheShell())
  self.skipWaiting()
})

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (isAllowedCache(key)) return Promise.resolve()
        return caches.delete(key)
      }))
    }).then(function () {
      return self.clients.claim()
    }).then(function () {
      return broadcastToWindows({
        type: "MOLTRACE_SW_ACTIVATED",
        version: SW_VERSION,
      })
    })
  )
})

self.addEventListener("message", function (event) {
  var data = event.data || {}
  if (data.type === "SKIP_WAITING") {
    self.skipWaiting()
    return
  }
  if (data.type === "CLEAR_PWA_CACHES") {
    event.waitUntil(
      clearAllCaches().then(function () {
        return precacheShell()
      }).then(function () {
        return broadcastToWindows({
          type: "MOLTRACE_PWA_CACHES_CLEARED",
          version: SW_VERSION,
        })
      })
    )
  }
})

self.addEventListener("fetch", function (event) {
  var request = event.request
  var url = new URL(request.url)

  if (request.method !== "GET" || isNeverCached(url)) {
    event.respondWith(networkOnly(request))
    return
  }

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request, OFFLINE_URL))
    return
  }

  if (isImmutableNextAsset(request, url)) {
    event.respondWith(cacheFirst(request))
    return
  }

  if (isReusableAsset(request, url)) {
    event.respondWith(networkFirstCachedAsset(request))
  }
})
