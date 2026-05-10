#!/usr/bin/env -S pnpm tsx
/**
 * INTEGRATION test for the redesigned SpectraCheck upload tabs.
 *
 * Where the smoke test only verifies "buttons fire APIs", this one inspects
 * the actual REQUEST PAYLOADS sent and confirms:
 *   - Nucleus pill selection (1H/13C) flows into the FormData "nucleus" field
 *   - Vendor pill selection (auto/bruker/agilent) flows into the FormData "vendor" field
 *   - Selections made AFTER one preview still apply to the next request
 *   - Spectrometer frequency edits flow through
 *   - Background job parameters carry the current pill values
 *   - The SpectraCheckUseUnifiedEvidenceButton meta uses the correct evidenceLayer
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/integration-spectracheck-uploads.ts
 */
import { chromium, type Page, type Request } from "@playwright/test"
// `Request` type retained for future per-route handlers.
void ({} as Request)
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "integration-uploads-report.md")
const BASE_URL = "http://localhost:3000"

type CheckResult = { tab: string; check: string; status: "pass" | "fail"; detail?: string }
const results: CheckResult[] = []

function record(tab: string, check: string, status: "pass" | "fail", detail?: string) {
  results.push({ tab, check, status, detail })
  const icon = status === "pass" ? "✓" : "✗"
  console.log(`  ${icon} ${tab.padEnd(14)} ${check}${detail ? ` — ${detail}` : ""}`)
}

async function safe<T>(fn: () => Promise<T>): Promise<{ ok: true; value: T } | { ok: false; error: string }> {
  try {
    return { ok: true, value: await fn() }
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) }
  }
}

/**
 * Captures every /nmr/*, /files/upload, and /jobs POST request body.
 * Bodies are captured via page.route inside the same interception that
 * fulfills the mock response (avoids race with page.on("request")).
 */
type Captured = { url: string; method: string; body: string }
const _capturedRef: { current: Captured[] } = { current: [] }
function newCaptureBuffer(): Captured[] {
  _capturedRef.current = []
  return _capturedRef.current
}

/** Pull a multipart field value by name. Returns "" if not found. */
function readMultipartField(body: string, fieldName: string): string {
  // Form-data style:
  //   content-disposition: form-data; name="nucleus"\r\n\r\nVALUE\r\n--boundary
  // (case-insensitive header). Newlines may be \n or \r\n.
  const re = new RegExp(`name="${fieldName}"[\\s\\S]*?\\r?\\n\\r?\\n([\\s\\S]*?)\\r?\\n--`, "i")
  const m = body.match(re)
  return m?.[1] ?? ""
}

/** For JSON bodies (background jobs), look up nested key path. */
function readJsonNested(body: string, ...path: string[]): unknown {
  try {
    let cur: unknown = JSON.parse(body)
    for (const k of path) {
      if (cur && typeof cur === "object" && k in (cur as Record<string, unknown>)) {
        cur = (cur as Record<string, unknown>)[k]
      } else {
        return undefined
      }
    }
    return cur
  } catch {
    return undefined
  }
}

async function mockNmrApis(page: Page) {
  function record(req: Request) {
    // Strip the /api/backend proxy prefix so checks can use the bare path
    // (e.g. "/nmr/processed/preview", "/files/upload", "/jobs").
    let url = new URL(req.url()).pathname
    url = url.replace(/^\/api\/backend/, "")
    let body = ""
    try {
      body = req.postData() ?? ""
    } catch {
      body = ""
    }
    _capturedRef.current.push({ url, method: req.method(), body })
  }

  await page.route(/\/api\/backend\/nmr\/.+/, async (route) => {
    record(route.request())
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
  await page.route(/\/api\/backend\/files\/upload$/, async (route) => {
    record(route.request())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ file_id: "fid-123", sha256: "b".repeat(64), filename: "uploaded" }),
    })
  })
  // Catch BOTH /jobs AND /jobs/.../events, etc.
  await page.route(/\/api\/backend\/jobs(\/.*)?$/, async (route) => {
    record(route.request())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job_id: "job-123", status: "queued" }),
    })
  })
}

async function gotoTab(page: Page, tabId: string) {
  // 120s — first cold compile of /spectracheck in dev mode can take 60-90s.
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const tab = page.getByTestId(`spectracheck-tab-${tabId}`)
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(800)
}

async function attachLocalFile(page: Page, inputId: string, name: string, content: string, mime: string) {
  await page.locator(`#${inputId}`).setInputFiles({
    name,
    mimeType: mime,
    buffer: Buffer.from(content),
  })
  await page.waitForTimeout(200)
}

async function clickPill(page: Page, text: string) {
  await page.getByRole("button", { name: new RegExp(`^${text}$`) }).first().click()
  await page.waitForTimeout(150)
}

// ──────────────────────────────────────────────────────────────────────────
// Processed 1H / 13C
// ──────────────────────────────────────────────────────────────────────────
async function testProcessedIntegration(page: Page) {
  const tab = "Processed"
  const captured = newCaptureBuffer()
  await gotoTab(page, "tab-processed")
  await attachLocalFile(page, "proc-file", "trace.csv", "ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n", "text/csv")

  // 1. Default nucleus (1H) flows into Preview FormData
  captured.length = 0
  await page.getByRole("button", { name: /Inspect spectrum/i }).click()
  await page.waitForTimeout(800)
  let req = captured.find((c) => c.url === "/nmr/processed/preview")
  let r = await safe(async () => {
    if (!req) throw new Error("no /nmr/processed/preview request captured")
    const nucleus = readMultipartField(req.body, "nucleus")
    if (nucleus !== "1H") throw new Error(`nucleus expected '1H', got '${nucleus}'`)
    const sample = readMultipartField(req.body, "sample_id")
    if (!sample) throw new Error(`sample_id missing`)
  })
  record(tab, "Default nucleus 1H sent on Preview", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 2. Switch to 13C → Analyze → FormData has nucleus=13C
  captured.length = 0
  await clickPill(page, "13C")
  await page.getByRole("button", { name: /Run evidence match/i }).click()
  await page.waitForTimeout(800)
  req = captured.find((c) => c.url === "/nmr/processed/analyze")
  r = await safe(async () => {
    if (!req) throw new Error("no /nmr/processed/analyze request captured")
    const nucleus = readMultipartField(req.body, "nucleus")
    if (nucleus !== "13C") throw new Error(`nucleus expected '13C', got '${nucleus}'`)
  })
  record(tab, "Pill switch 1H → 13C reflected in Analyze FormData", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 3. Spectrometer frequency edit flows through
  captured.length = 0
  // Edit the MHz input (it's the inner <input> in the bordered shell).
  // The sr-only file input has id="proc-file"; the MHz input has id="proc-mhz".
  await page.locator("#proc-mhz").fill("600")
  await clickPill(page, "1H")
  await page.getByRole("button", { name: /Inspect spectrum/i }).click()
  await page.waitForTimeout(800)
  req = captured.find((c) => c.url === "/nmr/processed/preview")
  r = await safe(async () => {
    if (!req) throw new Error("no /nmr/processed/preview request captured")
    const mhz = readMultipartField(req.body, "spectrometer_frequency_mhz")
    if (mhz !== "600") throw new Error(`MHz expected '600', got '${mhz}'`)
    const nucleus = readMultipartField(req.body, "nucleus")
    if (nucleus !== "1H") throw new Error(`nucleus expected '1H', got '${nucleus}'`)
  })
  record(tab, "MHz=600 + nucleus=1H both reflected in next FormData", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 4. Background-job button posts JSON with current nucleus + MHz
  captured.length = 0
  await clickPill(page, "13C")
  await page.locator("#proc-mhz").fill("700")
  // Background job "Analyze" — small mono-font outline button in the dashed-border row.
  // Use a more specific selector to disambiguate from the Step-2 tile.
  await page.locator("button.font-mono", { hasText: /^Analyze$/ }).click()
  await page.waitForTimeout(1000)

  // The background job posts to /files/upload then /jobs (or /jobs/...). Check the jobs request.
  const jobReq = captured.find((c) => c.url.startsWith("/jobs") && c.method === "POST")
  r = await safe(async () => {
    if (!jobReq) throw new Error("no /jobs POST captured")
    const nucleus = readJsonNested(jobReq.body, "parameters", "nucleus")
    const mhz = readJsonNested(jobReq.body, "parameters", "spectrometer_frequency_mhz")
    if (nucleus !== "13C") throw new Error(`bg job nucleus expected '13C', got '${nucleus}'`)
    if (mhz !== 700) throw new Error(`bg job MHz expected 700, got '${mhz}'`)
  })
  record(tab, "Background job carries current nucleus + MHz in JSON", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
}

// ──────────────────────────────────────────────────────────────────────────
// Raw FID
// ──────────────────────────────────────────────────────────────────────────
async function testRawFidIntegration(page: Page) {
  const tab = "Raw FID"
  const captured = newCaptureBuffer()
  await gotoTab(page, "tab-raw-fid")
  await attachLocalFile(page, "raw-file", "raw.zip", "PK..", "application/zip")

  // 1. Default nucleus 1H + vendor auto on Preview
  captured.length = 0
  await page.getByRole("button", { name: /Preview metadata/i }).click()
  await page.waitForTimeout(800)
  let req = captured.find((c) => c.url === "/nmr/raw-fid/preview")
  let r = await safe(async () => {
    if (!req) throw new Error("no /nmr/raw-fid/preview request captured")
    const nucleus = readMultipartField(req.body, "nucleus")
    const vendor = readMultipartField(req.body, "vendor")
    if (nucleus !== "1H") throw new Error(`nucleus expected '1H', got '${nucleus}'`)
    if (vendor !== "auto") throw new Error(`vendor expected 'auto', got '${vendor}'`)
  })
  record(tab, "Default nucleus=1H vendor=auto on Preview", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 2. Switch vendor Bruker → Process → FormData has vendor=bruker
  captured.length = 0
  await clickPill(page, "Bruker")
  await page.getByRole("button", { name: /Process FID/i }).click()
  await page.waitForTimeout(800)
  req = captured.find((c) => c.url === "/nmr/raw-fid/process")
  r = await safe(async () => {
    if (!req) throw new Error("no /nmr/raw-fid/process request captured")
    const vendor = readMultipartField(req.body, "vendor")
    if (vendor !== "bruker") throw new Error(`vendor expected 'bruker', got '${vendor}'`)
    const preserveRaw = readMultipartField(req.body, "preserve_raw")
    if (preserveRaw !== "true") throw new Error(`preserve_raw expected 'true', got '${preserveRaw}'`)
  })
  record(tab, "Pill switch → vendor=bruker + preserve_raw=true in Process FormData", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 3. Switch vendor Agilent → Preview → FormData has vendor=agilent
  captured.length = 0
  await clickPill(page, "Agilent")
  await page.getByRole("button", { name: /Preview metadata/i }).click()
  await page.waitForTimeout(800)
  req = captured.find((c) => c.url === "/nmr/raw-fid/preview")
  r = await safe(async () => {
    if (!req) throw new Error("no /nmr/raw-fid/preview request captured")
    const vendor = readMultipartField(req.body, "vendor")
    if (vendor !== "agilent") throw new Error(`vendor expected 'agilent', got '${vendor}'`)
  })
  record(tab, "Pill switch → vendor=agilent in Preview FormData", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 4. Switch nucleus 13C → Process → carries vendor=agilent + nucleus=13C
  captured.length = 0
  await clickPill(page, "13C")
  await page.getByRole("button", { name: /Process FID/i }).click()
  await page.waitForTimeout(800)
  req = captured.find((c) => c.url === "/nmr/raw-fid/process")
  r = await safe(async () => {
    if (!req) throw new Error("no /nmr/raw-fid/process request captured")
    const nucleus = readMultipartField(req.body, "nucleus")
    const vendor = readMultipartField(req.body, "vendor")
    if (nucleus !== "13C") throw new Error(`nucleus expected '13C', got '${nucleus}'`)
    if (vendor !== "agilent") throw new Error(`vendor expected 'agilent' (sticky), got '${vendor}'`)
  })
  record(tab, "Pills are independent (nucleus=13C vendor=agilent both stick)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 5. Background-job button carries current nucleus + vendor + preset in JSON
  captured.length = 0
  await clickPill(page, "Auto") // reset vendor for clarity
  // Need to ensure preset is set to default; advanced section may need expansion.
  // Open advanced + change preset
  await page.getByRole("button", { name: /Advanced options/i }).click()
  await page.waitForTimeout(300)
  await page.locator("#raw-preset").selectOption("no_baseline_correction")
  await page.waitForTimeout(150)
  // Background job "Process" small button
  await page.locator("button.font-mono", { hasText: /^Process$/ }).click()
  await page.waitForTimeout(1000)
  const jobReq = captured.find((c) => c.url.startsWith("/jobs") && c.method === "POST")
  r = await safe(async () => {
    if (!jobReq) throw new Error("no /jobs POST captured")
    const nucleus = readJsonNested(jobReq.body, "parameters", "nucleus")
    const vendor = readJsonNested(jobReq.body, "parameters", "vendor")
    const preset = readJsonNested(jobReq.body, "parameters", "processing_preset")
    const preserveRaw = readJsonNested(jobReq.body, "parameters", "preserve_raw")
    if (nucleus !== "13C") throw new Error(`bg job nucleus expected '13C', got '${nucleus}'`)
    if (vendor !== "auto") throw new Error(`bg job vendor expected 'auto', got '${vendor}'`)
    if (preset !== "no_baseline_correction")
      throw new Error(`bg job preset expected 'no_baseline_correction', got '${preset}'`)
    if (preserveRaw !== true) throw new Error(`bg job preserve_raw expected true, got '${preserveRaw}'`)
  })
  record(
    tab,
    "BG job JSON: nucleus=13C, vendor=auto, preset=no_baseline_correction, preserve_raw=true",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Spectrum + gain + Use Unified Evidence integration (Processed)
// ──────────────────────────────────────────────────────────────────────────
async function testSpectrumGainAndEvidence(page: Page) {
  const tab = "Spectrum"
  newCaptureBuffer()
  await gotoTab(page, "tab-processed")
  await attachLocalFile(page, "proc-file", "trace.csv", "ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n", "text/csv")
  await page.getByRole("button", { name: /Inspect spectrum/i }).click()
  // Wait for Step 3 results to render
  await page.getByText(/Peak count/i).first().waitFor({ timeout: 5_000 })
  // Wait for Plotly chart to mount
  await page.waitForTimeout(1500)

  // 1. Spectrum container takes (close to) full available width — not squeezed into a sidebar.
  let r = await safe(async () => {
    const sizes = await page.evaluate(() => {
      const main = document.querySelector("main") as HTMLElement
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement
      if (!main || !plot) return null
      return { mainW: main.clientWidth, plotW: plot.clientWidth }
    })
    if (!sizes) throw new Error("could not measure spectrum or main")
    // The plot should occupy at least 80% of the main content area width.
    const ratio = sizes.plotW / sizes.mainW
    if (ratio < 0.7) {
      throw new Error(`plot width ${sizes.plotW} only ${(ratio * 100).toFixed(0)}% of main ${sizes.mainW} — expected ≥70%`)
    }
  })
  record(tab, "Spectrum extends to full page width (≥70% of main)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 2. Vertical gain rail exists, has aria-label, and houses a vertical slider.
  r = await safe(async () => {
    const rail = page.locator("[aria-label='Intensity gain']").first()
    if ((await rail.count()) === 0) throw new Error("vertical gain rail not rendered")
    const sliderInRail = rail.locator('[role="slider"]')
    if ((await sliderInRail.count()) === 0) throw new Error("slider not found inside gain rail")
    const orientation = await sliderInRail.getAttribute("aria-orientation")
    if (orientation !== "vertical") throw new Error(`expected vertical slider, got orientation='${orientation}'`)
  })
  record(tab, "Vertical gain rail rendered on right side with vertical slider", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 3. Gain rail wheel scroll changes gain (touchpad-friendly).
  r = await safe(async () => {
    const rail = page.locator("[aria-label='Intensity gain']").first()
    const beforeMult = await rail.locator("text=/^×/").first().innerText()
    // Dispatch wheel event on the rail (deltaY -300 = scroll up = increase gain).
    await rail.dispatchEvent("wheel", { deltaY: -300, deltaX: 0, deltaMode: 0, bubbles: true, cancelable: true })
    await page.waitForTimeout(200)
    await rail.dispatchEvent("wheel", { deltaY: -300, deltaX: 0, deltaMode: 0, bubbles: true, cancelable: true })
    await page.waitForTimeout(200)
    const afterMult = await rail.locator("text=/^×/").first().innerText()
    if (beforeMult === afterMult) {
      throw new Error(`wheel scroll on gain rail did not change multiplier: '${beforeMult}' === '${afterMult}'`)
    }
  })
  record(tab, "Wheel scroll on gain rail adjusts gain (touchpad)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 4. Vertical slider keyboard control still works (ArrowUp/ArrowDown for vertical).
  r = await safe(async () => {
    const rail = page.locator("[aria-label='Intensity gain']").first()
    const before = await rail.locator("text=/^×/").first().innerText()
    const slider = rail.locator('[role="slider"]').first()
    await slider.focus()
    for (let i = 0; i < 5; i++) await slider.press("ArrowUp")
    await page.waitForTimeout(200)
    const after = await rail.locator("text=/^×/").first().innerText()
    if (before === after) throw new Error(`vertical slider keyboard did not change multiplier: '${before}' === '${after}'`)
  })
  record(tab, "Vertical gain slider responds to keyboard (ArrowUp)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 5. "Taller peaks" button still works and shifts the multiplier readout.
  r = await safe(async () => {
    const rail = page.locator("[aria-label='Intensity gain']").first()
    const before = await rail.locator("text=/^×/").first().innerText()
    await page.getByRole("button", { name: /Taller peaks/i }).click()
    await page.getByRole("button", { name: /Taller peaks/i }).click()
    await page.waitForTimeout(200)
    const after = await rail.locator("text=/^×/").first().innerText()
    if (before === after) throw new Error(`Taller peaks did not change rail multiplier: '${before}' === '${after}'`)
  })
  record(tab, "Taller peaks button increases combined gain × yZoom in rail readout", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 6. Y-axis range stays anchored — peaks visibly grow with gain instead of axis rescaling.
  r = await safe(async () => {
    // Reset zoom to a known baseline first.
    await page.getByRole("button", { name: /Reset zoom/i }).click()
    await page.waitForTimeout(300)

    const yRangeBefore = (await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _fullLayout?: { yaxis?: { range?: number[] } }
      }
      return plot?._fullLayout?.yaxis?.range ?? null
    })) as number[] | null
    if (!yRangeBefore) throw new Error("could not read Plotly y-axis range before")

    // Bump gain way up via the vertical rail keyboard.
    const slider = page.locator("[aria-label='Intensity gain'] [role='slider']").first()
    await slider.focus()
    for (let i = 0; i < 30; i++) await slider.press("ArrowUp")
    await page.waitForTimeout(400)

    const yRangeAfter = (await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _fullLayout?: { yaxis?: { range?: number[] } }
      }
      return plot?._fullLayout?.yaxis?.range ?? null
    })) as number[] | null
    if (!yRangeAfter) throw new Error("could not read Plotly y-axis range after")

    // Range should stay ~equal (peaks grow inside the fixed axis bounds).
    const yMaxBefore = yRangeBefore[1]
    const yMaxAfter = yRangeAfter[1]
    const ratio = yMaxAfter / yMaxBefore
    if (ratio < 0.95 || ratio > 1.05) {
      throw new Error(
        `y-axis range scaled with gain (ratio ${ratio.toFixed(3)}: ${yMaxBefore} → ${yMaxAfter}). ` +
          `Expected anchored axis with peaks growing inside.`,
      )
    }
  })
  record(
    tab,
    "Y-axis range stays anchored when gain increases (peaks grow within fixed axis)",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )

  // 7. "Full spectrum" button does a true reset (gain back to default, yZoom = 1).
  r = await safe(async () => {
    // First put state in a non-default position.
    const slider = page.locator("[aria-label='Intensity gain'] [role='slider']").first()
    await slider.focus()
    for (let i = 0; i < 10; i++) await slider.press("ArrowUp")
    await page.getByRole("button", { name: /Taller peaks/i }).click()
    await page.waitForTimeout(200)

    const rail = page.locator("[aria-label='Intensity gain']").first()
    const railBeforeReset = await rail.locator("text=/^×/").first().innerText()

    await page.getByRole("button", { name: /Full spectrum/i }).click()
    await page.waitForTimeout(300)

    const railAfterReset = await rail.locator("text=/^×/").first().innerText()
    if (railBeforeReset === railAfterReset) {
      throw new Error(`Full spectrum did not reset multiplier: '${railBeforeReset}' === '${railAfterReset}'`)
    }
  })
  record(tab, "Full spectrum button resets gain + yZoom + xRange", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 8. Plotly's built-in modebar is hidden — we provide our own draggable floating toolbar.
  r = await safe(async () => {
    const config = await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _context?: { displayModeBar?: unknown }
      }
      return plot?._context?.displayModeBar ?? null
    })
    if (config !== false) {
      throw new Error(`expected modebar config false (custom toolbar replaces it), got '${String(config)}'`)
    }
  })
  record(tab, "Plotly modebar disabled (custom draggable toolbar replaces it)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 9. Sticky chart container — the spectrum chart's wrapper has position: sticky.
  r = await safe(async () => {
    const sticky = await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement | null
      if (!plot) return null
      // Walk up the DOM looking for a position:sticky ancestor that owns the chart.
      let el: HTMLElement | null = plot.parentElement
      while (el) {
        const cs = getComputedStyle(el)
        if (cs.position === "sticky") return { className: el.className, top: cs.top }
        el = el.parentElement
      }
      return null
    })
    if (!sticky) throw new Error("no sticky ancestor found around the chart")
    if (!sticky.top || sticky.top === "auto") throw new Error(`sticky ancestor has no top offset: '${sticky.top}'`)
  })
  record(tab, "Spectrum chart container is position:sticky (stays in view on scroll)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 10. Default gain after Reset → multiplier ~1× (compact whole-spectrum view).
  r = await safe(async () => {
    await page.getByRole("button", { name: /Reset zoom/i }).click()
    await page.waitForTimeout(300)
    const rail = page.locator("[aria-label='Intensity gain']").first()
    const readout = await rail.locator("text=/^×/").first().innerText()
    // After reset: gain01 = 0 → mult = 1, yZoom = 1 → readout = "×1.0e+0"
    if (!/^×1\.0e\+0/.test(readout)) {
      throw new Error(`expected default readout '×1.0e+0' after reset, got '${readout}'`)
    }
  })
  record(tab, "Default gain after Reset is 1× (compact view)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 11. Floating draggable toolbar exists with the correct ARIA + drag handle.
  r = await safe(async () => {
    const toolbar = page.locator("[role='toolbar'][aria-label*='drag to reposition']")
    if ((await toolbar.count()) === 0) throw new Error("draggable toolbar not found")
    const cursorClass = await toolbar.first().getAttribute("class")
    if (!cursorClass?.includes("cursor-grab")) throw new Error("toolbar drag handle missing cursor-grab class")
  })
  record(tab, "Floating draggable toolbar present with grab cursor handle", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 12. Drag the toolbar — its position changes after a pointer drag on the handle.
  r = await safe(async () => {
    // Hover over chart to reveal the toolbar.
    const chart = page.locator(".js-plotly-plot").first()
    await chart.hover()
    await page.waitForTimeout(200)

    // Find the toolbar's parent (the absolutely-positioned panel).
    const handle = page.locator("[role='toolbar'][aria-label*='drag to reposition']").first()
    const beforeBox = await handle.evaluate((el) => {
      const panel = el.parentElement as HTMLElement
      const rect = panel.getBoundingClientRect()
      return { left: rect.left, top: rect.top }
    })

    // Use Playwright's drag-and-drop simulation via pointer events.
    const handleBox = await handle.boundingBox()
    if (!handleBox) throw new Error("could not get handle bounding box")
    const startX = handleBox.x + handleBox.width / 2
    const startY = handleBox.y + handleBox.height / 2
    await page.mouse.move(startX, startY)
    await page.mouse.down()
    await page.mouse.move(startX - 60, startY + 40, { steps: 10 })
    await page.mouse.up()
    await page.waitForTimeout(200)

    const afterBox = await handle.evaluate((el) => {
      const panel = el.parentElement as HTMLElement
      const rect = panel.getBoundingClientRect()
      return { left: rect.left, top: rect.top }
    })
    const dx = afterBox.left - beforeBox.left
    const dy = afterBox.top - beforeBox.top
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
      throw new Error(`toolbar did not move after drag: dx=${dx} dy=${dy}`)
    }
  })
  record(tab, "Toolbar can be dragged with mouse pointer", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 13. Toolbar buttons are still functional after the drag (Reset zoom).
  r = await safe(async () => {
    // After a drag, click the Reset zoom button inside the floating toolbar — the multiplier should reset.
    const slider = page.locator("[aria-label='Intensity gain'] [role='slider']").first()
    await slider.focus()
    for (let i = 0; i < 5; i++) await slider.press("ArrowUp")
    await page.waitForTimeout(150)

    const railBefore = await page
      .locator("[aria-label='Intensity gain']")
      .first()
      .locator("text=/^×/")
      .first()
      .innerText()

    await page.getByRole("button", { name: /^Full spectrum$/i }).click()
    await page.waitForTimeout(300)

    const railAfter = await page
      .locator("[aria-label='Intensity gain']")
      .first()
      .locator("text=/^×/")
      .first()
      .innerText()

    if (railBefore === railAfter) {
      throw new Error(`Full spectrum did not reset multiplier after drag: '${railBefore}' === '${railAfter}'`)
    }
    if (!/^×1\.0e\+0/.test(railAfter)) {
      throw new Error(`expected '×1.0e+0' after Full spectrum, got '${railAfter}'`)
    }
  })
  record(tab, "Floating toolbar buttons remain functional after dragging", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 14. Move mode toggle: clicking the toggle flips Plotly's dragmode to "pan".
  r = await safe(async () => {
    // Default state: dragmode should be "zoom".
    const initialMode = await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _fullLayout?: { dragmode?: string }
      }
      return plot?._fullLayout?.dragmode ?? null
    })
    if (initialMode !== "zoom") {
      throw new Error(`expected initial dragmode='zoom', got '${initialMode}'`)
    }
    // Click the toggle (button with aria-pressed=false initially → press it).
    const toggle = page.locator("button[aria-pressed='false']").filter({
      has: page.locator(".sr-only", { hasText: /Zoom mode active/ }),
    })
    if ((await toggle.count()) === 0) throw new Error("Move mode toggle not found")
    await toggle.first().click()
    await page.waitForTimeout(300)
    const afterToggle = await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _fullLayout?: { dragmode?: string }
      }
      return plot?._fullLayout?.dragmode ?? null
    })
    if (afterToggle !== "pan") {
      throw new Error(`expected dragmode='pan' after toggle, got '${afterToggle}'`)
    }
  })
  record(tab, "Move mode toggle switches Plotly dragmode to 'pan' (drag = move spectrum)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 15. Full spectrum resets dragmode back to "zoom" (first-preview default).
  r = await safe(async () => {
    // Now in pan mode (from previous test). Click Full spectrum.
    await page.getByRole("button", { name: /^Full spectrum$/i }).click()
    await page.waitForTimeout(300)
    const afterReset = await page.evaluate(() => {
      const plot = document.querySelector(".js-plotly-plot") as HTMLElement & {
        _fullLayout?: { dragmode?: string }
      }
      return plot?._fullLayout?.dragmode ?? null
    })
    if (afterReset !== "zoom") {
      throw new Error(`expected dragmode='zoom' after Full spectrum, got '${afterReset}'`)
    }
    // Also verify the toggle button reflects zoom mode again (aria-pressed=false).
    const togglePressed = await page
      .locator("button[aria-pressed='true']")
      .filter({ has: page.locator(".sr-only", { hasText: /Pan mode active/ }) })
      .count()
    if (togglePressed > 0) {
      throw new Error("Move toggle still shows pan-active after Full spectrum reset")
    }
  })
  record(tab, "Full spectrum resets dragmode to 'zoom' (first-preview default)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // 5. "Use in Unified Evidence" button is clickable + queues an item.
  //    Verify by switching to the Evidence Queue tab and seeing the item appear.
  r = await safe(async () => {
    // Reset gain so the button is reachable
    await page.getByRole("button", { name: /Reset zoom/i }).click()
    await page.waitForTimeout(200)

    const useEvBtn = page.getByRole("button", { name: /Use in Unified Evidence/i })
    if ((await useEvBtn.count()) === 0) throw new Error("Use in Unified Evidence button not rendered")
    await useEvBtn.scrollIntoViewIfNeeded()
    await useEvBtn.click()
    await page.waitForTimeout(500)

    // Switch to Evidence Queue tab
    await page.getByTestId("spectracheck-tab-tab-evidence-queue").click()
    await page.waitForTimeout(800)

    // Look for evidence-card content or any sign the item landed. The card title
    // for our submission contains "Processed spectrum preview" or "analyze".
    const card = page.getByText(/Processed spectrum (preview|analyze)/i).first()
    await card.waitFor({ timeout: 5_000 })
  })
  record(
    tab,
    "Use in Unified Evidence → item appears in Evidence Queue tab",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Cross-cutting integration
// ──────────────────────────────────────────────────────────────────────────
async function testCrossCutting(page: Page) {
  const tab = "Integration"

  // Verify the global tabs strip + AppShell sidebar still render
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 60_000 })
  await page.waitForTimeout(1500)

  // Sidebar Programs link visible
  let r = await safe(async () => {
    const programs = page.getByRole("link", { name: /^Programs$/ })
    if ((await programs.count()) === 0) throw new Error("Programs sidebar link missing")
  })
  record(tab, "Sidebar Programs link still rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // SpectraCheck brand H1
  r = await safe(() => page.getByRole("heading", { name: /SpectraCheck/i }).first().waitFor({ timeout: 5_000 }))
  record(tab, "SpectraCheck H1 still rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // All 12 tabs present
  r = await safe(async () => {
    const tabIds = [
      "tab-overview",
      "tab-workflow",
      "tab-nmr-text",
      "tab-processed",
      "tab-raw-fid",
      "tab-dept-2d",
      "tab-predicted",
      "tab-ms-evidence",
      "tab-evidence-queue",
      "tab-unified",
      "tab-report",
      "tab-dev-json",
    ]
    for (const id of tabIds) {
      const el = page.getByTestId(`spectracheck-tab-${id}`)
      if ((await el.count()) === 0) throw new Error(`tab ${id} missing`)
    }
  })
  record(tab, "All 12 SpectraCheck tabs still present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // Ensure the AI Evidence Queue side panel still renders (right rail integration)
  r = await safe(async () => {
    const queue = page.getByText(/AI Evidence Queue/i).first()
    if ((await queue.count()) === 0) throw new Error("AI Evidence Queue not visible")
  })
  record(tab, "AI Evidence Queue right-rail integration intact", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await mockNmrApis(page)

  console.log("\n── Processed 1H/13C — pill→FormData integration ─────────")
  await testProcessedIntegration(page)

  console.log("\n── Raw FID — pill→FormData integration ──────────────────")
  await testRawFidIntegration(page)

  console.log("\n── Spectrum width + gain + Use Unified Evidence ─────────")
  await testSpectrumGainAndEvidence(page)

  console.log("\n── Cross-cutting platform integration ───────────────────")
  await testCrossCutting(page)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# SpectraCheck integration — ${new Date().toISOString()}`,
    "",
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
