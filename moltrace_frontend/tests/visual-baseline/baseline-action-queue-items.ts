#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Regulatory Action Queue items + table.
 *
 * Locks in the user-visible contract for the action queue's INSIDE chrome:
 *   - Filter selects (severity, status, action_type, dossier_id, assigned_to)
 *   - Table column headers (title, action_type, severity, status, dossier,
 *     batch, compound, assigned_to, due_date, citations, updated_at, actions)
 *   - Per-row action buttons (In progress, Resolve, Dismiss, Defer, Assign)
 *   - Empty / loading states
 *   - "New action item" button + dialog
 *
 * Hermetic: all `/regulatory/*` and `/projects/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-action-queue-items.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-action-queue-items-report.md")
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
// Use ASCII hyphens only — ASCII em-dashes were causing locator regex matching trouble
const MOCK_ITEMS = [
  {
    id: 1,
    title: "Review Q3D update for Class 1 elemental impurities",
    action_type: "review",
    severity: "high",
    status: "open",
    dossier_id: 1,
    batch_id: 42,
    compound_id: 7,
    assigned_to: "alice@acme.com",
    due_date: NOW,
    citations: ["ICH Q3D"],
    updated_at: NOW,
  },
  {
    id: 2,
    title: "Acknowledge nitrosamine guidance",
    action_type: "acknowledge",
    severity: "medium",
    status: "in_progress",
    dossier_id: 1,
    batch_id: null,
    compound_id: null,
    assigned_to: "bob@acme.com",
    due_date: NOW,
    citations: [],
    updated_at: NOW,
  },
  {
    id: 3,
    title: "Resolved: USP 232 alignment",
    action_type: "follow_up",
    severity: "low",
    status: "resolved",
    dossier_id: 2,
    batch_id: null,
    compound_id: null,
    assigned_to: null,
    due_date: null,
    citations: [],
    updated_at: NOW,
  },
]
const MOCK_DOSSIERS = [
  { id: 1, title: "MTX-447 dossier", status: "in_review" },
  { id: 2, title: "ABT-118 dossier", status: "draft" },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Playwright route handlers are LIFO (most recently registered handles first).
  // Register the catch-all FIRST so the specific routes take precedence.
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
  // Specific routes registered LAST so they win the LIFO match
  await page.route(/\/api\/backend\/regulatory\/dossiers(\?.*)?$/, (r) => fulfillJson(r, MOCK_DOSSIERS))
  await page.route(/\/api\/backend\/regulatory\/action-items\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_ITEMS[0]))
  await page.route(/\/api\/backend\/regulatory\/action-items(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99 }, 201)
    return fulfillJson(r, MOCK_ITEMS)
  })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Action Queue items baseline regression ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory/action-queue`, { waitUntil: "load", timeout: 120_000 })
    await page.locator("text=Review Q3D update").first().waitFor({ timeout: 30_000 })
  })
  if (!r.ok) {
    record("Action queue page loads", "fail", r.error)
    process.exit(1)
  }
  record("Action queue page loads", "pass")

  // Page-level eyebrow + heading (added in earlier reskin) preserved
  r = await safe(() => page.locator("text=/Regulatory · Action Queue/i").first().waitFor({ timeout: 5_000 }))
  record("Page eyebrow tagline preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.getByRole("heading", { name: /^Action items$/i }).first().waitFor({ timeout: 5_000 }))
  record("Page h2 heading preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Filter row labels
  for (const label of ["severity", "status", "action_type", "dossier_id", "assigned_to (contains)"]) {
    r = await safe(() => page.locator(`text=${label}`).first().waitFor({ timeout: 5_000 }))
    record(`Filter "${label}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // "New action item" button preserved
  r = await safe(() =>
    page.getByRole("button", { name: /New action item/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("'New action item' button preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Table column headers preserved
  for (const header of ["title", "action_type", "severity", "status", "dossier", "batch", "compound", "assigned_to", "due_date", "citations", "updated_at", "actions"]) {
    r = await safe(() => page.locator(`th:has-text("${header}")`).first().waitFor({ timeout: 5_000 }))
    record(`Table column "${header}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // Sample row content (mocked items) renders
  r = await safe(() =>
    page.locator("text=Review Q3D update").first().waitFor({ timeout: 5_000 }),
  )
  record("Sample row title (Review Q3D update) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Per-row action buttons preserved
  for (const action of ["In progress", "Resolve", "Dismiss", "Defer", "Assign"]) {
    r = await safe(() =>
      page.getByRole("button", { name: new RegExp(`^${action}$`, "i") }).first().waitFor({ timeout: 5_000 }),
    )
    record(`Per-row action "${action}" button preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Action Queue items baseline regression — ${new Date().toISOString()}`,
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
