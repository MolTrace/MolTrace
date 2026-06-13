#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the AppTopbar widgets:
 *   - Search projects... button + CommandDialog
 *   - AI Queue button + badge
 *   - Tenant selector (MolTrace workspace)
 *   - Theme toggle
 *   - Notifications bell + dropdown
 *   - Profile (avatar) dropdown with Profile / Settings / Help & Support / Sign Out
 *
 * Hermetic: backend mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-topbar-widgets.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-topbar-widgets-report.md")
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
  // Catch-all FIRST so specific routes (registered later) win the LIFO match
  await page.route(/\/api\/backend\/.+$/, (r) => fulfillJson(r, []))
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── AppTopbar widgets baseline regression ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2500)
  })
  if (!r.ok) {
    record("Dashboard route loads (topbar mounted)", "fail", r.error)
    process.exit(1)
  }
  record("Dashboard route loads (topbar mounted)", "pass")

  // ── Search button preserved ──
  r = await safe(() =>
    page.getByRole("button", { name: /Search projects/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Search 'Search projects...' button preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── AI Queue button preserved (matches "AI Queue" or new aria-label "Toggle AI Evidence Queue") ──
  r = await safe(() =>
    page.getByRole("button", { name: /AI (Queue|Evidence)/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("AI Queue button preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Tenant selector preserved (shows tenant name) ──
  r = await safe(() => page.locator("text=Local development tenant").first().waitFor({ timeout: 5_000 }))
  record("Tenant selector ('Local development tenant') preserved", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Notifications dropdown opens + shows current items ──
  r = await safe(async () => {
    const bell = page.locator("header button:has(svg.lucide-bell)").first()
    await bell.click()
    await page.waitForTimeout(400)
    await page.locator("text=Notifications").first().waitFor({ timeout: 5_000 })
  })
  record("Notifications dropdown opens + shows 'Notifications' label", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // After redesign: dropdown should still render with empty state OR real items
  // Either an "Inbox" empty state OR a "View all notifications" footer link must be present
  r = await safe(() =>
    page.locator("text=/View all notifications|No new notifications/i").first().waitFor({ timeout: 5_000 }),
  )
  record(
    "Notifications dropdown shows empty state OR 'View all notifications' link",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )

  // Close notifications by pressing Escape
  await page.keyboard.press("Escape")
  await page.waitForTimeout(300)

  // ── Profile dropdown opens + shows all 4 menu items ──
  r = await safe(async () => {
    // Profile dropdown trigger is the LAST button in the header
    const triggers = page.locator("header button")
    const last = triggers.last()
    await last.click()
    await page.waitForTimeout(400)
    // After redesign: shows tenant display name OR generic "MolTrace user"
    await page.locator("text=/Active workspace|Local development tenant|MolTrace user/i").first().waitFor({ timeout: 5_000 })
  })
  record("Profile dropdown opens + shows user label", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const item of ["Profile", "Settings", "Help & Support", "Sign Out"]) {
    r = await safe(() =>
      page.getByRole("menuitem", { name: new RegExp(`^${item}$`, "i") }).first().waitFor({ timeout: 5_000 }),
    )
    record(`Profile dropdown menuitem "${item}" present`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await page.keyboard.press("Escape")
  await page.waitForTimeout(300)

  // ── Search command dialog opens ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /Search projects/i }).first().click()
    await page.waitForTimeout(400)
    // Quick navigation is the always-present group (project/reaction/session groups appear when there's data)
    await page.locator("text=/Quick navigation/i").first().waitFor({ timeout: 5_000 })
  })
  record("Search command dialog opens + shows 'Quick navigation' group", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // After redesign: search shows real-data groups OR a Quick navigation fallback
  // Quick navigation entries always present
  for (const item of ["Open SpectraCheck", "Open Regentry", "Open Reaction Optimization"]) {
    r = await safe(() => page.locator(`text=${item}`).first().waitFor({ timeout: 5_000 }))
    record(`Search 'Quick navigation' entry "${item}" present`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await page.keyboard.press("Escape")
  await page.waitForTimeout(300)

  // ── AI Evidence Queue side-panel ── (open by default per ResponsiveAppShell)
  r = await safe(() => page.locator("text=AI Evidence Queue").first().waitFor({ timeout: 5_000 }))
  record("AI Evidence Queue side-panel rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.getByRole("link", { name: /View All Analyses/i }).first().waitFor({ timeout: 5_000 }))
  record("AI Evidence Queue 'View All Analyses' link rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Sidebar nav links preserved ──
  for (const navLink of ["Dashboard", "Projects", "Programs", "Action Queue"]) {
    r = await safe(() =>
      page.locator("nav, [role='navigation']").locator(`text=${navLink}`).first().waitFor({ timeout: 5_000 }),
    )
    record(`Sidebar nav "${navLink}" preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# AppTopbar widgets baseline regression — ${new Date().toISOString()}`,
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
