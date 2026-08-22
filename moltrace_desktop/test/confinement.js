'use strict'
// §8.3 renderer confinement — the assertions, separated from the runner so a
// weakening probe can import and run them against a deliberately-broken main.
//
// WHY THIS IS BEHAVIOURAL AND NOT A SETTINGS READ-BACK:
// Electron 43.4.1 exposes no API returning WebPreferences from a live WebContents
// (no getWebPreferences, no getLastWebPreferences — every `webPreferences?:` in
// electron.d.ts is an INPUT option field). So the only honest measurement is what
// the renderer can actually reach. That is also the stronger test: `sandbox` is
// automatically disabled when nodeIntegration is true, so a declared value can be
// true while the effective value is false.

const PROBE = `(() => {
  const has = (k) => typeof globalThis[k] !== 'undefined'
  return {
    // nodeIntegration / sandbox reach. Any one of these being reachable in a
    // renderer means the renderer holds local authority.
    hasRequire: has('require'),
    hasProcess: has('process'),
    hasModule: has('module'),
    hasGlobal: has('global'),
    hasBuffer: has('Buffer'),
    // contextIsolation canary: the preload writes this onto its OWN isolated
    // global. If the renderer can see it, the worlds are not isolated.
    seesPreloadIsolatedMarker: has('__moltrace_preload_isolated_world_marker__'),
    // The bridge is the ONE sanctioned surface (spec §5.1).
    bridgeKeys: (globalThis.moltrace && typeof globalThis.moltrace === 'object')
      ? Object.keys(globalThis.moltrace).sort()
      : null,
  }
})()`

// The contextBridge allowlist. §7.1: "least-privilege capabilities per window,
// enumerated in one reviewable allowlist." Growing this list is a security review.
const ALLOWED_BRIDGE_KEYS = ['capabilities']

// The preload's self-report (§ main.js IPC). A main-world probe is structurally
// blind to nodeIntegration and sandbox while contextIsolation holds — MEASURED,
// not assumed: flipping either left a main-world-only test green. So these two
// are asserted from the preload environment instead.
// LAYER 2 — the DECLARED settings, and why a behavioural test is not enough.
//
// MEASURED 2026-08-22 on Electron 43.4.1: with `sandbox: true` set EXPLICITLY,
// flipping `nodeIntegration` to true does NOT disable the sandbox —
// process.sandboxed stayed true and node:fs stayed unreachable. So the
// documented auto-disable applies only when sandbox is left at its default.
// Good news for security (an explicit sandbox dominates), but it means
// `nodeIntegration: true` is invisible to any behavioural probe while sandbox
// holds. It is still an intent regression, and it becomes an EFFECTIVE one the
// moment someone later drops the explicit sandbox. So it is asserted here.
//
// This layer also covers `nodeIntegrationInSubFrames`, which no behavioural
// probe can see unless the fixture happens to contain a sub-frame.
const REQUIRED_DECLARED = Object.freeze({
  contextIsolation: true,
  nodeIntegration: false,
  sandbox: true,
  nodeIntegrationInSubFrames: false,
  webviewTag: false,
})

function assertDeclaredConfinement(declared) {
  const problems = []
  for (const [k, want] of Object.entries(REQUIRED_DECLARED)) {
    if (declared[k] !== want) {
      problems.push(`declared ${k} is ${declared[k]}, must be ${want}`)
    }
  }
  for (const k of Object.keys(declared)) {
    if (!(k in REQUIRED_DECLARED)) {
      problems.push(`unreviewed webPreference in the factory: ${k}`)
    }
  }
  return problems.map((p) => `[window-factory] ${p}`)
}

function assertPreloadConfined(url, report) {
  const problems = []
  if (!report) {
    problems.push('no preload confinement self-report — preload did not run, or IPC is blocked')
    return problems.map((p) => `[${url}] ${p}`)
  }
  if (report.fs || report.childProcess) {
    const got = [report.fs && 'node:fs', report.childProcess && 'node:child_process'].filter(Boolean)
    problems.push(`preload has full Node reach (${got.join(', ')}) — sandbox regressed to false`)
  }
  if (report.processSandboxed !== true) {
    problems.push(`process.sandboxed is ${report.processSandboxed} — expected true; sandbox or nodeIntegration regressed`)
  }
  return problems.map((p) => `[${url}] ${p}`)
}

function assertRendererConfined(url, probe) {
  const problems = []
  const reachable = ['hasRequire', 'hasProcess', 'hasModule', 'hasGlobal', 'hasBuffer']
    .filter((k) => probe[k])
  if (reachable.length) {
    problems.push(`renderer reaches Node (${reachable.join(', ')}) — nodeIntegration/sandbox regressed`)
  }
  if (probe.seesPreloadIsolatedMarker) {
    problems.push('renderer sees the preload isolated-world marker — contextIsolation regressed')
  }
  if (probe.bridgeKeys === null) {
    problems.push('no contextBridge surface found — preload did not run')
  } else {
    const extra = probe.bridgeKeys.filter((k) => !ALLOWED_BRIDGE_KEYS.includes(k))
    const missing = ALLOWED_BRIDGE_KEYS.filter((k) => !probe.bridgeKeys.includes(k))
    if (extra.length) problems.push(`contextBridge surface grew: ${extra.join(', ')}`)
    if (missing.length) problems.push(`contextBridge surface missing: ${missing.join(', ')}`)
  }
  return problems.map((p) => `[${url}] ${p}`)
}

module.exports = { PROBE, ALLOWED_BRIDGE_KEYS, REQUIRED_DECLARED, assertRendererConfined, assertPreloadConfined, assertDeclaredConfinement }
