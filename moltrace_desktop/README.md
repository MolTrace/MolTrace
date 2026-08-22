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

## Naming and marks

BUSL 1.1 already withholds trademark rights — *"This License does not grant you any right in any
trademark or logo of Licensor or its affiliates"* — so the licence side needs no addition. But a
licence clause does not stop a rebuilt binary from *looking* official to whoever runs it.

The control that works is the one VS Code uses: the checked-in default carries a **visibly
unofficial name**, and the brand arrives only with the private overlay at package time. VS Code's
public `product.json` names itself `Code - OSS`, not `Visual Studio Code`, for exactly this reason.
Here the inert default is `MolTrace Desktop (unconfigured build)`, and a test rejects any attempt to
put the official name on an unconfigured build.

## Running it

```bash
npm install
npm test                 # product-config assertions + the renderer confinement test
npm start                # refuses to start unconfigured, and says why
```

## The transport credential

`src/service-credential.js` implements §7.1's local-service credential: 256 bits from a CSPRNG,
fresh every launch, passed to the service over an **inherited handle (fd 3)** and closed
immediately — never argv, never an environment variable, never a file. Each exclusion answers a
real exposure: argv is readable by any local process and captured in crash reports; the environment
is inherited by every child and dumped by most diagnostic tooling; a file outlives the launch and
lands in backups and sync clients. A pipe ends when the process does.

It is presented in **one named header** and the module offers **no helper for any other position** —
no query, path, cookie or body affordance exists to reach for under deadline. A URL-borne credential
is the one form a subresource load can carry, which is why that position is closed by construction
rather than by rule.

The value lives in a closure, not a property, so it cannot be reached by a `JSON.stringify` in a log
line or an error report. And it **never crosses the contextBridge** — the confinement test hunts the
bridge surface for credential-shaped keys, because a renderer that can read it can talk to the
service directly and defeat the peer check, the header discipline and the rebinding refusals at
once.

## The capability readout

No server endpoint aggregates this. `GET /system/capabilities` reports only which products a
*deployment* includes — it says nothing about the entitlement, the local pack inventory, or whether
the science service is reachable. So the desktop assembles the answer from those four sources, and
`src/capabilities.js` is the one place that combination happens.

**The invariant is that a capability is never rendered as available and then fails on click.** That
makes the default *deny*: an input that is absent, unreadable or unreachable is not "probably fine",
it is unknown, and unknown is not available. Every gate must affirmatively say yes. The test checks
this exhaustively rather than by example — it drops each input in turn and asserts nothing survives.

Four causes of a locked capability are kept **distinguishable**, because they imply four different
next actions and presenting them as one denial sends a person to the wrong place: the deployment
does not serve the product, it is not switched on here, the local side is not provisioned, or the
account lacks permission. Those four codes are the platform's existing vocabulary and a test rejects
a fifth — the desktop and the web surface must name the same situation identically.

The role check runs **last**, so a permission refusal is never used to mask a provisioning gap an
operator ought to see.

The renderer receives verdicts, never inputs. A page that can see the entitlement or the service
versions can reason about them; availability is decided once, in one place.

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
