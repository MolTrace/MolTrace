#!/usr/bin/env -S pnpm tsx
/**
 * MolTrace UI design system — visual regression baseline capture.
 *
 * Visits every route in `routes.ts` against a running dev server and captures
 * a full-page screenshot at desktop viewport (1440×900). Produces a directory
 * of PNGs under `tests/visual-baseline/screenshots/` plus a JSON report at
 * `tests/visual-baseline/report.json` summarizing what was captured and any
 * routes that failed.
 *
 * Prereq: dev server running on http://localhost:3000.
 *
 * Run via: pnpm visual:baseline
 */

import { chromium, type Browser, type Page } from "@playwright/test"
import { mkdir, writeFile } from "node:fs/promises"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { ROUTES, type Route } from "./routes"

const __dirname = dirname(fileURLToPath(import.meta.url))
const SCREENSHOTS_DIR = join(__dirname, "screenshots")
const REPORT_PATH = join(__dirname, "report.json")
const REPORT_MD_PATH = join(__dirname, "report.md")

const BASE_URL = process.env.VISUAL_BASE_URL ?? "http://localhost:3000"
const VIEWPORT = { width: 1440, height: 900 }
const NAV_TIMEOUT_MS = Number(process.env.VISUAL_NAV_TIMEOUT_MS ?? 60_000)
const SETTLE_MS = Number(process.env.VISUAL_SETTLE_MS ?? 800)
const COOLDOWN_MS = Number(process.env.VISUAL_COOLDOWN_MS ?? 400)
const RETRY_COUNT = Number(process.env.VISUAL_RETRY_COUNT ?? 2)

type RouteResult = {
  name: string
  path: string
  accent: Route["accent"]
  status: "ok" | "error"
  durationMs: number
  errorMessage?: string
  screenshotPath?: string
}

async function attemptRoute(page: Page, route: Route): Promise<{ ok: true; screenshotPath: string } | { ok: false; errorMessage: string }> {
  const url = `${BASE_URL}${route.path}`
  try {
    // Use "load" instead of "networkidle" — many surfaces have long-poll fetches that never go fully idle.
    await page.goto(url, { waitUntil: "load", timeout: NAV_TIMEOUT_MS })
    await page.waitForTimeout(SETTLE_MS)
    const screenshotPath = join(SCREENSHOTS_DIR, `${route.name}.png`)
    await page.screenshot({ path: screenshotPath, fullPage: true, animations: "disabled" })
    return { ok: true, screenshotPath }
  } catch (err) {
    return { ok: false, errorMessage: err instanceof Error ? err.message : String(err) }
  }
}

async function captureRoute(page: Page, route: Route): Promise<RouteResult> {
  const start = Date.now()
  let lastError = ""
  for (let attempt = 0; attempt <= RETRY_COUNT; attempt++) {
    if (attempt > 0) {
      // Brief cooldown between retries to let dev-server compilation settle.
      await page.waitForTimeout(2_000)
    }
    const r = await attemptRoute(page, route)
    if (r.ok) {
      return {
        name: route.name,
        path: route.path,
        accent: route.accent,
        status: "ok",
        durationMs: Date.now() - start,
        screenshotPath: r.screenshotPath.replace(`${__dirname}/`, ""),
      }
    }
    lastError = r.errorMessage
  }
  return {
    name: route.name,
    path: route.path,
    accent: route.accent,
    status: "error",
    durationMs: Date.now() - start,
    errorMessage: lastError,
  }
}

async function main() {
  await mkdir(SCREENSHOTS_DIR, { recursive: true })

  console.log(`MolTrace visual baseline — capturing ${ROUTES.length} routes`)
  console.log(`  Base URL : ${BASE_URL}`)
  console.log(`  Viewport : ${VIEWPORT.width}×${VIEWPORT.height}`)
  console.log(`  Output   : tests/visual-baseline/screenshots/`)
  console.log()

  let browser: Browser | undefined
  const results: RouteResult[] = []

  try {
    browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ viewport: VIEWPORT })
    const page = await context.newPage()

    for (let i = 0; i < ROUTES.length; i++) {
      const route = ROUTES[i]!
      const idx = `[${String(i + 1).padStart(2, "0")}/${ROUTES.length}]`
      const result = await captureRoute(page, route)
      results.push(result)

      const statusIcon = result.status === "ok" ? "✓" : "✗"
      const ms = `${result.durationMs}ms`.padStart(7)
      const tail =
        result.status === "ok"
          ? `→ ${result.screenshotPath}`
          : `error: ${(result.errorMessage ?? "unknown").slice(0, 80)}`
      console.log(`${idx} ${statusIcon} ${ms} ${route.path.padEnd(48)} ${tail}`)

      // Cooldown between routes — gives the dev server breathing room when
      // compiling many cold pages back-to-back.
      if (i < ROUTES.length - 1) await page.waitForTimeout(COOLDOWN_MS)
    }

    await context.close()
  } finally {
    await browser?.close()
  }

  // Write JSON report
  const report = {
    capturedAt: new Date().toISOString(),
    baseUrl: BASE_URL,
    viewport: VIEWPORT,
    totalRoutes: results.length,
    okCount: results.filter((r) => r.status === "ok").length,
    errorCount: results.filter((r) => r.status === "error").length,
    results,
  }
  await writeFile(REPORT_PATH, JSON.stringify(report, null, 2) + "\n", "utf-8")

  // Write markdown summary
  const okRows = results
    .filter((r) => r.status === "ok")
    .map((r) => `| ${r.name} | ${r.accent} | ${r.path} | ${r.durationMs}ms |`)
    .join("\n")
  const errorRows = results
    .filter((r) => r.status === "error")
    .map((r) => `| ${r.name} | ${r.path} | ${r.errorMessage ?? "—"} |`)
    .join("\n")

  const md = [
    `# MolTrace visual baseline — ${report.capturedAt}`,
    "",
    `- Base URL: ${BASE_URL}`,
    `- Viewport: ${VIEWPORT.width}×${VIEWPORT.height}`,
    `- Total routes: ${report.totalRoutes}`,
    `- Captured: ${report.okCount}`,
    `- Errors: ${report.errorCount}`,
    "",
    "## Captured",
    "",
    "| Name | Accent | Path | Duration |",
    "|---|---|---|---|",
    okRows || "| _(none)_ | | | |",
    "",
    "## Errors",
    "",
    errorRows
      ? "| Name | Path | Error |\n|---|---|---|\n" + errorRows
      : "_None — all routes captured cleanly._",
    "",
  ].join("\n")
  await writeFile(REPORT_MD_PATH, md, "utf-8")

  console.log()
  console.log(`Done — ${report.okCount} captured, ${report.errorCount} errors`)
  console.log(`  JSON  : ${REPORT_PATH.replace(`${__dirname}/`, "")}`)
  console.log(`  MD    : ${REPORT_MD_PATH.replace(`${__dirname}/`, "")}`)

  if (report.errorCount > 0) process.exit(1)
}

main().catch((err) => {
  console.error("Fatal error:", err)
  process.exit(1)
})
