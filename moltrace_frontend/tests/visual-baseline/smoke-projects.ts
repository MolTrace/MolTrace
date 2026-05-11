#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Projects module surfaces.
 *
 * Verifies that each redesigned route exposes:
 *   - The new eyebrow tagline
 *   - The new <h1> page-title with expected new copy
 *   - The new descriptive subtitle
 * Plus preserves the existing functional contracts (Create button, SpectraCheck CTAs).
 *
 * Hermetic: all `/projects/*`, `/regulatory/*`, `/reaction-projects/*`,
 * `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-projects.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-projects-report.md")
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

const MOCK_PROJECTS = [
  { id: 1, name: "MTX program", description: "Methotrexate development", status: "active", updated_at: "2026-05-01T10:00:00Z" },
]
const MOCK_PROJECT_DETAIL = {
  id: 1,
  name: "MTX program",
  description: "Methotrexate development",
  status: "active",
  updated_at: "2026-05-01T10:00:00Z",
  created_at: "2026-04-01T10:00:00Z",
}
const MOCK_SAMPLES = [{ id: 1, sample_id: "SMP-001", project_id: 1, name: "MTX-447 batch 1", status: "draft" }]
const MOCK_SAMPLE_DETAIL = {
  id: 1,
  sample_id: "SMP-001",
  project_id: 1,
  name: "MTX-447 batch 1",
  status: "draft",
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99, name: "new" }, 201)
    return fulfillJson(r, MOCK_PROJECTS)
  })
  await page.route(/\/api\/backend\/projects\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECT_DETAIL))
  await page.route(/\/api\/backend\/projects\/\d+\/samples(\?.*)?$/, (r) => fulfillJson(r, MOCK_SAMPLES))
  await page.route(/\/api\/backend\/projects\/\d+\/samples\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_SAMPLE_DETAIL))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck|workflow-templates|knowledge|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
}

type Surface = {
  path: string
  label: string
  eyebrow: RegExp
  heading: RegExp
  subtitleSubstring: RegExp
}

const SURFACES: Surface[] = [
  {
    path: "/projects",
    label: "Projects index",
    eyebrow: /MolTrace · Projects/i,
    heading: /^Projects$/i,
    subtitleSubstring: /spectroscopy sessions, regulatory dossiers, and reaction campaigns/i,
  },
  {
    path: "/projects/1",
    label: "Project detail",
    eyebrow: /Project · Detail/i,
    heading: /Project workspace/i,
    subtitleSubstring: /SpectraCheck \/ Regulatory \/ Reaction campaigns/i,
  },
  {
    path: "/projects/1/samples/1",
    label: "Sample detail",
    eyebrow: /Project · Sample Detail/i,
    heading: /Sample workspace/i,
    subtitleSubstring: /direct entry points into SpectraCheck/i,
  },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Projects redesign smoke ─────────")

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

    r = await safe(() =>
      page.locator(`text=${s.subtitleSubstring}`).first().waitFor({ timeout: 5_000 }),
    )
    record(`${s.label} descriptive subtitle rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // Functional contract preservation — all critical buttons/links remain
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    await page.getByRole("button", { name: /Create project/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Functional preserved: 'Create project' button on /projects", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects/1`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("link", { name: /Open SpectraCheck/i }).first().waitFor({ timeout: 5_000 })
    await page.getByRole("link", { name: /New SpectraCheck Session/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Functional preserved: Project detail SpectraCheck CTA links", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(async () => {
    await page.goto(`${BASE_URL}/projects/1/samples/1`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    await page.getByRole("link", { name: /Open SpectraCheck/i }).first().waitFor({ timeout: 5_000 })
    await page.getByRole("link", { name: /New SpectraCheck Session/i }).first().waitFor({ timeout: 5_000 })
  })
  record("Functional preserved: Sample detail SpectraCheck CTA links", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Projects redesign — smoke ${new Date().toISOString()}`,
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
