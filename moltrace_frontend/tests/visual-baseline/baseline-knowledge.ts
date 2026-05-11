#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Knowledge Library module.
 *
 * Captures CURRENT behavior across all 9 routes + cross-module integration
 * (Knowledge → SpectraCheck via knowledge-link cards; Knowledge → Regulatory
 * via knowledge-link cards; AI prediction augmentation slot at /knowledge).
 *
 * Hermetic: all `/knowledge/*`, `/ai/*`, `/projects/*`, `/regulatory/*`,
 * `/reaction-projects/*`, `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-knowledge.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-knowledge-report.md")
const BASE_URL = "http://localhost:3000"

type CheckResult = { check: string; status: "pass" | "fail"; detail?: string }
const results: CheckResult[] = []
function record(check: string, status: "pass" | "fail", detail?: string) {
  results.push({ check, status, detail })
  const icon = status === "pass" ? "✓" : "✗"
  console.log(`  ${icon} ${check}${detail ? ` — ${detail}` : ""}`)
}
async function safe<T>(fn: () => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: string }> {
  try {
    return { ok: true, value: await fn() }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Knowledge endpoints (datasets, sources, extractions, records, reviews, model-improvement, links)
  await page.route(/\/api\/backend\/knowledge\/.+$/, (r) => fulfillJson(r, []))
  // AI predictions (augmentation card on /knowledge landing)
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
  // Cross-module (regulatory + reaction + spectracheck)
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck|workflow-templates|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
}

const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/knowledge", signal: /Knowledge Library|Knowledge|Library/i, label: "Knowledge Library landing" },
  { path: "/knowledge/datasets", signal: /Dataset|candidate dashboard/i, label: "Dataset candidates dashboard" },
  { path: "/knowledge/sources", signal: /Source|Knowledge sources/i, label: "Knowledge sources" },
  { path: "/knowledge/extractions", signal: /Extraction|Knowledge extractions/i, label: "Knowledge extractions" },
  { path: "/knowledge/analytical", signal: /Analytical|Extracted|Record/i, label: "Analytical extraction records" },
  { path: "/knowledge/reactions", signal: /Reaction|Extracted|Record/i, label: "Reaction extraction records" },
  { path: "/knowledge/regulatory", signal: /Regulatory|Extracted|Record/i, label: "Regulatory extraction records" },
  { path: "/knowledge/review", signal: /Review|Workflow queue/i, label: "Knowledge review tasks" },
  { path: "/knowledge/model-improvement", signal: /Model improvement|Operational backlog/i, label: "Model improvement queue" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Knowledge Library baseline regression ─────────")

  for (const route of ROUTES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(1500)
    })
    if (!r.ok) {
      record(`Route ${route.path} loads`, "fail", r.error)
      continue
    }
    record(`Route ${route.path} loads`, "pass")

    r = await safe(() => page.locator("text=Programs").first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — sidebar Programs link rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() => page.locator(`text=${route.signal}`).first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — ${route.label} signal text rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Cross-module: AI prediction augmentation slot at /knowledge ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/knowledge`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("heading", { name: /Knowledge: Optional controlled AI prediction/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: /knowledge → AI prediction augmentation slot present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: SpectraCheck retains all 12 tabs ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    const tabs = await page.locator('[data-testid^="spectracheck-tab-"]').count()
    if (tabs < 12) throw new Error(`expected ≥12 SpectraCheck tabs, got ${tabs}`)
  })
  record("Cross-module: SpectraCheck retains all 12 tabs", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Knowledge Library baseline regression — ${new Date().toISOString()}`,
    "",
    `- Pass: ${passes}`,
    `- Fail: ${fails}`,
    "",
    "| Check | Status | Detail |",
    "|---|---|---|",
    ...results.map((r) => `| ${r.check} | ${r.status === "pass" ? "✓" : "✗"} | ${r.detail ?? ""} |`),
    "",
  ].join("\n")
  await writeFile(REPORT_PATH, md, "utf-8")
  console.log(`Report → ${REPORT_PATH.replace(__dirname + "/", "")}`)

  if (fails > 0) process.exit(1)
}

main().catch((e) => {
  console.error("Fatal:", e)
  process.exit(1)
})
