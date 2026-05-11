#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Regulatory Dossier workspace tabs.
 *
 * Verifies that each of the 17 dossier tabs (7 visible triggers + 10 hidden
 * sub-tabs reachable via the Requirements / Action Items dropdown selectors)
 * opens with the new section header (eyebrow tagline + h2 + subtitle).
 *
 * Hermetic: all `/regulatory/*`, `/projects`, `/reaction-projects` mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-regulatory-dossier-tabs.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-regulatory-dossier-tabs-report.md")
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

const MOCK_DOSSIER = { id: 1, title: "MTX-447 dossier", status: "in_review", risk_level: "medium", jurisdiction_id: 1 }
const MOCK_REQUIREMENTS = [
  { id: "r1", label: "Identity proof", framework: "ICH Q6A", status: "complete", evidence_refs: ["NMR-014"] },
]

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) })
}

async function installMocks(page: Page) {
  await page.route(/\/api\/backend\/regulatory\/dossiers(\?.*)?$/, (r) => fulfillJson(r, [MOCK_DOSSIER]))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/risk-assessment$/, (r) => fulfillJson(r, { overall_risk: "medium" }))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+\/requirements$/, (r) => fulfillJson(r, MOCK_REQUIREMENTS))
  await page.route(/\/api\/backend\/regulatory\/dossiers\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { ...MOCK_DOSSIER, requirements: MOCK_REQUIREMENTS }),
  )
  await page.route(/\/api\/backend\/regulatory\/jurisdictions$/, (r) => fulfillJson(r, [{ id: 1, name: "FDA" }]))
  await page.route(/\/api\/backend\/regulatory\/changes(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/sources(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/notifications(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/action-items(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/rule-sets(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/rule-update-proposals(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, [{ id: 1, name: "MTX" }]))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/\d+\/samples$/, (r) => fulfillJson(r, []))
}

type TabKind = "visible" | "underRequirements" | "underActionItems"

type Tab = {
  value: string
  // Tab name as it appears in the visible TabsTrigger or in the dropdown SelectItem
  triggerName: string
  kind: TabKind
  eyebrow: RegExp
  heading: RegExp
}

const TABS: Tab[] = [
  // 7 visible triggers
  { value: "overview", triggerName: "Overview", kind: "visible", eyebrow: /Dossier · Overview/i, heading: /Dossier metadata at a glance/i },
  { value: "requirements", triggerName: "Requirements", kind: "visible", eyebrow: /Dossier · Requirements/i, heading: /Requirements & evidence sections/i },
  { value: "jurisdictional-map", triggerName: "Jurisdictional Map", kind: "visible", eyebrow: /Dossier · Jurisdictional Map/i, heading: /Per-region requirement coverage/i },
  { value: "change-impact", triggerName: "Change Impact", kind: "visible", eyebrow: /Dossier · Change Impact/i, heading: /Detected regulatory changes affecting this dossier/i },
  { value: "action-items", triggerName: "Action Items", kind: "visible", eyebrow: /Dossier · Action Items/i, heading: /Reviewer & operational workflow/i },
  { value: "submission-package", triggerName: "Submission Package Builder", kind: "visible", eyebrow: /Dossier · Submission Package/i, heading: /Assemble draft submission artefacts/i },
  { value: "json", triggerName: "Developer JSON", kind: "visible", eyebrow: /Dossier · Developer JSON/i, heading: /Raw payloads for debugging/i },
  // 7 hidden under Requirements dropdown
  { value: "evidence", triggerName: "Evidence Links", kind: "underRequirements", eyebrow: /Dossier · Evidence Links/i, heading: /Linked evidence & artifacts/i },
  { value: "compliance-rules", triggerName: "Compliance Rules", kind: "underRequirements", eyebrow: /Dossier · Compliance Rules/i, heading: /Active rule sets & coverage/i },
  { value: "impurity-register", triggerName: "Impurity Risk Register", kind: "underRequirements", eyebrow: /Dossier · Impurity Register/i, heading: /Specified & unspecified impurities/i },
  { value: "residual-solvents", triggerName: "Residual Solvent Watch", kind: "underRequirements", eyebrow: /Dossier · Residual Solvents/i, heading: /ICH Q3C residual-solvent watch/i },
  { value: "nitrosamine-watch", triggerName: "Nitrosamine Watch", kind: "underRequirements", eyebrow: /Dossier · Nitrosamine Watch/i, heading: /Nitrosamine risk assessment/i },
  { value: "qnmr-method-validation", triggerName: "qNMR / Method Validation", kind: "underRequirements", eyebrow: /Dossier · qNMR Validation/i, heading: /qNMR \/ method validation evidence/i },
  { value: "ai-governance", triggerName: "AI Governance", kind: "underRequirements", eyebrow: /Dossier · AI Governance/i, heading: /AI \/ model-governance trail/i },
  // 4 hidden under Action Items dropdown
  { value: "qa", triggerName: "Cited Q&A", kind: "underActionItems", eyebrow: /Dossier · Cited Q.{1,3}A/i, heading: /Reviewer Q.{1,3}A with citations/i },
  { value: "risk", triggerName: "Risk Assessment", kind: "underActionItems", eyebrow: /Dossier · Risk Assessment/i, heading: /Risk hot-spots & mitigation status/i },
  { value: "review", triggerName: "Review", kind: "underActionItems", eyebrow: /Dossier · Review/i, heading: /Reviewer decision/i },
  { value: "readiness", triggerName: "Readiness Report", kind: "underActionItems", eyebrow: /Dossier · Readiness Report/i, heading: /Submission readiness snapshot/i },
]

async function clickVisibleTrigger(page: Page, name: string): Promise<void> {
  await page.getByRole("tab", { name }).first().click()
  await page.waitForTimeout(400)
}

async function openViaDropdown(page: Page, parentTab: "Requirements" | "Action Items", optionName: string): Promise<void> {
  // First click the parent tab
  await clickVisibleTrigger(page, parentTab)
  // Then open the Select dropdown — there are multiple selects on this page; the relevant
  // one is labeled "Requirements dropdown" or "Action Items dropdown"
  const dropdownLabel = parentTab === "Requirements" ? "Requirements dropdown" : "Action Items dropdown"
  const dropdownTrigger = page.locator(`label:has-text("${dropdownLabel}") + button[role="combobox"], label:has-text("${dropdownLabel}") + * button[role="combobox"]`).first()
  if ((await dropdownTrigger.count()) === 0) {
    // Fallback: find combobox by aria-label or by adjacent label
    await page.locator('button[role="combobox"]').first().click()
  } else {
    await dropdownTrigger.click()
  }
  await page.waitForTimeout(300)
  await page.getByRole("option", { name: optionName }).click()
  await page.waitForTimeout(400)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Regulatory Dossier tabs reskin smoke ─────────")

  // Navigate to dossier 1 once
  await page.goto(`${BASE_URL}/regulatory/dossiers/1`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(2000)

  for (const tab of TABS) {
    let r = await safe(async () => {
      if (tab.kind === "visible") {
        await clickVisibleTrigger(page, tab.triggerName)
      } else if (tab.kind === "underRequirements") {
        await openViaDropdown(page, "Requirements", tab.triggerName)
      } else {
        await openViaDropdown(page, "Action Items", tab.triggerName)
      }
    })
    if (!r.ok) {
      record(`Tab "${tab.triggerName}" switch`, "fail", r.error)
      continue
    }
    record(`Tab "${tab.triggerName}" switch`, "pass")

    r = await safe(() => page.locator(`text=${tab.eyebrow}`).first().waitFor({ timeout: 4_000 }))
    record(`Tab "${tab.triggerName}" eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: tab.heading }).first().waitFor({ timeout: 4_000 }),
    )
    record(`Tab "${tab.triggerName}" heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Regulatory Dossier tabs reskin — smoke ${new Date().toISOString()}`,
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
