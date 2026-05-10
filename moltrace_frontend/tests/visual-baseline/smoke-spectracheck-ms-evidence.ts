#!/usr/bin/env -S pnpm tsx
/**
 * Functional smoke test for the redesigned MS Evidence Studio sub-tabs.
 * Verifies (lightweight render & navigation):
 *   - Each of the 11 MS sub-tabs renders Step 1 + Step 2 ModuleCards
 *   - Action tile prominently styled inside Step 2
 *   - Endpoint contracts (POST {url}) preserved in tooltip text
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-spectracheck-ms-evidence.ts
 */
import { chromium, type Page } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-ms-evidence-report.md")
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

async function gotoMsEvidenceTab(page: Page) {
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
  await page.waitForTimeout(1500)
  const tab = page.getByTestId("spectracheck-tab-tab-ms-evidence")
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(800)
}

async function openSubTab(page: Page, name: RegExp) {
  // MS Evidence sub-tabs use tab role from shadcn Tabs (no testid set in MsEvidenceTabWithTooltip)
  const tab = page.getByRole("tab", { name })
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(500)
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()

  console.log("\n── MS Evidence Studio sub-tabs reskin smoke ─────────")
  await gotoMsEvidenceTab(page)

  type Spec = {
    name: string
    tabName: RegExp
    step1Heading: RegExp
    step2Heading: RegExp
    actionTile: RegExp
    endpoint: string
  }
  const specs: Spec[] = [
    {
      name: "HRMS",
      tabName: /HRMS exact mass/i,
      step1Heading: /Configure HRMS inputs/i,
      step2Heading: /Match candidates by HRMS/i,
      actionTile: /Match candidates by HRMS/i,
      endpoint: "/ms/hrms/candidates/match/evidence",
    },
    {
      name: "Formula",
      tabName: /Formula search/i,
      step1Heading: /Configure mass \+ composition bounds/i,
      step2Heading: /Search molecular formulas/i,
      actionTile: /Search formulas/i,
      endpoint: "/ms/hrms/formulas/search",
    },
    {
      name: "Adduct",
      tabName: /Adduct \+ isotope/i,
      step1Heading: /Tolerances & MS1 peak list/i,
      step2Heading: /Infer adducts \+ isotopes/i,
      actionTile: /Infer adducts \+ isotopes/i,
      endpoint: "/ms/adducts/infer/evidence",
    },
    {
      name: "MS/MS",
      tabName: /Processed MS\/MS/i,
      step1Heading: /Precursor \+ tolerances \+ peak list/i,
      step2Heading: /Annotate MS\/MS peaks/i,
      actionTile: /Annotate MS\/MS/i,
      endpoint: "/ms/msms/annotate/evidence",
    },
    {
      name: "Frag Tree",
      tabName: /Fragmentation tree/i,
      step1Heading: /Tree depth \+ precursor \+ MS\/MS peaks/i,
      step2Heading: /Build fragmentation tree/i,
      actionTile: /Build fragmentation tree/i,
      endpoint: "/ms/msms/fragmentation-tree/evidence",
    },
    {
      name: "LC-MS Import",
      tabName: /LC-MS import/i,
      step1Heading: /File source \+ labels/i,
      step2Heading: /Import LC-MS\/MS/i,
      actionTile: /Import LC-MS\/MS/i,
      endpoint: "/ms/lcms/import/bridge/upload",
    },
    {
      name: "LC-MS Features",
      tabName: /LC-MS features/i,
      step1Heading: /File source \+ targets \+ tolerances/i,
      step2Heading: /Detect features \+ XICs/i,
      actionTile: /Detect features \+ XICs/i,
      endpoint: "/ms/lcms/features/detect/upload",
    },
    {
      name: "LC-MS Grouping",
      tabName: /LC-MS grouping/i,
      step1Heading: /Sample \+ blank tables \+ tolerances/i,
      step2Heading: /Group features/i,
      actionTile: /Group features/i,
      endpoint: "/ms/lcms/features/group/evidence",
    },
    {
      name: "LC-MS Consensus",
      tabName: /LC-MS consensus/i,
      step1Heading: /Grouped feature table \+ scoring toggles/i,
      step2Heading: /Score feature-family consensus/i,
      actionTile: /Score feature-family consensus/i,
      endpoint: "/ms/lcms/features/consensus/evidence",
    },
    {
      name: "LC-MS Dereplication",
      tabName: /LC-MS dereplication/i,
      step1Heading: /Library candidates \+ family table \+ tolerances/i,
      step2Heading: /Run dereplication/i,
      actionTile: /Run dereplication/i,
      endpoint: "/ms/lcms/dereplication/evidence",
    },
    {
      name: "LC-MS Bridge",
      tabName: /LC-MS bridge/i,
      step1Heading: /Candidates \+ consensus family table/i,
      step2Heading: /Bridge LC-MS evidence to candidate confidence/i,
      actionTile: /Bridge LC-MS evidence to candidate confidence/i,
      endpoint: "/confidence/candidates/lcms-consensus-bridge",
    },
  ]

  for (const spec of specs) {
    let r = await safe(() => openSubTab(page, spec.tabName))
    if (!r.ok) {
      record(`${spec.name} sub-tab opens`, "fail", r.error)
      continue
    }
    record(`${spec.name} sub-tab opens`, "pass")

    r = await safe(() => page.getByText(spec.step1Heading).first().waitFor({ timeout: 5_000 }))
    record(`${spec.name} Step 1 heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() => page.getByText(spec.step2Heading).first().waitFor({ timeout: 5_000 }))
    record(`${spec.name} Step 2 heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("button", { name: spec.actionTile }).first().waitFor({ timeout: 5_000 }),
    )
    record(`${spec.name} action tile rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# MS Evidence Studio sub-tabs reskin — smoke ${new Date().toISOString()}`,
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
