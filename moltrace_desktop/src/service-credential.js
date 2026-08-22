'use strict'
// §7.1 — the local scientific service credential.
//
// "Generate a 256-bit service credential per launch, pass it from host to service
//  over an inherited handle or pipe rather than a command line, an environment
//  variable, or a file, and never write it to disk. Never use the system API key."
//
// Each of those exclusions is a real exposure, not ceremony:
//   argv  — readable by any local process via `ps`, and captured in crash reports
//   env   — inherited by every child, and dumped by most diagnostic tooling
//   file  — outlives the launch, and lands in backups and sync clients
// A pipe is the only channel that ends when the process does.
const { randomBytes, timingSafeEqual } = require('node:crypto')

// §7.1: "Present the credential in one named request header, and refuse it in
// every other position — query string, path, cookie, and body." This module
// deliberately offers NO helper for any other position: an affordance that does
// not exist cannot be reached for under deadline.
const HEADER_NAME = 'x-moltrace-local-service'

const CREDENTIAL_BYTES = 32 // 256 bits

function create() {
  // Closure, not a property. A raw credential on the object is one JSON.stringify
  // — a log line, an error report, an IPC message — away from being published.
  const secret = randomBytes(CREDENTIAL_BYTES).toString('base64url')

  return {
    /** The single named header. The only sanctioned presentation. */
    headers() {
      return { [HEADER_NAME]: secret }
    },

    /**
     * The value, for writing into the inherited handle only. Named so that a
     * reviewer sees any other use as out of place.
     */
    valueForHandle() {
      return secret
    },

    /**
     * How to spawn the service so the credential travels over fd 3 and nowhere
     * else. The caller spawns; this decides the shape.
     */
    spawnPlan({ command, args = [], env = {} } = {}) {
      return {
        command,
        args: [...args], // never carries the credential
        env: { ...env }, // never carries the credential
        // 0,1,2 as usual; fd 3 is the credential channel, closed straight after.
        stdio: ['ignore', 'pipe', 'pipe', 'pipe'],
        writeCredential(child) {
          const handle = child.stdio && child.stdio[3]
          if (!handle) throw new Error('the service was spawned without the credential handle')
          handle.write(secret + '\n')
          handle.end()
        },
      }
    },

    /**
     * Constant-time comparison, for the host side of any check it performs.
     * §7.1 requires the comparison happen "before any request body is read"; a
     * length-varying compare leaks the credential a byte at a time.
     */
    matches(presented) {
      if (typeof presented !== 'string') return false
      const a = Buffer.from(presented)
      const b = Buffer.from(secret)
      if (a.length !== b.length) return false
      return timingSafeEqual(a, b)
    },
  }
}

module.exports = { create, HEADER_NAME, CREDENTIAL_BYTES }
