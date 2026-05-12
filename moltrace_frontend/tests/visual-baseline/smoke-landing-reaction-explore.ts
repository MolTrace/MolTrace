#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the Reaction Optimization "Explore Module" overlay.
 *
 * The overlay opens when "Explore Module" is clicked on Module 03 (Reaction).
 * Composed of:
 *   • Headline — "Navigate Complex Chemical Space."
 *   • Bulleted body — how the LLM-GP hybrid finds the highest yield with the
 *     fewest experiments (4 bullets covering LLM proposals + GP surrogate +
 *     multi-objective acquisition + typical-campaign efficiency)
 *   • Visual — an isometric 3D response surface plot SVG, colored by yield,
 *     with experiment markers + a "BEST · 94% yield" peak callout
 *
 * Hermetic: backend mocked.
 *
 * Verifies:
 *   1. Overlay HIDDEN by default on the Reaction panel.
 *   2. Click "Explore Module" → overlay opens.
 *   3. Headline + framing + eyebrow rendered.
 *   4. All 4 bullets rendered (LLM proposes, GP refines, multi-objective,
 *      8-15 experiments to converge).
 *   5. 3D response surface SVG renders with role=img + descriptive aria-label.
 *   6. Surface has chip header ("3D response surface"), yield-vs-axes subtitle,
 *      experiment-count footer.
 *   7. Peak callout text "BEST · 94% yield" visible inside the SVG.
 *   8. Color legend rendered (35 — low / 65 — mid / 94 — peak).
 *   9. Axis labels rendered (temperature / catalyst / yield).
 *  10. Close (X) collapses the overlay back to Capabilities view.
 *  11. Switching to Module 01 / 02 hides the overlay.
 *  12. Re-opening still works after a tab round-trip.
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-landing-reaction-explore-report.md")
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

async function switchToReaction(page: Page) {
  await page.getByRole("button", { name: /^MODULE 03$/i }).first().click()
  await page.locator("text=Reaction Optimization").first().waitFor({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

async function clickExploreOnActive(page: Page) {
  const exploreBtn = page
    .locator("section#platform")
    .getByRole("button", { name: /Explore Module/i })
    .first()
  await exploreBtn.waitFor({ timeout: 10_000 })
  await exploreBtn.click()
  await page
    .locator('[role="region"][aria-label*="Reaction Optimization"]')
    .first()
    .waitFor({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Landing Reaction explore overlay smoke ─────────")

  let r = await safe(() => gotoLandingHydrated(page))
  if (!r.ok) {
    record("Landing page loads", "fail", r.error)
    process.exit(1)
  }
  record("Landing page loads", "pass")

  r = await safe(() => switchToReaction(page))
  record("Switched to Module 03 (Reaction)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 1. Overlay HIDDEN by default ──
  r = await safe(async () => {
    const count = await page.locator("text=Navigate Complex Chemical Space.").count()
    if (count > 0) throw new Error(`expected 0 explore headlines in default view, got ${count}`)
  })
  record("Reaction explore overlay HIDDEN by default on Module 03", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("Default Reaction view still renders Capabilities card", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2. Click Explore Module → overlay opens ──
  r = await safe(() => clickExploreOnActive(page))
  record("Click 'Explore Module' on Reaction → overlay opens", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 3. Headline + framing + eyebrow ──
  r = await safe(() =>
    page.locator("text=Navigate Complex Chemical Space.").first().waitFor({ timeout: 10_000 }),
  )
  record("Headline 'Navigate Complex Chemical Space.' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Reaction Optimization · Live preview/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Eyebrow 'Reaction Optimization · Live preview' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/An LLM-GP hybrid finds the highest-yielding conditions/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Short framing sentence rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 4. Bulleted body (4 bullets) ──
  r = await safe(() =>
    page.locator("text=/LLM-GP hybrid · How it converges/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Body section eyebrow 'LLM-GP hybrid · How it converges' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Fewest experiments to peak").first().waitFor({ timeout: 10_000 }))
  record("Body title 'Fewest experiments to peak' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Bayesian optimization with chemistry-aware priors/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Subtitle 'Bayesian optimization with chemistry-aware priors' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const bullet of [
    { name: "LLM proposes + GP quantifies uncertainty", re: /An LLM proposes plausible reaction conditions.*Gaussian Process surrogate/i },
    { name: "Inner-loop refinement of GP, re-prompt LLM", re: /each new measurement refines the GP surrogate, which then re-prompts the LLM/i },
    { name: "Multi-objective acquisition (yield + selectivity + impurity)", re: /Multi-objective acquisition optimises yield, selectivity, AND impurity profile/i },
    { name: "8-15 experiments to converge vs 50+ for grid", re: /8 . 15 well-chosen experiments converge to .*90% of the global optimum versus 50/i },
  ]) {
    r = await safe(() => page.locator(`text=${bullet.re}`).first().waitFor({ timeout: 10_000 }))
    record(`Bullet: ${bullet.name}`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── 5. 3D response surface SVG ──
  r = await safe(() =>
    page
      .locator('svg[role="img"][aria-label*="3D response surface plot"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("3D response surface SVG rendered with role=img + descriptive aria-label", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // SVG aria-label content
  r = await safe(async () => {
    const svg = page.locator('svg[role="img"][aria-label*="3D response surface plot"]').first()
    const label = await svg.getAttribute("aria-label")
    if (!label) throw new Error("no aria-label")
    if (!/peak at 94 percent/i.test(label)) throw new Error(`aria-label missing peak %: "${label}"`)
    if (!/six experiment markers/i.test(label)) throw new Error(`aria-label missing experiment markers: "${label}"`)
  })
  record("SVG aria-label mentions 94% peak + 6 experiment markers", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 6. Card chrome (header chip + subtitle + footer) ──
  r = await safe(() =>
    page.locator("text=/3D response surface/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Card header chip '3D response surface' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/yield = f\\(temperature, catalyst loading\\)/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Card subtitle 'yield = f(temperature, catalyst loading)' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/6 experiments mapped · GP posterior shown/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Card footer '6 experiments mapped · GP posterior shown' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/σ uncertainty < 1\\.8%/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Card footer uncertainty 'σ uncertainty < 1.8%' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 7. Peak callout ──
  r = await safe(() =>
    page.locator("text=/BEST · 94% yield/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Peak callout 'BEST · 94% yield' rendered inside SVG", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 8. Color legend ──
  r = await safe(() => page.locator("text=YIELD %").first().waitFor({ timeout: 10_000 }))
  record("Color legend header 'YIELD %' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const swatch of ["35 — low", "65 — mid", "94 — peak"]) {
    r = await safe(() => page.locator(`text=${swatch}`).first().waitFor({ timeout: 10_000 }))
    record(`Color legend swatch "${swatch}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── 9. Axis labels ──
  for (const axis of [
    { name: "x — temperature", re: /temperature 60 → 120 °C/ },
    { name: "y — catalyst loading", re: /catalyst 1 → 10 mol%/ },
    { name: "z — yield range", re: /yield 35 → 94 %/ },
  ]) {
    r = await safe(() => page.locator(`text=${axis.re}`).first().waitFor({ timeout: 10_000 }))
    record(`Axis label: ${axis.name}`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // Stat row showing the headline efficiency claim
  r = await safe(() =>
    page.locator("text=/6 experiments · 94% yield/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Footer stat '6 experiments · 94% yield' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/vs\\. 50\\+ for grid/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Footer stat 'vs. 50+ for grid' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 10. Close button collapses overlay ──
  r = await safe(async () => {
    const closeBtn = page.getByRole("button", { name: /Close explore preview/i }).first()
    await closeBtn.waitFor({ timeout: 10_000 })
    await closeBtn.click()
    await page.waitForTimeout(400)
    const stillOpen = await page.locator("text=Navigate Complex Chemical Space.").count()
    if (stillOpen > 0) throw new Error(`overlay still open after close, count=${stillOpen}`)
  })
  record("Close (X) button collapses the overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("After close: Capabilities card restored", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 11. Switching modules cleans up ──
  r = await safe(() => clickExploreOnActive(page))
  record("Re-open explore overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 01$/i }).first().click()
    await page.waitForTimeout(500)
    const stillOpen = await page.locator("text=Navigate Complex Chemical Space.").count()
    if (stillOpen > 0) throw new Error(`overlay still open on Module 01, count=${stillOpen}`)
  })
  record("Switching to Module 01 hides overlay (useEffect cleanup)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 02$/i }).first().click()
    await page.waitForTimeout(500)
    const stillOpen = await page.locator("text=Navigate Complex Chemical Space.").count()
    if (stillOpen > 0) throw new Error(`overlay still open on Module 02, count=${stillOpen}`)
  })
  record("Switching to Module 02 hides overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 12. Re-open after tab round-trip ──
  r = await safe(async () => {
    await switchToReaction(page)
    await clickExploreOnActive(page)
    await page.locator("text=Navigate Complex Chemical Space.").first().waitFor({ timeout: 10_000 })
  })
  record("Re-open after tab round-trip works", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Landing Reaction explore overlay smoke — ${new Date().toISOString()}`,
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
