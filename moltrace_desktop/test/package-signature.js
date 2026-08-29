'use strict'
// Asserts the ad-hoc re-seal BOTH WAYS, for the same reason the freshness gate is
// proven both ways: a signer only ever seen succeeding is indistinguishable from
// one that reports success without doing anything.
//
// The failure this guards against is specific. @electron/packager renames the
// Electron binary and rewrites Info.plist after the prebuilt binary was
// linker-signed, which invalidates the inherited signature. `codesign -v` then
// answers "code has no resources but signature indicates they must be present" —
// an ERROR, not a policy verdict — and macOS presents the app as damaged, which
// the right-click-Open route does not recover.
const assert = require('node:assert')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync, spawnSync } = require('node:child_process')
const { signAdHoc } = require('../scripts/package.js')

const results = []
const check = (name, fn) => {
  try { fn(); results.push(['PASS', name]) }
  catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
}

if (process.platform !== 'darwin') {
  console.log('\nPACKAGE SIGNATURE SKIPPED — codesign exists only on macOS')
  process.exit(0)
}

const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'moltrace-sig-'))

// A minimal but REAL bundle: codesign refuses to reason about a directory that is
// not one, so proving anything here needs a genuine Mach-O inside a genuine layout.
function bundle(name) {
  const app = path.join(scratch, name + '.app')
  fs.mkdirSync(path.join(app, 'Contents', 'MacOS'), { recursive: true })
  fs.writeFileSync(path.join(app, 'Contents', 'Info.plist'),
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    + '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
    + '<plist version="1.0"><dict>'
    + '<key>CFBundleExecutable</key><string>' + name + '</string>'
    + '<key>CFBundleIdentifier</key><string>co.moltrace.test.' + name + '</string>'
    + '<key>CFBundleName</key><string>' + name + '</string>'
    + '</dict></plist>\n')
  fs.copyFileSync('/bin/echo', path.join(app, 'Contents', 'MacOS', name))
  return app
}

const verifies = (app) => {
  try { execFileSync('codesign', ['--verify', '--deep', app], { stdio: 'pipe' }); return true }
  catch { return false }
}

check('RED: the bundle does NOT verify before it is re-sealed', () => {
  const app = bundle('unsealed')
  assert.ok(!verifies(app), 'an unsigned bundle already verified, so the green case below proves nothing')
})

check('GREEN: the bundle verifies after signAdHoc', () => {
  const app = bundle('sealed')
  signAdHoc(app)
  assert.ok(verifies(app), 'signAdHoc returned but the bundle still does not verify')
})

check('the seal is ad-hoc, carrying no team identity it has not earned', () => {
  const app = bundle('adhoc')
  signAdHoc(app)
  // codesign writes bundle detail to stderr and exits 0, so read both streams
  // rather than trusting stdout to carry it.
  const r = spawnSync('codesign', ['-dvv', app], { encoding: 'utf8' })
  const info = (r.stderr || '') + (r.stdout || '')
  assert.match(info, /Signature=adhoc/, 'the seal is not ad-hoc')
  assert.match(info, /TeamIdentifier=not set/, 'an ad-hoc seal claimed a team identifier')
})

check('a bundle that is not there fails LOUDLY rather than reporting success', () => {
  let threw = false
  try { signAdHoc(path.join(scratch, 'does-not-exist.app')) } catch { threw = true }
  assert.ok(threw, 'signing a missing bundle returned normally; the caller would ship it unsealed')
})

fs.rmSync(scratch, { recursive: true, force: true })

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nPACKAGE SIGNATURE FAILED (${failed})` : `\nPACKAGE SIGNATURE OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
