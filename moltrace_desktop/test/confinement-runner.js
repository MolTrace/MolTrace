'use strict'
// Runs the §8.3 confinement assertions against EVERY live renderer.
//
// Capture point is `app.on('web-contents-created')`, NOT `did-create-window`.
// electron.d.ts:20412-20415 — a WindowOpenHandlerResponse.createWindow handler is
// "called instead of new BrowserWindow and event did-create-window will NOT be
// emitted". A test hooked on did-create-window is structurally blind to that path
// while the child renderer exists and holds whatever authority it was given.

const { app } = require('electron')
const { PROBE, assertRendererConfined, assertPreloadConfined, assertDeclaredConfinement, assertOsSandboxNotDisabled } = require('./confinement')
const fs = require('node:fs')
const path = require('node:path')

const seen = new Set()
app.on('web-contents-created', (_e, wc) => seen.add(wc))

// WATCHDOG. Two CI runners sat in this script for five hours and twenty minutes
// each before a human noticed, and the log's last line was from before the
// assertions started — so it said nothing about where it stopped. A security
// test that hangs is worse than one that fails: a failure is a red mark someone
// acts on, a hang is a spinner someone waits out. This bounds the run and names
// the stage it died in.
//
// The job also carries a `timeout-minutes` in CI. Both are wanted: this one
// reports the stage, that one survives this file being wrong.
let stage = 'starting'
const WATCHDOG_MS = Number(process.env.MOLTRACE_CONFINEMENT_TIMEOUT_MS || 120000)
const watchdog = setTimeout(() => {
  console.error(`\nCONFINEMENT TIMED OUT after ${WATCHDOG_MS}ms during: ${stage}`)
  try { require('../src/main.js').shutdown() } catch {}
  app.exit(1)
}, WATCHDOG_MS)
watchdog.unref()

async function waitFor(condition, timeoutMs, what) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (condition()) return
    await new Promise((r) => setTimeout(r, 100))
  }
  // Not a throw: the assertions below should still run and report what they can,
  // and "never became visible" is itself one of the things worth asserting.
  console.error(`  (timed out after ${timeoutMs}ms waiting for ${what})`)
}

// app.exit() does NOT emit `will-quit`, so the app's own cleanup never runs on
// this path. Measured: after app.exit(0) the `uv` and `python` processes were
// still alive and reparented to init. Every exit here goes through this.
function leave(code) {
  try { require('../src/main.js').shutdown() } catch {}
  clearTimeout(watchdog)
  app.exit(code)
}

function fail(lines) {
  console.error('\nCONFINEMENT FAILED:')
  for (const l of lines) console.error('  ✗ ' + l)
  leave(1)
}

async function run() {
  // Boot the real main process. It must not be a test-only window factory —
  // the point is to assert what the SHIPPING main process produces.
  stage = 'booting the main process'
  const main = require('../src/main.js')

  // Waits for the CONDITION rather than sleeping a fixed 2500ms. The fixed sleep
  // was a flake: starting the local service competes for the event loop, a cold
  // subprocess makes that competition slower, and `ready-to-show` slipped past
  // the deadline -- reporting "the build launches to nothing" for a scheduling
  // reason. A security test that passes two runs in three is worse than one that
  // fails, because the third result gets explained away.
  //
  // `waitFor` existed for this and was never called. The helper was written, the
  // call site was not changed, and the flake survived a fix that looked applied.
  const { BrowserWindow: BW } = require('electron')
  stage = 'waiting for a visible window'
  await waitFor(() => BW.getAllWindows().some((w) => w.isVisible()), 20000, 'a visible window')

  stage = 'collecting renderers'
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

  // A window nobody can see is not a shipped product. `show: false` with no
  // show() call launched a configured build that displayed nothing, and every
  // other layer here passed — a webContents exists whether or not anyone can
  // look at it. Asserted here because this is the only test that drives a real
  // window.
  const windows = BW.getAllWindows()
  if (windows.length === 0) {
    problems.push('[window] no window was created')
  } else if (!windows.some((w) => w.isVisible())) {
    problems.push('[window] a window was created but none is visible — the build launches to nothing')
  }

  // Layer 0: the OS-level sandbox. Checked first because if it is off, every
  // layer below is reporting on a weaker process than the one that ships.
  problems.push(...assertOsSandboxNotDisabled(require('electron').app.commandLine))

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

  stage = 'probing renderers'
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
  leave(0)
}

app.whenReady().then(run).catch((e) => fail([String(e && e.stack || e)]))
