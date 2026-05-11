#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Projects module.
 *
 * Captures CURRENT behavior across all 3 routes + cross-module integration
 * (Projects → SpectraCheck via projectId/sampleId query params; Projects →
 * Regulatory / Reaction via shared project_id).
 *
 * Hermetic: all `/projects/*`, `/regulatory/*`, `/reaction-projects/*`,
 * `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-projects.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-projects-report.md")
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

const MOCK_PROJECTS = [
  { id: 1, name: "MTX program", description: "Methotrexate development", status: "active", updated_at: "2026-05-01T10:00:00Z" },
  { id: 2, name: "ABT program", description: "ABT-118 screening", status: "active", updated_at: "2026-05-01T10:00:00Z" },
]
const MOCK_PROJECT_DETAIL = {
  id: 1,
  name: "MTX program",
  description: "Methotrexate development",
  status: "active",
  updated_at: "2026-05-01T10:00:00Z",
  created_at: "2026-04-01T10:00:00Z",
}
const MOCK_SAMPLES = [
  { id: 1, sample_id: "SMP-001", project_id: 1, name: "MTX-447 batch 1", status: "draft" },
]
const MOCK_SAMPLE_DETAIL = {
  id: 1,
  sample_id: "SMP-001",
  project_id: 1,
  name: "MTX-447 batch 1",
  status: "draft",
  created_at: "2026-04-15T10:00:00Z",
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Projects list + detail + samples
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99, name: "new" }, 201)
    return fulfillJson(r, MOCK_PROJECTS)
  })
  await page.route(/\/api\/backend\/projects\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECT_DETAIL))
  await page.route(/\/api\/backend\/projects\/\d+\/samples(\?.*)?$/, (r) => fulfillJson(r, MOCK_SAMPLES))
  await page.route(/\/api\/backend\/projects\/\d+\/samples\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_SAMPLE_DETAIL))
  await page.route(/\/api\/backend\/projects\/\d+\/(access|members|invitations|sessions|workflow-runs|recent-runs|value-summary|sample-counts|regulatory-dossiers|reaction-projects)(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
  // Regulatory + Reaction (cross-module data on the project detail)
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  // SpectraCheck (so the "Open SpectraCheck" link target loads cleanly when verified)
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  // Knowledge + workflow templates referenced from the project detail
  await page.route(/\/api\/backend\/(workflow-templates|knowledge|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, []),
  )
  // AI predictions
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
}

const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/projects", signal: /Projects/i, label: "Projects index" },
  { path: "/projects/1", signal: /MTX program|Project|Updated/i, label: "Project detail (id=1)" },
  { path: "/projects/1/samples/1", signal: /Sample|MTX-447|Open SpectraCheck/i, label: "Sample detail" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Projects baseline regression ─────────")

  for (const route of ROUTES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(1000)
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

  // ── Critical functional contract: "Create project" button on index ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.getByRole("button", { name: /Create project/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Functional: 'Create project' button rendered on /projects", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: Project detail surfaces Open SpectraCheck CTA ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects/1`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("link", { name: /Open SpectraCheck/i }).first().waitFor({ timeout: 5_000 })
    await page.getByRole("link", { name: /New SpectraCheck Session/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Project detail → SpectraCheck CTA links present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: Sample detail surfaces Open SpectraCheck CTA ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects/1/samples/1`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("link", { name: /Open SpectraCheck/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Sample detail → SpectraCheck CTA link present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: SpectraCheck still loads independently ──
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
    `# Projects baseline regression — ${new Date().toISOString()}`,
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
