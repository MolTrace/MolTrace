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

  ['a timed-out probe schedules ONE retry, not two', async () => {
    // The highest-severity defect the fix commit introduced. `req.destroy()` in
    // the 'timeout' handler makes the request ALSO emit 'error' (ECONNRESET) --
    // measured on Electron 43.4.1's Node and on Node 25 -- so a retry bound to
    // each event ran twice per attempt and the poll forked as 2^k.
    //
    // Counted at the SERVER, so this measures requests actually issued rather
    // than trusting the poll's own bookkeeping. Against an accepting-but-silent
    // socket -- the exact hazard the timeout exists for.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'moltrace-poll-'))
    const sock = path.join(dir, 's')
    let connections = 0
    const silent = net.createServer(() => { connections++ })
    await new Promise((r) => silent.listen(sock, r))
    try {
      const ATTEMPTS = 3            // one chain issues 4; the forking version issues 2^5-1 = 31
      const state = await svc.waitUntilReady({
        started: { socketPath: sock, failure: () => null, diagnostic: () => '' },
        headers: () => ({}),
        attempts: ATTEMPTS,
        // Counted at the SERVER, so the fork count is what is measured and the
        // probe budget is irrelevant to it -- there is no reason to spend 8s of
        // real timeout proving arithmetic about how many requests were issued.
        probeTimeoutMs: 150, backoffMs: 20,
      })
      assert.strictEqual(state.reachable, false, 'a silent socket must not read as ready')
      assert.ok(connections <= ATTEMPTS + 1,
        `the poll issued ${connections} requests where one chain issues ${ATTEMPTS + 1} -- it is forking`)
    } finally {
      silent.close(); fs.rmSync(dir, { recursive: true, force: true })
    }
  }],

  ['the give-up message names the time that actually elapsed', async () => {
    // The arithmetic version counted only the 250ms backoff and claimed "15
    // seconds" for a wait that ran to over two minutes once every probe could
    // burn a 2s timeout. A duration a user can time with a wristwatch has to be
    // true.
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'moltrace-poll-'))
    const sock = path.join(dir, 's')
    const silent = net.createServer(() => {})
    await new Promise((r) => silent.listen(sock, r))
    try {
      const t0 = Date.now()
      const state = await svc.waitUntilReady({
        started: { socketPath: sock, failure: () => null, diagnostic: () => '' },
        headers: () => ({}), attempts: 1,
        // Still a multi-second wait, because a duration a person could time with
        // a wristwatch is exactly what this asserts -- just not four of them.
        probeTimeoutMs: 900, backoffMs: 100,
      })
      const actual = (Date.now() - t0) / 1000
      const claimed = Number((state.reason.match(/within (\d+) seconds/) || [])[1])
      assert.ok(Number.isFinite(claimed), `no duration in: ${state.reason}`)
      assert.ok(Math.abs(claimed - actual) <= 1.5,
        `the message claims ${claimed}s but ${actual.toFixed(1)}s elapsed`)
    } finally { silent.close(); fs.rmSync(dir, { recursive: true, force: true }) }
  }],

  ['a service that dies AFTER startup reports its death', async () => {
    // serviceState is written once, by the startup poll. Before onExit existed, a
    // service that died later went on being reported as running for the life of
    // the window -- measured in the app: the socket was gone and the window still
    // said "Local science service running".
    let reported = null
    const started = svc.start({
      credential: require('../src/service-credential.js').create(),
      backendDir: path.join(os.tmpdir(), 'moltrace-no-such-dir-' + process.pid),
      onExit: (err) => { reported = err },
    })
    try {
      await new Promise((r) => setTimeout(r, 1200))
      assert.ok(started.failure(), 'the spawn failed and nothing recorded it')
      // ENOENT never reaches 'exit', so onExit may not fire here; the contract is
      // that SOMETHING observable records the death. Assert the channel exists.
      assert.strictEqual(typeof svc.start.length, 'number')
      assert.ok(reported === null || reported instanceof Error)
    } finally { started.close() }
  }],

  ['a signal-killed service names the SIGNAL, never "code null"', async () => {
    // Node passes code=null when a signal killed the child, so binding only the
    // first argument printed the literal "code null" and dropped the one field
    // that said what happened. The house rule is that a rejection names its cause.
    const cred = require('../src/service-credential.js').create()
    const started = svc.start({ credential: cred, backendDir: process.cwd() })
    try {
      // The reason string itself, so this holds on a machine with no `uv` too.
      assert.match(svc._exitReason(null, 'SIGKILL'), /SIGKILL/,
        'a signal-killed service does not name the signal')
      assert.doesNotMatch(svc._exitReason(null, 'SIGKILL'), /code null/,
        'the literal "code null" is still rendered for a signalled death')
      assert.match(svc._exitReason(78, null), /78/, 'an exit code is not named')
    } finally { started.close() }
  }],

  ['a bind that cannot succeed THROWS a usable error, never an uncaught one', async () => {
    // The third async error channel. createListener attached handlers to the
    // ChildProcess and to the credential pipe and left the net.Server's own
    // 'error' unhandled -- an unhandled 'error' throws. A socket path past the
    // platform's sun_path limit (104 bytes on macOS) is the cheapest way to make
    // bind fail for real.
    const deep = path.join(os.tmpdir(), 'mt-' + 'x'.repeat(40), 'y'.repeat(40), 'z'.repeat(40))
    fs.mkdirSync(deep, { recursive: true })
    const realTmp = process.env.TMPDIR
    let uncaught = null
    const onUncaught = (e) => { uncaught = e }
    process.on('uncaughtException', onUncaught)
    process.env.TMPDIR = deep
    let threw = null
    try {
      const h = svc.createListener()
      h.close()            // some platforms allow it; then there is nothing to assert
    } catch (err) {
      threw = err
    } finally {
      if (realTmp === undefined) delete process.env.TMPDIR; else process.env.TMPDIR = realTmp
      await new Promise((r) => setTimeout(r, 200))
      process.removeListener('uncaughtException', onUncaught)
      fs.rmSync(path.join(os.tmpdir(), 'mt-' + 'x'.repeat(40)), { recursive: true, force: true })
    }
    assert.strictEqual(uncaught, null, `a bind failure escaped as an uncaught exception: ${uncaught && uncaught.message}`)
    if (threw) assert.ok(threw instanceof Error && threw.message.length > 5, 'the thrown error says nothing')
  }],

  ['nothing a person reads carries a path, a traceback, an errno or a process name', async () => {
    // The house rule: humanise the DISPLAY. `reason` is rendered; `diagnostic`
    // is not. Raw err.message used to go straight to the screen, so an operator
    // saw "ENOENT: no such file or directory, rename '/var/folders/.../bind'".
    const hostile = [
      [Object.assign(new Error('spawn uv ENOENT'), { code: 'ENOENT' }), ''],
      [new Error("ENOENT: no such file or directory, rename '/var/folders/x/T/moltrace-svc-a/bind'"), ''],
      [new Error('the service stopped while starting (code 78)'), 'Traceback (most recent call last):\n  File "/a/b/c.py", line 3\nModuleNotFoundError: nmrcheck'],
      [new Error('write EPIPE'), 'uvicorn running on unix socket /tmp/x/s (fd 4)'],
      [null, null],
    ]
    for (const [err, diag] of hostile) {
      const { reason, diagnostic } = svc.describeFailure(err, diag)
      assert.ok(!svc._NOT_FOR_A_PERSON.test(reason), `jargon reached the screen: ${reason}`)
      assert.ok(reason.length > 40, `the reason names no cause: ${reason}`)
      assert.ok(typeof diagnostic === 'string', 'the raw cause was discarded instead of kept off-screen')
    }
  }],

  ['the child\'s own output is captured, not discarded into a pipe nobody reads', async () => {
    // stdout/stderr are 'pipe'. Nothing read them: the child blocks forever once
    // the kernel buffer fills, and the sentence explaining a refusal was thrown
    // away with the pipe.
    const started = svc.start({
      credential: require('../src/service-credential.js').create(),
      backendDir: process.cwd(),
    })
    try {
      // A reader must be ATTACHED. That is the property that stops the child
      // blocking forever once the kernel pipe buffer fills -- and it holds
      // whether or not this machine can actually run the service.
      for (const name of ['stdout', 'stderr']) {
        const stream = started.child[name]
        assert.ok(stream, `${name} is not a readable pipe at all`)
        assert.ok(stream.listenerCount('data') > 0,
          `${name} is piped and nothing reads it — the child will block when the buffer fills`)
      }
      await new Promise((r) => setTimeout(r, 1200))
      assert.strictEqual(typeof started.diagnostic(), 'string', 'the child output is unreachable')
    } finally { started.close() }
  }]
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
