import { redirect } from "next/navigation"

/**
 * `/dashboard/regulatory` was a v0 prototype: a fully static screen with no data
 * fetching of any kind, rendering invented records as though they were the
 * customer's own. Nothing in the product ever linked to it — the only
 * references were visual-baseline scripts, whose match signals pinned the
 * fabricated identifiers themselves.
 *
 * A mockup route cannot be made honest while remaining a mockup: there is no
 * live source behind it to fall back from. It redirects to Regentry, the real
 * surface, so the URL keeps working and lands on data that exists.
 */
export default function Page() {
  redirect("/regulatory")
}
