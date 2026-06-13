#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned ComplianceCore surfaces.
 *
 * Verifies that each redesigned surface now exposes:
 *   - The new eyebrow tagline (font-mono uppercase tracked)
 *   - The page-level h1 / section h2 with the expected new copy
 *
 * Hermetic: all `/regulatory/*`, `/projects`, `/reaction-projects` are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-regulatory-hub.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-regulatory-hub-report.md")
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

const MOCK_DOSSIERS = [
  { id: 1, title: "MTX-447 dossier", project_id: 1, sample_id: "SMP-1", status: "in_review", risk_level: "medium" },
]
const MOCK_JURISDICTIONS = [{ id: 1, code: "fda", label: "United States (FDA)", name: "FDA" }]
const MOCK_PROJECTS = [{ id: 1, name: "MTX program" }]
const MOCK_SOURCES = [{ id: 1, title: "ICH Q3D", source_type: "guideline", status: "active", version: "v3" }]

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  await page.route(/\/api\/backend\/regulatory\/dossiers(\?.*)?$/, (r) => fulfillJson(r, MOCK_DOSSIERS))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/risk-assessment$/, (r) => fulfillJson(r, { overall_risk: "medium" }))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/requirements$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { ...MOCK_DOSSIERS[0], requirements: [] }),
  )
  await page.route(/\/api\/backend\/regulatory\/jurisdictions$/, (r) => fulfillJson(r, MOCK_JURISDICTIONS))
  await page.route(/\/api\/backend\/regulatory\/changes(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/changes\/\d+(\?.*)?$/, (r) => fulfillJson(r, {}))
  await page.route(/\/api\/backend\/regulatory\/sources(\?.*)?$/, (r) => fulfillJson(r, MOCK_SOURCES))
  await page.route(/\/api\/backend\/regulatory\/sources\/\d+(\?.*)?$/, (r) => fulfillJson(r, MOCK_SOURCES[0]))
  await page.route(/\/api\/backend\/regulatory\/sources\/search$/, (r) => fulfillJson(r, { results: [] }))
  await page.route(/\/api\/backend\/regulatory\/notifications(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/action-items(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/rule-sets(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/rule-update-proposals(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/surveillance\/sources(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, MOCK_PROJECTS))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
}

type Spec = {
  path: string
  label: string
  // These must appear in the new chrome
  eyebrow: RegExp
  heading: RegExp
}

const SPECS: Spec[] = [
  {
    path: "/regulatory",
    label: "Intelligence landing",
    eyebrow: /MolTrace · ComplianceCore/i,
    heading: /^ComplianceCore$/i,
  },
  {
    path: "/regulatory/action-queue",
    label: "Action queue",
    eyebrow: /Regulatory · Action Queue/i,
    heading: /Action items/i,
  },
  {
    path: "/regulatory/surveillance",
    label: "Surveillance dashboard",
    eyebrow: /Regulatory · Surveillance/i,
    heading: /Regulatory Surveillance/i,
  },
  {
    path: "/regulatory/sources",
    label: "Source library",
    eyebrow: /MolTrace · Regulatory · Source Library/i,
    heading: /Regulatory Source Library/i,
  },
  {
    path: "/regulatory/rule-updates",
    label: "Rule updates",
    eyebrow: /Regulatory · Rule Updates/i,
    heading: /Rule Update Proposals/i,
  },
  {
    path: "/regulatory/notifications",
    label: "Notifications",
    eyebrow: /Regulatory · Notifications/i,
    heading: /Regulatory Notifications/i,
  },
  {
    path: "/regulatory/changes/1",
    label: "Change detail",
    eyebrow: /MolTrace · Regulatory · Change Detail/i,
    heading: /Regulatory Change Detail/i,
  },
  {
    path: "/regulatory/dossiers/1",
    label: "Dossier workspace",
    eyebrow: /MolTrace · Regulatory Dossier/i,
    heading: /Regulatory Dossier/i,
  },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── ComplianceCore redesign smoke ─────────")

  for (const spec of SPECS) {
    let r = await safe(async () => {
      await page.goto(`${BASE_URL}${spec.path}`, { waitUntil: "load", timeout: 120_000 })
      await page.waitForTimeout(800)
    })
    if (!r.ok) {
      record(`${spec.label} loads`, "fail", r.error)
      continue
    }
    record(`${spec.label} loads`, "pass")

    r = await safe(() => page.locator(`text=${spec.eyebrow}`).first().waitFor({ timeout: 5_000 }))
    record(`${spec.label} eyebrow tagline rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: spec.heading }).first().waitFor({ timeout: 5_000 }),
    )
    record(`${spec.label} heading "${spec.heading}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  // ── Intelligence landing's new section eyebrows must all render ──
  await page.goto(`${BASE_URL}/regulatory`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const newSectionEyebrows = [
    "Regulatory · At a glance",
    "Regulatory · Validation Readiness",
    "Regulatory · Notifications snapshot",
    "Regulatory · Action Cards",
    "Regulatory · Evidence Queue",
    "Regulatory · Create Dossier",
    "Regulatory · Dossier Index",
    "Regulatory · Related Workspaces",
    "Regulatory · Source Library",
    "Regulatory · Review Queue",
  ]
  for (const tag of newSectionEyebrows) {
    const r = await safe(() => page.locator(`text=${tag}`).first().waitFor({ timeout: 5_000 }))
    record(`Landing section eyebrow "${tag}" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# ComplianceCore redesign — smoke ${new Date().toISOString()}`,
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
