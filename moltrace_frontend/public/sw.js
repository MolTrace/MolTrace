var SW_VERSION = "2026-08-14-http-cache-respected-v3"
var STATIC_CACHE = "moltrace-static-" + SW_VERSION
var RUNTIME_CACHE = "moltrace-runtime-" + SW_VERSION
var OFFLINE_URL = "/offline"
// Icon URLs are versioned by ARTWORK version, never by SW_VERSION. Keying them
// to SW_VERSION put the precache in a different URL space from the page (page
// requests could never be served from it, and both copies were pinned for a
// year by the immutable header), and made every unrelated SW bump re-download
// the whole shell. This literal mirrors PWA_ASSET_VERSION in
// lib/pwa/asset-version.ts — sw-asset-version.test.ts fails if they drift.
var PWA_ASSET_VERSION = "2026-08-09-neon-prism-raised-m-v1"
var ICON_VERSION = "v=" + PWA_ASSET_VERSION
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

// Plain fetch, HTTP cache semantics intact. The old { cache: "no-store" } here
// forbade even conditional revalidation, which cancelled the s-maxage /
// stale-while-revalidate policy next.config.mjs sets for marketing pages — a
// repeat visit re-downloaded full bodies where a 304 would do.
function networkOnly(request) {
  return fetch(request)
}

function precacheShell() {
  return caches.open(STATIC_CACHE).then(function (cache) {
    return cache.addAll(SHELL_ASSETS)
  }).catch(function () {
    return Promise.resolve()
  })
}

// Documents revalidate, never go stale. The marketing paths carry
// `stale-while-revalidate=86400`, which Chrome and Firefox honour in the BROWSER
// cache too — with a plain fetch a returning visitor could be served yesterday's
// HTML (and yesterday's build id, which the update manager then cannot reload
// while the tab is visible). `no-cache` still permits a conditional request, so
// the 304 saving this SW change is about is preserved; only staleness is not.
function revalidatingFetch(request) {
  return fetch(request, { cache: "no-cache" })
}

function networkFirst(request, fallbackUrl) {
  return revalidatingFetch(request).catch(function () {
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
  return fetch(request).then(function (response) {
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

  // Never-cached requests (every cross-origin URL included) are not handled at
  // all: declining the event lets the browser fetch natively — no SW startup on
  // the critical path, normal HTTP caching, and streaming without body proxying.
  // The old respondWith(networkOnly(...)) added all three costs for zero value.
  if (request.method !== "GET" || isNeverCached(url)) {
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
