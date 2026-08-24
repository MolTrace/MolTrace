'use strict'
// Every relative require in the shipped source must resolve.
//
// This exists because it already happened: a commit wired main.js to a module it
// had not added, because `git commit -- <path>` picks up tracked files only. A
// fresh clone could not start the shell.
//
// Static resolution rather than `require()`-and-see: running main.js outside
// Electron throws for unrelated reasons (electron's API is absent), so a check
// that greps the runtime error is one unrelated failure away from lying.
const fs = require('node:fs')
const path = require('node:path')

const srcDir = path.join(__dirname, '..', 'src')
const problems = []
let checked = 0

for (const file of fs.readdirSync(srcDir).filter((n) => n.endsWith('.js'))) {
  const full = path.join(srcDir, file)
  const body = fs.readFileSync(full, 'utf8')
  for (const m of body.matchAll(/require\(\s*['"](\.[^'"]+)['"]\s*\)/g)) {
    checked++
    const spec = m[1]
    try {
      require.resolve(path.resolve(srcDir, spec))
    } catch {
      problems.push(`${file} requires ${spec}, which does not resolve`)
    }
  }
}

// The renderer's own assets must exist too — index.html references them by name,
// and a missing app.js is a blank window rather than an error.
const rendererDir = path.join(__dirname, '..', 'renderer')
const html = fs.readFileSync(path.join(rendererDir, 'index.html'), 'utf8')
for (const m of html.matchAll(/(?:src|href)="\.\/([^"]+)"/g)) {
  checked++
  if (!fs.existsSync(path.join(rendererDir, m[1]))) {
    problems.push(`renderer/index.html references ./${m[1]}, which is not in the tree`)
  }
}

// Every test suite must actually be RUN. A suite that exists and is wired into
// nothing is worse than no suite: it reads as coverage in the tree and in review,
// and it asserts nothing. That is not hypothetical -- test/local-service.js was
// written, committed, and never referenced by any npm script, so six assertions
// sat inert while CI reported the desktop green.
//
// A file in test/ is a suite unless it is a helper another test requires, or is
// prefixed with `_`. Anything else must appear in the `test` script chain.
const testDir = __dirname
const pkgScripts = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8')).scripts

// Reachable FROM `test`, following `npm run` transitively -- not "mentioned in
// some script anywhere". A first version scanned every script value, so a suite
// kept alive only by its own convenience alias (`test:service`) counted as
// wired. Measured: unwiring local-service from the `test` chain left the guard
// green. It was checking that the file was spelled somewhere, which is not the
// property. The suite must be reachable from the command CI runs.
const reachable = new Set()
const expand = (name) => {
  if (reachable.has(name) || !pkgScripts[name]) return ''
  reachable.add(name)
  const body = pkgScripts[name]
  let text = body
  for (const m of body.matchAll(/npm run ([A-Za-z0-9:_-]+)/g)) text += ' ' + expand(m[1])
  return text
}
const scriptText = expand('test')
const testFiles = fs.readdirSync(testDir).filter((n) => n.endsWith('.js') && !n.startsWith('_'))
const requiredByAnother = new Set()
for (const f of testFiles) {
  for (const m of fs.readFileSync(path.join(testDir, f), 'utf8').matchAll(/require\(\s*['"]\.\/([^'"]+)['"]\s*\)/g)) {
    requiredByAnother.add(m[1].endsWith('.js') ? m[1] : m[1] + '.js')
  }
}
for (const f of testFiles) {
  if (requiredByAnother.has(f)) continue
  checked++
  if (!scriptText.includes('test/' + f)) {
    problems.push(`test/${f} is a suite that no npm script runs — it asserts nothing`)
  }
}

for (const p of problems) console.log('  ✗ ' + p)
if (problems.length) {
  console.log(`\nMODULES FAILED (${problems.length} of ${checked} references unresolved)`)
  process.exit(1)
}
console.log(`  ✓ all ${checked} local references resolve`)
console.log('\nMODULES OK')
