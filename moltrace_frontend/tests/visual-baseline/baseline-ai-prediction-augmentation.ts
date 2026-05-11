#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the centralized AiModulePredictionAugmentation
 * component, captured at all 5 routes that mount it.
 *
 * Mount points:
 *   1. /spectracheck                  → ProgramsInterfaceWorkspace (multiple augmentations)
 *   2. /regulatory/dossiers/[id]      → Regulatory variant
 *   3. /reactions/[id]                → Reaction Optimization variant
 *   4. /knowledge                     → Knowledge variant
 *   5. /ai                            → MlAiInterfaceWorkspace (knowledge_extraction variant)
 *
 * Run BEFORE the redesign to lock in the existing user-visible contract.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-ai-prediction-augmentation.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-ai-prediction-augmentation-report.md")
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
  // AI prediction endpoint
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
  // Regulatory mocks
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/risk-assessment$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/requirements$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 1, title: "MTX dossier", status: "draft" }),
  )
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  // Reaction
  await page.route(/\/api\/backend\/reaction-projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 10, name: "MTX route opt", status: "active" }),
  )
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(recommendations|recommendation-batches|experiments|variables|design-space|cost-profile|safety-profile|objective-profile|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|advisor\/runs|advisor\/comparisons|optimization\/runs|optimization\/bo\/runs|optimization\/benchmark-runs)(\?.*)?$/, (r) => fulfillJson(r, []))
  // Knowledge
  await page.route(/\/api\/backend\/knowledge\/.+$/, (r) => fulfillJson(r, []))
  // Compound registry
  await page.route(/\/api\/backend\/compound-registry\/.+$/, (r) => fulfillJson(r, []))
  // Projects + samples
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, [{ id: 1, name: "MTX" }]))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
  // SpectraCheck
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
}

const ROUTES: { path: string; label: string; expectedAugmentations: { moduleTitle: string }[] }[] = [
  {
    path: "/spectracheck",
    label: "SpectraCheck (Programs interface)",
    expectedAugmentations: [{ moduleTitle: "SpectraCheck" }],
  },
  {
    path: "/regulatory/dossiers/1",
    label: "Regulatory Dossier",
    expectedAugmentations: [{ moduleTitle: "Regulatory Dossier" }],
  },
  {
    path: "/reactions/10",
    label: "Reaction Optimization project detail",
    expectedAugmentations: [{ moduleTitle: "Reaction Studio (project-level)" }],
  },
  {
    path: "/knowledge",
    label: "Knowledge Library",
    expectedAugmentations: [{ moduleTitle: "Knowledge" }],
  },
  {
    path: "/ai",
    label: "ML/AI Services",
    expectedAugmentations: [{ moduleTitle: "Knowledge" }],
  },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── AI Prediction Augmentation baseline regression ─────────")

  for (const route of ROUTES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(2000)
    })
    if (!r.ok) {
      record(`Route ${route.path} (${route.label}) loads`, "fail", r.error)
      continue
    }
    record(`Route ${route.path} (${route.label}) loads`, "pass")

    // /ai mounts MlAiInterfaceWorkspace where the augmentation lives in the
    // Knowledge Library tab (not the default AI Services tab).
    if (route.path === "/ai") {
      r = await safe(async () => {
        await page.getByRole("tab", { name: /Knowledge Library/i }).first().click()
        await page.waitForTimeout(800)
      })
      if (!r.ok) {
        record(`Route ${route.path} — switched to Knowledge Library tab`, "fail", r.error)
        continue
      }
      record(`Route ${route.path} — switched to Knowledge Library tab`, "pass")
    }

    // For each expected augmentation on this route, verify its title is present
    for (const aug of route.expectedAugmentations) {
      const expectedTitle = `${aug.moduleTitle}: Optional controlled AI prediction`
      r = await safe(() =>
        page.locator(`text=${expectedTitle}`).first().waitFor({ timeout: 5_000 }),
      )
      record(
        `${route.label} — augmentation card "${expectedTitle}" rendered`,
        r.ok ? "pass" : "fail",
        r.ok ? undefined : r.error,
      )
    }

    // Verify the "Run approved AI model" button exists at least once on the page
    r = await safe(() =>
      page.getByRole("button", { name: /Run approved AI model/i }).first().waitFor({ timeout: 5_000 }),
    )
    record(
      `${route.label} — "Run approved AI model" button rendered`,
      r.ok ? "pass" : "fail",
      r.ok ? undefined : r.error,
    )

    // Verify the IDs-and-summaries-only safety alert exists
    r = await safe(() =>
      page.locator("text=/Use IDs and summaries only/i").first().waitFor({ timeout: 5_000 }),
    )
    record(
      `${route.label} — safety alert ("Use IDs and summaries only") rendered`,
      r.ok ? "pass" : "fail",
      r.ok ? undefined : r.error,
    )
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# AI Prediction Augmentation baseline regression — ${new Date().toISOString()}`,
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
