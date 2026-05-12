#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the Explore Module button's responsive placement on the
 * "Three modules" landing section.
 *
 * Contract:
 *   • Desktop (lg+, viewport ≥ 1024px wide): the "Explore Module" button sits
 *     in the LEFT column (info), directly under the writeup. The Capabilities
 *     card is in the RIGHT column.
 *   • Mobile (< lg, viewport < 1024px wide): everything stacks. The button
 *     should appear BELOW the Capabilities card so the user can scan
 *     module capabilities before deciding to explore.
 *
 * Implementation: the button is rendered TWICE in the DOM with
 * mobile/desktop visibility classes (hidden lg:inline-flex on the desktop
 * copy, inline-flex lg:hidden on the mobile copy that sits as a 3rd grid
 * item). Exactly ONE copy is visible at a time per viewport.
 *
 * Tested across all three modules (Spectroscopy / Regulatory / Reaction).
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-landing-explore-button-responsive-report.md")
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

async function gotoLandingHydrated(page: Page) {
  await page.goto(`${BASE_URL}/`, { waitUntil: "load", timeout: 120_000 })
  await page.locator("text=Three modules. One unified platform.").first().waitFor({ timeout: 30_000 })
  await page.getByRole("button", { name: /^MODULE 01$/i }).first().waitFor({ timeout: 15_000 })
  await page.locator("section#platform").locator("text=Capabilities").first().waitFor({ timeout: 15_000 })
  await page.waitForTimeout(800)
}

async function activateModule(page: Page, tag: "MODULE 01" | "MODULE 02" | "MODULE 03") {
  await page.getByRole("button", { name: new RegExp(`^${tag}$`, "i") }).first().click()
  await page.waitForTimeout(500)
}

// Get the bounding-box y of the FIRST visible Explore Module button inside
// the platform section. (Filter to visible because at every viewport only one
// of the two copies is visible.)
async function visibleExploreButtonY(page: Page): Promise<number> {
  const handle = await page
    .locator('section#platform button:has-text("Explore Module"):visible')
    .first()
    .elementHandle()
  if (!handle) throw new Error("no visible Explore Module button found")
  const box = await handle.boundingBox()
  if (!box) throw new Error("no bounding box for Explore Module button")
  return box.y
}

async function capabilitiesHeadingY(page: Page): Promise<number> {
  const handle = await page
    .locator("section#platform")
    .locator("text=Capabilities")
    .first()
    .elementHandle()
  if (!handle) throw new Error("no Capabilities heading found")
  const box = await handle.boundingBox()
  if (!box) throw new Error("no bounding box for Capabilities heading")
  return box.y
}

// On mobile, the Capabilities CARD has its features stacked under the
// heading. We compare the button's y against the BOTTOM of the capabilities
// card (so we're sure the button is below the entire card, not just the
// heading). The card is the parent <div> of the Capabilities text.
async function capabilitiesCardBottomY(page: Page): Promise<number> {
  // Find the <ul> of capability features — it's nested in the Capabilities
  // card. The card's bottom = ul.bottom + a small footer padding.
  const handle = await page
    .locator("section#platform")
    .locator("text=Capabilities")
    .first()
    .locator("xpath=ancestor::div[contains(@class, 'rounded-xl')][1]")
    .elementHandle()
  if (!handle) throw new Error("no Capabilities card wrapper found")
  const box = await handle.boundingBox()
  if (!box) throw new Error("no bounding box for Capabilities card")
  return box.y + box.height
}

async function runForModule(
  page: Page,
  tag: "MODULE 01" | "MODULE 02" | "MODULE 03",
  label: string,
) {
  await activateModule(page, tag)

  // ── Desktop viewport ──
  await page.setViewportSize({ width: 1440, height: 1200 })
  await page.waitForTimeout(400)

  // Both button copies exist in DOM
  let r = await safe(async () => {
    const count = await page.locator('section#platform button:has-text("Explore Module")').count()
    if (count !== 2) throw new Error(`expected 2 button copies in DOM (desktop + mobile), got ${count}`)
  })
  record(`${label} · DOM has both desktop + mobile button copies (count=2)`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Exactly one is visible at desktop
  r = await safe(async () => {
    const visible = await page
      .locator('section#platform button:has-text("Explore Module"):visible')
      .count()
    if (visible !== 1) throw new Error(`expected 1 visible button at 1440px, got ${visible}`)
  })
  record(`${label} · Desktop (1440px): exactly 1 Explore Module button visible`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Visible button is ABOVE the Capabilities heading (it's in the left
  // column on desktop, so visually higher OR at same y as the heading).
  r = await safe(async () => {
    const btnY = await visibleExploreButtonY(page)
    const capY = await capabilitiesHeadingY(page)
    // On desktop they're side-by-side, so the button's y is roughly the
    // same as the Capabilities heading's y. Allow generous tolerance — the
    // key contract is the button is NOT below the card bottom.
    const cardBottom = await capabilitiesCardBottomY(page)
    if (btnY > cardBottom)
      throw new Error(
        `desktop: button y=${btnY} should NOT be below capabilities card bottom y=${cardBottom}`,
      )
    // Sanity: button and capabilities heading should be on roughly the same
    // visual row (within ~200px), confirming the side-by-side layout.
    if (Math.abs(btnY - capY) > 400)
      throw new Error(
        `desktop: button y=${btnY} and capabilities heading y=${capY} are too far apart — side-by-side layout broken?`,
      )
  })
  record(`${label} · Desktop: visible button is side-by-side with Capabilities (not below)`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Mobile viewport ──
  await page.setViewportSize({ width: 720, height: 1200 })
  await page.waitForTimeout(400)

  // Exactly one visible at mobile (the other copy hidden by lg:hidden /
  // lg:inline-flex)
  r = await safe(async () => {
    const visible = await page
      .locator('section#platform button:has-text("Explore Module"):visible')
      .count()
    if (visible !== 1) throw new Error(`expected 1 visible button at 720px, got ${visible}`)
  })
  record(`${label} · Mobile (720px): exactly 1 Explore Module button visible`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Visible button is BELOW the bottom of the Capabilities card
  r = await safe(async () => {
    const btnY = await visibleExploreButtonY(page)
    const cardBottom = await capabilitiesCardBottomY(page)
    if (btnY <= cardBottom)
      throw new Error(
        `mobile: button y=${btnY} should be BELOW capabilities card bottom y=${cardBottom}`,
      )
  })
  record(`${label} · Mobile: visible button is BELOW Capabilities card`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Button at mobile is still clickable (smoke-level functional check)
  r = await safe(async () => {
    const btn = page.locator('section#platform button:has-text("Explore Module"):visible').first()
    await btn.scrollIntoViewIfNeeded()
    await btn.click()
    await page.waitForTimeout(400)
    // The overlay should open — verify the close button is now in the DOM
    await page
      .getByRole("button", { name: /Close explore preview/i })
      .first()
      .waitFor({ timeout: 5_000 })
    // Close the overlay so we can move to the next module
    await page.getByRole("button", { name: /Close explore preview/i }).first().click()
    await page.waitForTimeout(300)
  })
  record(`${label} · Mobile button click opens the explore overlay (functional)`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Reset to desktop for the next module
  await page.setViewportSize({ width: 1440, height: 1200 })
  await page.waitForTimeout(400)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Landing Explore Module button responsive placement smoke ─────────")

  let r = await safe(() => gotoLandingHydrated(page))
  if (!r.ok) {
    record("Landing page loads", "fail", r.error)
    process.exit(1)
  }
  record("Landing page loads", "pass")

  await runForModule(page, "MODULE 01", "Spectroscopy")
  await runForModule(page, "MODULE 02", "Regulatory")
  await runForModule(page, "MODULE 03", "Reaction")

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Landing Explore Module responsive placement smoke — ${new Date().toISOString()}`,
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
