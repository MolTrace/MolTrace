# MolTrace Desktop

The Electron shell. Source-available under BUSL 1.1, like the rest of this repository —
production use requires a commercial licence.

## Why the source is here

Shipping an Electron application publishes its client. Packing this shell into an `app.asar` and
extracting it back takes two commands, no key and no password; Electron's own documentation says
ASAR "conceal[s] your source code from cursory inspection", and its integrity feature validates
**tampering, not reading**. The packaged scientific runtime is more readable still. So keeping this
directory private would have cost CI, commit-SHA pinning and divergence protection to buy
confidentiality the installer gives away anyway.

What protects the product is the licence, the backend, and the signature — not secrecy.

## What is NOT here, and never will be

`src/product.json` is checked in and **inert**: every operational value is `null`. A build from this
repository cannot reach a workspace, an update feed or a licensing authority, and **refuses to
start**, naming what it is missing. The real configuration is a private overlay laid down at package
time — the pattern VS Code uses for its own `product.json`.

Also absent by design: signing identities and notarization credentials, the entitlement **root
private key** (offline, air-gapped, never on a build runner), any deployment issuing key, and any
backend credential. The client **verifies** entitlement statements against a pinned public key; it
never mints one.

## Running it

```bash
npm install
npm test                 # product-config assertions + the renderer confinement test
npm start                # refuses to start unconfigured, and says why
```

## The confinement test

`test/confinement-runner.js` asserts §8.3 of the desktop specification in three layers, because no
one of them is sufficient:

1. **Behavioural** — evaluates inside every live renderer, plus a preload self-report over IPC.
   Electron exposes no API to read a live renderer's effective `webPreferences`, so the settings
   cannot be read back; measuring what the renderer can actually reach is the stronger test anyway.
2. **Declared** — the frozen settings in the single window factory. `nodeIntegration` and
   `nodeIntegrationInSubFrames` are invisible to a behavioural probe while `sandbox` holds, and are
   still intent regressions.
3. **Single construction site** — layers 1 and 2 are both blind to a window that was never created
   during the test run.

Every guard has been proven red by deliberate weakening rather than asserted. If you change a
`webPreference`, the declared layer will reject it until you add it to the reviewed list — that is
the point.
