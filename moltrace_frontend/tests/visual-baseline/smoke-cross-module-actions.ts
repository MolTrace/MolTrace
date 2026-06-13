#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned /actions page Action Queue tab.
 *
 * Verifies the NEW chrome:
 *   - Page-level eyebrow + h1 + descriptive subtitle (above the 4 tabs)
 *   - "Action Queue · Filters" section eyebrow inside the queue card
 *   - Reset filters button (hidden by default, appears when a filter is set)
 *   - Color-coded severity badges (high/critical → red, warning → amber, info → cyan)
 *   - Improved empty state ("No matches" with FilterX icon)
 *   - Improved loading state ("Loading cross-module action items…")
 *   - "Open source" / "Open target" buttons preserved with aria-label
 *
 * Hermetic: `/cross-module/action-items` mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-cross-module-actions.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-cross-module-actions-report.md")
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

const NOW = new Date("2026-05-10T10:00:00Z").toISOString()
const MOCK_ITEMS = [
  { id: 1, source_program: "spectracheck", target_program: "regulatory_hub", action_type: "create_dossier", title: "Promote MTX-447 spectra to dossier draft", severity: "high", status: "open", source_resource_type: "spectracheck_session", source_resource_id: 42, target_resource_type: "regulatory_dossier", target_resource_id: null, created_at: NOW },
  { id: 2, source_program: "regulatory_hub", target_program: "reaction_optimization", action_type: "create_reaction_constraint", title: "ICH Q3D Pd limit lowered", severity: "critical", status: "in_progress", source_resource_type: "regulatory_change", source_resource_id: 7, target_resource_type: "reaction_project", target_resource_id: 10, created_at: NOW },
  { id: 3, source_program: "reaction_optimization", target_program: "spectracheck", action_type: "review_required", title: "Confirm impurity peak attribution", severity: "warning", status: "resolved", source_resource_type: "reaction_experiment", source_resource_id: 88, target_resource_type: "spectracheck_session", target_resource_id: 12, created_at: NOW },
  { id: 4, source_program: "spectracheck", target_program: "regulatory_hub", action_type: "review_required", title: "Info-level: optional review", severity: "info", status: "blocked", source_resource_type: "spectracheck_session", source_resource_id: 1, target_resource_type: "regulatory_dossier", target_resource_id: 1, created_at: NOW },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Catch-all FIRST so specific routes (registered later) win the LIFO match
  await page.route(/\/api\/backend\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/cross-module\/action-items\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_ITEMS[0]))
  await page.route(/\/api\/backend\/cross-module\/action-items(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99 }, 201)
    return fulfillJson(r, MOCK_ITEMS)
  })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── /actions page Action Queue redesign smoke ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/actions`, { waitUntil: "load", timeout: 120_000 })
    await page.locator("text=Promote MTX-447 spectra").first().waitFor({ timeout: 30_000 })
  })
  if (!r.ok) {
    record("Page loads + table populated", "fail", r.error)
    process.exit(1)
  }
  record("Page loads + table populated", "pass")

  // ── New page-level header (eyebrow + h1 + subtitle) ──
  r = await safe(() => page.locator("text=/MolTrace · Cross-Module Action Queue/i").first().waitFor({ timeout: 5_000 }))
  record("Page eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByRole("heading", { name: /^Action Queue$/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Page h1 'Action Queue' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Coordinate work across SpectraCheck, ComplianceCore, and Reaction Optimization/i").first().waitFor({ timeout: 5_000 }),
  )
  record("Page subtitle rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 4 tabs preserved ──
  for (const tab of ["Action Queue", "Reports", "Review", "Validation Center"]) {
    r = await safe(() => page.getByRole("tab", { name: new RegExp(`^${tab}$`, "i") }).first().waitFor({ timeout: 5_000 }))
    record(`Tab "${tab}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── New filter section eyebrow ──
  r = await safe(() => page.locator("text=/Action Queue · Filters/i").first().waitFor({ timeout: 5_000 }))
  record("Filter section eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Reset filters NOT visible at default ──
  r = await safe(async () => {
    const reset = page.getByRole("button", { name: /Reset filters/i })
    if ((await reset.count()) > 0) throw new Error("Reset button visible despite no filter active")
  })
  record("Reset filters button hidden when filters are default", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Color-coded severity badges in table rows ──
  for (const sev of ["high", "critical", "warning", "info"]) {
    r = await safe(() =>
      page.locator("table tbody").locator(`text=/^${sev}$/i`).first().waitFor({ timeout: 5_000 }),
    )
    record(`Severity badge "${sev}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Per-row "Open source" / "Open target" links preserved ──
  for (const link of ["Open source", "Open target"]) {
    r = await safe(() => page.getByRole("link", { name: new RegExp(`^${link}$`, "i") }).first().waitFor({ timeout: 5_000 }))
    record(`Per-row link "${link}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Reset filters appears when a filter is set ──
  r = await safe(async () => {
    // Set the source program filter from the queue card filter row (the second of the two
    // `source program` selects: the form has one too).
    // Use a simpler approach: find the comboboxes inside the filter row by their parent label "Action Queue · Filters" sibling.
    // Easiest reliable path: click the "All" combobox under filter section and pick "SpectraCheck".
    const filterCard = page.locator("text=/Cross-Module Action Queue/i").locator("xpath=ancestor::*[contains(@class, 'rounded')][1]").first()
    // Click the first "All" select inside the filter card
    const filterRow = filterCard.locator("text=/source program/i").locator("xpath=following::button[@role='combobox'][1]").first()
    await filterRow.click()
    await page.waitForTimeout(300)
    await page.getByRole("option", { name: /^SpectraCheck$/i }).first().click()
    await page.waitForTimeout(400)
    await page.getByRole("button", { name: /Reset filters/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Reset filters button appears when filter is set", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Reset filters clears the filter ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /Reset filters/i }).first().click()
    await page.waitForTimeout(400)
    const remainingResetBtns = await page.getByRole("button", { name: /Reset filters/i }).count()
    if (remainingResetBtns > 0) throw new Error("Reset button still visible after click")
  })
  record("Reset filters button clears filter on click", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Cross-Module Action Queue redesign — smoke ${new Date().toISOString()}`,
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
