import { isStepUpRequired } from "@/lib/auth/mfa"

/**
 * Run a privileged request; if the backend answers `401 step_up_required`, run the
 * step-up ceremony and retry once. Use at gated call sites (e-signature create,
 * admin mutations, MFA management). Prefer also calling `ensureStepUp()`
 * proactively before opening a signing/admin modal so the user isn't bounced.
 *
 *   const ensure = useStepUp().ensureStepUp
 *   await withStepUp(() => apiFetch("/esignatures/records", { method: "POST", body }), ensure)
 */
export async function withStepUp<T>(call: () => Promise<T>, ensureStepUp: () => Promise<boolean>): Promise<T> {
  try {
    return await call()
  } catch (err) {
    if (!isStepUpRequired(err)) throw err
    const stepped = await ensureStepUp()
    if (!stepped) throw err // user cancelled — surface the original 401
    return call() // retry once with the now-elevated session
  }
}
