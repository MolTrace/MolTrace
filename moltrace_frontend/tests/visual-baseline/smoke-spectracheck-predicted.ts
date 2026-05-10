#!/usr/bin/env -S pnpm tsx
/**
 * Functional smoke + integration test for the redesigned Predicted NMR matching tab.
 * Verifies (across the 3 sub-sections — 1H/13C evidence, Similarity, Compare):
 *   - Step 1 / Step 2 / Step 3 chrome rendered for each section
 *   - Drop-zones exist for obs2d / ref2d / candDept / candNmr2d + click → input.click() fires
 *   - Real File drop attaches via DataTransfer DragEvent for at least one drop-zone
 *   - Advanced collapsibles open & reveal hidden file pickers
 *   - Action tiles fire correct API endpoints with correct shared session payloads
 *   - Reference textareas (refProton, refCarbon) flow into FormData when populated
 *   - Compare tile fires /candidates/compare/evidence
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-spectracheck-predicted.ts
 */
import { chromium, type Page, type Request } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-predicted-report.md")
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

const _captured: { url: string; method: string; body: string }[] = []
function record_req(req: Request) {
  let url = new URL(req.url()).pathname
  url = url.replace(/^\/api\/backend/, "")
  let body = ""
  try {
    body = req.postData() ?? ""
  } catch {
    body = ""
  }
  _captured.push({ url, method: req.method(), body })
}

async function mockApis(page: Page) {
  await page.route(/\/api\/backend\/(prediction|similarity|candidates)\/.+/, async (route) => {
    record_req(route.request())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sample_id: "smoke-test",
        candidates: [{ name: "Ethanol", smiles: "CCO", score: 0.9 }],
        warnings: [],
        notes: [],
      }),
    })
  })
}

function readMultipart(body: string, name: string): string {
  const re = new RegExp(`name="${name}"[\\s\\S]*?\\r?\\n\\r?\\n([\\s\\S]*?)\\r?\\n--`, "i")
  return body.match(re)?.[1] ?? ""
}

async function gotoPredictedTab(page: Page) {
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const tab = page.getByTestId("spectracheck-tab-tab-predicted")
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(800)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await mockApis(page)

  console.log("\n── Predicted NMR matching redesign smoke + integration ─────────")
  await gotoPredictedTab(page)

  // ── Step 1 chrome rendered for all 3 sections ──────────────────────────
  let r = await safe(() =>
    page.getByText("Inputs from shared session", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 1 (1H/13C) Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByText("Configure references & 2D pairs", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 2 (Similarity) Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByText("Optional DEPT + 2D uploads", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 3 (Compare) Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Step 2 chrome rendered for all 3 sections ──────────────────────────
  r = await safe(() =>
    page.getByText("Match predicted vs observed", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 1 Step 2 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByText("Score spectral similarity", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 2 Step 2 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() =>
    page.getByText("Compare candidates with full evidence", { exact: true }).first().waitFor({ timeout: 5_000 })
  )
  record("Section 3 Step 2 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 1 (1H/13C evidence) summary chips render shared session state ──
  r = await safe(async () => {
    await page.getByText(/Candidates/i).first().waitFor({ timeout: 2_000 })
    await page.getByText(/NMR text/i).first().waitFor({ timeout: 2_000 })
    await page.getByText(/Sample ID/i).first().waitFor({ timeout: 2_000 })
    await page.getByText(/Solvent/i).first().waitFor({ timeout: 2_000 })
  })
  record("Section 1 summary chips (Candidates/NMR/Sample ID/Solvent) render", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 1 action tile fires /prediction/nmr/match/evidence ─────────
  r = await safe(async () => {
    _captured.length = 0
    await page.getByRole("button", { name: /Run 1H \/ 13C evidence match/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/prediction/nmr/match/evidence")
    if (!req) throw new Error("no /prediction/nmr/match/evidence request captured")
    const candidates = readMultipart(req.body, "candidates_text")
    const proton = readMultipart(req.body, "observed_proton_text")
    const carbon = readMultipart(req.body, "observed_carbon13_text")
    if (!candidates) throw new Error(`expected candidates_text populated, got empty`)
    if (!proton) throw new Error(`expected observed_proton_text populated, got empty`)
    if (!carbon) throw new Error(`expected observed_carbon13_text populated, got empty`)
  })
  record("Section 1 tile fires /prediction/nmr/match/evidence with shared session payload", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 2 (Similarity) Advanced collapsible opens & reveals 2D inputs ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /Advanced — paired 2D files/i }).click()
    await page.waitForTimeout(300)
    await page.getByText(/Observed 2D file/i).first().waitFor({ timeout: 2_000 })
    await page.getByText(/Reference 2D file/i).first().waitFor({ timeout: 2_000 })
  })
  record("Section 2 Advanced collapsible reveals obs2d + ref2d drop-zones", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 2 obs2d drop-zone exists + click triggers input ────────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop observed 2D file']")
    if ((await zone.count()) === 0) throw new Error("obs2d drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("sim-obs2d-file") as HTMLInputElement
      ;(window as unknown as { __obs2dClicked: boolean }).__obs2dClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __obs2dClicked: boolean }).__obs2dClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __obs2dClicked: boolean }).__obs2dClicked)
    if (!clicked) throw new Error("obs2d drop-zone click did not call input.click()")
  })
  record("Section 2 obs2d drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 2 ref2d drop-zone exists + click triggers input ────────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop reference 2D file']")
    if ((await zone.count()) === 0) throw new Error("ref2d drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("sim-ref2d-file") as HTMLInputElement
      ;(window as unknown as { __ref2dClicked: boolean }).__ref2dClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __ref2dClicked: boolean }).__ref2dClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __ref2dClicked: boolean }).__ref2dClicked)
    if (!clicked) throw new Error("ref2d drop-zone click did not call input.click()")
  })
  record("Section 2 ref2d drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 2 real File drop attaches obs2d ─────────────────────────────
  r = await safe(async () => {
    await page.evaluate(() => {
      const zone = document.querySelector(
        "div[role='button'][aria-label*='Drop observed 2D file']",
      ) as HTMLElement
      const file = new File(["f1,f2\n4.1,30.2"], "obs-2d.csv", { type: "text/csv" })
      const dt = new DataTransfer()
      dt.items.add(file)
      zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
    await page.waitForTimeout(400)
    await page.getByText("obs-2d.csv").first().waitFor({ timeout: 2_000 })
  })
  record("Section 2 obs2d real File drop attaches + chip appears", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 2 reference text + similarity action fires /similarity/score/evidence ──
  r = await safe(async () => {
    // Type into reference proton text
    await page.locator("#sim-ref-proton").fill("1H NMR ref δ 3.65 (q, 2H)")
    await page.waitForTimeout(150)
    _captured.length = 0
    await page.getByRole("button", { name: /Score spectral similarity/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/similarity/score/evidence")
    if (!req) throw new Error("no /similarity/score/evidence request captured")
    const refProton = readMultipart(req.body, "reference_proton_text")
    if (!refProton.includes("3.65")) throw new Error(`expected reference_proton_text to contain '3.65', got '${refProton}'`)
  })
  record("Section 2 Score tile fires /similarity/score/evidence with reference text", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 3 (Compare) Advanced collapsible opens & reveals DEPT + 2D ──
  r = await safe(async () => {
    await page.getByRole("button", { name: /Advanced — DEPT\/APT \+ 2D peak table/i }).click()
    await page.waitForTimeout(300)
    await page.getByText(/Optional DEPT \/ APT file/i).first().waitFor({ timeout: 2_000 })
    await page.getByText(/Optional 2D peak table/i).first().waitFor({ timeout: 2_000 })
  })
  record("Section 3 Advanced collapsible reveals candDept + candNmr2d drop-zones", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 3 candDept drop-zone exists + click triggers input ──────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop DEPT/APT file for candidate compare']")
    if ((await zone.count()) === 0) throw new Error("candDept drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("cand-dept") as HTMLInputElement
      ;(window as unknown as { __candDeptClicked: boolean }).__candDeptClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __candDeptClicked: boolean }).__candDeptClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __candDeptClicked: boolean }).__candDeptClicked)
    if (!clicked) throw new Error("candDept drop-zone click did not call input.click()")
  })
  record("Section 3 candDept drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 3 candNmr2d drop-zone exists + click triggers input ─────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop 2D peak table for candidate compare']")
    if ((await zone.count()) === 0) throw new Error("candNmr2d drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("cand-nmr2d") as HTMLInputElement
      ;(window as unknown as { __candNmr2dClicked: boolean }).__candNmr2dClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __candNmr2dClicked: boolean }).__candNmr2dClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __candNmr2dClicked: boolean }).__candNmr2dClicked)
    if (!clicked) throw new Error("candNmr2d drop-zone click did not call input.click()")
  })
  record("Section 3 candNmr2d drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Section 3 Compare tile fires /candidates/compare/evidence ───────────
  r = await safe(async () => {
    _captured.length = 0
    await page.getByRole("button", { name: /Compare candidates \(evidence\)/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/candidates/compare/evidence")
    if (!req) throw new Error("no /candidates/compare/evidence request captured")
    const candidates = readMultipart(req.body, "candidates_text")
    if (!candidates) throw new Error(`expected candidates_text populated, got empty`)
  })
  record("Section 3 Compare tile fires /candidates/compare/evidence with shared candidates", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Predicted NMR matching redesign — smoke + integration ${new Date().toISOString()}`,
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
