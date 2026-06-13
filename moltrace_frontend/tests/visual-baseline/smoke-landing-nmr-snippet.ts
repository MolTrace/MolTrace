#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Spectroscopy "Explore Module" interface.
 *
 * The explore overlay is a horizontal SNAP-CAROUSEL with 3 enlarged slides:
 *   01. Resolved ¹H NMR        (CDCl₃ · 400 MHz)         ← multiplet trace
 *   02. Decoupled ¹³C NMR      (WALTZ-16 decoupled)      ← real ¹³C peaks +
 *                                                           CDCl₃ triplet @ 77
 *   03. LC-MS chromatogram     (TIC, ESI+, 30 min)       ← Gaussian peaks
 *
 * Each slide pairs a bulleted body-text panel (left) with the enlarged figure
 * (right). They flow together: scrolling/dragging horizontally moves the text
 * AND the figure as one slide. Pagination uses indicator pills + prev/next
 * arrow buttons.
 *
 * Carousel auto-advances every 5s, looping 1 → 2 → 3 → 1. Auto-play stops
 * permanently on the first manual interaction (drag, wheel, key, or button
 * click), and pauses while the user hovers. A `?autoplay=0` query disables
 * auto-play entirely — used here so deterministic assertions don't race
 * against an auto-advance.
 *
 * Tests:
 *   PHASE A — deterministic checks under ?autoplay=0:
 *     1. NMR snippet HIDDEN by default on the Spectroscopy panel.
 *     2. Click "Explore Module" → overlay opens.
 *     3. Headline + short framing copy ("Three spectra, one continuous picture
 *        of your molecule." — exact short version).
 *     4. Carousel container exists (role=region, aria-roledescription=carousel,
 *        data-autoplay-state="stopped" because of ?autoplay=0).
 *     5. Slide 01 — title + eyebrow + 01/03 counter + ¹H <sup> rendered +
 *        bullets cover deconvolution / FID processing / USP <761>.
 *     6. Slide 02 — title + eyebrow + ¹³C <sup> rendered + "peaks" wording +
 *        CDCl₃ triplet anchor + DEPT bullets + real-13C SVG (no "stick" word
 *        in the aria-label).
 *     7. Slide 03 — title + eyebrow + TIC bullets + Gaussian-style aria-label
 *        (no "stick plot" wording).
 *     8. Pagination row: prev/next + 3 indicator pills.
 *     9. Click "Next" → indicator 02 selected; click indicator 03 → end.
 *    10. Close (X) collapses the overlay.
 *    11. Switching modules hides the overlay.
 *
 *   PHASE B — autoplay verification (no query param):
 *    12. Reload landing page (no autoplay=0).
 *    13. Open explore → carousel reports data-autoplay-state="playing".
 *    14. Wait ~6s → carousel auto-advanced to slide 02 (indicator 02 selected).
 *    15. Click prev/next or send a key → data-autoplay-state="stopped".
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-landing-nmr-snippet-report.md")
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

async function gotoLandingHydrated(page: Page, queryString = "") {
  await page.goto(`${BASE_URL}/${queryString}`, { waitUntil: "load", timeout: 120_000 })
  // Wait on a chain of stable anchors — Next.js dev-server hydration is
  // genuinely flaky and the only robust mitigation is to confirm the marketing
  // section + active panel + nested content is mounted before probing.
  await page.locator("text=Three modules. One unified platform.").first().waitFor({ timeout: 30_000 })
  await page.getByRole("button", { name: /^MODULE 01$/i }).first().waitFor({ timeout: 15_000 })
  await page.locator("section#platform").locator("text=Capabilities").first().waitFor({ timeout: 15_000 })
  await page.locator("text=/1D & 2D NMR interpretation/").first().waitFor({ timeout: 15_000 })
  await page.waitForTimeout(800)
}

async function clickExploreSpectroscopy(page: Page) {
  const exploreBtn = page
    .locator("section#platform")
    .getByRole("button", { name: /Explore Module/i })
    .first()
  await exploreBtn.waitFor({ timeout: 10_000 })
  await exploreBtn.click()
  await page
    .locator('[role="region"][aria-roledescription="carousel"]')
    .first()
    .waitFor({ timeout: 10_000 })
  await page.waitForTimeout(400)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Landing Spectroscopy explore carousel smoke ─────────")
  console.log("── Phase A: deterministic checks (?autoplay=0) ───────────")

  let r = await safe(() => gotoLandingHydrated(page, "?autoplay=0"))
  if (!r.ok) {
    record("Landing page loads", "fail", r.error)
    process.exit(1)
  }
  record("Landing page loads (?autoplay=0)", "pass")

  // ── 1. NMR snippet HIDDEN on default Spectroscopy panel ──
  r = await safe(async () => {
    const count = await page.locator("text=/Resolved 1H NMR/i").count()
    if (count > 0) throw new Error(`expected 0 1H NMR titles in default view, got ${count}`)
  })
  record("¹H NMR slide HIDDEN by default on Spectroscopy panel", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("Default Spectroscopy view still renders Capabilities card", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const count = await page.locator("text=/Uncover the Ground Truth in Your Data/i").count()
    if (count > 0) throw new Error(`expected explore headline hidden, got ${count}`)
  })
  record("Explore headline HIDDEN by default", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2. Click "Explore Module" → overlay opens ──
  r = await safe(() => clickExploreSpectroscopy(page))
  record("Click 'Explore Module' on Spectroscopy", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 3. Headline + new SHORT framing copy ──
  r = await safe(() =>
    page.locator("text=Uncover the Ground Truth in Your Data.").first().waitFor({ timeout: 10_000 }),
  )
  record("Headline 'Uncover the Ground Truth in Your Data.' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=Spectroscopy Intelligence · Live preview").first().waitFor({ timeout: 10_000 }),
  )
  record("Eyebrow 'Spectroscopy Intelligence · Live preview' rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // The new short framing — verify the EXACT text and that the longer
  // legacy sentence is NOT rendered anywhere (regression guard).
  r = await safe(() =>
    page.locator("text=Three spectra, one continuous picture of your molecule.").first().waitFor({ timeout: 10_000 }),
  )
  record("Short framing 'Three spectra, one continuous picture of your molecule.'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const count = await page.locator("text=/each slide carries the commentary/i").count()
    if (count > 0) throw new Error(`legacy long framing sentence still present, count=${count}`)
  })
  record("Legacy long framing sentence is GONE (regression guard)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // The auto-advance "hint row" was removed per UX decision — the carousel
  // still auto-advances (Phase B verifies that), but we no longer advertise
  // the cadence in copy. This is a regression guard.
  r = await safe(async () => {
    const count = await page.locator("text=/Auto-advancing every 5 seconds/i").count()
    if (count > 0) throw new Error(`auto-advance hint row should be removed, count=${count}`)
  })
  record("Auto-advance hint row REMOVED (no copy advertising the cadence)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 4. Carousel container with autoplay disabled by ?autoplay=0 ──
  const carouselWrapperSel = '[data-autoplay-state]'
  r = await safe(() =>
    page
      .locator('[role="region"][aria-roledescription="carousel"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("Carousel container rendered (role=region + aria-roledescription)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const wrapper = page.locator(carouselWrapperSel).first()
    await wrapper.waitFor({ timeout: 10_000 })
    const state = await wrapper.getAttribute("data-autoplay-state")
    if (state !== "stopped") throw new Error(`expected data-autoplay-state="stopped", got "${state}"`)
  })
  record("Auto-play DISABLED by ?autoplay=0 (data-autoplay-state=stopped)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 5. Slide 01 — ¹H NMR ──
  r = await safe(() => page.locator("text=Resolved 1H NMR").first().waitFor({ timeout: 10_000 }))
  record("Slide 01: 'Resolved ¹H NMR' title rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Verify the ¹ is rendered as <sup> — actual structural check
  r = await safe(async () => {
    const count = await page.locator("h4:has-text('Resolved') sup:has-text('1')").count()
    if (count < 1) throw new Error(`expected <sup>1</sup> inside ¹H NMR title, found ${count}`)
  })
  record("Slide 01: '1' rendered as <sup> superscript inside title", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/1H NMR · 01 \\/ 03/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01: eyebrow with '01 / 03' counter rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/CDCl₃ · 400 MHz/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01: 'CDCl₃ · 400 MHz' subtitle rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Slide 01 bullets
  r = await safe(() => page.locator("text=/Automated deconvolution unwraps overlapping multiplets/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01 bullet: deconvolution / quartet under residual solvent", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/apodization, zero-filling, phase correction/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01 bullet: 'apodization, zero-filling, phase correction'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/Auto-referenced against a known standard/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01 bullet: auto-referencing / re-derivable shifts", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/USP <761>-ready integrations/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01 bullet: USP <761>-ready integrations", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/SNR 240/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 01 footer: 'SNR 240' badge rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page
      .locator('svg[role="img"][aria-label*="Resolved 1H NMR spectrum"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("Slide 01: ¹H NMR SVG figure rendered with role=img", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 6. Slide 02 — ¹³C NMR (real-13C styling) ──
  r = await safe(() => page.locator("text=Decoupled 13C NMR").first().waitFor({ timeout: 10_000 }))
  record("Slide 02: 'Decoupled ¹³C NMR' title rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Verify '13' is rendered as <sup>13</sup>
  r = await safe(async () => {
    const count = await page.locator("h4:has-text('Decoupled') sup:has-text('13')").count()
    if (count < 1) throw new Error(`expected <sup>13</sup> inside ¹³C NMR title, found ${count}`)
  })
  record("Slide 02: '13' rendered as <sup> superscript inside title", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/13C NMR · 02 \\/ 03/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 02: eyebrow with '02 / 03' counter rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/WALTZ-16 decoupled/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 02: 'WALTZ-16 decoupled' subtitle rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── PEAK terminology — must use 'peak' not 'stick' ──
  r = await safe(() =>
    page.locator("text=/Proton-decoupled acquisition.*single sharp peak/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Slide 02 bullet uses 'peak' (not 'stick'): single sharp peak per carbon", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // CDCl₃ triplet bullet — the new 'real ¹³C' anchor
  r = await safe(() =>
    page.locator("text=/Signature CDCl₃ triplet at δ 77\\.0/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Slide 02 bullet: CDCl₃ triplet @ δ 77.0 anchor (real-¹³C signature)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/DEPT-135/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 02 bullet: DEPT-135 multiplicity confirmation", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/DEPT confirmed/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 02 footer: 'DEPT confirmed' badge rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // SVG aria-label must NOT say "stick spectrum" anymore (regression guard)
  r = await safe(async () => {
    const stickCount = await page.locator('svg[aria-label*="stick spectrum"]').count()
    if (stickCount > 0) throw new Error(`13C SVG still labelled with "stick spectrum", count=${stickCount}`)
  })
  record("Slide 02: 13C SVG aria-label no longer uses 'stick spectrum'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page
      .locator('svg[role="img"][aria-label*="Decoupled 13C NMR spectrum"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("Slide 02: 13C NMR SVG figure rendered with role=img", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // The new CDCl₃ triplet feature must appear in the SVG aria-label
  r = await safe(async () => {
    const svg = page.locator('svg[role="img"][aria-label*="13C NMR"]').first()
    const label = await svg.getAttribute("aria-label")
    if (!label || !/CDCl3 triplet 77/i.test(label)) {
      throw new Error(`13C SVG aria-label missing CDCl3 triplet 77 mention: "${label}"`)
    }
  })
  record("Slide 02: 13C SVG aria-label mentions 'CDCl3 triplet 77'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // δ-prefixed peak labels visible inside the SVG
  for (const peak of [
    { display: "δ 205.3 / C=O", re: /δ 205\.3/ },
    { display: "δ 170.2 / COOR", re: /δ 170\.2/ },
    { display: "δ 77.0 / CDCl₃", re: /δ 77\.0/ },
    { display: "δ 22.1 / CH₃", re: /δ 22\.1/ },
  ]) {
    r = await safe(() => page.locator(`text=${peak.re}`).first().waitFor({ timeout: 10_000 }))
    record(`Slide 02: 13C peak label "${peak.display}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── 7. Slide 03 — LC-MS (Gaussian-shaped chromatographic peaks) ──
  r = await safe(() => page.locator("text=LC-MS chromatogram (TIC)").first().waitFor({ timeout: 10_000 }))
  record("Slide 03: 'LC-MS chromatogram (TIC)' title rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/LC-MS · 03 \\/ 03/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 03: eyebrow with '03 / 03' counter rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/30 min gradient/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 03: 'ESI+ · 30 min gradient' subtitle rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Slide 03 bullets — TIC / annotated m/z / library matching, with 'peak' wording
  r = await safe(() => page.locator("text=/Total Ion Chromatogram/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 03 bullet: TIC over 30-min gradient", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.locator("text=/Each retention-time peak is m\\/z-annotated/i").first().waitFor({ timeout: 10_000 }),
  )
  record("Slide 03 bullet uses 'peak' (not 'stick'): retention-time peak m/z-annotated", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/MS² fragmentation/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 03 bullet: MS² fragmentation library matching", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=/Five features auto-tagged/i").first().waitFor({ timeout: 10_000 }))
  record("Slide 03 bullet: five features → regulatory dossier", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // SVG aria-label must NOT say "stick plot" (regression guard)
  r = await safe(async () => {
    const stickCount = await page.locator('svg[aria-label*="stick plot"]').count()
    if (stickCount > 0) throw new Error(`LC-MS SVG still labelled "stick plot", count=${stickCount}`)
  })
  record("Slide 03: LC-MS SVG aria-label no longer uses 'stick plot'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page
      .locator('svg[role="img"][aria-label*="LC-MS total ion chromatogram"]')
      .first()
      .waitFor({ timeout: 10_000 }),
  )
  record("Slide 03: LC-MS chromatogram SVG rendered with role=img", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // m/z annotations on Gaussian peaks
  for (const mz of ["m/z 195", "m/z 251", "m/z 412"]) {
    r = await safe(() => page.locator(`text=${mz}`).first().waitFor({ timeout: 10_000 }))
    record(`Slide 03: LC-MS peak label "${mz}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // Confirm exactly 3 spectrum SVGs (one per slide)
  r = await safe(async () => {
    const svgs = await page.locator('section#platform svg[role="img"]').count()
    if (svgs !== 3) throw new Error(`expected 3 spectrum SVGs (¹H + ¹³C + LC-MS), got ${svgs}`)
  })
  record("Exactly 3 spectrum SVG figures rendered (one per carousel slide)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 8. Pagination ──
  r = await safe(() =>
    page.getByRole("button", { name: /^Previous spectrum$/i }).first().waitFor({ timeout: 10_000 }),
  )
  record("Pagination: 'Previous spectrum' arrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByRole("button", { name: /^Next spectrum$/i }).first().waitFor({ timeout: 10_000 }),
  )
  record("Pagination: 'Next spectrum' arrow rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const tabs = await page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]').count()
    if (tabs !== 3) throw new Error(`expected 3 indicator tabs, got ${tabs}`)
  })
  record("Pagination: 3 indicator pills rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const prev = page.getByRole("button", { name: /^Previous spectrum$/i }).first()
    if (!(await prev.isDisabled())) throw new Error(`Previous should be disabled at slide 01`)
  })
  record("First load: Previous arrow disabled (carousel starts at slide 01)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    const tabs = page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]')
    const sel = await tabs.nth(0).getAttribute("aria-selected")
    if (sel !== "true") throw new Error(`indicator 1 aria-selected = "${sel}", expected "true"`)
  })
  record("First load: indicator 01 selected (aria-selected=true)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 9. Click "Next spectrum" → indicator 02 selected ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /^Next spectrum$/i }).first().click()
    await page.waitForTimeout(900) // smooth scroll + scroll-snap settle
    const tabs = page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]')
    const sel = await tabs.nth(1).getAttribute("aria-selected")
    if (sel !== "true") throw new Error(`indicator 2 aria-selected = "${sel}", expected "true"`)
  })
  record("Click 'Next spectrum' advances to slide 02 (¹³C NMR)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Click indicator 03 → end
  r = await safe(async () => {
    const tabs = page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]')
    await tabs.nth(2).click()
    await page.waitForTimeout(900)
    const sel = await tabs.nth(2).getAttribute("aria-selected")
    if (sel !== "true") throw new Error(`indicator 3 aria-selected = "${sel}", expected "true"`)
    const next = page.getByRole("button", { name: /^Next spectrum$/i }).first()
    if (!(await next.isDisabled())) throw new Error("Next should be disabled at slide 03")
  })
  record("Click indicator 03 jumps to LC-MS slide (Next disabled at end)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 10. Close ──
  r = await safe(async () => {
    const closeBtn = page.getByRole("button", { name: /Close explore preview/i }).first()
    await closeBtn.waitFor({ timeout: 10_000 })
    await closeBtn.click()
    await page.waitForTimeout(400)
    const stillOpen = await page.locator("text=/Uncover the Ground Truth in Your Data/i").count()
    if (stillOpen > 0) throw new Error(`overlay still open after close, count=${stillOpen}`)
  })
  record("Close (X) button collapses the overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 }))
  record("After close: Capabilities card restored", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 11. Re-open + module-switch hides overlay ──
  r = await safe(() => clickExploreSpectroscopy(page))
  record("Re-open explore overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 02$/i }).first().click()
    await page.waitForTimeout(500)
    const stillOpen = await page.locator("text=/Uncover the Ground Truth in Your Data/i").count()
    if (stillOpen > 0) throw new Error(`overlay still open on Module 02, count=${stillOpen}`)
  })
  record("Switching to Module 02 hides explore overlay (useEffect cleanup)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.locator("text=Regentry").first().waitFor({ timeout: 10_000 }))
  record("Module 02 still renders 'Regentry'", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /^MODULE 01$/i }).first().click()
    await page.waitForTimeout(500)
    await page.locator("text=Capabilities").first().waitFor({ timeout: 10_000 })
  })
  record("Switching back to Module 01 returns to default view (overlay closed)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ────────────────────────────────────────────────────────────────────────
  console.log("\n── Phase B: AUTO-PLAY behavior verification (no query) ──")
  // ────────────────────────────────────────────────────────────────────────

  // ── 12. Reload landing without ?autoplay=0 ──
  r = await safe(() => gotoLandingHydrated(page, ""))
  record("Phase B: reload landing page (autoplay enabled)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => clickExploreSpectroscopy(page))
  record("Phase B: open explore overlay", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 13. data-autoplay-state should be 'playing' ──
  r = await safe(async () => {
    const wrapper = page.locator('[data-autoplay-state]').first()
    await wrapper.waitFor({ timeout: 10_000 })
    const state = await wrapper.getAttribute("data-autoplay-state")
    if (state !== "playing") throw new Error(`expected 'playing', got "${state}"`)
  })
  record("Phase B: auto-play active by default (data-autoplay-state=playing)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 14. Wait for auto-advance to slide 02 ──
  // Auto-advance fires every AUTOPLAY_INTERVAL_MS (5s in component code).
  // Under dev-server load on Next.js, the JS event loop can lag, so we poll
  // for slide-02 selection rather than waiting a fixed duration.
  r = await safe(async () => {
    // Initial state should be slide 01
    const tabs = page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]')
    const initial = await tabs.nth(0).getAttribute("aria-selected")
    if (initial !== "true") throw new Error(`pre-wait: indicator 1 expected selected, got "${initial}"`)
    // Poll up to 12s for the next auto-advance (interval is 5s + smooth-scroll
    // settle of ~500ms; under load this can stretch to 8-10s).
    await page.waitForFunction(
      () => {
        const tab = document.querySelector(
          '[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]:nth-child(2)',
        )
        return tab?.getAttribute("aria-selected") === "true"
      },
      null,
      { timeout: 12_000 },
    )
  })
  record("Phase B: auto-advance to slide 02 within 12s", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 15. Manual interaction stops auto-play ──
  // We only care about the latch flipping (data-autoplay-state=stopped). The
  // exact slide position post-click is irrelevant — the next test verifies
  // "stays put" by snapshotting whatever slide we land on and checking it
  // doesn't change.
  r = await safe(async () => {
    const prev = page.getByRole("button", { name: /^Previous spectrum$/i }).first()
    await prev.click()
    // Wait for the autoplay latch to flip — this is set synchronously inside
    // gotoSlide, so should be near-instant after click.
    await page.waitForFunction(
      () => document.querySelector("[data-autoplay-state]")?.getAttribute("data-autoplay-state") === "stopped",
      null,
      { timeout: 5_000 },
    )
    // Belt-and-braces snapshot read for the assertion message.
    const wrapper = page.locator('[data-autoplay-state]').first()
    const state = await wrapper.getAttribute("data-autoplay-state")
    if (state !== "stopped") throw new Error(`expected 'stopped' after manual nav, got "${state}"`)
  })
  record("Phase B: manual nav permanently stops auto-play (data-autoplay-state=stopped)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // After stopping, the carousel must not auto-advance again. Snapshot the
  // current indicator pattern (whichever slide we landed on after Prev), wait
  // 6.5s, and confirm it didn't change.
  r = await safe(async () => {
    const tabs = page.locator('[role="tablist"][aria-label*="Spectrum indicators"] [role="tab"]')
    // Let any in-flight smooth scroll settle first.
    await page.waitForTimeout(800)
    const before = await Promise.all([0, 1, 2].map((i) => tabs.nth(i).getAttribute("aria-selected")))
    await page.waitForTimeout(6_500)
    const after = await Promise.all([0, 1, 2].map((i) => tabs.nth(i).getAttribute("aria-selected")))
    if (after.join(",") !== before.join(",")) {
      throw new Error(
        `carousel auto-advanced after stop! before=[${before.join(",")}] after=[${after.join(",")}]`,
      )
    }
  })
  record("Phase B: carousel stays put after auto-play stopped (no further auto-advance)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Landing Spectroscopy explore carousel smoke — ${new Date().toISOString()}`,
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
