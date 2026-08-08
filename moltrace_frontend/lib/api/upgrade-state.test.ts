import { describe, expect, it } from "vitest"

import { ApiError } from "@/lib/api/client"
import { readUpgradeRefusal, upgradeCopy, type UpgradeState } from "@/lib/api/upgrade-state"

/**
 * The point of these four states is that they lead to four DIFFERENT next
 * actions. A test that only checked they parse would miss the entire defect this
 * replaces — one generic lock, where three of the four possible guesses send the
 * reader somewhere that cannot help them.
 */

function refusal(code: string, product = "Repho", status = 403) {
  return new ApiError(status, { code, detail: "irrelevant prose" }, "msg", product)
}

describe("readUpgradeRefusal", () => {
  const cases: Array<[string, UpgradeState]> = [
    ["product_not_in_plan", "not_in_plan"],
    ["product_not_enabled", "not_enabled"],
    ["product_not_provisioned", "not_provisioned"],
    ["role_required", "role_required"],
  ]

  it.each(cases)("maps %s to %s", (code, state) => {
    expect(readUpgradeRefusal(refusal(code))?.state).toBe(state)
  })

  it("returns null for module_not_licensed, which is not one of the four", () => {
    // Deployment-wide: the product is not served here at all, so there is no
    // per-user next action and callers keep their existing handling.
    expect(readUpgradeRefusal(refusal("module_not_licensed"))).toBeNull()
  })

  it("returns null for an unrelated failure rather than guessing", () => {
    expect(readUpgradeRefusal(new ApiError(500, { code: "unavailable" }, "boom"))).toBeNull()
    expect(readUpgradeRefusal(new Error("not an ApiError"))).toBeNull()
    expect(readUpgradeRefusal(refusal("product_not_in_plan", "Repho", 404))).toBeNull()
  })
})

describe("upgradeCopy", () => {
  it("sends the two actionable states to different destinations", () => {
    const actions = (["not_in_plan", "not_enabled", "not_provisioned", "role_required"] as const).map(
      (state) => upgradeCopy({ state, product: "Repho" }).action?.href ?? null,
    )
    // Two states are resolved by somebody else and correctly offer nothing.
    expect(actions.filter(Boolean).length).toBe(2)

    // Compare PATHS, not full hrefs. An earlier version of this test compared
    // whole URLs and passed while both actions pointed at /contact with
    // different query strings — i.e. it would not have noticed the four
    // collapsing back toward one generic lock, which is the entire defect this
    // replaces.
    const paths = actions.filter((h): h is string => Boolean(h)).map((h) => h.split("?")[0])
    expect(new Set(paths).size).toBe(paths.length)
  })

  it("routes each actionable state to the place that can resolve it", () => {
    expect(upgradeCopy({ state: "not_in_plan", product: "Repho" }).action?.href.split("?")[0]).toBe("/contact")
    // Setup is finished in settings, not in a sales conversation.
    expect(upgradeCopy({ state: "not_provisioned", product: "Repho" }).action?.href.split("?")[0]).toBe(
      "/dashboard/settings",
    )
  })

  it("never invents a SKU, a price, or an in-place upgrade", () => {
    for (const state of ["not_in_plan", "not_enabled", "not_provisioned", "role_required"] as const) {
      const copy = upgradeCopy({ state, product: "Repho" })
      const text = `${copy.title} ${copy.body} ${copy.action?.label ?? ""}`.toLowerCase()
      // Packaging is not in this codebase. Anything priced or tiered here would
      // be invented.
      expect(text).not.toMatch(/\$|\bprice|\bpricing|\btier\b|\bper seat\b|\bper month\b/)
      expect(text).not.toMatch(/upgrade now|buy now|start (your )?trial/)
    }
  })

  it("offers a conversation for not_in_plan, not a checkout", () => {
    const copy = upgradeCopy({ state: "not_in_plan", product: "Repho" })
    expect(copy.action?.href).toContain("/contact")
    expect(copy.action?.href).toContain("Repho")
  })

  it("offers no action where the reader genuinely cannot act", () => {
    // An administrator resolves both of these. A button to a settings page they
    // cannot change would be another dead end wearing a different label.
    expect(upgradeCopy({ state: "not_enabled", product: "Repho" }).action).toBeNull()
    expect(upgradeCopy({ state: "role_required", product: null }).action).toBeNull()
  })

  it("reads sensibly when the backend named no product", () => {
    const copy = upgradeCopy({ state: "not_in_plan", product: null })
    expect(copy.title).toMatch(/this product/i)
    expect(copy.title).not.toContain("null")
    expect(copy.title).not.toContain("undefined")
  })
})

describe("formatApiError integration", () => {
  it("stops telling a signed-in user to sign in when a product is simply closed", async () => {
    const { formatApiError } = await import("@/components/spectracheck/spectracheck-helpers")

    // This formatter has ~104 call sites and used to collapse every 401/403 into
    // one auth message, so all four closed-product states told the reader to sign
    // in — advice that cannot help someone already signed in.
    for (const code of [
      "product_not_in_plan",
      "product_not_enabled",
      "product_not_provisioned",
      "role_required",
    ]) {
      const message = formatApiError(refusal(code), "fallback")
      expect(message.toLowerCase()).not.toContain("sign in")
    }
  })

  it("still treats an ordinary auth failure as one", async () => {
    const { formatApiError } = await import("@/components/spectracheck/spectracheck-helpers")
    expect(formatApiError(new ApiError(401, { detail: "nope" }, "m"), "fallback").toLowerCase()).toContain(
      "sign in",
    )
    // module_not_licensed is the deployment-wide gate, not one of the four.
    expect(formatApiError(refusal("module_not_licensed"), "fallback").toLowerCase()).toContain("sign in")
  })
})
