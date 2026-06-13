#!/usr/bin/env -S pnpm tsx
/**
 * Baseline regression test for the ComplianceCore module.
 *
 * Captures CURRENT behavior across all 9 regulatory routes + cross-module
 * integration points (SpectraCheck → Regulatory, Regulatory → Reaction
 * Optimization). Run BEFORE the reskin to establish a baseline, and AFTER
 * each redesign step to catch regressions.
 *
 * All `/regulatory/*`, `/projects`, `/reaction-projects` endpoints are mocked
 * so the test is hermetic and runs without a backend.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/baseline-regulatory-hub.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "baseline-regulatory-hub-report.md")
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

// ─── Hermetic mock fixtures ──────────────────────────────────────────────────
const MOCK_DOSSIERS = [
  { id: 1, title: "MTX-447 dossier", project_id: 1, sample_id: "SMP-1", status: "draft", risk_level: "medium" },
  { id: 2, title: "ABT-118 dossier", project_id: 2, sample_id: "SMP-2", status: "in_review", risk_level: "high" },
]
const MOCK_JURISDICTIONS = [
  { id: 1, code: "fda", label: "United States (FDA)" },
  { id: 2, code: "ema", label: "European Union (EMA)" },
  { id: 3, code: "pmda", label: "Japan (PMDA)" },
]
const MOCK_PROJECTS = [{ id: 1, name: "MTX program" }, { id: 2, name: "ABT program" }]
const MOCK_REACTION_PROJECTS = [{ id: 10, name: "MTX route opt" }]
const MOCK_CHANGES = [
  { id: 1, title: "ICH Q3D update — Class 1 elemental impurities", source_id: 1, severity: "high", status: "pending_review" },
  { id: 2, title: "FDA draft guidance — nitrosamine risk assessment", source_id: 2, severity: "medium", status: "ack" },
]
const MOCK_SOURCES = [
  { id: 1, name: "ICH Quality Guidelines", jurisdiction: "ich", status: "active" },
  { id: 2, name: "FDA CDER Drug Guidances", jurisdiction: "fda", status: "active" },
]
const MOCK_NOTIFICATIONS = [
  { id: 1, title: "New change ready for review", change_id: 1, kind: "change", status: "unread", created_at: "2026-05-01" },
]
const MOCK_ACTION_ITEMS = [
  { id: 1, title: "Review Q3D update", status: "open", priority: "high", change_id: 1, created_at: "2026-05-01" },
]
const MOCK_RULE_PROPOSALS = [
  { id: 1, title: "Tighten Pd limit", status: "proposed", impact: "medium", created_at: "2026-05-01" },
]
const MOCK_RULE_SETS = [{ id: 1, name: "Phase 1 IND", status: "active" }]
const MOCK_REQUIREMENTS = [
  { id: "r1", label: "Identity proof", framework: "ICH Q6A", status: "complete", evidence_refs: ["NMR-014"] },
]
const MOCK_RISK_ASSESSMENT = { overall_risk: "medium", risk_score: 0.42, factors: [] }
const MOCK_SURVEILLANCE_SOURCES = [
  { id: 1, name: "FDA Drug Safety alerts", url: "https://fda.gov", crawl_state: "ok", last_crawled_at: "2026-05-01" },
]

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  })
}

async function installRegulatoryMocks(page: Page) {
  await page.route(/\/api\/backend\/regulatory\/dossiers\?.*$/, (r) => fulfillJson(r, MOCK_DOSSIERS))
  await page.route(/\/api\/backend\/regulatory\/dossiers$/, (r) => {
    if (r.request().method() === "POST") {
      return fulfillJson(r, { id: 99, title: "New dossier" }, 201)
    }
    return fulfillJson(r, MOCK_DOSSIERS)
  })
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/risk-assessment$/, (r) =>
    fulfillJson(r, MOCK_RISK_ASSESSMENT),
  )
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/requirements$/, (r) => fulfillJson(r, MOCK_REQUIREMENTS))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { ...MOCK_DOSSIERS[0], requirements: MOCK_REQUIREMENTS }),
  )
  await page.route(/\/api\/backend\/regulatory\/jurisdictions$/, (r) => fulfillJson(r, MOCK_JURISDICTIONS))
  await page.route(/\/api\/backend\/regulatory\/changes(\?.*)?$/, (r) => fulfillJson(r, MOCK_CHANGES))
  await page.route(/\/api\/backend\/regulatory\/changes\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_CHANGES[0]))
  await page.route(/\/api\/backend\/regulatory\/sources(\?.*)?$/, (r) => fulfillJson(r, MOCK_SOURCES))
  await page.route(/\/api\/backend\/regulatory\/sources\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_SOURCES[0]))
  await page.route(/\/api\/backend\/regulatory\/sources\/upload$/, (r) => fulfillJson(r, { id: 99, status: "uploaded" }))
  await page.route(/\/api\/backend\/regulatory\/sources\/search$/, (r) => fulfillJson(r, { results: MOCK_SOURCES }))
  await page.route(/\/api\/backend\/regulatory\/notifications(\?.*)?$/, (r) => fulfillJson(r, MOCK_NOTIFICATIONS))
  await page.route(/\/api\/backend\/regulatory\/action-items(\?.*)?$/, (r) => {
    if (r.request().method() === "POST") return fulfillJson(r, { id: 99, status: "open" }, 201)
    return fulfillJson(r, MOCK_ACTION_ITEMS)
  })
  await page.route(/\/api\/backend\/regulatory\/rule-sets(\?.*)?$/, (r) => fulfillJson(r, MOCK_RULE_SETS))
  await page.route(/\/api\/backend\/regulatory\/rule-update-proposals(\?.*)?$/, (r) => fulfillJson(r, MOCK_RULE_PROPOSALS))
  await page.route(/\/api\/backend\/regulatory\/surveillance\/sources(\?.*)?$/, (r) =>
    fulfillJson(r, MOCK_SURVEILLANCE_SOURCES),
  )
  await page.route(/\/api\/backend\/regulatory\/surveillance\/runs$/, (r) =>
    fulfillJson(r, { id: 99, status: "queued" }, 202),
  )
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECTS))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, MOCK_REACTION_PROJECTS))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) =>
    fulfillJson(r, [{ id: 1, sample_id: "SMP-1", project_id: 1 }]),
  )
}

async function installSpectracheckMocks(page: Page) {
  // For the cross-module test that loads SpectraCheck
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms)\/.+/, (r) =>
    fulfillJson(r, { sample_id: "smoke", warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/spectracheck\/.+/, (r) => fulfillJson(r, { items: [], warnings: [] }))
}

// ─── Routes to verify ────────────────────────────────────────────────────────
const ROUTES: { path: string; signal: RegExp; label: string }[] = [
  { path: "/regulatory", signal: /Regulatory|Dossier|Surveillance/i, label: "Intelligence landing" },
  { path: "/regulatory/action-queue", signal: /Action queue|Action items/i, label: "Action queue" },
  { path: "/regulatory/surveillance", signal: /Surveillance|sources/i, label: "Surveillance" },
  { path: "/regulatory/sources", signal: /Source library|Sources/i, label: "Source library" },
  { path: "/regulatory/sources/1", signal: /Version|Timeline|Source/i, label: "Source version timeline" },
  { path: "/regulatory/rule-updates", signal: /Rule|Update|proposed/i, label: "Rule updates" },
  { path: "/regulatory/notifications", signal: /Notification/i, label: "Notifications" },
  { path: "/regulatory/changes/1", signal: /Change|Q3D|Severity/i, label: "Change detail" },
  { path: "/regulatory/dossiers/1", signal: /Dossier|requirement/i, label: "Dossier workspace" },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installRegulatoryMocks(page)
  await installSpectracheckMocks(page)

  console.log("\n── ComplianceCore baseline regression ─────────")

  // ── 9 main routes load + render module signal text ──
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

    // Sidebar must remain rendered (cross-module integration: AppShell)
    r = await safe(() =>
      page.locator("text=Programs").first().waitFor({ timeout: 5_000 }),
    )
    record(`Route ${route.path} — sidebar Programs link rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    // Module signal text rendered (smoke)
    r = await safe(() => page.locator(`text=${route.signal}`).first().waitFor({ timeout: 5_000 }))
    record(`Route ${route.path} — ${route.label} signal text rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Cross-module: SpectraCheck Regulatory Impact card still loads on SpectraCheck Overview ──
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    // Open Overview tab if not already
    const tab = page.getByTestId("spectracheck-tab-tab-overview")
    await tab.scrollIntoViewIfNeeded()
    await tab.click()
    await page.waitForTimeout(500)
    // Regulatory impact card sits under "Readiness & impact" section
    await page.locator("text=Readiness & impact").first().waitFor({ timeout: 5_000 })
  })
  record(
    "Cross-module: SpectraCheck Overview → Readiness & impact section (regulatory card slot) rendered",
    r.ok ? "pass" : "fail",
    r.ok ? undefined : r.error,
  )

  // ── Cross-module: Reaction Optimization regulatory constraints panel still importable ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/reaction-optimization`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    // Just confirm the page itself loads (panel renders inside individual project detail)
    const headings = await page.locator("h1, h2").allInnerTexts()
    if (headings.length === 0) throw new Error("no headings rendered")
  })
  record("Cross-module: Reaction Optimization page loads (regulatory constraints panel host)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── Cross-module: navigation from Regulatory landing → action queue ──
  r = await safe(async () => {
    await page.goto(`${BASE_URL}/regulatory`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
    // Direct nav (avoid clicking link selectors that may shift in redesign)
    await page.goto(`${BASE_URL}/regulatory/action-queue`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(800)
    await page.locator("text=Action queue").first().waitFor({ timeout: 5_000 })
  })
  record("Navigation: Regulatory landing → /regulatory/action-queue still works", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# ComplianceCore baseline regression — ${new Date().toISOString()}`,
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
