#!/usr/bin/env -S pnpm tsx
/**
 * Functional smoke test for the redesigned SpectraCheck upload tabs.
 *
 * For each tab (Processed 1H/13C, Raw FID), it exercises every interactive
 * element: pill toggles, advanced collapsible, drop-zone (drag-drop and click-
 * to-browse), selected-file chip and its X clear, and the action tile buttons.
 * Network requests to /nmr/* are intercepted and mocked so the buttons can be
 * clicked without a backend.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-spectracheck-uploads.ts
 */

import { chromium, type Page } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-uploads-report.md")
const BASE_URL = "http://localhost:3000"

type CheckResult = { tab: string; check: string; status: "pass" | "fail"; detail?: string }
const results: CheckResult[] = []

function record(tab: string, check: string, status: "pass" | "fail", detail?: string) {
  results.push({ tab, check, status, detail })
  const icon = status === "pass" ? "✓" : "✗"
  console.log(`  ${icon} ${tab.padEnd(18)} ${check}${detail ? ` — ${detail}` : ""}`)
}

async function safe<T>(fn: () => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: string }> {
  try {
    return { ok: true, value: await fn() }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}

async function gotoTab(page: Page, tabId: string) {
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 60_000 })
  await page.waitForTimeout(1500)
  const tab = page.getByTestId(`spectracheck-tab-${tabId}`)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(800)
}

/**
 * Mocks all /nmr/* POST endpoints so action buttons can fire without a backend.
 * Returns a counter of intercepted requests.
 */
async function mockNmrApis(page: Page): Promise<{ counts: Record<string, number> }> {
  const counts: Record<string, number> = {}
  await page.route(/\/nmr\/.+/, async (route) => {
    const url = new URL(route.request().url()).pathname
    counts[url] = (counts[url] ?? 0) + 1
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sample_id: "smoke-test",
        nucleus: "1H",
        x: [4.2, 4.1, 4.0],
        y: [0, 3, 0],
        peaks: [{ ppm: 4.1, intensity: 1e3 }],
        warnings: [],
        notes: [],
        peak_count: 1,
        score: 0.9,
        raw_sha256: "a".repeat(64),
        vendor_detected: "bruker",
        spectral_width_hz: 8000,
        time_domain_points: 65536,
        processing_parameters: { lb: 0.3 },
      }),
    })
  })
  return { counts }
}

async function testProcessedTab(page: Page) {
  const tab = "Processed"
  await gotoTab(page, "tab-processed")

  // 1. Page heading visible
  let r = await safe(() => page.getByText("Configure & upload spectrum", { exact: true }).first().waitFor({ timeout: 5_000 }))
  record(tab, "Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 2. Nucleus pill toggle: click 13C, then back to 1H
  const nucleus13c = page.locator("button", { hasText: /^13C$/ }).first()
  r = await safe(async () => {
    await nucleus13c.click()
    await page.waitForTimeout(150)
    // Active style is inline backgroundColor — assert the computed bg looks "filled"
    const bg = await nucleus13c.evaluate((el) => getComputedStyle(el).backgroundColor)
    if (!bg.includes("rgb")) throw new Error(`unexpected bg: ${bg}`)
  })
  record(tab, "Nucleus pill 13C → 1H toggle", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  await page.locator("button", { hasText: /^1H$/ }).first().click()

  // 3. Advanced collapsible toggles
  r = await safe(async () => {
    const adv = page.getByRole("button", { name: /Advanced options/i })
    await adv.click()
    await page.waitForTimeout(300)
    // After expanding, "Reuse session file" should be visible
    await page.getByText(/Reuse session file/i).waitFor({ timeout: 2_000 })
    await adv.click()
    await page.waitForTimeout(300)
  })
  record(tab, "Advanced collapsible expand/collapse", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 4. Click-to-browse: file input is hidden inside the drop-zone label, but
  //    setting files directly on the <input type="file"> simulates the picker.
  r = await safe(async () => {
    const fileInput = page.locator("#proc-file")
    await fileInput.setInputFiles({
      name: "trace.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n"),
    })
    await page.waitForTimeout(300)
    // Selected-file chip should appear with the filename
    await page.getByText("trace.csv").first().waitFor({ timeout: 2_000 })
  })
  record(tab, "Click-to-browse file → chip appears", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 5. X button on chip clears selected file
  r = await safe(async () => {
    const xBtn = page.getByRole("button", { name: /Remove selected file/i })
    await xBtn.click()
    await page.waitForTimeout(300)
    // Chip text should disappear
    const chip = await page.getByText("trace.csv").count()
    if (chip > 0) throw new Error("file chip still visible after X click")
  })
  record(tab, "Selected-file × clears chip", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 6. Re-attach a file (needed for action buttons to fire)
  r = await safe(async () => {
    const fileInput = page.locator("#proc-file")
    await fileInput.setInputFiles({
      name: "trace.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n"),
    })
    await page.waitForTimeout(300)
  })
  record(tab, "Re-attach file for action test", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 7. Action tile: Inspect spectrum (Preview)
  r = await safe(async () => {
    const previewBtn = page.getByRole("button", { name: /Inspect spectrum/i })
    await previewBtn.click()
    // Wait for mocked response → Step 3 KPI tile "Peak count" appears
    await page.getByText(/Peak count/i).first().waitFor({ timeout: 5_000 })
  })
  record(tab, "Action tile: Inspect → Step 3 renders", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 8. Action tile: Analyze (Run evidence match)
  r = await safe(async () => {
    const analyzeBtn = page.getByRole("button", { name: /Run evidence match/i })
    await analyzeBtn.click()
    await page.waitForTimeout(800)
    // Step 3 title should be "Analysis output" after analyze
    await page.getByText(/Analysis output/i).first().waitFor({ timeout: 5_000 })
  })
  record(tab, "Action tile: Run evidence match → analysis output", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 9. Drop-zone exists with correct text + accept attributes.
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop processed spectrum']")
    if ((await zone.count()) === 0) throw new Error("drop-zone div not found")
    const inputAccept = await page.locator("#proc-file").getAttribute("accept")
    if (!inputAccept?.includes(".csv")) throw new Error(`accept missing .csv: ${inputAccept}`)
    if (!inputAccept?.includes(".jcamp")) throw new Error(`accept missing .jcamp: ${inputAccept}`)
  })
  record(tab, "Drop-zone present + accept covers expected types", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 9b. Click drop zone fires input.click() (verifies fileRef wiring).
  r = await safe(async () => {
    await page.evaluate(() => {
      const input = document.getElementById("proc-file") as HTMLInputElement
      ;(window as unknown as { __clicked: boolean }).__clicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __clicked: boolean }).__clicked = true
      }
      void orig
    })
    await page.locator("div[role='button'][aria-label*='Drop processed spectrum']").click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(
      () => (window as unknown as { __clicked: boolean }).__clicked,
    )
    if (!clicked) throw new Error("clicking drop zone did not call input.click()")
  })
  record(tab, "Drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 9c. Real drop with a File — constructs DragEvent + DataTransfer in-page.
  r = await safe(async () => {
    await page.evaluate(() => {
      const zone = document.querySelector(
        "div[role='button'][aria-label*='Drop processed spectrum']",
      ) as HTMLElement
      if (!zone) throw new Error("drop zone not found")
      const file = new File(["ppm,intensity\n4.0,2\n"], "drop-test.csv", { type: "text/csv" })
      const dt = new DataTransfer()
      dt.items.add(file)
      zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
    await page.waitForTimeout(400)
    await page.getByText("drop-test.csv").first().waitFor({ timeout: 2_000 })
  })
  record(tab, "Drop-zone real File drop attaches", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  // Clear before next test
  await page.getByRole("button", { name: /Remove selected file/i }).click().catch(() => {})

  // 10. Background job buttons render and are clickable
  r = await safe(async () => {
    const jobPrev = page.getByRole("button", { name: /^Preview$/ }).first()
    if ((await jobPrev.count()) === 0) throw new Error("background job Preview button not found")
  })
  record(tab, "Background job buttons present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 11. Clear button
  r = await safe(async () => {
    const clearBtn = page.getByRole("button", { name: /^Clear$/ })
    await clearBtn.click()
    await page.waitForTimeout(300)
    // After clear, Step 3 should disappear
    const step3 = await page.getByText(/Analysis output|Preview output/i).count()
    if (step3 > 0) throw new Error("Step 3 still visible after Clear")
  })
  record(tab, "Clear button hides Step 3 results", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
}

async function testRawFidTab(page: Page) {
  const tab = "Raw FID"
  await gotoTab(page, "tab-raw-fid")

  let r = await safe(() => page.getByText("Configure & upload raw FID archive", { exact: true }).first().waitFor({ timeout: 5_000 }))
  record(tab, "Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Nucleus pill toggle
  r = await safe(async () => {
    await page.locator("button", { hasText: /^13C$/ }).first().click()
    await page.waitForTimeout(150)
    await page.locator("button", { hasText: /^1H$/ }).first().click()
  })
  record(tab, "Nucleus pill toggles", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Vendor pill toggle (3 options: Auto / Bruker / Agilent)
  r = await safe(async () => {
    await page.getByRole("button", { name: /^Bruker$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^Agilent$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^Auto$/ }).click()
  })
  record(tab, "Vendor pill 3-option toggle", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Preserve-raw badge visible
  r = await safe(() => page.getByText(/Original FID preserved/i).waitFor({ timeout: 2_000 }))
  record(tab, "Preserve-raw badge rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Advanced collapsible
  r = await safe(async () => {
    const adv = page.getByRole("button", { name: /Advanced options/i })
    await adv.click()
    await page.waitForTimeout(300)
    await page.getByText(/Reuse session raw FID/i).waitFor({ timeout: 2_000 })
    await adv.click()
  })
  record(tab, "Advanced collapsible expand/collapse", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Click-to-browse → chip
  r = await safe(async () => {
    const fileInput = page.locator("#raw-file")
    await fileInput.setInputFiles({
      name: "raw.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK..."),
    })
    await page.waitForTimeout(300)
    await page.getByText("raw.zip").first().waitFor({ timeout: 2_000 })
  })
  record(tab, "Click-to-browse archive → chip appears", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Click drop-zone fires input.click()
  r = await safe(async () => {
    await page.evaluate(() => {
      const input = document.getElementById("raw-file") as HTMLInputElement
      ;(window as unknown as { __clicked: boolean }).__clicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __clicked: boolean }).__clicked = true
      }
      void orig
    })
    await page.locator("div[role='button'][aria-label*='Drop raw FID']").click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(
      () => (window as unknown as { __clicked: boolean }).__clicked,
    )
    if (!clicked) throw new Error("clicking drop zone did not call input.click()")
  })
  record(tab, "Drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Real drop event with a File
  r = await safe(async () => {
    await page.getByRole("button", { name: /Remove selected file/i }).click().catch(() => {})
    await page.evaluate(() => {
      const zone = document.querySelector(
        "div[role='button'][aria-label*='Drop raw FID']",
      ) as HTMLElement
      if (!zone) throw new Error("drop zone not found")
      const file = new File(["raw"], "dropped.zip", { type: "application/zip" })
      const dt = new DataTransfer()
      dt.items.add(file)
      zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
    await page.waitForTimeout(400)
    await page.getByText("dropped.zip").first().waitFor({ timeout: 2_000 })
  })
  record(tab, "Drop-zone real File drop attaches", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Action tile: Preview metadata (re-attach file first to ensure independent test)
  r = await safe(async () => {
    const fileInput = page.locator("#raw-file")
    await fileInput.setInputFiles({
      name: "raw.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK..."),
    })
    await page.waitForTimeout(200)
    const previewBtn = page.getByRole("button", { name: /Preview metadata/i })
    await previewBtn.click()
    await page.waitForTimeout(800)
    // Step 3 KPI: Vendor or Spectral width tile should render
    await page.getByText(/Spectral width/i).first().waitFor({ timeout: 5_000 })
  })
  record(tab, "Action tile: Preview metadata → Step 3 KPIs", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Action tile: Process FID
  r = await safe(async () => {
    const processBtn = page.getByRole("button", { name: /Process FID/i })
    await processBtn.click()
    await page.waitForTimeout(800)
    await page.getByText(/Processed FID output/i).first().waitFor({ timeout: 5_000 })
  })
  record(tab, "Action tile: Process FID → processed output", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Clear
  r = await safe(async () => {
    await page.getByRole("button", { name: /^Clear$/ }).click()
    await page.waitForTimeout(300)
    const step3 = await page.getByText(/Processed FID output|Raw archive metadata/i).count()
    if (step3 > 0) throw new Error("Step 3 still visible after Clear")
  })
  record(tab, "Clear hides Step 3 results", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await mockNmrApis(page)

  console.log("\n── Processed 1H/13C upload ────────────────────────────")
  await testProcessedTab(page)

  console.log("\n── Raw FID upload ─────────────────────────────────────")
  await testRawFidTab(page)

  await context.close()
  await browser.close()

  // Build report
  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# SpectraCheck upload tabs — functional smoke ${new Date().toISOString()}`,
    "",
    `- Total: ${results.length}`,
    `- Pass: ${passes}`,
    `- Fail: ${fails}`,
    "",
    "| Tab | Check | Status | Detail |",
    "|---|---|---|---|",
    ...results.map((r) => `| ${r.tab} | ${r.check} | ${r.status === "pass" ? "✓" : "✗"} | ${r.detail ?? ""} |`),
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
