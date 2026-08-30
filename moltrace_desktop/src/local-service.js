'use strict'
// Starting the local science service, per §7.1.
//
// The host creates the listening socket and passes the BOUND DESCRIPTOR down.
// The service must never bind by path itself: the packaged runtime chmods a
// path-bound socket to world-accessible mode, which would hand every local
// account a door. The service refuses to start without a passed socket rather
// than falling back to a port, so this side has to get it right.
//
// Measured on Node v25.9.0 (see the transport measurement note):
//   * `server._handle.fd` is the ONLY way to reach a listening server's raw
//     descriptor, and it is a PRIVATE API. It is asserted at startup so a Node
//     upgrade that removes it fails loudly rather than yielding `undefined`.
//   * `listen(path)` creates the socket at 0755 REGARDLESS of the parent
//     directory's mode. The chmod below is mandatory and is the line that is
//     easy to omit, because the directory already looks locked.
//
// THE HOST MUST STOP ACCEPTING ONCE THE SERVICE HAS THE DESCRIPTOR, and getting
// that wrong is what made the service "never become ready" for an entire build.
// Both processes hold a descriptor for the SAME listening socket, so they share
// one accept queue and whichever calls accept() first takes the connection. The
// host's `net.Server` has no connection handler, so a connection it wins is
// accepted and then never answered — the client waits forever and never errors.
//
// Measured with NO CHILD IN THE PICTURE AT ALL: a request to a socket held only
// by this host hangs indefinitely rather than being refused. That is the whole
// mechanism, and it presented as "the child spawns, stays alive, writes nothing
// to stderr, and readiness never arrives" — which reads like a broken child and
// is not.
//
// Closing the host's server is what stops it competing, and closing it has a
// second effect that must be handled or the cure is worse than the disease:
// libuv UNLINKS the path it bound. Measured — after `server.close()` the socket
// file is gone and every subsequent connect fails. So the socket is bound under
// a staging name and RENAMED to its real name before the host closes: libuv then
// unlinks a name that no longer exists, while the real path survives pointing at
// the same bound inode, now accepted on only by the service. The child's own
// descriptor (dup'd by spawn) keeps the socket alive across the host's close.
//
// Measured end to end: ready in 1.9 s and 40/40 requests answered, against
// never-ready-in-120 s before.
const fs = require('node:fs')
const net = require('node:net')
const os = require('node:os')
const path = require('node:path')
const { spawn } = require('node:child_process')
const http = require('node:http')

function createSocketDirectory() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'moltrace-svc-'))
  fs.chmodSync(dir, 0o700)
  return { dir, cleanup: () => fs.rmSync(dir, { recursive: true, force: true }) }
}

function createListener() {
  const { dir, cleanup } = createSocketDirectory()
  const socketPath = path.join(dir, 's')
  // Bound under a staging name so the host's own close cannot unlink the real
  // one. Measured 50/50: bind is synchronous inside listen(), so the rename and
  // chmod immediately after are safe without waiting for the 'listening' event.
  const bindPath = path.join(dir, 'bind')
  const server = net.createServer()

  // THE THIRD ASYNCHRONOUS ERROR CHANNEL. The commit that added this staging
  // dance handled 'error' on the ChildProcess and on the credential pipe and
  // left this one live -- which is the exact half-applied shape it was written
  // to avoid. A failed bind (descriptor exhaustion, a TMPDIR long enough to
  // overflow macOS's 104-byte sun_path, a sandboxed runtime refusing) emits
  // 'error' on the server, and an unhandled 'error' throws.
  //
  // Recorded rather than swallowed: when the synchronous path below then fails
  // with a confusing secondary error (a rename of a socket that was never
  // created), the listen error is the one worth reporting.
  let listenError = null
  server.on('error', (err) => { listenError = err })

  try {
    server.listen(bindPath)
    fs.renameSync(bindPath, socketPath)
    // Node makes it 0755. §7.1 wants owner-only on the socket AND its parent.
    fs.chmodSync(socketPath, 0o600)
  } catch (err) {
    try { server.close() } catch {}
    cleanup()
    throw listenError || err
  }

  const handle = server._handle
  const fd = handle && typeof handle.fd === 'number' ? handle.fd : -1
  if (fd < 0) {
    server.close()
    cleanup()
    throw new Error(
      'this Node build does not expose the listening socket descriptor, so the local science ' +
      'service cannot be given one. It will not be started.',
    )
  }
  return {
    server,
    socketPath,
    fd,
    // Called ONLY after the child holds its own descriptor. Before that, closing
    // here would destroy the socket the child was going to be given.
    stopAccepting: () => { try { server.close() } catch {} },
    close: () => { try { server.close() } catch {} cleanup() },
  }
}

/**
 * Where the service actually is.
 *
 * A PACKAGED build ships a frozen copy of the service beside the app and runs
 * that. A development checkout has no frozen copy and runs it from source
 * through `uv`. Resolved by asking the filesystem rather than by a build-time
 * flag, so a packaged build cannot be handed a development command and a
 * developer cannot accidentally test the frozen one they have not rebuilt.
 *
 * The frozen binary is what a tester gets: it refuses to start without a passed
 * socket exactly as the source does — verified against the built artifact, not
 * assumed from the source it was built from.
 */
function resolveService({ resourcesPath, backendDir }) {
  if (resourcesPath) {
    const frozen = path.join(resourcesPath, 'moltrace-local-service', 'moltrace-local-service')
    if (fs.existsSync(frozen)) {
      // cwd is the bundle's own directory: a frozen build resolves its data
      // files relative to itself, and inheriting the app's cwd has no meaning.
      return { command: frozen, args: [], cwd: path.dirname(frozen), frozen: true }
    }
  }
  return {
    command: 'uv',
    args: ['run', 'python', '-m', 'nmrcheck.local_service_main'],
    cwd: backendDir,
    frozen: false,
  }
}

/** How to spawn it. Separated so the shape is testable without spawning. */
function buildSpawn({ credential, socketFd, backendDir, resourcesPath, service }) {
  const target = service || resolveService({ resourcesPath, backendDir })
  const plan = credential.spawnPlan({ command: target.command, args: target.args })
  return {
    command: plan.command,
    args: plan.args,                        // never carries the credential
    options: {
      cwd: target.cwd,
      env: { ...process.env },              // never carries the credential
      // 0,1,2 as usual; 3 is the credential pipe; 4 is the bound socket.
      stdio: ['ignore', 'pipe', 'pipe', 'pipe', socketFd],
    },
    writeCredential: plan.writeCredential,
  }
}

/**
 * The whole startup sequence, in the one order that works.
 *
 * The ordering is encapsulated rather than documented because the two ways to
 * get it wrong are both silent: stop accepting BEFORE the spawn and the child
 * inherits a dead socket; never stop accepting and the host swallows the
 * readiness probes. A caller holding the pieces separately has to remember. A
 * caller calling this does not.
 */
function start({ credential, backendDir, resourcesPath, service, onExit }) {
  const listener = createListener()
  const plan = buildSpawn({ credential, socketFd: listener.fd, backendDir, resourcesPath, service })
  const child = spawn(plan.command, plan.args, plan.options)

  // MEASURED: `spawn uv ENOENT` arrives as an ASYNCHRONOUS 'error' event, which
  // a try/catch around spawn() cannot see, and an unhandled 'error' on an
  // EventEmitter THROWS. In the main process that becomes an uncaught exception
  // and Electron's default handling of one is a MODAL dialog — on a machine with
  // no one to dismiss it, the app hangs rather than failing. Two CI runners hung
  // for five hours each on exactly this. Holding the error turns a hang into a
  // sentence an operator can read.
  let failure = null
  child.on('error', (err) => { failure = err })

  // The SECOND escape route, and it is a different stream. Writing the
  // credential to fd 3 of a child that never launched fails with EPIPE -- also
  // asynchronously, also as an unhandled 'error' that throws, and NOT on the
  // ChildProcess but on the pipe. Handling the ChildProcess alone left this one
  // live; it was caught by the test written for the first one, which is the
  // argument for writing the test rather than reasoning about the fix.
  const credentialPipe = child.stdio && child.stdio[3]
  if (credentialPipe && typeof credentialPipe.on === 'function') {
    credentialPipe.on('error', (err) => { failure = failure || err })
  }

  // DRAIN stdout AND stderr. They are 'pipe', and nothing read them -- two harms.
  // A pipe nobody reads fills at the kernel buffer and the child then BLOCKS
  // FOREVER on its next write, which presents as a service that started and went
  // silent. And the service's own explanation of why it refused to start went
  // into that pipe and was discarded, so an operator saw a bare exit code while
  // the sentence naming the cause was thrown away. Keeping the tail bounded: this
  // is diagnostic text, not a log, and an unbounded string is its own leak.
  let output = ''
  for (const stream of [child.stdout, child.stderr]) {
    if (!stream || typeof stream.on !== 'function') continue
    stream.setEncoding('utf8')
    stream.on('data', (chunk) => { output = (output + chunk).slice(-4000) })
    stream.on('error', () => { /* a dead pipe is the exit we already report */ })
  }

  try {
    plan.writeCredential(child)
  } catch (err) {
    failure = failure || err
  }

  // (code, signal) -- Node passes code=null when a signal killed the child, so
  // binding only the first argument printed the literal "code null" and dropped
  // the one field that said what happened.
  child.on('exit', (code, signal) => {
    failure = failure || new Error(_exitReason(code, signal))
    // A death AFTER startup has to reach the readout. Without this the app keeps
    // reporting a service that is gone: serviceState is written once, by the
    // startup poll, and this handler was its only other writer before the
    // lifecycle moved in here.
    if (typeof onExit === 'function') { try { onExit(failure, output) } catch {} }
  })

  // Only now, with the child holding its own descriptor.
  listener.stopAccepting()

  return {
    socketPath: listener.socketPath,
    child,
    failure: () => failure,
    /** The child's own words. For a cause line and for logs -- never rendered raw. */
    diagnostic: () => output,
    close: () => {
      try { child.kill() } catch {}
      listener.close()
    },
  }
}

//: Text that must never reach a person's screen: absolute paths, Python
//: tracebacks, errno codes, and the names of the programs this app happens to
//: run. The house rule is that display copy is humanised while wire values are
//: not renamed -- so the raw text is still carried, just not rendered.
//: NOT case-insensitive, deliberately. With an /i flag the errno alternative
//: `\bE[A-Z]{3,}\b` matches any ordinary four-letter word beginning with "e" --
//: it flagged the word "engine" in this module's own copy. An errno code is
//: uppercase by nature, so the case IS the signal; the alternatives that can
//: legitimately vary spell both forms out.
const _NOT_FOR_A_PERSON = new RegExp([
  '(?:/[\\w.-]+){2,}',        // two or more path segments
  'Traceback', 'File "',       // a Python stack
  '\\bE[A-Z]{3,}\\b', 'errno',  // errno codes, uppercase by nature
  '\\b[Uu][Vv]\\b', '\\b[Pp]ython\\d*\\b', '[Uu]vicorn',   // the programs this app happens to run
  '\\bfd \\d',                 // file descriptor numbers
].join('|'))

/**
 * The service's own last words, when they are a sentence rather than a stack.
 *
 * The service writes a deliberate refusal sentence when it will not start, and
 * that sentence is the most useful thing an operator can be told. A traceback is
 * not, and neither is a path into a temporary directory.
 */
function _serviceSentence(diagnostic) {
  const lines = String(diagnostic || '').split('\n').map((l) => l.trim()).filter(Boolean)
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i]
    if (line.length >= 20 && line.length <= 200 && !_NOT_FOR_A_PERSON.test(line)) return line
  }
  return null
}

/** Why it is not running, in words a scientist reads, with the cause named. */
function _humanCause(err, diagnostic) {
  const sentence = _serviceSentence(diagnostic)
  if (sentence) return sentence

  const code = err && err.code
  const message = (err && err.message) || ''
  if (code === 'ENOENT' || /\bENOENT\b/.test(message)) {
    return 'The analysis engine that runs on this computer could not be found in this installation.'
  }
  if (code === 'EACCES' || /\bEACCES\b/.test(message)) {
    return 'This computer did not permit the analysis engine to start.'
  }
  if (code === 'EPIPE' || /\bEPIPE\b/.test(message)) {
    return 'It closed before it had finished starting up.'
  }
  // Messages this module wrote itself are already written for a person.
  if (message && !_NOT_FOR_A_PERSON.test(message)) return message.charAt(0).toUpperCase() + message.slice(1) + '.'
  return 'It could not be started, and did not say why.'
}

/**
 * `reason` is rendered. `diagnostic` is NOT -- it is for a log or a support
 * bundle, and putting it on screen is what this function exists to prevent.
 */
// Polls the health route rather than sleeping a fixed time. A fixed sleep is
// either too short on a cold start or wasted on a warm one, and it turns a slow
// machine into a "service unavailable" that is not true.
//
// EVERY REQUEST CARRIES A TIMEOUT, and that is load-bearing rather than tidy. A
// request to this socket can be accepted by something that never answers it, in
// which case the response callback never fires AND the error callback never
// fires -- so a poll without a timeout does not retry, it stops. That is not
// hypothetical: the host's own listener used to do exactly this, and a single
// swallowed probe left the promise below permanently unsettled.
//
// AND A TIMED-OUT REQUEST FIRES TWICE. Measured on Electron 43.4.1's Node and on
// Node 25: `req.destroy()` inside the 'timeout' handler makes the request emit
// 'error' with ECONNRESET, so a handler on each event ran the retry TWICE for one
// attempt and the poll forked as 2^k. Measured with attempts=6 against an
// accepting-but-silent socket: 127 requests issued and 64 concurrent, where one
// chain issues 7. At the shipped attempts=60 that is not a number worth writing
// down. The `retried` latch is the fix, and it must stay even if one of the two
// handlers is ever removed -- dropping the timeout handler instead would restore
// the original hang, because 'error' does not fire for a swallowed connection.
function waitUntilReady({
  started, headers, cancelled, attempts = 60,
  // The probe budget, injectable so a test can assert the POLL'S SHAPE without
  // paying its production wall-clock. The defaults are the shipped values and
  // no caller in the app passes anything else; the two tests that count probes
  // were spending 13 of this suite's 18 seconds watching real timeouts elapse.
  probeTimeoutMs = 2000, backoffMs = 250,
}) {
  const socketPath = started.socketPath
  const startedAt = Date.now()
  return new Promise((resolve) => {
    const attempt = (n) => {
      // Cancelled means cancelled: after shutdown there is nothing to be ready.
      if (cancelled && cancelled()) {
        return resolve(describeFailure(new Error('it was stopped before it finished starting')))
      }
      // A child that failed to launch will never answer. Say so with its cause
      // rather than spending the whole budget discovering it.
      const err = started.failure()
      if (err) return resolve(describeFailure(err, started.diagnostic()))

      let retried = false
      const req = http.request(
        {
          socketPath,
          path: '/health',
          method: 'GET',
          headers: headers(),
          timeout: probeTimeoutMs,
        },
        (res) => {
          res.resume()
          if (res.statusCode === 200) resolve({ reachable: true, versions: { fid: '1' }, reason: null })
          else if (n > 0) setTimeout(() => attempt(n - 1), backoffMs)
          else resolve(describeFailure(new Error('it did not start up correctly'), started.diagnostic()))
        },
      )
      const retry = () => {
        if (retried) return
        retried = true
        if (n > 0) setTimeout(() => attempt(n - 1), backoffMs)
        else {
          // The ELAPSED time, not the arithmetic of the backoff. That arithmetic
          // counted only the 250ms delay and so claimed 15 seconds for a wait
          // that, once every probe could burn a 2s timeout, ran to over two
          // minutes. A number a user can time with a wristwatch has to be true.
          const seconds = Math.round((Date.now() - startedAt) / 1000)
          resolve(describeFailure(
            new Error(`it did not answer within ${seconds} seconds of starting`), started.diagnostic()))
        }
      }
      req.on('timeout', () => { req.destroy(); retry() })
      req.on('error', retry)
      req.end()
    }
    attempt(attempts)
  })
}


/**
 * Why the child ended, in one sentence.
 *
 * Node passes `code = null` when a SIGNAL killed the child, so a handler binding
 * only the first argument printed the literal "code null" and dropped the one
 * field that said what happened. Separated from the handler so it can be tested
 * without a live child -- CI has no `uv`, so a test that needs one to die is a
 * test that only runs on a developer's machine.
 */
function _exitReason(code, signal) {
  if (signal) return `the service was stopped by ${signal}`
  if (code === 0) return 'the service exited on its own'
  return `the service stopped while starting (code ${code})`
}

function describeFailure(err, diagnostic) {
  return {
    reachable: false,
    versions: {},
    reason:
      'The local science service is not running, so analysis on this computer is unavailable. ' +
      _humanCause(err, diagnostic),
    diagnostic: (err && err.message ? err.message + '\n' : '') + String(diagnostic || ''),
  }
}

/**
 * Why one file could not be read, in the words that fit what actually happened.
 *
 * TWO DIFFERENT FAILURES were being told as one. `describeFailure` exists to
 * describe a dead CHILD and opens with "The local science service is not running,
 * so analysis on this computer is unavailable." Every per-file refusal was routed
 * through it, so a service that had just read the file and correctly declined it
 * was reported as dead -- and the real cause, which names the file and what is
 * wrong with it, was demoted to the second half of a sentence that had already
 * misdiagnosed the app to itself. A reader told the service is down restarts it
 * and gets the same result.
 */
function readFailureReason(err) {
  if (err && err.answeredByService && err.message) return err.message
  return describeFailure(err).reason
}

/** The four sources §7.1 names, as the capability readout expects them. */
function capabilityWorld(service) {
  return {
    // Still null: these arrive with the entitlement work and the pack inventory.
    // Null fails closed, which is the honest answer while they do not exist.
    modules: null,
    entitlement: null,
    packs: null,
    service,
    role: null,
  }
}

module.exports = {
  createSocketDirectory, createListener, buildSpawn, start, waitUntilReady, describeFailure,
  capabilityWorld, spawn, _exitReason, resolveService,
  _NOT_FOR_A_PERSON, readFailureReason }
