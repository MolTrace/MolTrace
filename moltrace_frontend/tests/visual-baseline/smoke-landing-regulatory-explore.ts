#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the Regulatory Intelligence Hub "Explore Module" overlay.
 *
 * The overlay opens when "Explore Module" is clicked on Module 02 (Regulatory).
 * Composed of:
 *   • Headline — "Built-in Compliance and Safety."
 *   • Bulleted body — how QA-RAG checks against EPA / FDA / ICH guidance
 *     (4 bullets covering corpora, citation grounding, jurisdiction-aware
 *     thresholds, human-reviewer gate)
 *   • Visual — a chat-snippet showing a chemist asking about NDMA dosing,
 *     QA-RAG flagging it as a Class 1 mutagen with cited regulations and a
 *     "requires reviewer sign-off · PENDING" gate
 *
 * Hermetic: backend mocked.
 *
 * Verifies:
 *   1. Overlay HIDDEN by default on the Regulatory panel.
 *   2. Click "Explore Module" → overlay opens.
 *   3. Headline rendered.
 *   4. All 4 bullets rendered (covering EPA/FDA/ICH/REACH, RAG grounding,
 *      jurisdiction thresholds, reviewer gate).
 *   5. QA-RAG chat snippet renders with role=img + descriptive aria-label.
 *   6. Chat content: user question, flagged Class 1 mutagen warning, NDMA
 *      96 ng/day cited, 3 citation chips (ICH M7, FDA, EMA), PENDING gate.
 *   7. Close (X) collapses the overlay back to Capabilities view.
 *   8. Switching to Module 01 (Spectroscopy) hides the overlay.
 *   9. Switching to Module 03 (Reaction) hides the overlay.
 *  10. Re-opening still works after a tab round-trip.
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-landing-regulatory-explore-report.md")
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

async function switchToRegulatory(page: Page) {
  await page.getByRole("button", { name: /^MODULE 02$/i }).first().click()
  await page.locator("text=Regulatory Intelligence Hub").first().waitFor({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

async function clickExploreOnActive(page: Page) {
  const exploreBtn = page
    .locator("section#platform")
    .getByRole("button", { name: /Explore Module/i })
    .first()
  await exploreBtn.waitFor({ timeout: 10_000 })
  await exploreBtn.click()
  // Wait for the regulatory region to mount before continuing.
  await page
    .locator('[role="region"][aria-label*="Regulatory Intelligence Hub"]')
    .first()
    .waitFor({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Landing Regulatory explore overlay smoke ─────────")

  let r = await safe(() => gotoLandingHydrated(page))
  if (!r.ok) {
    record("Landing page loads", "fail", r.error)
    process.exit(1)
  }
  record("Landing page loads", "pass")

  r = await safe(() => switchToRegulatory(page))
  record("Switched to Module 02 (Regulatory)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 1. Overlay HIDDEN by default ──
  r = await safe(async () => {
    const count = await page.locator("text=Built-in Compliance and Safety.").count()
    if (count > 0) throw new Error(`expected 0 explore headlines in default view, got ${count}`)
  })
  record("Regulatory explore overlay HIDDEN by default on Module 02", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("Default Regulatory view still renders Capabilities card", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2. Click Explore Module → overlay opens ──
  r = await safe(() => clickExploreOnActive(page))
  record("Click 'Explore Module' on Regulatory → overlay opens", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 3. Headline ──
  r = await safe(() =>
    page.locator("text=Built-in Compliance and Safety.").first().waitFor({ timeout: 10_000 }),
  )
  record("Headline 'Built-in Compliance and Safety.' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Regulatory Intelligence Hub · Live preview/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Eyebrow 'Regulatory Intelligence Hub · Live preview' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/QA-RAG grounds every answer in your regulatory corpus/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Short framing sentence rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 4. Bulleted body (4 bullets) ──
  r = await safe(() =>
    page.locator("text=/QA-RAG · How it works/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Body section eyebrow 'QA-RAG · How it works' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Grounded in citations").first().waitFor({ timeout: 10_000 }))
  record("Body title 'Grounded in citations' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Subtitle lists corpora (regression guard for completeness)
  r = await safe(() =>
    page.locator("text=/EPA · FDA · ICH · EMA · REACH/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Subtitle lists corpora (EPA · FDA · ICH · EMA · REACH)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const bullet of [
    { name: "ICH/EPA/FDA/REACH/SOPs corpus", re: /ICH \(Q3A\/B\/C\/D, M7, Q14\), EPA TRI, FDA Q3C/i },
    { name: "RAG grounding (no hallucinated regs)", re: /Retrieval-augmented generation grounds every claim/i },
    { name: "Jurisdiction-aware risk thresholds", re: /jurisdiction-aware: an impurity that's safe at FDA limits may flag at PMDA/i },
    { name: "Human reviewer gate for flagged findings", re: /Flagged findings.*require human reviewer sign-off/i },
  ]) {
    r = await safe(() => page.locator(`text=${bullet.re}`).first().waitFor({ timeout: 10_000 }))
    record(`Bullet: ${bullet.name}`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── 5. QA-RAG chat snippet visual ──
  r = await safe(() =>
    page
      .locator('[role="img"][aria-label*="QA-RAG chat preview"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("QA-RAG chat snippet rendered with role=img + descriptive aria-label", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Card header
  r = await safe(() => page.locator("text=/QA-RAG · Live answer/i").first().waitFor({ timeout: 10_000 }))
  record("Snippet header chip 'QA-RAG · Live answer' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 6. Chat content checks ──
  r = await safe(() =>
    page.locator("text=/Can we ship NDMA at .*110 ng\\/day.* in this generic API/i").first().waitFor({ timeout: 10_000 }),
  )
  record("User question bubble: NDMA 110 ng/day in generic API", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/Flagged · Class 1 mutagen/i").first().waitFor({ timeout: 10_000 }))
  record("Flagged toxicity warning: 'Flagged · Class 1 mutagen' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/NDMA intake is capped at .*96 ng\\/day.* per ICH M7/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Verdict cites NDMA cap at 96 ng/day per ICH M7", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const cite of ["ICH M7(R2) §6.3", "FDA Guidance 2021", "EMA/CHMP/428592/2019"]) {
    r = await safe(() => page.locator(`text=${cite}`).first().waitFor({ timeout: 10_000 }))
    record(`Citation chip "${cite}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  r = await safe(() =>
    page.locator("text=/Requires reviewer sign-off/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Reviewer gate 'Requires reviewer sign-off' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=PENDING").first().waitFor({ timeout: 10_000 }))
  record("Reviewer gate status 'PENDING' badge rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 7. Close button collapses overlay ──
  r = await safe(async () => {
    const closeBtn = page.getByRole("button", { name: /Close explore preview/i }).first()
    await closeBtn.waitFor({ timeout: 10_000 })
    await closeBtn.click()
    await page.waitForTimeout(400)
    const stillOpen = await page.locator("text=Built-in Compliance and Safety.").count()
    if (stillOpen > 0) throw new Error(`overlay still open after close, count=${stillOpen}`)
  })
  record("Close (X) button collapses the overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("After close: Capabilities card restored", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 8. Switching modules cleans up ──
  r = await safe(() => clickExploreOnActive(page))
  record("Re-open explore overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 01$/i }).first().click()
    await page.waitForTimeout(500)
    const stillOpen = await page.locator("text=Built-in Compliance and Safety.").count()
    if (stillOpen > 0) throw new Error(`overlay still open on Module 01, count=${stillOpen}`)
  })
  record("Switching to Module 01 hides overlay (useEffect cleanup)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 03$/i }).first().click()
    await page.waitForTimeout(500)
    const stillOpen = await page.locator("text=Built-in Compliance and Safety.").count()
    if (stillOpen > 0) throw new Error(`overlay still open on Module 03, count=${stillOpen}`)
  })
  record("Switching to Module 03 hides overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 9. Re-open after tab round-trip ──
  r = await safe(async () => {
    await switchToRegulatory(page)
    await clickExploreOnActive(page)
    await page.locator("text=Built-in Compliance and Safety.").first().waitFor({ timeout: 10_000 })
  })
  record("Re-open after tab round-trip works", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Landing Regulatory explore overlay smoke — ${new Date().toISOString()}`,
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
