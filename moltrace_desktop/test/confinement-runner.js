'use strict'
// Runs the §8.3 confinement assertions against EVERY live renderer.
//
// Capture point is `app.on('web-contents-created')`, NOT `did-create-window`.
// electron.d.ts:20412-20415 — a WindowOpenHandlerResponse.createWindow handler is
// "called instead of new BrowserWindow and event did-create-window will NOT be
// emitted". A test hooked on did-create-window is structurally blind to that path
// while the child renderer exists and holds whatever authority it was given.

const { app } = require('electron')
const { PROBE, assertRendererConfined, assertPreloadConfined, assertDeclaredConfinement } = require('./confinement')
const fs = require('node:fs')
const path = require('node:path')

const seen = new Set()
app.on('web-contents-created', (_e, wc) => seen.add(wc))

function fail(lines) {
  console.error('\nCONFINEMENT FAILED:')
  for (const l of lines) console.error('  ✗ ' + l)
  app.exit(1)
}

async function run() {
  // Boot the real main process. It must not be a test-only window factory —
  // the point is to assert what the SHIPPING main process produces.
  const main = require('../src/main.js')
  await new Promise((r) => setTimeout(r, 2500))

  const { webContents } = require('electron')
  const all = webContents.getAllWebContents()
  if (all.length === 0) return fail(['no renderers were created — nothing was asserted'])

  // Cross-check: every live webContents must have been seen by the hook. If the
  // hook missed one, the hook is the defect, not the renderer.
  const missed = all.filter((wc) => !seen.has(wc))
  if (missed.length) {
    return fail([`${missed.length} live renderer(s) never fired web-contents-created — the capture point is blind`])
  }

  const problems = []

  // Layer 2: the declared settings in the single construction site.
  problems.push(...assertDeclaredConfinement(require('../src/window-factory.js').CONFINEMENT))

  // Layer 3: there must BE a single construction site. A second `new BrowserWindow`
  // anywhere else would produce a window the factory never touched — and layers 1
  // and 2 would both still pass, because neither can see a window that was never
  // created during the test run.
  // Scans the WHOLE package, not just src/. A first version scanned src/ only —
  // and a stray identical copy of window-factory.js was then found sitting at the
  // package root, invisible to it. It was dead code, but a live one would have
  // been a second construction site the check could not see. The lesson is the
  // same one this test exists for: a guard is only as wide as what it walks.
  const pkgRoot = path.join(__dirname, '..')
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((d) => {
    if (d.name === 'node_modules' || d.name.startsWith('.')) return []
    const full = path.join(dir, d.name)
    return d.isDirectory() ? walk(full) : (d.name.endsWith('.js') ? [full] : [])
  })
  for (const full of walk(pkgRoot)) {
    const rel = path.relative(pkgRoot, full)
    if (rel === path.join('src', 'window-factory.js')) continue
    if (rel.startsWith('test' + path.sep)) continue
    if (/new\s+BrowserWindow\s*\(/.test(fs.readFileSync(full, 'utf8'))) {
      problems.push(`[${rel}] constructs BrowserWindow outside src/window-factory.js — the invariants are bypassable`)
    }
  }

  for (const wc of all) {
    if (wc.isDestroyed()) continue
    const url = wc.getURL() || '(no url)'
    let probe
    try {
      probe = await wc.executeJavaScript(PROBE, true)
    } catch (err) {
      problems.push(`[${url}] probe did not execute: ${err.message}`)
      continue
    }
    problems.push(...assertRendererConfined(url, probe))
    problems.push(...assertPreloadConfined(url, main.confinementReports.get(wc.id)))
  }

  if (problems.length) return fail(problems)
  console.log(`\nCONFINEMENT OK — ${all.length} renderer(s) asserted, all confined.`)
  app.exit(0)
}

app.whenReady().then(run).catch((e) => fail([String(e && e.stack || e)]))
