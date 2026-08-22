'use strict'
// §7.1: "Report module, local-pack, network, and service capabilities at startup
// as a single desktop capability readout, assembled by the desktop from the
// module set, the entitlement statement, the local pack inventory, and the
// reachable service versions — because no server endpoint aggregates them."
// And: "Distinguish the four upgrade states, and never render a capability as
// available and fail on click."
const assert = require('node:assert')
const caps = require('../src/capabilities.js')

const results = []
const check = (n, f) => { try { f(); results.push(['PASS', n]) } catch (e) { results.push(['FAIL', n + ' — ' + e.message]) } }

// A fully-satisfied world, used as the baseline every case degrades from.
const OK = {
  modules: ['spectracheck'],
  entitlement: { valid: true, modules: ['spectracheck'] },
  packs: ['rules-ich'],
  service: { reachable: true, versions: { fid: '1' } },
  role: 'analyst',
}
const CAP = {
  key: 'fid.process',
  displayName: 'Process a raw acquisition',
  requiresModule: 'spectracheck',
  requiresPack: 'rules-ich',
  requiresService: 'fid',
  requiresRole: 'analyst',
}

check('a fully-satisfied capability is available', () => {
  const r = caps.assess(CAP, OK)
  assert.strictEqual(r.available, true, r.reason || '')
})

check('available:true is never returned with an unmet gate', () => {
  // The §7.1 invariant, checked exhaustively rather than by example: drop each
  // input in turn and assert nothing stays available.
  const worlds = [
    ['no module', { ...OK, modules: [] }],
    ['entitlement invalid', { ...OK, entitlement: { valid: false, modules: [] } }],
    ['pack missing', { ...OK, packs: [] }],
    ['service unreachable', { ...OK, service: { reachable: false, versions: {} } }],
    ['service reachable but lacks the engine', { ...OK, service: { reachable: true, versions: {} } }],
    ['wrong role', { ...OK, role: 'viewer' }],
  ]
  for (const [label, world] of worlds) {
    const r = caps.assess(CAP, world)
    assert.strictEqual(r.available, false, `stayed available with ${label}`)
    assert.ok(r.reason, `no reason given for ${label}`)
  }
})

check('an ABSENT input fails closed rather than assuming yes', () => {
  for (const k of ['modules', 'entitlement', 'packs', 'service', 'role']) {
    const world = { ...OK }
    delete world[k]
    const r = caps.assess(CAP, world)
    assert.strictEqual(r.available, false, `missing ${k} was treated as satisfied`)
  }
})

check('the four locked states are distinguishable, not one denial', () => {
  const seen = new Set()
  seen.add(caps.assess(CAP, { ...OK, modules: [] }).code)
  seen.add(caps.assess(CAP, { ...OK, entitlement: { valid: false, modules: [] } }).code)
  seen.add(caps.assess(CAP, { ...OK, packs: [] }).code)
  seen.add(caps.assess(CAP, { ...OK, role: 'viewer' }).code)
  assert.strictEqual(seen.size, 4, `four causes collapsed to ${seen.size} code(s): ${[...seen].join(', ')}`)
})

check('every locked code is one the platform already defines', () => {
  // §4.2's vocabulary. Inventing a fifth word here would mean the desktop and the
  // web surface name the same situation differently.
  for (const world of [
    { ...OK, modules: [] },
    { ...OK, entitlement: { valid: false, modules: [] } },
    { ...OK, packs: [] },
    { ...OK, role: 'viewer' },
  ]) {
    const r = caps.assess(CAP, world)
    assert.ok(caps.LOCKED_CODES.includes(r.code), `${r.code} is not in the platform vocabulary`)
  }
})

check('a reason names its cause in words a person reads', () => {
  const r = caps.assess(CAP, { ...OK, packs: [] })
  assert.ok(r.reason.length > 10, 'reason is not a sentence')
  assert.ok(!/[0-9]{3}|HTTP|GET |POST |_json|endpoint|env |null/.test(r.reason),
    `reason leaks backend jargon: ${r.reason}`)
  assert.ok(r.reason.includes(CAP.displayName) || r.reason.length > 20,
    'reason does not identify what is locked')
})

check('the readout covers every declared capability, with no silent omission', () => {
  const all = caps.readout([CAP, { ...CAP, key: 'other', requiresRole: 'admin' }], OK)
  assert.strictEqual(all.length, 2)
  assert.ok(all.every((r) => typeof r.available === 'boolean' && r.key))
})

check('an unconfigured world makes NOTHING available', () => {
  const all = caps.readout([CAP], {})
  assert.ok(all.every((r) => r.available === false), 'a capability survived an empty world')
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nCAPABILITIES FAILED (${failed})` : `\nCAPABILITIES OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
