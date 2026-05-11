#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the Reaction Optimization module.
 *
 * Captures CURRENT behavior across all 5 reaction routes + cross-module
 * integration (Regulatory ← Reaction handoff card; SpectraCheck ← Reaction
 * link-spectracheck-session seam). Run BEFORE the reskin to establish a
 * baseline, and AFTER each redesign step to catch regressions.
 *
 * Hermetic: all `/reaction-projects`, `/projects`, `/regulatory/*`,
 * `/compound-registry/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-reaction-optimization.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-reaction-optimization-report.md")
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

const MOCK_REACTION_PROJECTS = [
  { id: 10, name: "MTX route opt", status: "active", project_id: 1 },
  { id: 11, name: "ABT screen", status: "active", project_id: 2 },
]
const MOCK_PROJECTS = [{ id: 1, name: "MTX program" }, { id: 2, name: "ABT program" }]
const MOCK_VARIABLES = [
  { id: 1, name: "temperature_C", lower_bound: 25, upper_bound: 80, kind: "continuous" },
]
const MOCK_EXPERIMENTS = [
  { id: 1, label: "EXP-001", reaction_project_id: 10, status: "completed" },
]
const MOCK_RECOMMENDATIONS = [
  { id: 1, recommendation_id: 1, score: 0.78, status: "open", reaction_project_id: 10 },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  // Reaction projects
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99, name: "new" }, 201)
    return fulfillJson(r, MOCK_REACTION_PROJECTS)
  })
  await page.route(/\/api\/backend\/reaction-projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, MOCK_REACTION_PROJECTS[0]),
  )
  // Project detail sub-resources
  await page.route(/\/api\/backend\/reaction-projects\/\d+\/(variables|experiments|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches|design-space)(\?.*)?$/, (r) => {
    const url = r.request().url()
    if (url.includes("/variables")) return fulfillJson(r, MOCK_VARIABLES)
    if (url.includes("/experiments")) return fulfillJson(r, MOCK_EXPERIMENTS)
    return fulfillJson(r, [])
  })
  await page.route(/\/api\/backend\/reaction-projects\/\d+\/(advisor\/run|advisor\/compare-bo-llm|optimization\/run|optimization\/benchmark)(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 1, status: "queued" }, 202),
  )
  // Recommendations + execution
  await page.route(/\/api\/backend\/recommendations(\?.*)?$/, (r) => fulfillJson(r, MOCK_RECOMMENDATIONS))
  await page.route(/\/api\/backend\/recommendation-batches(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-recommendation-batches\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-execution-batches\/\d+(\/items)?(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-execution-items\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-experiments\/\d+\/(evidence|link-spectracheck-session)(\?.*)?$/, (r) =>
    fulfillJson(r, {}),
  )
  await page.route(/\/api\/backend\/reaction-mechanistic-hypotheses\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-optimization-cycles\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-recommendations\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-outcome-extraction-runs\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/reaction-advisor-runs\/\d+.*$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/(advisor\/runs|advisor\/comparisons|optimization\/runs|optimization\/bo\/runs|optimization\/benchmark-runs|recommendations|recommendation-batches|experiments|variables|design-space|cost-profile|safety-profile|objective-profile|literature-priors|mechanistic-hypotheses|optimization-cycles|execution-batches)(\?.*)?$/, (r) => fulfillJson(r, []))
  // Compound registry
  await page.route(/\/api\/backend\/compound-registry\/(search|batches)(\?.*)?$/, (r) => fulfillJson(r, []))
  // Projects
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECTS))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
  // Regulatory (cross-module: handoff card lives in Reaction → calls regulatory endpoints)
  await page.route(/\/api\/backend\/regulatory\/(dossiers|jurisdictions|sources|action-items|notifications|changes|rule-sets|rule-update-proposals)(\?.*)?$/, (r) =>
    fulfillJson(r, []),
  )
  // SpectraCheck (cross-module link)
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
}

const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/reactions", signal: /Reaction|Optimization|Studio/i, label: "Reactions program landing" },
  { path: "/reactions?tab=reaction-studio", signal: /Studio|Reaction/i, label: "Reactions program (studio tab)" },
  { path: "/reactions/10", signal: /Reaction|Project|Variables|Experiments/i, label: "Reaction project detail (id=10)" },
  { path: "/reactions/studio", signal: /Studio|Reaction/i, label: "Reaction studio direct" },
  { path: "/dashboard/reactions", signal: /Reaction|Recommendations|Experiments/i, label: "Dashboard reactions view" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Reaction Optimization baseline regression ─────────")

  for (const route of ROUTES) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${route.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(800)
    })
    if (!r.ok) {
      record(`Route ${route.path} loads`, "fail", r.error)
      continue
    }
    record(`Route ${route.path} loads`, "pass")

    r = await safe(() => page.locator("text=Programs").first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — sidebar Programs link rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() => page.locator(`text=${route.signal}`).first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — ${route.label} signal text rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Cross-module: Regulatory dossier still loads + handoff card host present ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory/dossiers/1`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    // Handoff card sits inside Action Items tab
    await page.getByRole("tab", { name: "Action Items" }).first().click()
    await page.waitForTimeout(500)
    const handoffMatches = await page.locator("text=/Reaction Optimization|Hand-off|Handoff/i").count()
    if (handoffMatches === 0) throw new Error("No reaction-handoff text found on dossier action-items tab")
  })
  record(
    "Cross-module: Regulatory Dossier Action Items → Reaction Optimization handoff card slot present",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )

  // ── Cross-module: SpectraCheck tabs still all present ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    const tabs = await page.locator('[data-testid^="spectracheck-tab-"]').count()
    if (tabs < 12) throw new Error(`expected ≥12 SpectraCheck tabs, got ${tabs}`)
  })
  record("Cross-module: SpectraCheck retains all 12 tabs", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Wrapper tabs on /reactions: switch overview ↔ studio ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/reactions`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    const overviewTab = page.getByRole("tab", { name: /Reaction Optimization/i }).first()
    const studioTab = page.getByRole("tab", { name: /Reaction Studio/i }).first()
    await overviewTab.click()
    await page.waitForTimeout(300)
    await studioTab.click()
    await page.waitForTimeout(300)
    await overviewTab.click()
  })
  record("Wrapper tabs: reaction-overview ↔ reaction-studio toggle works", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Project detail tab strip: 11 tabs reachable ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/reactions/10`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(2000)
    const tabs = await page.locator('button[role="tab"]').count()
    if (tabs < 11) throw new Error(`expected ≥11 project-detail tabs, got ${tabs}`)
  })
  record("Project detail: ≥11 tabs in TabsList", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Reaction Optimization baseline regression — ${new Date().toISOString()}`,
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
