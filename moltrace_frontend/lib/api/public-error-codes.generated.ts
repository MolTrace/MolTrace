// GENERATED FILE — do not edit.
// Source: moltrace_backend/src/nmrcheck/error_codes.py (PUBLIC_CODES).
// Regenerate: cd moltrace_backend && uv run python -m nmrcheck.error_code_mirrors --write
// Pinned by moltrace_backend/tests/test_error_code_mirrors.py.

/** Codes the backend marks safe to survive 401/403 sanitization. */
export const PUBLIC_ERROR_CODES = [
  "credentials_invalid",
  "feature_not_enabled",
  "mfa_enrollment_required",
  "mfa_factor_invalid",
  "mfa_required",
  "module_not_licensed",
  "product_not_enabled",
  "product_not_in_plan",
  "product_not_provisioned",
  "role_required",
  "step_up_required",
  "token_expired",
  "token_invalid",
  "token_reuse_detected",
] as const

export type PublicErrorCode = (typeof PUBLIC_ERROR_CODES)[number]

export const PUBLIC_ERROR_CODE_SET: ReadonlySet<PublicErrorCode> = new Set(
  PUBLIC_ERROR_CODES,
)
