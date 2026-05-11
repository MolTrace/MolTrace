#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Knowledge Library module surfaces.
 *
 * Verifies that each redesigned route exposes:
 *   - The new module-coded eyebrow tagline (amber, "MolTrace · Knowledge · …")
 *   - The new <h1> page-title with expected new copy
 *
 * Hermetic: all `/knowledge/*`, `/ai/*`, `/projects/*`, `/regulatory/*`,
 * `/reaction-projects/*`, `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-knowledge.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-knowledge-report.md")
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
  await page.route(/\/api\/backend\/knowledge\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck|workflow-templates|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
}

type Surface = {
  path: string
  label: string
  eyebrow: RegExp
  heading: RegExp
}

const SURFACES: Surface[] = [
  {
    path: "/knowledge",
    label: "Knowledge Library landing",
    eyebrow: /MolTrace · Knowledge Library/i,
    heading: /Knowledge Library/i,
  },
  {
    path: "/knowledge/datasets",
    label: "Dataset candidates dashboard",
    eyebrow: /MolTrace · Knowledge · Dataset Candidates/i,
    heading: /Dataset candidate dashboard/i,
  },
  {
    path: "/knowledge/sources",
    label: "Knowledge sources",
    eyebrow: /MolTrace · Knowledge · Sources/i,
    heading: /Knowledge sources/i,
  },
  {
    path: "/knowledge/extractions",
    label: "Knowledge extractions",
    eyebrow: /MolTrace · Knowledge Extractions/i,
    heading: /Knowledge extractions/i,
  },
  {
    path: "/knowledge/analytical",
    label: "Analytical extraction records",
    eyebrow: /MolTrace · Knowledge · Analytical Records/i,
    heading: /Analytical/i,
  },
  {
    path: "/knowledge/reactions",
    label: "Reaction extraction records",
    eyebrow: /MolTrace · Knowledge · Reaction Records/i,
    heading: /Reaction/i,
  },
  {
    path: "/knowledge/regulatory",
    label: "Regulatory extraction records",
    eyebrow: /MolTrace · Knowledge · Regulatory Records/i,
    heading: /Regulatory/i,
  },
  {
    path: "/knowledge/review",
    label: "Knowledge review tasks",
    eyebrow: /MolTrace · Knowledge · Review Queue/i,
    heading: /Knowledge review tasks/i,
  },
  {
    path: "/knowledge/model-improvement",
    label: "Model improvement queue",
    eyebrow: /MolTrace · Knowledge · Model Improvement/i,
    heading: /Model improvement queue/i,
  },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Knowledge Library redesign smoke ─────────")

  for (const s of SURFACES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${s.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(1500)
    })
    if (!r.ok) {
      record(`${s.label} loads`, "fail", r.error)
      continue
    }
    record(`${s.label} loads`, "pass")

    r = await safe(() => page.locator(`text=${s.eyebrow}`).first().waitFor({ timeout: 5_000 }))
    record(`${s.label} eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: s.heading }).first().waitFor({ timeout: 5_000 }),
    )
    record(`${s.label} h1 heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // Cross-module: AI prediction augmentation slot at /knowledge still renders
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/knowledge`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("heading", { name: /Knowledge: Optional controlled AI prediction/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Cross-module: /knowledge → AI prediction augmentation slot present", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Knowledge Library redesign — smoke ${new Date().toISOString()}`,
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
