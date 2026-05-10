#!/usr/bin/env -S pnpm tsx
/**
 * Functional smoke test for the redesigned remaining SpectraCheck tabs:
 *   Overview, Workflow, NMR text, MS Evidence, Evidence Queue, Unified, Report, Dev JSON.
 *
 * Verifies (lightweight render & navigation):
 *   - Each tab's eyebrow tagline + h2 heading renders
 *   - Each tab can be opened from the tab strip without errors
 *   - Key sub-modules still render inside each tab
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-spectracheck-remaining-tabs.ts
 */
import { chromium, type Page } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-remaining-tabs-report.md")
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

async function gotoSpectracheck(page: Page) {
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
}
async function openTab(page: Page, tabValue: string) {
  const tab = page.getByTestId(`spectracheck-tab-${tabValue}`)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(500)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()

  console.log("\n── Remaining SpectraCheck tabs reskin smoke ─────────")
  await gotoSpectracheck(page)

  // ── tab-overview ───────────────────────────────────────────
  await openTab(page, "tab-overview")
  let r = await safe(() => page.getByText(/Spectroscopy · At a glance/i).first().waitFor({ timeout: 5_000 }))
  record("Overview eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByRole("heading", { name: /Analysis summary/i }).first().waitFor({ timeout: 5_000 }))
  record("Overview Analysis summary heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Saved-session value & linked compound/i).first().waitFor({ timeout: 5_000 }))
  record("Overview Section 3 (Session context) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Quick orientation/i).first().waitFor({ timeout: 5_000 }))
  record("Overview Section 4 (How it works) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Uploads, artifacts & recent jobs/i).first().waitFor({ timeout: 5_000 }))
  record("Overview Section 6 (Activity) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-workflow ───────────────────────────────────────────
  await openTab(page, "tab-workflow")
  r = await safe(() => page.getByText(/Pre-built analysis pipelines/i).first().waitFor({ timeout: 5_000 }))
  record("Workflow heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Choose a workflow template/i).first().waitFor({ timeout: 5_000 }))
  record("Workflow Step 1 ModuleCard rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Launch & monitor the workflow/i).first().waitFor({ timeout: 5_000 }))
  record("Workflow Step 2 ModuleCard rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-nmr-text ───────────────────────────────────────────
  await openTab(page, "tab-nmr-text")
  r = await safe(() => page.getByText(/Sample identity & solvent/i).first().waitFor({ timeout: 5_000 }))
  record("NMR text Step 1 (Sample identity) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() =>
    page.getByRole("heading", { name: "Candidate structures", exact: true }).first().waitFor({ timeout: 5_000 }),
  )
  record("NMR text Step 2 (Candidate structures) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Paste 1H and 13C NMR text/i).first().waitFor({ timeout: 5_000 }))
  record("NMR text Step 3 (Observed NMR text) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(async () => {
    const textarea = page.locator("#spectracheck-candidates")
    if ((await textarea.count()) === 0) throw new Error("candidates textarea missing")
  })
  record("NMR text candidates textarea wired", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(async () => {
    // Type into 1H NMR text and verify the chip flips to "Detected ✓"
    await page.locator("#spectracheck-proton").fill("1H NMR (400 MHz, CDCl3) δ 3.65")
    await page.waitForTimeout(200)
    await page.getByText(/^Detected ✓$/).first().waitFor({ timeout: 2_000 })
  })
  record("NMR text 1H detection chip flips Empty → Detected ✓", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-ms-evidence ────────────────────────────────────────
  await openTab(page, "tab-ms-evidence")
  r = await safe(() =>
    page.getByRole("heading", { name: /MS Evidence Studio/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("MS Evidence Studio heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/HRMS, MS\/MS & fragmentation/i).first().waitFor({ timeout: 5_000 }))
  record("MS Step 2 (Analyze) ModuleCard rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/LC-MS pipeline & confidence bridge/i).first().waitFor({ timeout: 5_000 }))
  record("MS Step 3 (Advanced LC-MS) ModuleCard rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-evidence-queue ─────────────────────────────────────
  await openTab(page, "tab-evidence-queue")
  r = await safe(() =>
    page.getByRole("heading", { name: /AI Evidence Queue/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Evidence Queue heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-unified ────────────────────────────────────────────
  await openTab(page, "tab-unified")
  r = await safe(() =>
    page.getByRole("heading", { name: /Cross-modal evidence build/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Unified Evidence heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Unified · Confidence build/i).first().waitFor({ timeout: 5_000 }))
  record("Unified Confidence build section eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-report ─────────────────────────────────────────────
  await openTab(page, "tab-report")
  r = await safe(() =>
    page.getByRole("heading", { name: /Reviewer-ready report/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Report heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Report · Build & preview/i).first().waitFor({ timeout: 5_000 }))
  record("Report Build & preview eyebrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── tab-dev-json ───────────────────────────────────────────
  await openTab(page, "tab-dev-json")
  r = await safe(() =>
    page.getByRole("heading", { name: /JSON snapshot hub/i }).first().waitFor({ timeout: 5_000 }),
  )
  record("Dev JSON heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Snapshot index/i).first().waitFor({ timeout: 5_000 }))
  record("Dev JSON Step 1 (Snapshot index) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/Raw response payloads/i).first().waitFor({ timeout: 5_000 }))
  record("Dev JSON Step 2 (Payloads) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  r = await safe(() => page.getByText(/No snapshots yet/i).first().waitFor({ timeout: 5_000 }))
  record("Dev JSON empty state rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Remaining SpectraCheck tabs reskin — smoke ${new Date().toISOString()}`,
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
