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

for (const p of problems) console.log('  ✗ ' + p)
if (problems.length) {
  console.log(`\nMODULES FAILED (${problems.length} of ${checked} references unresolved)`)
  process.exit(1)
}
console.log(`  ✓ all ${checked} local references resolve`)
console.log('\nMODULES OK')
