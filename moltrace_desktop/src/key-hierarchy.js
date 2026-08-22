'use strict'
// §8.2 — the key hierarchy, declared.
//
// "Version 1.0 required protected storage and never said what protects what."
// This module is that answer, in one place, so a later change that moves a key
// into a weaker class is a visible diff against a test rather than a quiet edit.
//
// Nothing here holds key MATERIAL. It declares where each class of key lives,
// how it rotates, and — the part that is easy to skip — what protection the
// platform actually provides, stated rather than implied.

const STORAGE_CLASSES = [
  'os-key-store',    // the platform secret store
  'wrapped-by-kek',  // encrypted at rest by the key-encryption key, never stored raw
  'process-memory',  // exists only for the life of the process
  'pinned-public',   // a public key compiled into the build; no secret at all
]

const KEYS = {
  dataEncryptionKey: {
    purpose: 'Encrypts the local database and derived artifacts.',
    storage: 'wrapped-by-kek',
    renderer: false,
    rotation: 'Rotated by re-wrapping. A lost wrapper means the local data is unrecoverable, and the interface must say so before anyone relies on local-only custody.',
  },
  keyEncryptionKey: {
    purpose: 'Wraps the data-encryption key.',
    storage: 'os-key-store',
    renderer: false,
    rotation: 'Re-wrapped on a credential change. Not exportable.',
  },
  deviceIdentityKey: {
    purpose: 'Signs journal envelopes, sync submissions and the qualification report.',
    storage: 'os-key-store',
    renderer: false,
    rotation: 'Rotated on re-enrolment. Revocation is server-side — a device cannot revoke itself.',
  },
  accessTokens: {
    purpose: 'Authenticate to the cloud.',
    storage: 'os-key-store',
    renderer: false,
    rotation: 'Rotating and single-use; reuse revokes the family.',
  },
  localServiceCredential: {
    purpose: 'Authenticates the host to the local science service.',
    storage: 'process-memory',
    renderer: false,
    rotation: 'Regenerated every launch, passed over an inherited handle, never written to disk.',
  },
  verificationKeys: {
    purpose: 'Verify signed updates, packs and releases.',
    storage: 'pinned-public',
    renderer: false,
    rotation: 'Rotated by release, with an overlap window so an in-flight artifact stays verifiable.',
  },
}

/** A verification key is public by definition. Private material here is a defect. */
function assertPublicOnly(material) {
  if (typeof material === 'string' && /PRIVATE KEY|BEGIN [A-Z ]*PRIVATE/.test(material)) {
    throw new Error('private key material supplied where a public verification key is required')
  }
  return material
}

// Linux backends that are real secret stores. Anything else — including
// 'basic_text' and 'unknown' — is not, and must not be reported as one.
//
// MEASURED on Electron 43.4.1: `isEncryptionAvailable()` returns TRUE while the
// selected backend is 'basic_text', which uses an in-memory password rather than
// a secret store. So availability is not protection, and a check that trusts
// availability alone is right about what it measures and wrong about what it
// implies. This is the single most likely way this module would ship a lie.
const REAL_LINUX_BACKENDS = ['gnome_libsecret', 'kwallet', 'kwallet5', 'kwallet6']

// §8.2: "Bind the key-store entry to the signed application by access-control
// list where the platform supports it, and state per platform where it cannot
// be." None of the three binds to the signed application today, so all three
// state the same residual limit rather than any of them implying otherwise.
const SAME_USER_LIMIT =
  'Anything running as your operating-system user on this computer can read these stored keys. ' +
  'They are protected from other people who use this computer, not from other software running as you.'

const NO_STORE_LIMIT =
  'This computer has no usable secret store, so keys cannot be protected at rest here. ' +
  'Local encrypted custody is unavailable on this installation.'

const WEAK_STORE_LIMIT =
  'This computer reported a secret store, but the one in use keeps its password in memory rather than ' +
  'in a system keyring, so keys are not meaningfully protected at rest. ' +
  'Local encrypted custody is unavailable on this installation.'

function assessStore({ available, backend, platform }) {
  if (!available) {
    return { usable: false, osBacked: false, backend, limitation: NO_STORE_LIMIT }
  }
  if (platform === 'linux') {
    const real = REAL_LINUX_BACKENDS.includes(backend)
    // 'unknown' and anything unrecognised fail CLOSED: an unnamed backend is not
    // evidence of a good one.
    if (!real) {
      return { usable: false, osBacked: false, backend, limitation: WEAK_STORE_LIMIT }
    }
    return { usable: true, osBacked: true, backend, limitation: SAME_USER_LIMIT }
  }
  // macOS Keychain and Windows DPAPI. Both bind to the OS user, neither binds to
  // the signed application, so the same limit holds and is stated.
  return { usable: true, osBacked: true, backend, limitation: SAME_USER_LIMIT }
}

module.exports = {
  KEYS, STORAGE_CLASSES, assertPublicOnly, assessStore, REAL_LINUX_BACKENDS,
  SAME_USER_LIMIT, NO_STORE_LIMIT, WEAK_STORE_LIMIT,
}
