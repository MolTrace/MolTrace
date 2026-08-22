'use strict'
// §7.1: "Distinguish the four upgrade states, and never render a capability as
// available and fail on click." §4.2: the four causes "imply four different next
// actions. Presenting them as one denial sends a user to the wrong place."
//
// The readout decides availability; this decides what a person is TOLD. A readout
// that distinguishes four states, rendered as one grey "unavailable", has thrown
// the distinction away at the last step.
const assert = require('node:assert')
const view = require('../src/capability-view.js')
const caps = require('../src/capabilities.js')

const results = []
const check = (n, f) => { try { f(); results.push(['PASS', n]) } catch (e) { results.push(['FAIL', n + ' — ' + e.message]) } }

const locked = (code) => ({ key: 'k', displayName: 'Process a raw acquisition', available: false, code, reason: 'because reasons' })

check('the four states produce four DIFFERENT next actions', () => {
  const actions = caps.LOCKED_CODES.map((c) => view.present(locked(c)).action)
  assert.strictEqual(new Set(actions).size, 4,
    `four causes collapsed to ${new Set(actions).size} action(s): ${[...new Set(actions)].join(' | ')}`)
})

check('every locked state names an action, not just a status', () => {
  for (const c of caps.LOCKED_CODES) {
    const p = view.present(locked(c))
    assert.ok(p.action && p.action.length > 8, `${c} has no next action`)
    assert.ok(/[a-z]/.test(p.action), `${c}'s action is not a sentence`)
  }
})

check('the four states are visually distinguishable, not one grey box', () => {
  const tones = caps.LOCKED_CODES.map((c) => view.present(locked(c)).tone)
  assert.ok(new Set(tones).size >= 2,
    'every locked state renders with the same tone — the distinction is thrown away at the last step')
})

check('an available capability renders as available and offers no upsell', () => {
  const p = view.present({ key: 'k', displayName: 'X', available: true, code: null, reason: null })
  assert.strictEqual(p.available, true)
  assert.strictEqual(p.action, null, 'an available capability was given a next action')
})

check('an UNKNOWN code still renders something — no silent gap', () => {
  // Fail loud, not blank. A code this view has not been taught about must not
  // render as an empty cell that reads like "fine".
  const p = view.present(locked('something_new_the_backend_added'))
  assert.ok(p.action && p.action.length > 8, 'an unrecognised state rendered with no action')
  assert.strictEqual(p.available, false, 'an unrecognised state was treated as available')
})

check('nothing rendered carries backend jargon', () => {
  for (const c of [...caps.LOCKED_CODES, 'unrecognised']) {
    const p = view.present(locked(c))
    const text = `${p.headline} ${p.action}`
    assert.ok(!/[0-9]{3}\b|HTTP|GET |POST |_json|endpoint|\bnull\b|env |product_not_|role_required/.test(text),
      `${c} leaks jargon: ${text}`)
  }
})

check('the machine code is carried for the client, but never shown', () => {
  const p = view.present(locked('product_not_in_plan'))
  assert.strictEqual(p.code, 'product_not_in_plan', 'the code was dropped — a client cannot branch')
  assert.ok(!`${p.headline} ${p.action}`.includes('product_not_in_plan'), 'the code leaked into copy')
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nUPGRADE STATES FAILED (${failed})` : `\nUPGRADE STATES OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
