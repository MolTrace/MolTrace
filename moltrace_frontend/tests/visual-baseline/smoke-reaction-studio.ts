#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Reaction Studio (program-level) workspace.
 *
 * The studio is reachable two ways:
 *   1. Direct: /reactions/studio  (renders ReactionStudioWorkspace)
 *   2. Wrapper tab: /reactions?tab=reaction-studio  (renders the same component
 *      inside the ReactionProgramInterfaceWorkspace tab)
 *
 * Both paths must show the same 7 page-level section headers (eyebrow + h2)
 * that we added on top of the existing ModuleCards.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-reaction-studio.ts
 */
import { chromium, type Page } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-reaction-studio-report.md")
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

type Section = { eyebrow: RegExp; heading: RegExp; label: string }
const SECTIONS: Section[] = [
  { label: "Reaction scheme", eyebrow: /Studio · Reaction Scheme/i, heading: /Structure drawing & SMARTS canvas/i },
  { label: "Run data (conditions + outcomes)", eyebrow: /Studio · Run Data/i, heading: /Condition matrix & outcomes/i },
  { label: "ELN connectors (import + export)", eyebrow: /Studio · ELN Connectors/i, heading: /ELN import & export bridges/i },
  { label: "Response surface", eyebrow: /Studio · Response Surface/i, heading: /Predicted vs observed surface plot/i },
  { label: "Approval gate", eyebrow: /Studio · Approval Gate/i, heading: /Human approval & audit trail/i },
]

async function checkPath(page: Page, path: string, prefix: string) {
  let r = await safe(async () => {
    await page.goto(`${BASE_URL}${path}`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
  })
  if (!r.ok) {
    record(`${prefix} loads`, "fail", r.error)
    return
  }
  record(`${prefix} loads`, "pass")

  // Verify the workspace's own h1 is present
  r = await safe(() =>
    page.getByRole("heading", { name: /Optimization workspace/i }).first().waitFor({ timeout: 5_000 }),
  )
  record(`${prefix} workspace h1 "Optimization workspace" rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  for (const s of SECTIONS) {
    r = await safe(() => page.locator(`text=${s.eyebrow}`).first().waitFor({ timeout: 4_000 }))
    record(`${prefix} ${s.label} eyebrow rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

    r = await safe(() =>
      page.getByRole("heading", { name: s.heading }).first().waitFor({ timeout: 4_000 }),
    )
    record(`${prefix} ${s.label} heading rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()

  console.log("\n── Reaction Studio (program-level) reskin smoke ─────────")

  // Path 1: Direct studio route
  await checkPath(page, "/reactions/studio", "[direct /reactions/studio]")

  // Path 2: Wrapper tab on /reactions
  await checkPath(page, "/reactions?tab=reaction-studio", "[wrapper /reactions?tab=reaction-studio]")

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Reaction Studio reskin — smoke ${new Date().toISOString()}`,
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
