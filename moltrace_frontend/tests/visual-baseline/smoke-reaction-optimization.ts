#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Reaction Optimization surfaces + project-detail tabs.
 *
 * Verifies that each redesigned surface exposes:
 *   - The new section eyebrow tagline (font-mono uppercase tracked)
 *   - The new <h2> page-title with expected new copy
 * For the project detail page, also clicks through all 11 tabs.
 *
 * Hermetic: all `/reaction-projects`, `/projects`, `/regulatory/*`,
 * `/compound-registry/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-reaction-optimization.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-reaction-optimization-report.md")
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

const MOCK_REACTION_PROJECTS = [{ id: 10, name: "MTX route opt", status: "active", project_id: 1 }]
const MOCK_PROJECTS = [{ id: 1, name: "MTX program" }]
const MOCK_VARIABLES = [{ id: 1, name: "temperature_C", lower_bound: 25, upper_bound: 80, kind: "continuous" }]
const MOCK_EXPERIMENTS = [{ id: 1, label: "EXP-001", reaction_project_id: 10, status: "completed" }]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99, name: "new" }, 201)
    return fulfillJson(r, MOCK_REACTION_PROJECTS)
  })
  await page.route(/\/api\/backend\/reaction-projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, MOCK_REACTION_PROJECTS[0]),
  )
  await page.route(/\/api\/backend\/reaction-projects\/\d+\/(variables|experiments|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|design-space|cost-profile|safety-profile|objective-profile|regulatory-constraints|compliance-objective)(\?.*)?$/, (r) => {
    const url = r.request().url()
    if (url.includes("/variables")) return fulfillJson(r, MOCK_VARIABLES)
    if (url.includes("/experiments")) return fulfillJson(r, MOCK_EXPERIMENTS)
    return fulfillJson(r, [])
  })
  await page.route(/\/api\/backend\/reaction-projects\/\d+\/.+$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/(recommendations|recommendation-batches|experiments|variables|design-space|cost-profile|safety-profile|objective-profile|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|advisor\/runs|advisor\/comparisons|optimization\/runs|optimization\/bo\/runs|optimization\/benchmark-runs)(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-recommendation-batches\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-execution-batches\/\d+.*$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-execution-items\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-experiments\/\d+\/.+$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-mechanistic-hypotheses\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-optimization-cycles\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-recommendations\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-outcome-extraction-runs\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-advisor-runs\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/compound-registry\/(search|batches)(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECTS))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
}

// ── Top-level surface checks ──────────────────────────────────────────────────
type Surface = { path: string; eyebrow: RegExp; heading: RegExp; label: string }
const SURFACES: Surface[] = [
  {
    path: "/reactions",
    label: "Wrapper workspace header",
    eyebrow: /MolTrace · Reaction Optimization/i,
    heading: /Reaction program workspace/i,
  },
]

// ── Project-detail tab section headers ────────────────────────────────────────
type Tab = { value: string; triggerName: string; eyebrow: RegExp; heading: RegExp }
const PROJECT_TABS: Tab[] = [
  { value: "overview", triggerName: "Overview", eyebrow: /Project · Overview/i, heading: /Reaction project at a glance/i },
  { value: "variables", triggerName: "Variables", eyebrow: /Project · Variables/i, heading: /Optimization variable definitions/i },
  { value: "experiments", triggerName: "Experiments", eyebrow: /Project · Experiments/i, heading: /Experiment matrix & outcomes/i },
  { value: "objective", triggerName: "Objective", eyebrow: /Project · Objective/i, heading: /Optimization objective & weights/i },
  { value: "cost-safety", triggerName: "Cost & Safety", eyebrow: /Project · Cost & Safety/i, heading: /Cost profile & safety constraints/i },
  { value: "optimization", triggerName: "Optimization", eyebrow: /Project · Optimization/i, heading: /Bayesian optimization & benchmark runs/i },
  { value: "advisor", triggerName: "Advisor", eyebrow: /Project · Optimization Advisor/i, heading: /LLM-assisted optimization advisor/i },
  { value: "recommendations", triggerName: "Recommendations", eyebrow: /Project · Recommendations/i, heading: /Reviewer queue & approvals/i },
  { value: "execution", triggerName: "Execution", eyebrow: /Project · Execution/i, heading: /Lab execution batches & outcomes/i },
  { value: "evidence", triggerName: "Evidence Links", eyebrow: /Project · Evidence Links/i, heading: /SpectraCheck-linked analytical evidence/i },
  { value: "developer", triggerName: "Developer JSON", eyebrow: /Project · Developer JSON/i, heading: /Raw payloads for debugging/i },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Reaction Optimization redesign smoke ─────────")

  // ── Wrapper workspace ──
  for (const s of SURFACES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${s.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(800)
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
    record(`${s.label} heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Landing section eyebrows ──
  await page.goto(`${BASE_URL}/reactions`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const landingEyebrows = [
    "Reaction · Campaign Summary",
    "Reaction · Validation Readiness",
    "Reaction · Recommendation Evidence",
    "Reaction · Create Project",
    "Reaction · Project Index",
  ]
  for (const tag of landingEyebrows) {
    const r = await safe(() => page.locator(`text=${tag}`).first().waitFor({ timeout: 5_000 }))
    record(`Landing section eyebrow "${tag}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Project detail: 11 tabs ──
  await page.goto(`${BASE_URL}/reactions/10`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(2500)

  for (const tab of PROJECT_TABS) {
    let r = await safe(async () => {
      await page.getByRole("tab", { name: tab.triggerName, exact: false }).first().click()
      await page.waitForTimeout(400)
    })
    if (!r.ok) {
      record(`Project tab "${tab.triggerName}" switch`, "fail", r.error)
      continue
    }
    record(`Project tab "${tab.triggerName}" switch`, "pass")

    r = await safe(() => page.locator(`text=${tab.eyebrow}`).first().waitFor({ timeout: 4_000 }))
    record(`Project tab "${tab.triggerName}" eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: tab.heading }).first().waitFor({ timeout: 4_000 }),
    )
    record(`Project tab "${tab.triggerName}" heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Reaction Optimization redesign — smoke ${new Date().toISOString()}`,
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
