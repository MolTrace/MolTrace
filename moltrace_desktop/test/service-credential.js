'use strict'
// §7.1 transport credential. Written before the implementation.
const assert = require('node:assert')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const results = []
const check = (name, fn) => {
  try { fn(); results.push(['PASS', name]) } catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
}

const cred = require('../src/service-credential.js')

check('the credential is 256 bits', () => {
  const c = cred.create()
  assert.strictEqual(Buffer.from(c.valueForHandle(), 'base64url').length, 32,
    'credential is not 32 bytes')
})

check('it comes from a CSPRNG, not Math.random', () => {
  const src = fs.readFileSync(require.resolve('../src/service-credential.js'), 'utf8')
  assert.ok(/randomBytes/.test(src), 'no randomBytes call')
  assert.ok(!/Math\.random/.test(src), 'Math.random appears in credential generation')
})

check('every launch gets a different credential', () => {
  const seen = new Set()
  for (let i = 0; i < 50; i++) seen.add(cred.create().valueForHandle())
  assert.strictEqual(seen.size, 50, 'credentials repeated across launches')
})

check('it is presented in exactly ONE named header', () => {
  const c = cred.create()
  const h = c.headers()
  assert.deepStrictEqual(Object.keys(h), [cred.HEADER_NAME],
    'more than one header carries the credential')
})

check('it refuses every other position — no query, path, cookie or body helper exists', () => {
  const c = cred.create()
  for (const forbidden of ['queryParam', 'toQueryString', 'cookie', 'toCookie', 'body', 'toBody', 'toUrl']) {
    assert.strictEqual(typeof c[forbidden], 'undefined',
      `credential exposes ${forbidden}() — a URL- or body-borne credential is reachable by a subresource load`)
  }
})

check('the raw value is not reachable from the object except for the handle write', () => {
  const c = cred.create()
  const leaked = Object.keys(c).filter((k) => typeof c[k] === 'string' && c[k].length > 20)
  assert.deepStrictEqual(leaked, [], `raw credential exposed as a plain property: ${leaked.join(', ')}`)
})

check('it never lands in an environment variable', () => {
  const c = cred.create()
  const v = c.valueForHandle()
  const hits = Object.entries(process.env).filter(([, val]) => val && val.includes(v))
  assert.deepStrictEqual(hits.map(([k]) => k), [], 'credential found in the environment')
})

check('it never lands in argv', () => {
  const c = cred.create()
  const v = c.valueForHandle()
  assert.ok(!process.argv.some((a) => a.includes(v)), 'credential found in argv')
})

check('spawning the service passes it over a HANDLE, not argv/env/file', () => {
  const c = cred.create()
  const plan = c.spawnPlan({ command: 'svc', args: ['--serve'] })
  const v = c.valueForHandle()
  assert.ok(!plan.args.some((a) => a.includes(v)), 'credential is in the spawn args')
  assert.ok(!Object.values(plan.env || {}).some((x) => String(x).includes(v)),
    'credential is in the spawn environment')
  assert.ok(Array.isArray(plan.stdio) && plan.stdio.length >= 4,
    'no extra pipe for the credential handle')
  assert.strictEqual(plan.stdio[3], 'pipe', 'fd 3 is not a pipe')
  assert.strictEqual(typeof plan.writeCredential, 'function', 'no handle writer')
})

check('nothing writes the credential to disk', () => {
  const src = fs.readFileSync(require.resolve('../src/service-credential.js'), 'utf8')
  assert.ok(!/writeFile|createWriteStream|appendFile/.test(src),
    'the credential module writes to the filesystem')
})

check('a scan of the temp dir after creation finds no credential file', () => {
  const c = cred.create()
  const v = c.valueForHandle()
  const dir = os.tmpdir()
  const hits = fs.readdirSync(dir).filter((n) => n.includes(v.slice(0, 12)))
  assert.deepStrictEqual(hits, [], `credential-named file left in ${dir}`)
})

check('the header name matches the one the ENGINE verifies', () => {
  // The two halves are in different languages and were written hours apart. They
  // agree today, and nothing made them agree — a rename on either side would be
  // silent, and every request would fail authentication with a correct
  // credential. Read the Python constant rather than restating it.
  const py = fs.readFileSync(
    path.join(__dirname, '..', '..', 'moltrace_backend', 'src', 'nmrcheck', 'desktop_transport.py'),
    'utf8',
  )
  const m = py.match(/^CREDENTIAL_HEADER\s*=\s*"([^"]+)"/m)
  assert.ok(m, 'could not find CREDENTIAL_HEADER in desktop_transport.py')
  assert.strictEqual(cred.HEADER_NAME, m[1],
    `the shell sends ${cred.HEADER_NAME} and the engine reads ${m[1]}`)
})

check('the emitted length clears the ENGINE\'s minimum', () => {
  const py = fs.readFileSync(
    path.join(__dirname, '..', '..', 'moltrace_backend', 'src', 'nmrcheck', 'local_service_entry.py'),
    'utf8',
  )
  const m = py.match(/_MIN_CREDENTIAL_CHARS\s*=\s*(\d+)/)
  assert.ok(m, 'could not find _MIN_CREDENTIAL_CHARS in local_service_entry.py')
  const emitted = cred.create().valueForHandle().length
  assert.ok(emitted >= Number(m[1]),
    `the shell emits ${emitted} characters and the engine requires ${m[1]}`)
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nSERVICE CREDENTIAL FAILED (${failed})` : `\nSERVICE CREDENTIAL OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
