#!/usr/bin/env -S pnpm tsx
import { chromium, type Route } from "@playwright/test"
;(async () => {
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext()
  const page = await context.newPage()
  // Log every request that matches /regulatory/action-items
  page.on("request", (req) => {
    const u = req.url()
    if (u.includes("regulatory")) console.log(`REQ ${req.method()} ${u}`)
  })
  page.on("requestfailed", (req) => {
    const u = req.url()
    if (u.includes("regulatory")) console.log(`FAIL ${req.method()} ${u} :: ${req.failure()?.errorText}`)
  })
  page.on("response", async (res) => {
    const u = res.url()
    if (u.includes("regulatory")) console.log(`RESP ${res.status()} ${u}`)
  })

  await page.route(/\/api\/backend\/regulatory\/action-items(\?.*)?$/, async (r: Route) => {
    console.log("MOCK MATCHED action-items")
    await r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([{ id: 1, title: "MOCKED ROW", action_type: "review", severity: "high", status: "open" }]) })
  })
  await page.route(/\/api\/backend\/regulatory\/dossiers(\?.*)?$/, async (r: Route) => {
    await r.fulfill({ status: 200, contentType: "application/json", body: "[]" })
  })

  await page.goto("http://localhost:3000/regulatory/action-queue", { waitUntil: "load", timeout: 60000 })
  await page.waitForTimeout(5000)
  // Snapshot all button accessible names
  const buttonTexts = await page.locator('button').evaluateAll((nodes) =>
    nodes.map((n) => (n as HTMLElement).innerText.trim()).filter(Boolean),
  )
  console.log("--- ALL BUTTON TEXTS ---")
  console.log(JSON.stringify(buttonTexts, null, 2))
  await browser.close()
})().catch((e) => {
  console.error(e)
  process.exit(1)
})
