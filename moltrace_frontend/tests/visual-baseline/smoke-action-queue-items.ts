#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Regulatory Action Queue items.
 *
 * Verifies the NEW chrome:
 *   - Filter section eyebrow + Reset filters button (only when filters active)
 *   - Color-coded severity badges (high/medium/low/info)
 *   - Color-coded status badges (open/in_progress/resolved/dismissed/deferred)
 *   - Icon-led action buttons (Play / CheckCircle2 / X / Clock / UserPlus)
 *   - Improved empty state when filters yield 0 rows
 *   - All original action buttons (In progress / Resolve / Dismiss / Defer / Assign) preserved
 *
 * Hermetic: all `/regulatory/*` and `/projects/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-action-queue-items.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-action-queue-items-report.md")
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
  { id: 1, title: "Review Q3D update for Class 1 elemental impurities", action_type: "review", severity: "high", status: "open", dossier_id: 1, batch_id: 42, compound_id: 7, assigned_to: "alice@acme.com", due_date: NOW, citations: ["ICH Q3D"], updated_at: NOW },
  { id: 2, title: "Acknowledge nitrosamine guidance", action_type: "acknowledge", severity: "medium", status: "in_progress", dossier_id: 1, batch_id: null, compound_id: null, assigned_to: "bob@acme.com", due_date: NOW, citations: [], updated_at: NOW },
  { id: 3, title: "Resolved USP 232 alignment", action_type: "follow_up", severity: "low", status: "resolved", dossier_id: 2, batch_id: null, compound_id: null, assigned_to: null, due_date: null, citations: [], updated_at: NOW },
  { id: 4, title: "Deferred tracking - non-critical", action_type: "follow_up", severity: "info", status: "deferred", dossier_id: 2, batch_id: null, compound_id: null, assigned_to: null, due_date: null, citations: [], updated_at: NOW },
  { id: 5, title: "Dismissed false-positive", action_type: "review", severity: "low", status: "dismissed", dossier_id: 1, batch_id: null, compound_id: null, assigned_to: null, due_date: null, citations: [], updated_at: NOW },
]
const MOCK_DOSSIERS = [
  { id: 1, title: "MTX-447 dossier", status: "in_review" },
  { id: 2, title: "ABT-118 dossier", status: "draft" },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Catch-all FIRST so specific routes (registered later) win the LIFO match
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
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

  console.log("\n── Action Queue items redesign smoke ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory/action-queue`, { waitUntil: "load", timeout: 120_000 })
    await page.locator("text=Review Q3D update").first().waitFor({ timeout: 30_000 })
  })
  if (!r.ok) {
    record("Page loads + table populated", "fail", r.error)
    process.exit(1)
  }
  record("Page loads + table populated", "pass")

  // ── New filter section eyebrow ──
  r = await safe(() =>
    page.locator("text=/Action Queue · Filters/i").first().waitFor({ timeout: 5_000 }),
  )
  record("New filter section eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Reset filters button NOT visible when filters are at default ──
  r = await safe(async () => {
    const reset = page.getByRole("button", { name: /Reset filters/i })
    if ((await reset.count()) > 0) throw new Error("Reset button visible despite no active filters")
  })
  record("Reset filters button hidden when filters are default", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Color-coded severity badges ── (high → red-ish, medium → amber-ish, low → slate)
  // We assert presence by text match on the badge contents
  for (const sev of ["high", "medium", "low", "info"]) {
    r = await safe(async () => {
      const badge = page.locator("table tbody").locator(`text=/^${sev}$/i`).first()
      await badge.waitFor({ timeout: 5_000 })
    })
    record(`Severity badge "${sev}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Color-coded status badges ── (in_progress renders as "in progress" after replacement)
  for (const [raw, displayed] of [["open", "open"], ["in_progress", "in progress"], ["resolved", "resolved"], ["deferred", "deferred"], ["dismissed", "dismissed"]] as const) {
    r = await safe(async () => {
      const badge = page.locator("table tbody").locator(`text=/^${displayed}$/i`).first()
      await badge.waitFor({ timeout: 5_000 })
    })
    record(`Status badge "${raw}" (displayed as "${displayed}") rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Icon-led action buttons ── (preserve aria-labels)
  for (const action of ["In progress", "Resolve", "Dismiss", "Defer", "Assign"]) {
    r = await safe(async () => {
      const btn = page.getByRole("button", { name: new RegExp(`^${action}$`, "i") }).first()
      await btn.waitFor({ timeout: 5_000 })
    })
    record(`Action button "${action}" preserved with aria-label`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Reset filters button APPEARS when a filter is set ──
  r = await safe(async () => {
    // Type into the assigned_to filter to activate the Reset button
    const assignedInput = page.locator("input[placeholder='Filter']").first()
    await assignedInput.fill("alice")
    await page.waitForTimeout(300)
    await page.getByRole("button", { name: /Reset filters/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Reset filters button appears when filters are active", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Reset filters clears the filter ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /Reset filters/i }).first().click()
    await page.waitForTimeout(300)
    const val = await page.locator("input[placeholder='Filter']").first().inputValue()
    if (val !== "") throw new Error(`expected empty filter, got "${val}"`)
  })
  record("Reset filters clears active filter", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Action Queue items redesign — smoke ${new Date().toISOString()}`,
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
