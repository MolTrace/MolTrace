'use strict'
// §8.2. "Version 1.0 required protected storage and never said what protects
// what." This pins the hierarchy so a later change cannot quietly move a key
// into a weaker class, and pins the honesty requirement that goes with it:
// "state per platform where it cannot be [bound to the signed application]".
const assert = require('node:assert')
const kh = require('../src/key-hierarchy.js')

const results = []
const check = (n, f) => { try { f(); results.push(['PASS', n]) } catch (e) { results.push(['FAIL', n + ' — ' + e.message]) } }

check('every key in §8.2 is declared, and no others', () => {
  assert.deepStrictEqual(Object.keys(kh.KEYS).sort(), [
    'accessTokens', 'dataEncryptionKey', 'deviceIdentityKey',
    'keyEncryptionKey', 'localServiceCredential', 'verificationKeys',
  ])
})

check('every key declares where it lives and how it rotates', () => {
  for (const [name, k] of Object.entries(kh.KEYS)) {
    assert.ok(k.storage, `${name} has no storage class`)
    assert.ok(kh.STORAGE_CLASSES.includes(k.storage), `${name} has an unreviewed storage class: ${k.storage}`)
    assert.ok(k.rotation && k.rotation.length > 10, `${name} has no rotation rule`)
  }
})

check('NO key is reachable from the renderer', () => {
  // §8.2 says tokens live in the OS key store, "never the WebView". That is true
  // of every entry here, not just tokens — a renderer that can read any of them
  // can act as the device.
  for (const [name, k] of Object.entries(kh.KEYS)) {
    assert.strictEqual(k.renderer, false, `${name} is marked reachable from the renderer`)
  }
})

check('the data-encryption key is WRAPPED, never stored directly', () => {
  assert.strictEqual(kh.KEYS.dataEncryptionKey.storage, 'wrapped-by-kek')
  assert.notStrictEqual(kh.KEYS.dataEncryptionKey.storage, 'os-key-store')
})

check('verification keys are PUBLIC and pinned — a private one is rejected', () => {
  assert.strictEqual(kh.KEYS.verificationKeys.storage, 'pinned-public')
  assert.throws(() => kh.assertPublicOnly('-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----'),
    /private key/i, 'private key material was accepted as a verification key')
  assert.doesNotThrow(() => kh.assertPublicOnly('ed25519:' + 'a'.repeat(64)))
})

check('the local service credential is memory-only, matching what was built', () => {
  assert.strictEqual(kh.KEYS.localServiceCredential.storage, 'process-memory')
})

// --- the honesty half -------------------------------------------------------

check('basic_text is NOT treated as an OS-backed store', () => {
  // MEASURED: on Linux, isEncryptionAvailable() returns TRUE while the backend is
  // 'basic_text', which uses an in-memory password rather than a secret store.
  // A check that trusts isEncryptionAvailable() alone is right about what it
  // measures and wrong about what it implies.
  const a = kh.assessStore({ available: true, backend: 'basic_text', platform: 'linux' })
  assert.strictEqual(a.osBacked, false, 'basic_text was accepted as an OS-backed store')
  assert.ok(a.limitation, 'no limitation stated for basic_text')
})

check('a real secret store IS os-backed', () => {
  for (const b of ['gnome_libsecret', 'kwallet', 'kwallet5', 'kwallet6']) {
    assert.strictEqual(kh.assessStore({ available: true, backend: b, platform: 'linux' }).osBacked, true, b)
  }
})

check('an UNKNOWN backend fails closed', () => {
  const a = kh.assessStore({ available: true, backend: 'unknown', platform: 'linux' })
  assert.strictEqual(a.osBacked, false, 'an unknown backend was assumed safe')
})

check('unavailable encryption is never reported as protected', () => {
  const a = kh.assessStore({ available: false, backend: 'gnome_libsecret', platform: 'linux' })
  assert.strictEqual(a.osBacked, false)
  assert.strictEqual(a.usable, false)
})

check('every platform states a binding limit rather than implying protection', () => {
  // §8.2: "On a store that binds only to the operating-system user, any same-user
  // process can retrieve the key-encryption key, and §15 records that as the
  // residual limit rather than implying otherwise."
  //
  // Asserts the PROPERTY — that a limit is stated and it is the same one on every
  // platform, because none of the three binds to the signed application. It does
  // NOT assert wording. An earlier version required the literal phrase
  // "same-user" and failed on copy that states the exposure in plainer words,
  // which put it in direct conflict with the no-jargon test below. A test that
  // pins prose forces jargon into user-visible strings.
  for (const platform of ['darwin', 'win32', 'linux']) {
    const a = kh.assessStore({ available: true, backend: platform === 'linux' ? 'gnome_libsecret' : 'n/a', platform })
    assert.strictEqual(a.limitation, kh.SAME_USER_LIMIT, `${platform} states no residual limit, or a different one`)
  }
})

check('the stated limit actually describes the same-user exposure', () => {
  // Checked once, on the constant, rather than per-platform on the output. The
  // property is about the SENTENCE, so this is where it belongs.
  const t = kh.SAME_USER_LIMIT.toLowerCase()
  assert.ok(t.includes('user'), 'the limit does not mention the user boundary')
  assert.ok(/read|retrieve|access/.test(t), 'the limit does not say the keys can be read')
  assert.ok(/other software|another program|any program|running as you/.test(t),
    'the limit does not say OTHER SOFTWARE running as you can read them — which is the whole exposure')
})

check('the limitation is user-readable, not jargon', () => {
  const a = kh.assessStore({ available: true, backend: 'basic_text', platform: 'linux' })
  assert.ok(!/[0-9]{3}\b|HTTP|_json|isEncryptionAvailable|getSelectedStorageBackend/.test(a.limitation),
    `limitation leaks API names: ${a.limitation}`)
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nKEY HIERARCHY FAILED (${failed})` : `\nKEY HIERARCHY OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
