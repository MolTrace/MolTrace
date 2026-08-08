/**
 * Reading the compound registry's owner-scoped refusals.
 *
 * The registry used to be readable by every signed-in user and only its writes
 * were gated. It is now owner-scoped by default (`COMPOUND_REGISTRY_VISIBILITY`
 * on the deployment), which changes what a 404 means on every compound route
 * and on every child record — structures, aliases, batches, aliquots,
 * relationships, evidence links, and the knowledge graph.
 *
 * A 404 no longer means "this compound does not exist". It means *either* that
 * *or* that it belongs to another account, and the backend deliberately will not
 * say which: compound ids are sequential, so a 403 there would confirm a
 * compound exists at an id the caller cannot read. The UI has to preserve that
 * indistinguishability — which means never phrasing a 404 as a factual claim
 * about existence.
 *
 * The two refusals are told apart by status code only. The `/api/backend` proxy
 * sanitises every 401/403 body, so a 403's `detail` may not survive the trip and
 * cannot be matched on.
 */

import { ApiError } from "@/lib/api/client"

/**
 * True when a registry request was refused in a way that says nothing about
 * whether the record exists.
 *
 * In `shared` deployments a write refusal arrives as 403 instead, because the
 * row is readable anyway and 403 is the more useful answer — that case is
 * deliberately excluded here and left to the ordinary permission copy.
 */
export function isCompoundOutOfScope(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

/** Heading for the neutral unavailable state. Never asserts non-existence. */
export const COMPOUND_UNAVAILABLE_TITLE = "Compound not available"

/**
 * Body copy for the neutral unavailable state.
 *
 * Names both possibilities without resolving them. A reader who knows a
 * colleague registered the compound would otherwise read the empty page as a
 * broken product rather than as a visibility boundary.
 */
export const COMPOUND_UNAVAILABLE_DESCRIPTION =
  "This compound isn't available in your registry. It may not exist, or it may have been registered by " +
  "another account — the registry doesn't distinguish the two. If your lab works from one shared registry, " +
  "an administrator can turn on shared visibility."

/** The same boundary, phrased for a failed write rather than a failed read. */
export const COMPOUND_UNAVAILABLE_WRITE_MESSAGE =
  "This compound isn't available in your registry, so nothing can be attached to it."

/**
 * The boundary as it reaches a batch or aliquot.
 *
 * Batches and aliquots hang off a compound and inherit its scope, so they carry
 * the same 404 — and the same obligation not to phrase it as a claim about
 * whether the record exists.
 */
export const BATCH_UNAVAILABLE_MESSAGE = "This batch isn't available in your registry."
