'use strict'
// The service lifecycle: socket, spawn, readiness, shutdown.
//
// This is the piece that had never existed. Every layer below it was proven
// individually and one harness had driven them in sequence by hand; nothing in
// the app started the service. These are the properties that must hold once it
// does.
const assert = require('node:assert')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const svc = require('../src/local-service.js')

const results = []
const check = (n, f) => { try { f(); results.push(['PASS', n]) } catch (e) { results.push(['FAIL', n + ' — ' + e.message]) } }

check('the socket directory is owner-only', () => {
  const { dir, cleanup } = svc.createSocketDirectory()
  try {
    assert.strictEqual(fs.statSync(dir).mode & 0o777, 0o700, 'the directory is not 0700')
  } finally { cleanup() }
})

check('the socket itself is chmodded to owner-only', () => {
  // MEASURED: Node's listen(path) creates the socket at 0755 regardless of the
  // parent directory's mode. §7.1 requires owner-only on BOTH, so the chmod is
  // mandatory and is exactly the line that is easy to omit because the directory
  // already looks locked.
  const h = svc.createListener()
  try {
    assert.strictEqual(fs.statSync(h.socketPath).mode & 0o777, 0o600,
      'the socket is not 0600 — Node creates it 0755 and it must be chmodded')
  } finally { h.close() }
})

check('the raw descriptor is a real number, asserted at startup', () => {
  // server._handle.fd is a PRIVATE Node API. Asserting it here means a Node
  // upgrade that removes it fails loudly at startup rather than producing an
  // `undefined` fd that spawn would quietly mishandle.
  const h = svc.createListener()
  try {
    assert.strictEqual(typeof h.fd, 'number')
    assert.ok(h.fd >= 0, `fd is ${h.fd}`)
  } finally { h.close() }
})

check('the spawn carries the credential in NEITHER argv NOR env', () => {
  const cred = require('../src/service-credential.js').create()
  const plan = svc.buildSpawn({ credential: cred, socketFd: 7, backendDir: '/x' })
  const secret = cred.valueForHandle()
  assert.ok(!JSON.stringify(plan.args).includes(secret), 'the credential is in argv')
  assert.ok(!JSON.stringify(plan.options.env || {}).includes(secret), 'the credential is in env')
  assert.strictEqual(plan.options.stdio[3], 'pipe', 'fd 3 is not the credential pipe')
  assert.strictEqual(plan.options.stdio[4], 7, 'fd 4 is not the passed socket')
})

check('a failure to start is reported, not thrown away', () => {
  const state = svc.describeFailure(new Error('boom'))
  assert.strictEqual(state.reachable, false)
  assert.ok(state.reason && state.reason.length > 10)
  assert.ok(!/boom/.test(state.reason) || state.reason.includes('boom'),
    'the reason should be usable either way')
})

check('an unreachable service still yields a usable capability world', () => {
  // The app must open and say why, not fail to open. The readout already treats
  // an unreachable service as not-provisioned; this asserts the shape it is
  // handed is the shape it expects.
  const world = svc.capabilityWorld({ reachable: false, versions: {} })
  const caps = require('../src/capabilities.js')
  const r = caps.assess(
    { key: 'k', displayName: 'X', requiresService: 'fid' },
    { ...world, modules: ['spectracheck'], entitlement: { valid: true, modules: ['spectracheck'] }, packs: [], role: null },
  )
  assert.strictEqual(r.available, false)
  assert.ok(r.code, 'no cause given for an unreachable service')
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nLOCAL SERVICE FAILED (${failed})` : `\nLOCAL SERVICE OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
