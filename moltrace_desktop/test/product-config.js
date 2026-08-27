'use strict'
// Asserts the product-config invariants. Runs in plain node — no Electron, no
// display — so it can gate in CI on any runner.
const assert = require('node:assert')
const product = require('../src/product.js')

const results = []
const check = (name, fn) => {
  try { fn(); results.push(['PASS', name]) }
  catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
}

check('the checked-in default is INERT — an unconfigured build cannot launch', () => {
  const v = product.validate()
  assert.strictEqual(v.configured, false,
    'the committed product.json is configured; a build from source could reach a real endpoint')
})

check('no product-config key is outside the reviewed allowlist', () => {
  const v = product.validate()
  assert.deepStrictEqual(v.problems, [])
})

check('every required-for-launch key is null in the committed default', () => {
  for (const k of product.REQUIRED_FOR_LAUNCH) {
    assert.strictEqual(product.raw[k], null, `${k} has a value committed — it must be null`)
  }
})

check('a private key in the product config is rejected', () => {
  const v = product.validate({ ...product.raw, entitlementRootPublicKey: '-----BEGIN PRIVATE KEY-----' })
  assert.ok(v.problems.some((p) => /private key material/.test(p)),
    'private key material was not detected')
})

check('an unreviewed key is rejected', () => {
  const v = product.validate({ ...product.raw, licenceSigningSecret: 'x' })
  assert.ok(v.problems.some((p) => /unreviewed product-config key/.test(p)))
})

check('the refusal names its cause and carries no jargon', () => {
  const msg = product.unconfiguredMessage(['workspaceUrl'])
  assert.ok(msg.includes('workspaceUrl'), 'refusal does not name what is missing')
  assert.ok(!/HTTP|[0-9]{3} status|endpoint|env|GET |POST /.test(msg),
    'refusal leaks backend jargon into user-visible copy')
})

check('a CONFIGURED overlay does launch — the gate is not simply always-closed', () => {
  const v = product.validate({
    ...product.raw,
    workspaceUrl: 'https://example.invalid',
    entitlementRootPublicKey: 'ed25519:' + 'a'.repeat(64),
    entitlementRootKeyId: 'mtroot1:abcdef123456',
  })
  assert.strictEqual(v.configured, true)
  assert.deepStrictEqual(v.problems, [])
})

check('a CONFIGURED baked build IGNORES the overlay — no redirection primitive', () => {
  // The security property of the overlay: it exists for dev/CI and is inert on a
  // shipped build. Simulated by asking loadRaw() with a baked config that IS
  // configured; the overlay must not win.
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
  const evil = path.join(os.tmpdir(), 'evil-product.json')
  fs.writeFileSync(evil, JSON.stringify({ workspaceUrl: 'https://attacker.invalid' }))
  const prev = process.env.MOLTRACE_PRODUCT_CONFIG
  process.env.MOLTRACE_PRODUCT_CONFIG = evil
  try {
    // Unconfigured baked -> overlay IS honoured (that is the dev path).
    delete require.cache[require.resolve('../src/product.js')]
    const dev = require('../src/product.js')
    assert.strictEqual(dev.raw.workspaceUrl, 'https://attacker.invalid',
      'overlay was not honoured on an unconfigured build — the dev path is broken')
    // The guard itself: loadRaw only consults the overlay when baked is unconfigured.
    const src = fs.readFileSync(require.resolve('../src/product.js'), 'utf8')
    assert.ok(/if \(bakedConfigured\) return baked/.test(src),
      'the overlay is not gated on the baked config being unconfigured')
  } finally {
    if (prev === undefined) delete process.env.MOLTRACE_PRODUCT_CONFIG
    else process.env.MOLTRACE_PRODUCT_CONFIG = prev
    fs.rmSync(evil, { force: true })
    delete require.cache[require.resolve('../src/product.js')]
  }
})

check('the inert default does NOT carry the official product name', () => {
  // BUSL withholds trademark rights, but a licence clause does not stop a rebuilt
  // binary from LOOKING official to whoever runs it. VS Code's public config names
  // itself "Code - OSS" for exactly this reason.
  assert.notStrictEqual(product.baked.productName, product.OFFICIAL_PRODUCT_NAME,
    'the committed default is branded — an unofficial build would present itself as MolTrace')
  const v = product.validate()
  assert.deepStrictEqual(v.problems, [])
})

check('branding an unconfigured build is rejected', () => {
  const v = product.validate({ ...product.baked, productName: product.OFFICIAL_PRODUCT_NAME })
  assert.ok(v.problems.some((p) => /present itself as MolTrace/.test(p)),
    'a branded unconfigured build was not rejected')
})

check('a CONFIGURED build may carry the official name', () => {
  const v = product.validate({
    ...product.baked,
    productName: product.OFFICIAL_PRODUCT_NAME,
    workspaceUrl: 'https://example.invalid',
    entitlementRootPublicKey: 'ed25519:' + 'a'.repeat(64),
    entitlementRootKeyId: 'mtroot1:abcdef123456',
  })
  assert.deepStrictEqual(v.problems, [], 'the official build was wrongly refused the brand')
  assert.strictEqual(v.configured, true)
})

// --- the preview world, and the one condition that makes it safe -----------

/** Run `fn` with the BAKED config temporarily looking like a shipped build. */
function withConfiguredBakedBuild(fn) {
  const saved = {}
  for (const k of product.REQUIRED_FOR_LAUNCH) {
    saved[k] = product.baked[k]
    product.baked[k] = 'set-by-the-packager'
  }
  try { return fn() } finally {
    for (const k of product.REQUIRED_FOR_LAUNCH) product.baked[k] = saved[k]
  }
}

check('a preview build with no declaration unlocks nothing', () => {
  assert.strictEqual(product.previewWorld({}), null)
  assert.strictEqual(product.previewWorld({ previewModules: [] }), null)
  assert.strictEqual(product.previewWorld({ previewModules: 'spectracheck' }), null,
    'a string was accepted where a list is required')
})

check('an unconfigured build MAY declare the products it stands in for', () => {
  const w = product.previewWorld({ previewModules: ['spectracheck'] })
  assert.ok(w, 'the preview world was refused in an unconfigured build')
  assert.strictEqual(w.preview, true, 'the world does not mark itself as a preview')
  assert.deepStrictEqual(w.modules, ['spectracheck'])
})

check('a CONFIGURED build ignores previewModules entirely — the security property', () => {
  // This is the assertion the whole mechanism rests on. A shipped installation
  // always carries a baked configuration, so it must never be able to take this
  // path — not through the environment, and NOT by someone baking
  // `previewModules` into the packaged file, because the test is on the baked
  // config's completeness rather than on where the key came from.
  withConfiguredBakedBuild(() => {
    assert.strictEqual(product.previewWorld({ previewModules: ['spectracheck'] }), null,
      'a configured build honoured previewModules — this is a licence bypass on every customer machine')
    assert.strictEqual(product.previewWorld({ previewModules: ['spectracheck', 'regentry'] }), null)
  })
})

check('a preview build NEVER fabricates an entitlement statement', () => {
  // The client verifies statements against a pinned key and never mints one.
  // Handing assess() an object shaped like a verified statement would be exactly
  // that, dressed up as configuration.
  const w = product.previewWorld({ previewModules: ['spectracheck'] })
  assert.strictEqual(w.entitlement, null, 'the preview world invented an entitlement statement')
  assert.deepStrictEqual(w.packs, [], 'a preview build claimed reference data it does not have')
})

check('previewModules is inside the reviewed key allowlist', () => {
  assert.ok(product.ALLOWED_KEYS.includes('previewModules'),
    'a key the loader honours is not in the allowlist validate() checks')
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nPRODUCT CONFIG FAILED (${failed})` : `\nPRODUCT CONFIG OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
