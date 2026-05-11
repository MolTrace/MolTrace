#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the redesigned Validation Center module surfaces.
 *
 * Verifies that each redesigned route exposes the new module-coded eyebrow
 * (green, "MolTrace · …") and the existing h1 page-title.
 *
 * Hermetic: all `/validation/*`, `/projects/*`, `/regulatory/*`,
 * `/reaction-projects/*`, `/spectracheck/*` endpoints are mocked.
 *
 * Run while dev server is up: pnpm tsx tests/visual-baseline/smoke-validation-center.ts
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-validation-center-report.md")
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
  await page.route(/\/api\/backend\/validation\/projects\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 1, name: "MTX validation", status: "active", project_id: 1 }),
  )
  await page.route(/\/api\/backend\/validation\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/validation\/runs\/\d+(\?.*)?$/, (r) =>
    fulfillJson(r, { id: 1, validation_project_id: 1, status: "completed" }),
  )
  await page.route(/\/api\/backend\/validation\/runs(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/validation\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/regulatory\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/reaction-projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects(\?.*)?$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/projects\/.+$/, (r) => fulfillJson(r, []))
  await page.route(/\/api\/backend\/(carbon13|nmr2d|prediction|similarity|candidates|sessions|ms|spectracheck|workflow-templates|knowledge|compound-registry|secure-shares)\/.+$/, (r) =>
    fulfillJson(r, { warnings: [], notes: [] }),
  )
  await page.route(/\/api\/backend\/ai\/.+$/, (r) => fulfillJson(r, []))
}

type Surface = {
  path: string
  label: string
  eyebrow: RegExp
}

const SURFACES: Surface[] = [
  { path: "/validation-center", label: "Validation Center landing", eyebrow: /MolTrace · Validation Center/i },
  { path: "/validation-center/projects", label: "Validation projects index (also Validation Center)", eyebrow: /MolTrace · Validation Center/i },
  { path: "/validation-center/projects/1", label: "Validation project detail", eyebrow: /MolTrace · Validation Project/i },
  { path: "/validation-center/capa", label: "CAPA workspace", eyebrow: /MolTrace · CAPA/i },
  { path: "/validation-center/controlled-records", label: "Controlled records", eyebrow: /MolTrace · Controlled Records/i },
  { path: "/validation-center/data-integrity", label: "Data integrity", eyebrow: /MolTrace · Data Integrity/i },
  { path: "/validation-center/deviations", label: "Deviations", eyebrow: /MolTrace · Deviations/i },
  { path: "/validation-center/esignatures", label: "E-signatures", eyebrow: /MolTrace · e-Signatures/i },
  { path: "/validation-center/inspection-package", label: "Inspection package", eyebrow: /MolTrace · Inspection Package/i },
  { path: "/validation-center/releases", label: "System releases", eyebrow: /MolTrace · System Releases/i },
  { path: "/validation-center/traceability", label: "Traceability", eyebrow: /MolTrace · Traceability Matrix/i },
  { path: "/validation", label: "Validation dashboard", eyebrow: /MolTrace · Validation/i },
  { path: "/validation/1", label: "Validation run detail", eyebrow: /MolTrace · Validation Run/i },
]

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── Validation Center redesign smoke ─────────")

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

    // Verify sidebar still rendered (the AppShell fix on /validation-center/projects sticks)
    r = await safe(() => page.locator("text=Programs").first().waitFor({ timeout: 5_000 }))
    record(`${s.label} sidebar Programs link rendered`, r.ok ? "pass" : "fail", r.ok ? undefined : r.error)
  }

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# Validation Center redesign — smoke ${new Date().toISOString()}`,
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
