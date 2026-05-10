#!/usr/bin/env -S pnpm tsx
/**
 * Quick one-shot capture of /spectracheck with the "Processed 1H/13C upload"
 * tab clicked. Used for design-iteration screenshots.
 *
 * Output: tests/visual-baseline/screenshots/_iter/processed-1h-13c-redesign.png
 */
import { chromium } from "@playwright/test"
import { mkdir } from "node:fs/promises"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, "screenshots", "_iter")
const BASE_URL = "http://localhost:3000"

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 60_000 })
  await page.waitForTimeout(1500)

  // Click the target tab — env var TAB picks which one (default tab-processed).
  const tabId = process.env.TAB ?? "tab-processed"
  const tab = page.getByTestId(`spectracheck-tab-${tabId}`)
  if (await tab.count()) {
    await tab.scrollIntoViewIfNeeded()
    await tab.click()
    await page.waitForTimeout(1500)
  }

  // Scroll the AppShell's inner main element so the tab content sits near the top.
  await page.evaluate(() => {
    const main = document.querySelector("main")
    if (!main) return
    // Find the active TabsContent panel and scroll it into the top of the main area.
    const active = document.querySelector('[data-state="active"][role="tabpanel"]')
    if (active) {
      const rect = active.getBoundingClientRect()
      main.scrollBy({ top: rect.top - 80, behavior: "instant" as ScrollBehavior })
    }
  })
  await page.waitForTimeout(400)

  // Capture the entire main scroll container at full height so it shows all sections.
  await page.evaluate(() => {
    const main = document.querySelector("main")
    if (main) main.scrollTop = 0
  })
  await page.waitForTimeout(200)

  // Resize viewport to be very tall so all tab content fits in fullPage capture.
  await page.setViewportSize({ width: 1440, height: 3200 })
  await page.waitForTimeout(400)

  const outName = process.env.OUT ?? "processed-1h-13c-redesign"
  await page.screenshot({
    path: join(OUT_DIR, `${outName}.png`),
    fullPage: false, // taking the full viewport (which we made tall)
    animations: "disabled",
  })
  console.log(`captured → screenshots/_iter/${outName}.png`)

  await context.close()
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
