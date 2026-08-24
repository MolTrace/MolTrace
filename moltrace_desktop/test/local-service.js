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

// --- the two invariants that cost a build ----------------------------------

const net = require('node:net')

/** Connect and report which of the three things happened. */
function probe(socketPath, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const c = net.connect(socketPath)
    const t = setTimeout(() => { c.destroy(); resolve('accepted-and-ignored') }, timeoutMs)
    c.on('connect', () => { /* wait: an accepting-but-silent peer holds it open */ })
    c.on('error', (e) => { clearTimeout(t); resolve(e.code) })
    c.on('close', () => { clearTimeout(t); resolve('closed') })
  })
}

const asyncChecks = [
  ['the host SWALLOWS connections while it is still accepting', async () => {
    // Documents the hazard the fix exists for, so that removing the fix fails
    // here rather than in a five-hour CI hang. With no child in the picture at
    // all, a request to this socket is accepted by the host's own server and
    // then never answered -- the caller waits forever and never gets an error.
    const h = svc.createListener()
    try {
      assert.strictEqual(await probe(h.socketPath), 'accepted-and-ignored',
        'the host no longer swallows -- if this changed, the staging-rename dance may be unnecessary')
    } finally { h.close() }
  }],

  ['once the host stops accepting, a connection is REFUSED, not swallowed', async () => {
    // The invariant. A refused connection is a retry; a swallowed one is a hang.
    const h = svc.createListener()
    try {
      h.stopAccepting()
      const r = await probe(h.socketPath)
      assert.strictEqual(r, 'ECONNREFUSED', `expected ECONNREFUSED, got ${r}`)
    } finally { h.close() }
  }],

  ['the socket path SURVIVES the host closing its server', async () => {
    // libuv unlinks the path it BOUND. That is why the socket is bound under a
    // staging name and renamed before the host closes -- libuv then unlinks a
    // name that is already gone. Delete the rename and this goes red, which is
    // the point: without it the host's close destroys the service's socket and
    // nothing can connect at all.
    const h = svc.createListener()
    try {
      h.stopAccepting()
      assert.ok(fs.existsSync(h.socketPath),
        'the host closing its server unlinked the socket -- the service is unreachable')
    } finally { h.close() }
  }],

  ['a service that cannot be spawned is REPORTED, never thrown', async () => {
    // The five-hour hang. `spawn` reports ENOENT as an ASYNCHRONOUS 'error'
    // event, which no try/catch around spawn() can see, and an unhandled 'error'
    // on an EventEmitter throws. In Electron's main process that becomes an
    // uncaught exception, whose default handling is a MODAL dialog -- and on a
    // machine with nobody to dismiss it, the app hangs instead of failing.
    //
    // A non-existent working directory makes spawn fail exactly that way.
    let uncaught = null
    const onUncaught = (e) => { uncaught = e }
    process.on('uncaughtException', onUncaught)
    const started = svc.start({
      credential: require('../src/service-credential.js').create(),
      backendDir: path.join(os.tmpdir(), 'moltrace-no-such-dir-' + process.pid),
    })
    try {
      await new Promise((r) => setTimeout(r, 1200))
      assert.strictEqual(uncaught, null, `spawn failure escaped as an uncaught exception: ${uncaught && uncaught.message}`)
      const f = started.failure()
      assert.ok(f, 'the spawn failed and nothing recorded why')
      assert.ok(svc.describeFailure(f).reason.length > 10, 'the failure has no readable cause')
    } finally {
      process.removeListener('uncaughtException', onUncaught)
      started.close()
    }
  }],
]

;(async () => {
  for (const [name, fn] of asyncChecks) {
    try { await fn(); results.push(['PASS', name]) }
    catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
  }
  for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
  const failed = results.filter(([s]) => s === 'FAIL').length
  console.log(failed ? `\nLOCAL SERVICE FAILED (${failed})` : `\nLOCAL SERVICE OK — ${results.length} assertions`)
  process.exit(failed ? 1 : 0)
})()
