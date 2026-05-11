#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Validation Center module.
 *
 * Captures CURRENT behavior across all 13 validation routes + cross-module
 * integration (Validation readiness cards on SpectraCheck / Regulatory /
 * Reaction landings).
 *
 * Hermetic: all `/validation/*`, `/projects/*`, `/regulatory/*`,
 * `/reaction-projects/*`, `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-validation-center.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-validation-center-report.md")
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

const MOCK_VALIDATION_PROJECTS = [
  { id: 1, name: "MTX validation", status: "active", project_id: 1 },
]
const MOCK_VALIDATION_RUNS = [{ id: 1, validation_project_id: 1, status: "completed" }]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  await page.route(/\/api\/backend\/validation\/projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, MOCK_VALIDATION_PROJECTS[0]),
  )
  await page.route(/\/api\/backend\/validation\/projects(\?.*)?$/, (r) =>
    fulfillJson(r, MOCK_VALIDATION_PROJECTS),
  )
  await page.route(/\/api\/backend\/validation\/runs\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_VALIDATION_RUNS[0]))
  await page.route(/\/api\/backend\/validation\/runs(\?.*)?$/, (r) => fulfillJson(r, MOCK_VALIDATION_RUNS))
  await page.route(/\/api\/backend\/validation\/.+$/, (r) => fulfillJson(r, []))
  // Cross-module
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck|workflow-templates|knowledge|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
}

const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/validation-center", signal: /Validation|Center|Project/i, label: "Validation Center landing" },
  { path: "/validation-center/projects", signal: /Validation|Project/i, label: "Validation projects index" },
  { path: "/validation-center/projects/1", signal: /Validation|Project|Run/i, label: "Validation project detail" },
  { path: "/validation-center/capa", signal: /CAPA|corrective|action/i, label: "CAPA workspace" },
  { path: "/validation-center/controlled-records", signal: /Controlled|Record|GxP/i, label: "Controlled records" },
  { path: "/validation-center/data-integrity", signal: /Data integrity|ALCOA/i, label: "Data integrity" },
  { path: "/validation-center/deviations", signal: /Deviation|Variance/i, label: "Deviations" },
  { path: "/validation-center/esignatures", signal: /e-?signature|Signature/i, label: "E-signatures" },
  { path: "/validation-center/inspection-package", signal: /Inspection|Package|Audit/i, label: "Inspection package" },
  { path: "/validation-center/releases", signal: /Release|System|Version/i, label: "System releases" },
  { path: "/validation-center/traceability", signal: /Traceability|Matrix|Requirement/i, label: "Traceability" },
  { path: "/validation", signal: /Validation|Dashboard|Run/i, label: "Validation dashboard" },
  { path: "/validation/1", signal: /Validation|Run|Detail/i, label: "Validation run detail" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Validation Center baseline regression ─────────")

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

  // ── Cross-module: Validation readiness cards on SpectraCheck/Regulatory/Reaction landings ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.locator("text=/Validation/i").first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Regulatory landing hosts Validation readiness signal", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.goto(`${BASE_URL}/reactions`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.locator("text=/Validation/i").first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: Reaction landing hosts Validation readiness signal", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

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
    `# Validation Center baseline regression — ${new Date().toISOString()}`,
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
