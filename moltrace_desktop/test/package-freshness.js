'use strict'
// Asserts the packaging freshness gate BOTH WAYS. A gate only ever seen refusing is
// indistinguishable from one that always refuses, so the green direction is proven
// here too — against a freeze stamped in the future, which no commit can precede.
//
// Runs in plain node against the real repository, because the thing under test is a
// claim about this repository's history. It reads; it never writes.
const assert = require('node:assert')
const fs = require('node:fs')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { scienceNewerThanFreeze, FROZEN_SCIENCE_SURFACE, FROZEN_SERVICE } = require('../scripts/package.js')

const REPO = path.join(__dirname, '..', '..')
const results = []
const check = (name, fn) => {
  try { fn(); results.push(['PASS', name]) }
  catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
}

// A stand-in whose mtime we control. The real frozen binary is a build input another
// step owns; a test that rewrote its timestamp would be corrupting the thing it checks.
const scratch = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'moltrace-freshness-'))
const stamp = (whenSeconds) => {
  const f = path.join(scratch, 'moltrace-local-service')
  fs.writeFileSync(f, 'not a real binary; only its mtime is under test')
  fs.utimesSync(f, whenSeconds, whenSeconds)
  return f
}

check('the surface is scoped to what the frozen entry point imports, not all of src', () => {
  assert.ok(FROZEN_SCIENCE_SURFACE.length > 0, 'the surface is empty, so nothing is watched')
  for (const rel of FROZEN_SCIENCE_SURFACE) {
    assert.ok(fs.existsSync(path.join(REPO, rel)), `${rel} does not exist, so the gate watches nothing there`)
  }
  assert.ok(
    !FROZEN_SCIENCE_SURFACE.includes('moltrace_backend/src'),
    'the whole backend src is watched; an api.py edit cannot change a number a tester sees, '
    + 'and a gate that fires on it gets bypassed',
  )
})

check('RED: a freeze older than a commit on the surface is reported stale', () => {
  // The oldest commit touching the surface, minus a second: everything after it counts.
  const oldest = execFileSync('git', [
    'log', '--reverse', '--format=%at', '--', ...FROZEN_SCIENCE_SURFACE,
  ], { cwd: REPO, encoding: 'utf8' }).split('\n').filter(Boolean)[0]
  assert.ok(oldest, 'no commit touches the surface at all — the query is wrong')
  const r = scienceNewerThanFreeze(stamp(Number(oldest) - 1))
  assert.strictEqual(r.checked, true, 'the check could not run')
  assert.ok(r.commits.length > 0, 'a freeze older than every commit on the surface reported nothing newer')
})

check('GREEN: a freeze newer than every commit is NOT reported stale', () => {
  // One day ahead. Proves the gate can pass, which the refusing case cannot show.
  const future = Math.floor(Date.now() / 1000) + 86400
  const r = scienceNewerThanFreeze(stamp(future))
  assert.strictEqual(r.checked, true, 'the check could not run')
  assert.deepStrictEqual(r.commits, [], 'commits reported as newer than a freeze stamped tomorrow')
  assert.deepStrictEqual(r.dirty, [], 'files reported as newer than a freeze stamped tomorrow')
})

check('an unreadable freeze fails CLOSED rather than reporting fresh', () => {
  let threw = false
  try { scienceNewerThanFreeze(path.join(scratch, 'does-not-exist')) } catch { threw = true }
  assert.ok(threw, 'a missing freeze returned a verdict instead of refusing to guess; '
    + 'the caller would read that as fresh')
})

check('the gate reads the repository and never writes to it', () => {
  const before = execFileSync('git', ['status', '--porcelain'], { cwd: REPO, encoding: 'utf8' })
  scienceNewerThanFreeze(stamp(Math.floor(Date.now() / 1000)))
  const after = execFileSync('git', ['status', '--porcelain'], { cwd: REPO, encoding: 'utf8' })
  assert.strictEqual(after, before, 'running the freshness check changed the working tree')
})

fs.rmSync(scratch, { recursive: true, force: true })

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nPACKAGE FRESHNESS FAILED (${failed})` : `\nPACKAGE FRESHNESS OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
