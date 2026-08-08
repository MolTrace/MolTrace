import { ApiError } from "@/lib/api/client"

/**
 * The four reasons a product can be closed to you, and the four different things
 * you would do about each.
 *
 * Until now these all arrived as one generic lock, so the UI had to guess — and
 * three of the four guesses send a reader somewhere that cannot help them. A user
 * whose ADMIN simply has not switched a product on does not need a sales
 * conversation; a user whose ROLE excludes an action does not need a plan change;
 * a workspace that has bought a product and not finished setting it up needs
 * neither.
 *
 * TWO RULES, from the handoff, and both are about not lying:
 *
 *  1. Never render a capability as available and then fail on click. The sidebar
 *     already hides routes this deployment does not serve; this component is for
 *     the cases that slip through, not a substitute for that.
 *
 *  2. Never invent an upgrade call-to-action for a SKU that does not exist.
 *     Pricing and packaging are not in this codebase, so nothing here names a
 *     tier, quotes a price, or offers to upgrade in place. `not_in_plan` opens a
 *     conversation, which is true, rather than a checkout, which would be
 *     fiction.
 */

export type UpgradeState =
  | "not_in_plan"
  | "not_enabled"
  | "not_provisioned"
  | "role_required"

/** Backend `code` -> the state it represents. Codes come from error_codes.PUBLIC_CODES. */
const CODE_TO_STATE: Record<string, UpgradeState> = {
  product_not_in_plan: "not_in_plan",
  product_not_enabled: "not_enabled",
  product_not_provisioned: "not_provisioned",
  role_required: "role_required",
}

export type UpgradeRefusal = {
  state: UpgradeState
  /** The product, from the `X-MolTrace-Module` header, when the backend named one. */
  product: string | null
}

function codeOf(data: unknown): string | null {
  if (data && typeof data === "object") {
    const code = (data as { code?: unknown }).code
    if (typeof code === "string" && code) return code
  }
  return null
}

/**
 * Read a refusal as one of the four states, or null when it is not one of them.
 *
 * Returns null rather than guessing for `module_not_licensed`, the older
 * deployment-wide gate: that says the deployment does not serve the product at
 * all, which is not one of these four and has no per-user next action. Callers
 * keep their existing handling for it.
 */
export function readUpgradeRefusal(err: unknown): UpgradeRefusal | null {
  if (!(err instanceof ApiError)) return null
  if (err.status !== 403 && err.status !== 402) return null
  const code = codeOf(err.data)
  if (!code) return null
  const state = CODE_TO_STATE[code]
  if (!state) return null
  return { state, product: err.moduleNotIncluded || null }
}

export type UpgradeCopy = {
  title: string
  body: string
  /** The one action that can actually resolve this state, or null when the reader has none. */
  action: { label: string; href: string } | null
}

/**
 * What to say, and the single next step that can actually resolve it.
 *
 * `action` is null where the reader genuinely cannot act — `not_enabled` and
 * `role_required` are resolved by somebody else, and offering a button that
 * takes them to a settings page they have no permission to change would be
 * another dead end wearing a different label.
 */
export function upgradeCopy(refusal: UpgradeRefusal): UpgradeCopy {
  const product = refusal.product?.trim()
  const named = product ? `“${product}”` : "This product"

  switch (refusal.state) {
    case "not_in_plan":
      return {
        title: `${named} is not part of your plan`,
        // No tier, no price, no "upgrade now": packaging is not in this codebase,
        // so the honest offer is a conversation.
        body: "Your workspace does not currently include it. We can talk through what adding it would involve.",
        action: {
          label: "Contact us about access",
          href: `/contact?reason=${encodeURIComponent(`Access to ${product || "an additional product"}`)}`,
        },
      }
    case "not_enabled":
      return {
        title: `${named} is not switched on for this workspace`,
        body: "It is available to your organization, but an administrator has not enabled it here yet.",
        action: null,
      }
    case "not_provisioned":
      return {
        title: `${named} is enabled but not set up`,
        body: "Setup has not been finished, so there is nothing to show yet. An administrator can complete it in Settings.",
        action: { label: "Open settings", href: "/dashboard/settings" },
      }
    case "role_required":
      return {
        title: "Your role does not include this",
        body: "Someone with the right role can do this, or an administrator can change yours.",
        action: null,
      }
  }
}
