#!/usr/bin/env -S pnpm tsx
/**
 * Smoke test for the Workflow Template Gallery card-as-button behavior.
 *
 * Background: previously, selecting a workflow template required clicking the
 * "Select workflow" button explicitly. The cards have been upgraded so the
 * entire card body is clickable (and keyboard-activatable via Enter / Space)
 * to select the template — while preserving the inner "View steps" button
 * (which must NOT also select the template).
 *
 * Hermetic: backend mocked. The gallery normally fetches /workflow-templates;
 * we substitute a 2-template fixture so assertions are deterministic.
 *
 * Verifies:
 *   1. SpectraCheck workflow tab loads the gallery with both fixture cards.
 *   2. Each card renders with role=button + tabIndex=0 + aria-pressed.
 *   3. Initially nothing is selected (aria-pressed=false on both cards).
 *   4. Clicking the card BODY (not on a button) selects it (aria-pressed=true).
 *   5. Switching selection by clicking the OTHER card's body works
 *      (only one card aria-pressed=true at a time).
 *   6. Clicking "View steps" opens the steps dialog WITHOUT changing
 *      selection (regression guard for the propagation fix).
 *   7. The explicit "Select workflow" button still selects (back-compat).
 *   8. Keyboard: focusing a card and pressing Enter selects it.
 *   9. Keyboard: focusing a card and pressing Space selects it.
 */
import { chromium, type Page, type Route } from "@playwright/test"
import { writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPORT_PATH = join(__dirname, "smoke-spectracheck-workflow-card-click-report.md")
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

const FIXTURE_TEMPLATES = [
  {
    id: "template-alpha",
    name: "Routine 1H NMR review",
    category: "Spectroscopy",
    description:
      "Predefined pipeline for triaging routine proton-NMR sessions through QC, evidence and unified-confidence steps.",
    required_inputs_count: 2,
    estimated_steps_count: 6,
    human_review_required: true,
    steps: [
      { title: "QC", description: "Phase + baseline checks." },
      { title: "Evidence", description: "Match to spectral library." },
    ],
  },
  {
    id: "template-beta",
    name: "Impurity scoping (LC-MS)",
    category: "MS",
    description: "Surface unknown impurities above s/n threshold with m/z annotation and library matching.",
    required_inputs_count: 1,
    estimated_steps_count: 4,
    human_review_required: false,
    steps: [
      { title: "Detect", description: "Find features above threshold." },
      { title: "Annotate", description: "Match against library." },
    ],
  },
]

async function installMocks(page: Page) {
  // Catch-all FIRST so specific routes (registered later) win the LIFO match.
  await page.route(/\/api\/backend\/.+$/, (r) => fulfillJson(r, []))
  // Specific override for the workflow-templates endpoint we care about.
  await page.route(/\/api\/backend\/workflow-templates(\?.*)?$/, (r) =>
    fulfillJson(r, FIXTURE_TEMPLATES),
  )
}

async function openWorkflowTab(page: Page) {
  // The SpectraCheck workspace exposes data-testid for each tab.
  const tab = page.getByTestId("spectracheck-tab-tab-workflow")
  await tab.scrollIntoViewIfNeeded()
  await tab.click()
  await page.waitForTimeout(500)
}

async function getCard(page: Page, name: string) {
  return page.getByRole("button", { name: new RegExp(`Select workflow template: ${name}`) }).first()
}

async function pressedState(page: Page, name: string): Promise<string | null> {
  const card = await getCard(page, name)
  return card.getAttribute("aria-pressed")
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await installMocks(page)

  console.log("\n── SpectraCheck workflow card-click smoke ─────────")

  let r = await safe(async () => {
    await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 120_000 })
    await page.waitForTimeout(1500)
  })
  if (!r.ok) {
    record("SpectraCheck loads", "fail", r.error)
    process.exit(1)
  }
  record("SpectraCheck loads", "pass")

  r = await safe(() => openWorkflowTab(page))
  record("Open workflow tab", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 1. Both gallery cards render ──
  r = await safe(() => page.getByText("Routine 1H NMR review").first().waitFor({ timeout: 10_000 }))
  record("Card 1 (Routine 1H NMR review) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  r = await safe(() => page.getByText("Impurity scoping (LC-MS)").first().waitFor({ timeout: 10_000 }))
  record("Card 2 (Impurity scoping) rendered", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 2. Cards are role=button with aria-pressed (the new clickable-card contract) ──
  r = await safe(async () => {
    const card = await getCard(page, "Routine 1H NMR review")
    await card.waitFor({ timeout: 10_000 })
    const tabIndex = await card.getAttribute("tabindex")
    if (tabIndex !== "0") throw new Error(`expected tabindex="0", got "${tabIndex}"`)
    const ariaPressed = await card.getAttribute("aria-pressed")
    if (ariaPressed === null) throw new Error("aria-pressed missing on card")
  })
  record("Card 1 has role=button + tabindex=0 + aria-pressed", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 3. Initially neither card is selected ──
  r = await safe(async () => {
    const a = await pressedState(page, "Routine 1H NMR review")
    const b = await pressedState(page, "Impurity scoping \\(LC-MS\\)")
    if (a !== "false") throw new Error(`Card 1 aria-pressed = "${a}", expected "false"`)
    if (b !== "false") throw new Error(`Card 2 aria-pressed = "${b}", expected "false"`)
  })
  record("Initial state: both cards aria-pressed=false", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 4. Click Card 1 BODY (on the title text, not on a button) → selects it ──
  r = await safe(async () => {
    // Click the title — outside any button — to prove card-body selection works.
    await page.getByText("Routine 1H NMR review").first().click()
    await page.waitForTimeout(300)
    const a = await pressedState(page, "Routine 1H NMR review")
    if (a !== "true") throw new Error(`after card-body click: aria-pressed = "${a}", expected "true"`)
  })
  record("Click on card BODY (title text) selects the template", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 5. Click Card 2's body → selection switches; only one selected at a time ──
  r = await safe(async () => {
    await page.getByText("Impurity scoping (LC-MS)").first().click()
    await page.waitForTimeout(300)
    const a = await pressedState(page, "Routine 1H NMR review")
    const b = await pressedState(page, "Impurity scoping \\(LC-MS\\)")
    if (b !== "true") throw new Error(`Card 2 aria-pressed = "${b}", expected "true"`)
    if (a !== "false") throw new Error(`Card 1 aria-pressed = "${a}", expected "false" (selection should switch)`)
  })
  record("Selection switches by clicking another card's body (mutually exclusive)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 6. Click "View steps" on Card 1 → opens dialog WITHOUT changing selection ──
  // The dialog uses aria-modal=true, which hides the cards behind it from the
  // accessibility tree, so we must close it before re-reading aria-pressed.
  // We snapshot the selection state before clicking, then verify it is
  // restored after the dialog closes.
  r = await safe(async () => {
    // Snapshot selection state BEFORE clicking View steps
    const aBefore = await pressedState(page, "Routine 1H NMR review")
    const bBefore = await pressedState(page, "Impurity scoping \\(LC-MS\\)")

    const card1 = await getCard(page, "Routine 1H NMR review")
    const viewStepsBtn = card1.getByRole("button", { name: /^View steps$/i })
    await viewStepsBtn.click()
    await page.waitForTimeout(400)

    // Dialog opens — verify by its title
    await page
      .getByRole("dialog")
      .getByText("Routine 1H NMR review")
      .first()
      .waitFor({ timeout: 5_000 })

    // Close the dialog so the cards become accessible again
    await page.keyboard.press("Escape")
    await page.waitForTimeout(300)

    // CRITICAL regression check: aria-pressed should be unchanged from before
    // the click (Card 2 was selected and should still be).
    const aAfter = await pressedState(page, "Routine 1H NMR review")
    const bAfter = await pressedState(page, "Impurity scoping \\(LC-MS\\)")
    if (aAfter !== aBefore)
      throw new Error(
        `'View steps' changed Card 1 selection: "${aBefore}" → "${aAfter}" (expected unchanged)`,
      )
    if (bAfter !== bBefore)
      throw new Error(
        `'View steps' changed Card 2 selection: "${bBefore}" → "${bAfter}" (expected unchanged)`,
      )
  })
  record("'View steps' opens dialog WITHOUT changing selection (propagation guard)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 7. Explicit 'Select workflow' button still works ──
  r = await safe(async () => {
    const card1 = await getCard(page, "Routine 1H NMR review")
    const selectBtn = card1.getByRole("button", { name: /^Select workflow$/i })
    await selectBtn.click()
    await page.waitForTimeout(300)
    const a = await pressedState(page, "Routine 1H NMR review")
    const b = await pressedState(page, "Impurity scoping \\(LC-MS\\)")
    if (a !== "true") throw new Error(`'Select workflow' click — Card 1 = "${a}", expected "true"`)
    if (b !== "false") throw new Error(`'Select workflow' click — Card 2 = "${b}", expected "false"`)
  })
  record("Explicit 'Select workflow' button still selects (back-compat)", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 8. Keyboard: focus a card + press Enter selects ──
  r = await safe(async () => {
    const card2 = await getCard(page, "Impurity scoping \\(LC-MS\\)")
    await card2.focus()
    await page.keyboard.press("Enter")
    await page.waitForTimeout(300)
    const b = await pressedState(page, "Impurity scoping \\(LC-MS\\)")
    if (b !== "true") throw new Error(`after Enter on focused card: aria-pressed = "${b}", expected "true"`)
  })
  record("Keyboard: focused card + Enter selects template", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  // ── 9. Keyboard: focus a card + press Space selects ──
  r = await safe(async () => {
    const card1 = await getCard(page, "Routine 1H NMR review")
    await card1.focus()
    await page.keyboard.press(" ")
    await page.waitForTimeout(300)
    const a = await pressedState(page, "Routine 1H NMR review")
    if (a !== "true") throw new Error(`after Space on focused card: aria-pressed = "${a}", expected "true"`)
  })
  record("Keyboard: focused card + Space selects template", r.ok ? "pass" : "fail", r.ok ? undefined : r.error)

  await context.close()
  await browser.close()

  const passes = results.filter((r) => r.status === "pass").length
  const fails = results.filter((r) => r.status === "fail").length
  console.log(`\n── Summary: ${passes} pass, ${fails} fail ──`)

  const md = [
    `# SpectraCheck workflow card-click smoke — ${new Date().toISOString()}`,
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
