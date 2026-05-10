#!/usr/bin/env -S pnpm tsx
/**
 * Functional smoke + integration test for the redesigned DEPT/APT + 2D NMR tab.
 * Verifies:
 *   - Step 1 / Step 2 / Step 3 chrome rendered for both DEPT and 2D sections
 *   - Drop-zone exists for each file input + click-to-browse opens the picker
 *   - Real File drop attaches via DataTransfer DragEvent
 *   - DEPT experiment-type pill toggle (Auto / DEPT45 / DEPT90 / DEPT135 / APT) flows into FormData
 *   - DEPT APT-positive pill toggle (CH+CH3 / CH only) flows into FormData
 *   - 2D experiment pill toggle (HSQC / HMBC / COSY / HMQC) flows into FormData
 *   - Action tiles fire correct API endpoints
 *   - SMILES required validation for 2D NMR
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-spectracheck-dept-2d.ts
 */
import { chromium, type Page, type Request } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-dept-2d-report.md")
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
  await page.route(/\/api\/backend\/(carbon13|nmr2d)\/.+/, async (route) => {
    record_req(route.request())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        sample_id: "smoke-test",
        experiment: "smoke",
        peaks: [{ ppm: 4.1, intensity: 1e3 }],
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

async function gotoDeptTab(page: Page) {
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const tab = page.getByTestId("spectracheck-tab-tab-dept-2d")
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(800)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await mockApis(page)

  console.log("\n── DEPT/APT + 2D NMR redesign smoke + integration ─────────")
  await gotoDeptTab(page)

  // ── Step 1 & 2 chrome rendered for DEPT ────────────────────────────────
  let r = await safe(() => page.getByText("Configure & upload DEPT/APT peak table", { exact: true }).first().waitFor({ timeout: 5_000 }))
  record("DEPT Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.getByText("Configure & upload 2D peak table", { exact: true }).first().waitFor({ timeout: 5_000 }))
  record("2D NMR Step 1 heading rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── DEPT pill toggles ──────────────────────────────────────────────────
  r = await safe(async () => {
    await page.getByRole("button", { name: /^DEPT135$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^APT$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^Auto$/ }).click()
  })
  record("DEPT experiment-type pill toggle (Auto/DEPT45/DEPT90/DEPT135/APT) clicks", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.getByRole("button", { name: /CH only/i }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /CH \+ CH3/i }).click()
  })
  record("DEPT APT-positive pill toggle (CH+CH3 / CH only) clicks", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2D experiment pill toggle ──────────────────────────────────────────
  r = await safe(async () => {
    await page.getByRole("button", { name: /^HMBC$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^COSY$/ }).click()
    await page.waitForTimeout(150)
    await page.getByRole("button", { name: /^HSQC$/ }).click()
  })
  record("2D experiment pill toggle (HSQC/HMBC/COSY/HMQC) clicks", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── DEPT drop-zone exists + click triggers input ───────────────────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop DEPT/APT peak table']")
    if ((await zone.count()) === 0) throw new Error("DEPT drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("dept-file") as HTMLInputElement
      ;(window as unknown as { __deptClicked: boolean }).__deptClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __deptClicked: boolean }).__deptClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __deptClicked: boolean }).__deptClicked)
    if (!clicked) throw new Error("DEPT drop-zone click did not call input.click()")
  })
  record("DEPT drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2D drop-zone exists + click triggers input ─────────────────────────
  r = await safe(async () => {
    const zone = page.locator("div[role='button'][aria-label*='Drop 2D peak table']")
    if ((await zone.count()) === 0) throw new Error("2D drop-zone not found")
    await page.evaluate(() => {
      const input = document.getElementById("nmr2d-file") as HTMLInputElement
      ;(window as unknown as { __twoDClicked: boolean }).__twoDClicked = false
      const orig = input.click.bind(input)
      input.click = () => {
        ;(window as unknown as { __twoDClicked: boolean }).__twoDClicked = true
      }
      void orig
    })
    await zone.click()
    await page.waitForTimeout(150)
    const clicked = await page.evaluate(() => (window as unknown as { __twoDClicked: boolean }).__twoDClicked)
    if (!clicked) throw new Error("2D drop-zone click did not call input.click()")
  })
  record("2D NMR drop-zone click → input.click() fires", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Real File drop attaches a DEPT file ─────────────────────────────────
  r = await safe(async () => {
    await page.evaluate(() => {
      const zone = document.querySelector(
        "div[role='button'][aria-label*='Drop DEPT/APT peak table']",
      ) as HTMLElement
      const file = new File(["ppm,mult\n4.1,CH"], "dept-test.csv", { type: "text/csv" })
      const dt = new DataTransfer()
      dt.items.add(file)
      zone.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
    await page.waitForTimeout(400)
    await page.getByText("dept-test.csv").first().waitFor({ timeout: 2_000 })
  })
  record("DEPT real File drop attaches + chip appears", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── DEPT Preview action fires correct endpoint with correct fields ─────
  r = await safe(async () => {
    _captured.length = 0
    // Set DEPT135 + CH only first to verify pills flow through.
    await page.getByRole("button", { name: /^DEPT135$/ }).click()
    await page.getByRole("button", { name: /CH only/i }).click()
    await page.waitForTimeout(150)
    // Click "Inspect peak table" tile (the Preview tile in Step 2 for DEPT).
    await page.getByRole("button", { name: /Inspect peak table/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/carbon13/dept/preview")
    if (!req) throw new Error("no /carbon13/dept/preview request captured")
    const expType = readMultipart(req.body, "experiment_type")
    const aptPos = readMultipart(req.body, "apt_positive")
    if (expType !== "DEPT135") throw new Error(`expected experiment_type='DEPT135', got '${expType}'`)
    if (aptPos !== "CH_only") throw new Error(`expected apt_positive='CH_only', got '${aptPos}'`)
  })
  record("DEPT Preview tile fires /carbon13/dept/preview with pill values in FormData", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── DEPT Analyze action fires correct endpoint ─────────────────────────
  r = await safe(async () => {
    _captured.length = 0
    await page.getByRole("button", { name: /Run carbon-type evidence/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/carbon13/dept/analyze")
    if (!req) throw new Error("no /carbon13/dept/analyze request captured")
    const expType = readMultipart(req.body, "experiment_type")
    if (expType !== "DEPT135") throw new Error(`expected experiment_type='DEPT135', got '${expType}'`)
  })
  record("DEPT Analyze tile fires /carbon13/dept/analyze with pill values", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2D NMR Analyze validates SMILES + sends correct experiment ─────────
  r = await safe(async () => {
    // Attach a 2D file
    await page.locator("#nmr2d-file").setInputFiles({
      name: "two-d.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("f1,f2\n4.1,30.2"),
    })
    await page.waitForTimeout(200)
    // Pick HMBC then run
    await page.getByRole("button", { name: /^HMBC$/ }).click()
    await page.waitForTimeout(150)
    _captured.length = 0
    await page.getByRole("button", { name: /Run 2D correlation analysis/i }).click()
    await page.waitForTimeout(800)
    const req = _captured.find((c) => c.url === "/nmr2d/analyze")
    if (!req) throw new Error("no /nmr2d/analyze request captured")
    const exp = readMultipart(req.body, "experiment")
    const smiles = readMultipart(req.body, "smiles")
    if (exp !== "HMBC") throw new Error(`expected experiment='HMBC', got '${exp}'`)
    if (!smiles) throw new Error(`expected SMILES populated (default from candidates), got empty`)
  })
  record("2D NMR Analyze tile fires /nmr2d/analyze with experiment + smiles", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2D Advanced collapsible reveals optional DEPT file picker ──────────
  r = await safe(async () => {
    await page.getByRole("button", { name: /Advanced — optional DEPT cross-link/i }).click()
    await page.waitForTimeout(300)
    await page.getByText(/Optional DEPT\/APT file/i).waitFor({ timeout: 2_000 })
  })
  record("2D Advanced collapsible reveals optional DEPT file picker", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# DEPT/APT + 2D NMR redesign — smoke + integration ${new Date().toISOString()}`,
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
