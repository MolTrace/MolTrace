'use strict'
// The whole vertical, from a click in the page to a table in the page.
//
// Every other suite here tests one layer. This is the only one that proves they
// connect: the renderer's button, the contextBridge, the IPC handler, the
// capability gate, the per-launch credential, the owner-only socket, the
// packaged Python service, a REAL instrument acquisition, and the DOM that comes
// back. It exists because the layers were each proven separately once before and
// the thing still did nothing -- `spawnPlan` was defined and never called.
//
// THE ONLY STUB IS ELECTRON'S FILE CHOOSER. It is Electron's code rather than
// ours, it cannot be driven headlessly, and stubbing it leaves every line this
// repository owns on the real path. Stated plainly because a test that quietly
// stubs more than it admits is worse than no test.
//
// SKIPS ARE LOUD. This needs a working `uv` environment for the service and a
// reference acquisition on disk; CI has neither. A skip that reads like a pass
// is how a suite comes to assert nothing while reporting green, so a skip here
// prints what was missing and why, and says NOTHING WAS ASSERTED.
const { app, BrowserWindow, dialog } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const problems = []
const asserted = []
function check(name, fn) {
  try { fn(); asserted.push(name); console.log(`  ✓ ${name}`) }
  catch (e) { problems.push(`${name} — ${e.message}`); console.log(`  ✗ ${name} — ${e.message}`) }
}

function skip(why) {
  console.log(`\nSPECTRUM ROUND TRIP SKIPPED — NOTHING WAS ASSERTED.\n  ${why}`)
  app.exit(0)
}

/** A public reference acquisition, by role. Never named in an assertion. */
function findAcquisition() {
  const root = path.join(__dirname, '..', '..', 'moltrace_backend', 'tests', 'fixtures',
    'nmrshiftdb2', 'raw', 'extracted')
  if (!fs.existsSync(root)) return null
  for (const dataset of fs.readdirSync(root)) {
    if (!/1h/i.test(dataset)) continue
    const datasetDir = path.join(root, dataset)
    if (!fs.statSync(datasetDir).isDirectory()) continue
    for (const expno of fs.readdirSync(datasetDir)) {
      const candidate = path.join(datasetDir, expno)
      if (fs.existsSync(path.join(candidate, 'pdata'))) return candidate
    }
  }
  return null
}

const WATCHDOG_MS = 180000
const watchdog = setTimeout(() => {
  console.log(`\nSPECTRUM ROUND TRIP TIMED OUT after ${WATCHDOG_MS}ms — treat as a failure, not a skip.`)
  try { require('../src/main.js').shutdown() } catch {}
  app.exit(1)
}, WATCHDOG_MS)
watchdog.unref()

const acquisition = findAcquisition()
let asked = 0
let pickerOptions = null
dialog.showOpenDialog = async (opts) => {
  asked++
  pickerOptions = opts
  return { canceled: false, filePaths: [acquisition] }
}

app.whenReady().then(async () => {
  if (!acquisition) return skip('no public reference acquisition is present in this checkout')

  const main = require('../src/main.js')
  let win
  for (let i = 0; i < 50 && !win; i++) {
    await new Promise((r) => setTimeout(r, 200))
    win = BrowserWindow.getAllWindows()[0]
  }
  if (!win) { clearTimeout(watchdog); console.log('\nSPECTRUM ROUND TRIP FAILED: no window opened'); return app.exit(1) }

  const text = () => win.webContents.executeJavaScript('document.body.innerText', true)
  let running = false
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 500))
    const t = await text()
    if (/service running/i.test(t) && !/not running/i.test(t)) { running = true; break }
  }
  if (!running) {
    main.shutdown()
    return skip('the local science service did not start here — it needs a working `uv` environment')
  }

  const clicked = await win.webContents.executeJavaScript(
    "(()=>{const b=document.querySelector('.analysis__open'); if(!b) return 'NO BUTTON'; b.click(); return 'clicked'})()", true)
  if (clicked !== 'clicked') {
    main.shutdown()
    return skip('the analysis button was not offered — this build declares no preview products')
  }

  for (let i = 0; i < 120; i++) {
    await new Promise((r) => setTimeout(r, 500))
    const done = await win.webContents.executeJavaScript(
      "!!document.querySelector('.peaks tbody tr') || !!document.querySelector('.analysis__error')", true)
    if (done) break
  }

  const raw = await win.webContents.executeJavaScript([
    '(()=>{',
    "  const err = document.querySelector('.analysis__error')",
    "  const g = (s) => { const e = document.querySelector(s); return e ? e.textContent : null }",
    "  const all = (s) => [].slice.call(document.querySelectorAll(s)).map(function(e){return e.textContent})",
    '  return JSON.stringify({',
    '    error: err ? err.textContent : null,',
    "    svgTicks: all('.spectrum__tick-label').map(parseFloat),",
    "    svgMarkers: document.querySelectorAll('.spectrum__marker').length,",
    "    svgCaption: g('.spectrum__caption'),",
    "    sectionHeadings: all('.peaks-section__heading'),",
    "    head: g('.result__head'), counts: g('.result__counts'),",
    "    heads: all('.peaks thead th'), limits: all('.result__limits li'),",
    "    rows: [].slice.call(document.querySelectorAll('.peaks tbody tr')).map(function(tr){",
    '      return [].slice.call(tr.cells).map(function(c){ return c.textContent })',
    '    }),',
    '  })',
    '})()',
  ].join('\n'), true)
  const dom = JSON.parse(raw)

  console.log('')
  check('the click reached the OS file chooser exactly once', () => {
    if (asked !== 1) throw new Error(`the chooser was invoked ${asked} times`)
  })
  check('the chooser offers files AND directories', () => {
    // A Bruker acquisition is a directory; JCAMP-DX is a file. Offering one makes
    // half the instruments in a lab unopenable.
    const p = (pickerOptions && pickerOptions.properties) || []
    if (!p.includes('openFile') || !p.includes('openDirectory')) {
      throw new Error(`properties were ${JSON.stringify(p)}`)
    }
  })
  check('a real acquisition produced a table, not an error', () => {
    if (dom.error) throw new Error(dom.error)
    if (!dom.rows.length) throw new Error('no rows rendered')
  })
  check('lines were GROUPED into signals, not listed raw', () => {
    // The detector over-picks. A row per fitted line misstates how many signals
    // the spectrum contains, which is the first thing a chemist would catch.
    const m = /(\d+) signals resolved from (\d+) fitted lines/.exec(dom.counts || '')
    if (!m) throw new Error(`counts line did not say what it resolved: ${dom.counts}`)
    const [, signals, lines] = m
    if (Number(signals) >= Number(lines)) throw new Error(`${signals} signals from ${lines} lines — nothing was grouped`)
    if (Number(signals) !== dom.rows.length) throw new Error(`said ${signals} signals, rendered ${dom.rows.length} rows`)
  })
  check('areas are labelled as a SHARE, never as protons', () => {
    // Without an assigned structure there is nothing to normalise a proton count
    // against, so a column headed H would be a number nothing computed.
    const heads = dom.heads.join('|')
    if (/\bH\b/.test(heads)) throw new Error(`a proton-count column was rendered: ${heads}`)
    if (!/share/i.test(heads)) throw new Error(`no share-of-signal column: ${heads}`)
  })
  check('the spectrum itself is drawn, not just tabulated', () => {
    // A peak table with no trace beside it cannot be checked. Reading NMR is
    // looking at the lines and the numbers together; a chemist handed only a
    // table has to take every row on trust.
    if (!dom.svgTicks || dom.svgTicks.length < 2) throw new Error('no spectrum was drawn')
    if (!dom.svgCaption) throw new Error('the trace carries no caption saying how it was reduced')
  })

  check('the ppm axis runs the way a chemist reads it', () => {
    // Right to left, high ppm first. An axis the other way round is one they
    // have to translate every single time.
    const t = dom.svgTicks
    for (let i = 1; i < t.length; i++) {
      if (!(t[i - 1] >= t[i])) throw new Error(`ppm ascends left to right: ${t.join(', ')}`)
    }
  })

  check('every reported signal is findable on the trace', () => {
    if (dom.svgMarkers !== dom.rows.length) {
      throw new Error(`${dom.rows.length} rows in the table but ${dom.svgMarkers} marked on the spectrum`)
    }
  })

  check('measurable and merely-detected signals are separate claims', () => {
    // A three-sigma bump and a real carbon are not the same kind of row. On a
    // real acquisition 47 of 55 signals sat at the detection floor, and every
    // one outside the range carbon-13 shifts occupy was among them.
    const headings = (dom.sectionHeadings || []).join(' | ')
    if (!/measure/i.test(headings)) {
      throw new Error(`the table does not separate what can be measured: ${headings}`)
    }
  })

  check('the screen says WHERE the numbers came from', () => {
    // An acquisition may carry a spectrum the instrument processed, or only the
    // raw measurement this application then processed with its own phasing and
    // baseline settings. Those are different numbers, and a chemist comparing
    // them to their spectrometer's printout needs to know which they are looking
    // at before they call a difference a defect.
    const said = dom.counts || ''
    if (!/instrument|computed here/i.test(said)) {
      throw new Error(`nothing says which processing produced these numbers: ${said}`)
    }
  })

  check('the table says how wide each signal is', () => {
    // Two lines closer than the analysis can separate are reported as one, and
    // width is the only thing on screen that shows it happened.
    const heads = dom.heads.join('|')
    if (!/width/i.test(heads)) throw new Error(`no width column: ${heads}`)
  })

  check('the limits state what cannot be separated at all', () => {
    const joined = (dom.limits || []).join(' ')
    if (!/closer together than about [\d.]+ Hz/.test(joined)) {
      throw new Error('nothing states the resolution limit of this analysis')
    }
  })

  check('the limits are rendered with the numbers, every time', () => {
    if (dom.limits.length < 3) throw new Error(`only ${dom.limits.length} limits rendered`)
    const joined = dom.limits.join(' ').toLowerCase()
    if (!/ratio/.test(joined)) throw new Error('nothing says the areas are ratios')
    if (!/structure/.test(joined)) throw new Error('nothing says this was not checked against a structure')
  })
  check('no filesystem path is rendered on screen', () => {
    // A path carries a compound name into a screenshot.
    const shown = [dom.head, dom.counts].concat(dom.limits).join(' ')
    if (/(?:\/[\w.-]+){2,}/.test(shown)) throw new Error(`a path was rendered: ${dom.head}`)
  })
  check('the acquisition is named in a way that identifies it', () => {
    // A Bruker experiment directory is a bare number; "251" tells a chemist
    // nothing about which sample they opened.
    if (!dom.head) throw new Error('nothing names the acquisition')
    const name = dom.head.split('—')[0].trim()
    if (/^\d+$/.test(name)) throw new Error(`the acquisition is named "${name}", which identifies nothing`)
  })

  // ---- the structure feeding back into the measurement ---------------------
  //
  // Everything above measures the spectrum. This types a structure and asserts
  // what comes back the other way. Deliberately structure-INDEPENDENT: the
  // fixture is whichever acquisition this checkout happens to hold, so the
  // assertions are invariants that must hold for any structure against any
  // spectrum, not facts about one molecule.
  const typed = await win.webContents.executeJavaScript([
    '(()=>{',
    '  const i = document.querySelector(\'input[aria-label="Candidate structure as SMILES"]\')',
    "  if (!i) return 'NO INPUT'",
    "  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set",
    "  setter.call(i, 'C=CCOCC1CO1')",
    "  i.dispatchEvent(new Event('input', { bubbles: true }))",
    "  const b = [...document.querySelectorAll('button')].find(x => /^Check structure/.test(x.textContent.trim()))",
    "  if (!b) return 'NO BUTTON'",
    '  b.click(); return \'clicked\'',
    '})()',
  ].join('\n'), true)

  if (typed === 'clicked') {
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 500))
      const settled = await win.webContents.executeJavaScript(
        "/Expected against observed|Proton counts|could not be worked out|was not checked/.test(document.body.textContent||'')", true)
      if (settled) break
    }
    const inv = await win.webContents.executeJavaScript(
      "(()=>{const t=document.body.textContent||''; return JSON.stringify({"
      + "counts: /Nearest whole/.test(t), circular: /totals match because they were made to/i.test(t),"
      + "declined: /Proton counts/.test(t) && !/Nearest whole/.test(t),"
      + "regions: /Region of the spectrum/.test(t),"
      + "path: /(?:\\/[\\w.-]+){2,}/.test(t)})})()", true)
    const got = JSON.parse(inv)

    check('a checked structure produces proton counts or says why not', () => {
      if (!got.counts && !got.declined) {
        throw new Error('the structure check produced neither proton counts nor a stated reason')
      }
    })
    // THE ONE THAT MATTERS. The counts sum to the structure's hydrogen count
    // because the scale was chosen to make them; shown without that sentence,
    // the bottom row reads as confirmation of the structure it assumed.
    check('proton counts never appear without saying the total is circular', () => {
      if (got.counts && !got.circular) {
        throw new Error('proton counts rendered with no note that the total agrees by construction')
      }
    })
    check('shift regions are labelled as regions, not as assignments', () => {
      if (got.counts && !got.regions) throw new Error('the expected-vs-observed table did not render')
    })
    check('counting protons renders no filesystem path', () => {
      if (got.path) throw new Error('a path was rendered by the proton-count panel')
    })
  }

  clearTimeout(watchdog)
  main.shutdown()
  console.log(problems.length
    ? `\nSPECTRUM ROUND TRIP FAILED (${problems.length})`
    : `\nSPECTRUM ROUND TRIP OK — ${asserted.length} assertions, real service, real acquisition`)
  setTimeout(() => app.exit(problems.length ? 1 : 0), 400)
})
