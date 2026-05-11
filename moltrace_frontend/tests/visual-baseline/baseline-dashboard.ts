#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Dashboard module.
 *
 * Captures CURRENT behavior across all 8 dashboard routes + cross-module
 * integration (the shared dashboard cards — alert-card, module-card,
 * kpi-card — that every other module's landing depends on).
 *
 * Hermetic: all `/dashboard/*`, `/projects/*`, `/regulatory/*`,
 * `/reaction-projects/*`, `/spectracheck/*`, `/validation/*`, `/knowledge/*`
 * endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-dashboard.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-dashboard-report.md")
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
  // Generic catch-all for everything the dashboard might pull
  await page.route(/\/api\/backend\/(dashboard|reports|roi|automation-roi|projects|regulatory|reaction-projects|reaction|validation|knowledge|spectracheck|sessions|recommendations|recommendation-batches|experiments|variables|design-space|cost-profile|safety-profile|objective-profile|advisor|optimization|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|carbon13|nmr2d|prediction|similarity|candidates|ms|workflow-templates|compound-registry|secure-shares|ai|ai\/.*)\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(projects|reaction-projects|regulatory\/dossiers|knowledge|validation\/projects|workflow-templates)(\?.*)?$/, (r) => fulfillJson(r, []))
}

const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/dashboard", signal: /Dashboard|Welcome|Overview/i, label: "Main dashboard (DashboardV0)" },
  { path: "/dashboard/projects", signal: /Projects|FolderOpen|Active/i, label: "Dashboard Projects subpage" },
  { path: "/dashboard/reactions", signal: /Reaction|Optimization|RXN/i, label: "Dashboard Reactions subpage" },
  { path: "/dashboard/regulatory", signal: /Regulatory|REG-2024|Compliance/i, label: "Dashboard Regulatory subpage" },
  { path: "/dashboard/spectroscopy", signal: /Spectroscopy|NMR-2024|Sample/i, label: "Dashboard Spectroscopy subpage" },
  { path: "/dashboard/reports", signal: /Reports|Saved|Generate/i, label: "Saved reports workspace" },
  { path: "/dashboard/roi", signal: /ROI|Automation|Value/i, label: "Automation ROI dashboard" },
  { path: "/dashboard/settings", signal: /Settings|Preference|Profile/i, label: "Dashboard settings" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Dashboard baseline regression ─────────")

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

    r = await safe(() => page.locator(`text=${route.signal}`).first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — ${route.label} signal text rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Cross-module: shared dashboard cards still work on Regulatory landing (uses ModuleCard) ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.locator("text=/Active dossiers|Source documents|High-risk/i").first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Regulatory landing KPI cards (uses shared kpi-card) still render", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: SpectraCheck Overview still works (uses ModuleCard heavily) ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    const tabs = await page.locator('[data-testid^="spectracheck-tab-"]').count()
    if (tabs < 12) throw new Error(`expected ≥12 SpectraCheck tabs, got ${tabs}`)
  })
  record("Cross-module: SpectraCheck retains all 12 tabs", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: Reaction landing module cards still work ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/reactions`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.locator("text=/Active campaigns|Pending recommendations|Experiments completed/i").first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Reaction landing KPI cards still render", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Dashboard baseline regression — ${new Date().toISOString()}`,
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
