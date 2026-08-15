/**
 * The service worker is plain JS served as a static file, so it cannot import
 * the shared artwork version — it carries a literal copy. These tests are what
 * keep the copy honest, and they exist because two related defects shipped:
 *
 *  - the SW keyed its shell icon URLs to SW_VERSION rather than the artwork
 *    version, so the precache lived in a different URL space from the page
 *    (page requests could never be served from it) and every unrelated SW bump
 *    re-downloaded the whole shell; and
 *  - icons are now served `immutable` for a year, which makes `?v=` the only
 *    way to publish new artwork — a drifted or missing version is unfixable by
 *    redeploying.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"

import { describe, expect, it } from "vitest"

import { PWA_ASSET_VERSION, versionedIcon } from "@/lib/pwa/asset-version"

const swSource = readFileSync(join(process.cwd(), "public/sw.js"), "utf8")

describe("service worker asset versioning", () => {
  it("pins the same artwork version as the shared module", () => {
    const match = swSource.match(/var PWA_ASSET_VERSION = "([^"]+)"/)
    expect(match?.[1]).toBe(PWA_ASSET_VERSION)
  })

  it("versions shell icons by artwork version, not by SW_VERSION", () => {
    expect(swSource).toMatch(/var ICON_VERSION = "v=" \+ PWA_ASSET_VERSION/)
  })

  it("revalidates navigations instead of serving stale-while-revalidate HTML", () => {
    expect(swSource).toMatch(/function revalidatingFetch\(request\) \{\s*return fetch\(request, \{ cache: "no-cache" \}\)/)
    expect(swSource).toMatch(/function networkFirst\(request, fallbackUrl\) \{\s*return revalidatingFetch\(request\)/)
  })

  it("builds the same icon URL the page requests", () => {
    // If these diverge the precache is dead weight: cache.put/caches.match are
    // called without ignoreSearch, so a query mismatch is a permanent miss.
    expect(swSource).toContain('"/icons/icon-192.png?" + ICON_VERSION')
    expect(versionedIcon("/icons/icon-192.png")).toBe(
      `/icons/icon-192.png?v=${PWA_ASSET_VERSION}`,
    )
  })
})
