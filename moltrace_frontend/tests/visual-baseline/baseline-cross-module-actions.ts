#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the /actions page (Action Queue + Reports +
 * Review + Validation Center tabs).
 *
 * Locks in the user-visible contract for the Action Queue tab specifically:
 *   - 4 tab triggers (Action Queue / Reports / Review / Validation Center)
 *   - "Operational queue" alert
 *   - "New action item" form card (with all 11 fields)
 *   - "Cross-Module Action Queue" table card with 5 filters and 10-column table
 *   - Per-row open-source / open-target buttons
 *
 * Hermetic: `/cross-module/action-items` mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-cross-module-actions.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-cross-module-actions-report.md")
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
  {
    id: 1,
    source_program: "spectracheck",
    target_program: "regulatory_hub",
    action_type: "create_dossier",
    title: "Promote MTX-447 spectra to dossier draft",
    severity: "high",
    status: "open",
    source_resource_type: "spectracheck_session",
    source_resource_id: 42,
    target_resource_type: "regulatory_dossier",
    target_resource_id: null,
    created_at: NOW,
  },
  {
    id: 2,
    source_program: "regulatory_hub",
    target_program: "reaction_optimization",
    action_type: "create_reaction_constraint",
    title: "ICH Q3D Pd limit lowered - update constraints",
    severity: "critical",
    status: "in_progress",
    source_resource_type: "regulatory_change",
    source_resource_id: 7,
    target_resource_type: "reaction_project",
    target_resource_id: 10,
    created_at: NOW,
  },
  {
    id: 3,
    source_program: "reaction_optimization",
    target_program: "spectracheck",
    action_type: "review_required",
    title: "Confirm impurity peak attribution",
    severity: "warning",
    status: "resolved",
    source_resource_type: "reaction_experiment",
    source_resource_id: 88,
    target_resource_type: "spectracheck_session",
    target_resource_id: 12,
    created_at: NOW,
  },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Catch-all FIRST so specific routes (registered later) win the LIFO match
  await page.route(/\/api\/backend\/.+$/, (r) => fulfillJson(r, []))
  // Specific routes registered LAST
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

  console.log("\n── /actions page — Cross-Module Action Queue baseline regression ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/actions`, { waitUntil: "load", timeout: 120_000 })
    // Wait for table to populate
    await page.locator("text=Promote MTX-447 spectra").first().waitFor({ timeout: 30_000 })
  })
  if (!r.ok) {
    record("/actions page loads + Action Queue tab populated", "fail", r.error)
    process.exit(1)
  }
  record("/actions page loads + Action Queue tab populated", "pass")

  // ── 4 tab triggers ──
  for (const tab of ["Action Queue", "Reports", "Review", "Validation Center"]) {
    r = await safe(() => page.getByRole("tab", { name: new RegExp(`^${tab}$`, "i") }).first().waitFor({ timeout: 5_000 }))
    record(`Tab trigger "${tab}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Operational queue alert ──
  r = await safe(() => page.locator("text=Operational queue").first().waitFor({ timeout: 5_000 }))
  record("'Operational queue' alert preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── "New action item" form card ──
  r = await safe(() => page.locator("text=New action item").first().waitFor({ timeout: 5_000 }))
  record("'New action item' form card heading preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Form fields
  for (const field of ["source program", "target program", "action type", "title", "description", "severity", "status", "source resource type", "source resource id", "target resource type", "target resource id"]) {
    r = await safe(() => page.locator(`label:has-text("${field}")`).first().waitFor({ timeout: 5_000 }))
    record(`Form field "${field}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── "Create action item" button ──
  r = await safe(() => page.getByRole("button", { name: /Create action item/i }).first().waitFor({ timeout: 5_000 }))
  record("'Create action item' button preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Queue card heading ──
  r = await safe(() => page.locator("text=Cross-Module Action Queue").first().waitFor({ timeout: 5_000 }))
  record("'Cross-Module Action Queue' table card heading preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 10 table column headers ──
  for (const col of ["source program", "target program", "action type", "title", "severity", "status", "linked resource", "created date", "open source", "open target"]) {
    r = await safe(() => page.locator(`th:has-text("${col}")`).first().waitFor({ timeout: 5_000 }))
    record(`Table column "${col}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Sample row title ──
  r = await safe(() => page.locator("text=Promote MTX-447 spectra").first().waitFor({ timeout: 5_000 }))
  record("Sample row title rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Per-row "Open source" + "Open target" buttons ──
  for (const action of ["Open source", "Open target"]) {
    r = await safe(() => page.getByRole("link", { name: new RegExp(`^${action}$`, "i") }).first().waitFor({ timeout: 5_000 }))
    record(`Per-row "${action}" button/link preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Cross-Module Action Queue baseline regression — ${new Date().toISOString()}`,
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
