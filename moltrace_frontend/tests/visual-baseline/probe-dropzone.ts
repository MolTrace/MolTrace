#!/usr/bin/env -S pnpm tsx
/**
 * Quick probe: does clicking the drop-zone label actually trigger the
 * hidden file input? We listen for input.click() being called and report.
 */
import { chromium } from "@playwright/test"

const BASE_URL = "http://localhost:3000"

async function main() {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 } })
  const page = await context.newPage()
  await page.goto(`${BASE_URL}/spectracheck`, { waitUntil: "load", timeout: 60_000 })
  await page.waitForTimeout(1500)
  await page.getByTestId("spectracheck-tab-tab-processed").click()
  await page.waitForTimeout(800)

  // Patch the input so we can detect when click() is called.
  await page.evaluate(() => {
    const input = document.getElementById("proc-file") as HTMLInputElement | null
    if (!input) return
    ;(window as unknown as { __clickedInput: boolean }).__clickedInput = false
    const origClick = input.click.bind(input)
    input.click = function () {
      ;(window as unknown as { __clickedInput: boolean }).__clickedInput = true
      // Don't actually open the file picker (would block headless).
      console.log("[probe] input.click() invoked")
    }
    void origClick // keep reference
  })

  // Click the drop-zone div[role="button"] (new design)
  const zone = page.locator("div[role='button'][aria-label*='Drop processed spectrum']")
  if ((await zone.count()) === 0) {
    console.log("FAIL: drop-zone div not found")
    process.exit(1)
  }
  await zone.click()
  await page.waitForTimeout(300)

  const clickedZone = await page.evaluate(
    () => (window as unknown as { __clickedInput: boolean }).__clickedInput,
  )
  console.log(`Drop-zone click → input.click() fired: ${clickedZone}`)

  // Also test the small Label[for=proc-file] above the zone
  await page.evaluate(() => {
    ;(window as unknown as { __clickedInput: boolean }).__clickedInput = false
  })
  const smallLabel = page.locator("label[data-slot='label'][for='proc-file']")
  if ((await smallLabel.count()) > 0) {
    await smallLabel.click()
    await page.waitForTimeout(300)
    const clickedSmall = await page.evaluate(
      () => (window as unknown as { __clickedInput: boolean }).__clickedInput,
    )
    console.log(`Small Label click → input.click() fired: ${clickedSmall}`)
  } else {
    console.log("No small Label[data-slot=label] found")
  }

  // Keyboard activation (Enter on focused drop zone)
  await page.evaluate(() => {
    ;(window as unknown as { __clickedInput: boolean }).__clickedInput = false
  })
  await zone.focus()
  await zone.press("Enter")
  await page.waitForTimeout(300)
  const clickedKbd = await page.evaluate(
    () => (window as unknown as { __clickedInput: boolean }).__clickedInput,
  )
  console.log(`Drop-zone Enter key → input.click() fired: ${clickedKbd}`)

  // Inspect input visibility
  const inputInfo = await page.locator("#proc-file").evaluate((el) => {
    const cs = getComputedStyle(el as HTMLElement)
    const rect = (el as HTMLElement).getBoundingClientRect()
    return {
      display: cs.display,
      visibility: cs.visibility,
      position: cs.position,
      width: cs.width,
      height: cs.height,
      pointerEvents: cs.pointerEvents,
      rectW: rect.width,
      rectH: rect.height,
      className: (el as HTMLInputElement).className,
    }
  })
  console.log("Input style probe:", inputInfo)

  await context.close()
  await browser.close()
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
