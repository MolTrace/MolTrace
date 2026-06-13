#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the landing page's "Three modules" section.
 *
 * Locks in the current contract:
 *   - Section heading "Three modules. One unified platform."
 *   - 3 tab buttons (Module 01 / Module 02 / Module 03)
 *   - Active module shows: title, writeup, "Most Popular" badge (Spectroscopy
 *     only), Explore Module button, Capabilities heading + 6 features
 *   - Switching tabs swaps the displayed module info
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-landing-modules-report.md")
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
  await page.route(/\/api\/backend\/.+$/, (r) => fulfillJson(r, []))
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Landing 'Three modules' baseline regression ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/`, { waitUntil: "load", timeout: 120_000 })
    // Wait on a chain of stable anchors before probing — Next.js dev-server
    // hydration is genuinely slow and the only robust mitigation is to
    // confirm the marketing section + active panel content is mounted.
    await page.locator("text=Three modules. One unified platform.").first().waitFor({ timeout: 30_000 })
    await page.getByRole("button", { name: /^MODULE 01$/i }).first().waitFor({ timeout: 15_000 })
    await page.locator("section#platform").locator("text=Capabilities").first().waitFor({ timeout: 15_000 })
    await page.locator("text=/1D & 2D NMR interpretation/").first().waitFor({ timeout: 15_000 })
    await page.waitForTimeout(800)
  })
  if (!r.ok) {
    record("Landing page loads", "fail", r.error)
    process.exit(1)
  }
  record("Landing page loads", "pass")

  // ── Section heading ──
  r = await safe(() => page.locator("text=Three modules. One unified platform.").first().waitFor({ timeout: 10_000 }))
  record("Section heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Each module is purpose-built for scientific rigour").first().waitFor({ timeout: 10_000 }))
  record("Section subtitle rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 3 tab buttons ──
  for (const tab of ["MODULE 01", "MODULE 02", "MODULE 03"]) {
    r = await safe(() =>
      page.getByRole("button", { name: new RegExp(`^${tab}$`, "i") }).first().waitFor({ timeout: 10_000 }),
    )
    record(`Tab button "${tab}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Default active panel: Spectroscopy Intelligence ──
  r = await safe(() => page.locator("text=Spectroscopy Intelligence").first().waitFor({ timeout: 10_000 }))
  record("Default active module title 'Spectroscopy Intelligence' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Most Popular").first().waitFor({ timeout: 10_000 }))
  record("'Most Popular' badge rendered for Spectroscopy", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Interpret raw FID files, elucidate molecular structures/").first().waitFor({ timeout: 10_000 }),
  )
  record("Spectroscopy writeup rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Spectroscopy's "Explore Module" trigger is now a <button> (toggles the
  // explore overlay); Modules 02/03 are still <a href="#demo">. Either role is
  // a valid trigger inside the platform section.
  r = await safe(() =>
    page
      .locator("section#platform")
      .locator(`button:has-text("Explore Module"), a:has-text("Explore Module")`)
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("'Explore Module' trigger preserved (button or link)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Capabilities card ──
  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("Capabilities heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const feature of [
    "1D & 2D NMR interpretation",
    "LC-MS/MS fragmentation",
    "Unknown compound structure",
    "Peak-to-structure mapping",
    "Residual solvent",
    "qNMR quantification",
  ]) {
    r = await safe(() => page.locator(`text=/${feature}/`).first().waitFor({ timeout: 10_000 }))
    record(`Spectroscopy capability "${feature}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Switch to Module 02 + verify content swaps ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 02$/i }).first().click()
    await page.waitForTimeout(400)
    await page.locator("text=ComplianceCore").first().waitFor({ timeout: 10_000 })
  })
  record("Switching to Module 02 swaps to 'ComplianceCore'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Switch back to Module 01
  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 01$/i }).first().click()
    await page.waitForTimeout(400)
    await page.locator("text=Spectroscopy Intelligence").first().waitFor({ timeout: 10_000 })
  })
  record("Switching back to Module 01 restores Spectroscopy view", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Landing 'Three modules' baseline regression — ${new Date().toISOString()}`,
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
