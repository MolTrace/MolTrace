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
  server.listen(bindPath)
  fs.renameSync(bindPath, socketPath)

  // Node makes it 0755. §7.1 wants owner-only on the socket AND its parent.
  fs.chmodSync(socketPath, 0o600)

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

/** How to spawn it. Separated so the shape is testable without spawning. */
function buildSpawn({ credential, socketFd, backendDir }) {
  const plan = credential.spawnPlan({
    command: 'uv',
    args: ['run', 'python', '-m', 'nmrcheck.local_service_main'],
  })
  return {
    command: plan.command,
    args: plan.args,                        // never carries the credential
    options: {
      cwd: backendDir,
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
function start({ credential, backendDir }) {
  const listener = createListener()
  const plan = buildSpawn({ credential, socketFd: listener.fd, backendDir })
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

  try {
    plan.writeCredential(child)
  } catch (err) {
    failure = failure || err
  }
  child.on('exit', (code) => {
    failure = failure || new Error(`the service stopped (code ${code})`)
  })

  // Only now, with the child holding its own descriptor.
  listener.stopAccepting()

  return {
    socketPath: listener.socketPath,
    child,
    failure: () => failure,
    close: () => {
      try { child.kill() } catch {}
      listener.close()
    },
  }
}

function describeFailure(err) {
  return {
    reachable: false,
    versions: {},
    reason:
      'The local science service is not running, so analysis on this computer is unavailable. ' +
      (err && err.message ? `(${err.message})` : ''),
  }
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
  createSocketDirectory, createListener, buildSpawn, start, describeFailure, capabilityWorld, spawn,
}
