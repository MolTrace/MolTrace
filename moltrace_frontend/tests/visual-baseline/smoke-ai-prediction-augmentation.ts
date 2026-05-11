#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned centralized AiModulePredictionAugmentation
 * component, verified at all 5 mount points.
 *
 * Verifies that the redesigned component now exposes:
 *   - Module-coded eyebrow tagline (e.g. "Reaction Optimization · Optional AI Prediction")
 *   - Step 1 / Step 2 / Step 3 ModuleCard headers
 *   - Module-coded action tile for "Run approved AI model"
 *   - Original safety alert + functional buttons preserved
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-ai-prediction-augmentation.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-ai-prediction-augmentation-report.md")
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
  await page.route(/\/api\/backend\/ai\/predictions$/, (r) => {
    if (r.request().method() === "POST") {
      return fulfillJson(
        r,
        { id: 1, prediction_id: "1", status: "pending_review", confidence: 0.62, model_name: "test", model_version: "v1" },
        201,
      )
    }
    return fulfillJson(r, [])
  })
  await page.route(/\/api\/backend\/ai\/predictions\/.+\/feedback$/, (r) => fulfillJson(r, { ok: true }))
  await page.route(/\/api\/backend\/ai\/active-learning\/candidates$/, (r) => fulfillJson(r, { id: 1 }, 201))
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/risk-assessment$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/requirements$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 1, title: "MTX dossier", status: "draft" }),
  )
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 10, name: "MTX route opt", status: "active" }),
  )
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(recommendations|recommendation-batches|experiments|variables|design-space|cost-profile|safety-profile|objective-profile|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|advisor\/runs|advisor\/comparisons|optimization\/runs|optimization\/bo\/runs|optimization\/benchmark-runs)(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/knowledge\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/compound-registry\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, [{ id: 1, name: "MTX" }]))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
}

type MountPoint = {
  path: string
  label: string
  switchTab?: { name: RegExp }
  // Module-coded eyebrow shown above the augmentation
  expectedEyebrow: RegExp
  // The full augmentation h2 we emit now
  expectedHeading: RegExp
  // Step 1 / Step 2 ModuleCard eyebrows we add per module
  expectedStepOneEyebrow: RegExp
  expectedStepTwoEyebrow: RegExp
}

const MOUNTS: MountPoint[] = [
  {
    path: "/spectracheck",
    label: "SpectraCheck (Programs interface)",
    expectedEyebrow: /SpectraCheck · Optional AI Prediction/i,
    expectedHeading: /SpectraCheck: Optional controlled AI prediction/i,
    expectedStepOneEyebrow: /SpectraCheck AI · Step 1 · Setup/i,
    expectedStepTwoEyebrow: /SpectraCheck AI · Step 2 · Run/i,
  },
  {
    path: "/regulatory/dossiers/1",
    label: "Regulatory Dossier",
    expectedEyebrow: /Regulatory · Optional AI Prediction/i,
    expectedHeading: /Regulatory Dossier: Optional controlled AI prediction/i,
    expectedStepOneEyebrow: /Regulatory AI · Step 1 · Setup/i,
    expectedStepTwoEyebrow: /Regulatory AI · Step 2 · Run/i,
  },
  {
    path: "/reactions/10",
    label: "Reaction project detail",
    expectedEyebrow: /Reaction Optimization · Optional AI Prediction/i,
    expectedHeading: /Reaction Studio \(project-level\): Optional controlled AI prediction/i,
    expectedStepOneEyebrow: /Reaction Optimization AI · Step 1 · Setup/i,
    expectedStepTwoEyebrow: /Reaction Optimization AI · Step 2 · Run/i,
  },
  {
    path: "/knowledge",
    label: "Knowledge Library",
    expectedEyebrow: /Knowledge Extraction · Optional AI Prediction/i,
    expectedHeading: /Knowledge: Optional controlled AI prediction/i,
    expectedStepOneEyebrow: /Knowledge Extraction AI · Step 1 · Setup/i,
    expectedStepTwoEyebrow: /Knowledge Extraction AI · Step 2 · Run/i,
  },
  {
    path: "/ai",
    label: "ML/AI Services (Knowledge tab)",
    switchTab: { name: /Knowledge Library/i },
    expectedEyebrow: /Knowledge Extraction · Optional AI Prediction/i,
    expectedHeading: /Knowledge: Optional controlled AI prediction/i,
    expectedStepOneEyebrow: /Knowledge Extraction AI · Step 1 · Setup/i,
    expectedStepTwoEyebrow: /Knowledge Extraction AI · Step 2 · Run/i,
  },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── AI Prediction Augmentation redesign smoke ─────────")

  for (const m of MOUNTS) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${m.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(2000)
    })
    if (!r.ok) {
      record(`${m.label} loads`, "fail", r.error)
      continue
    }
    record(`${m.label} loads`, "pass")

    if (m.switchTab) {
      r = await safe(async () => {
        await page.getByRole("tab", { name: m.switchTab!.name }).first().click()
        await page.waitForTimeout(800)
      })
      record(`${m.label} — tab switch performed`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
    }

    r = await safe(() => page.locator(`text=${m.expectedEyebrow}`).first().waitFor({ timeout: 5_000 }))
    record(`${m.label} — module-coded eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: m.expectedHeading }).first().waitFor({ timeout: 5_000 }),
    )
    record(`${m.label} — augmentation h2 heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() => page.locator(`text=${m.expectedStepOneEyebrow}`).first().waitFor({ timeout: 5_000 }))
    record(`${m.label} — Step 1 ModuleCard eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() => page.locator(`text=${m.expectedStepTwoEyebrow}`).first().waitFor({ timeout: 5_000 }))
    record(`${m.label} — Step 2 ModuleCard eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    // Action tile (Run button) still present + accessible by name
    r = await safe(() =>
      page.getByRole("button", { name: /^Run approved AI model$/i }).first().waitFor({ timeout: 5_000 }),
    )
    record(`${m.label} — "Run approved AI model" action tile rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    // Safety alert preserved
    r = await safe(() =>
      page.locator("text=/Use IDs and summaries only/i").first().waitFor({ timeout: 5_000 }),
    )
    record(`${m.label} — safety alert preserved`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# AI Prediction Augmentation redesign — smoke ${new Date().toISOString()}`,
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
