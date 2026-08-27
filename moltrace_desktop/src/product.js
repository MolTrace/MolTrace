'use strict'
// Product configuration, on the VS Code `product.json` pattern.
//
// WHY THE DEFAULT IS INERT RATHER THAN GITIGNORED:
// A gitignored secrets file fails OPEN the first time someone forgets the ignore
// line or copies a working tree. An inert checked-in default fails CLOSED by
// construction — there is no endpoint to reach, so a build from public source
// cannot phone home even by accident. Verified as the shipping pattern: VS Code's
// public product.json carries no extensionsGallery, no telemetry key and no
// update URL, and a build from the public repo therefore reaches none of them.
const baked = require('./product.json')

// DEV/TEST OVERLAY — and the constraint on it is the security property.
//
// A shipping build carries its real configuration BAKED into product.json at
// package time (the VS Code pattern: the private file replaces the inert one).
// Development and CI need a way to supply one without editing a tracked file, so
// an overlay path is honoured — but ONLY when the baked config is unconfigured.
//
// That condition is what makes it safe. A shipped, configured build IGNORES the
// overlay entirely, so the variable cannot be used to point a real installation
// at an attacker's workspace or root key. Without that check this would be a
// redirection primitive on every customer machine.
function loadRaw() {
  const bakedConfigured = ['workspaceUrl', 'entitlementRootPublicKey', 'entitlementRootKeyId']
    .every((k) => baked[k])
  if (bakedConfigured) return baked
  const overlayPath = process.env.MOLTRACE_PRODUCT_CONFIG
  if (!overlayPath) return baked
  try {
    return { ...baked, ...require('node:fs').existsSync(overlayPath)
      ? JSON.parse(require('node:fs').readFileSync(overlayPath, 'utf8'))
      : {} }
  } catch {
    return baked
  }
}

const raw = loadRaw()

// Exactly these keys. An unexpected key is a defect, not a feature — it is how a
// secret gets added to a file people have stopped reading.
const ALLOWED_KEYS = [
  '_comment',
  'productName',
  'workspaceUrl',
  'updateFeedUrl',
  'telemetryDsn',
  'entitlementRootPublicKey',
  'entitlementRootKeyId',
  // PREVIEW BUILDS ONLY. See previewWorld() -- it is ignored outright unless the
  // BAKED config is unconfigured, so a shipped installation cannot be unlocked
  // with it even if someone bakes it in.
  'previewModules',
]

// The name a build presents to a user. BUSL 1.1 already withholds trademark
// rights ("This License does not grant you any right in any trademark or logo of
// Licensor"), so the licence side is covered — but a licence clause does not stop
// a rebuilt binary from *looking* official to the person running it. The
// protection that works is the same one VS Code uses: the public default carries
// a visibly unofficial name, and the brand arrives only with the private overlay.
const OFFICIAL_PRODUCT_NAME = 'MolTrace'

// Keys without which the product cannot honestly operate. `telemetryDsn` is
// deliberately NOT required — a build with no telemetry is a legitimate build.
const REQUIRED_FOR_LAUNCH = ['workspaceUrl', 'entitlementRootPublicKey', 'entitlementRootKeyId']

function validate(cfg = raw) {
  const problems = []
  for (const k of Object.keys(cfg)) {
    if (!ALLOWED_KEYS.includes(k)) problems.push(`unreviewed product-config key: ${k}`)
  }
  // A private key in a client is never correct — the client verifies, never mints.
  for (const [k, v] of Object.entries(cfg)) {
    if (typeof v === 'string' && /PRIVATE KEY|BEGIN [A-Z ]*PRIVATE/.test(v)) {
      problems.push(`product config carries private key material in ${k}`)
    }
  }
  // An unconfigured build must not claim the brand.
  const configuredNow = REQUIRED_FOR_LAUNCH.every((k) => cfg[k])
  if (!configuredNow && cfg.productName === OFFICIAL_PRODUCT_NAME) {
    problems.push('an unconfigured build carries the official product name — it would present itself as MolTrace')
  }

  const missing = REQUIRED_FOR_LAUNCH.filter((k) => !cfg[k])
  return { problems, missing, configured: missing.length === 0 }
}

/**
 * The capability inputs a PREVIEW build may use, or null.
 *
 * A prototype handed to evaluators has to be able to do something, and the real
 * inputs come from a signed entitlement statement this build has no way to
 * obtain. So a preview build may declare which products it is standing in for.
 *
 * THE CONDITION IS THE WHOLE SECURITY PROPERTY, and it is the same one the
 * config overlay already rests on: this is honoured only when the BAKED config
 * is unconfigured. A shipped installation always carries a baked configuration,
 * so it can never take this path -- not through the environment, and not by
 * someone baking `previewModules` into the packaged file, because the test is on
 * the baked config's completeness rather than on where the key came from.
 *
 * It does NOT fabricate an entitlement statement. There is no statement here and
 * the app says so: `preview: true` travels with every verdict this produces, and
 * the window states that entitlement was not verified. Minting one would be the
 * one thing this client must never do.
 */
function previewWorld(cfg = raw) {
  const bakedConfigured = REQUIRED_FOR_LAUNCH.every((k) => baked[k])
  if (bakedConfigured) return null
  const modules = Array.isArray(cfg.previewModules) ? cfg.previewModules.filter((m) => typeof m === 'string') : []
  if (!modules.length) return null
  return {
    preview: true,
    modules,
    // No reference data is installed in a preview build. An empty inventory is a
    // true statement, and it keeps every pack-gated capability locked -- so the
    // gate is still visibly doing its job rather than being switched off.
    packs: [],
    entitlement: null,
    role: null,
  }
}

// §7.1: a refusal names its cause, in words a person reads — no endpoint paths,
// no env-var names, no status codes.
function unconfiguredMessage(missing) {
  return (
    'This copy of MolTrace has not been set up for a workspace yet, so it cannot ' +
    'start. It is missing: ' + missing.join(', ') + '. ' +
    'A prepared installation from MolTrace carries these settings.'
  )
}

module.exports = { raw, baked, loadRaw, previewWorld, OFFICIAL_PRODUCT_NAME, ALLOWED_KEYS, REQUIRED_FOR_LAUNCH, validate, unconfiguredMessage }
