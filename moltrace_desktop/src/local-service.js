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
  const server = net.createServer()
  server.listen(socketPath)

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
  return { server, socketPath, fd, close: () => { try { server.close() } catch {} cleanup() } }
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

module.exports = { createSocketDirectory, createListener, buildSpawn, describeFailure, capabilityWorld, spawn }
