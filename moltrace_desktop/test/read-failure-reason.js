'use strict'
// A service that REFUSES a file is a service that is working. Saying it is dead
// sends the reader to restart the app, which cannot change the answer.
//
// Before this, `main.js` funnelled every per-file failure through
// `describeFailure`, whose whole job is to describe a dead child: the reader was
// told "The local science service is not running, so analysis on this computer is
// unavailable." even when the service had just read their file and named exactly
// what was wrong with it.
const assert = require('node:assert')

const results = []
const check = (name, fn) => {
  try { fn(); results.push(['PASS', name]) }
  catch (e) { results.push(['FAIL', name + ' — ' + e.message]) }
}

// main.js reaches into electron at require time, so the decision under test is
// exercised through its own module boundary rather than by booting a window.
const { readFailureReason } = require('../src/local-service.js')

check('a refusal the service ANSWERED with is passed through in its own words', () => {
  const err = new Error(
    "This acquisition's parameter file 'acqus' is incomplete: the entry 'PCPD' stops "
    + 'before its values do.',
  )
  err.answeredByService = true
  const reason = readFailureReason(err)
  assert.strictEqual(reason, err.message, 'the service\'s own sentence was replaced')
  assert.ok(!/not running/i.test(reason), 'a working service was described as not running')
  assert.ok(!/unavailable/i.test(reason), 'a working service was described as unavailable')
})

check('a service that never answered is still described as unreachable', () => {
  const reason = readFailureReason(new Error('connect ENOENT'))
  assert.ok(/not running|unavailable/i.test(reason), 'a dead service was not described as dead: ' + reason)
})

check('a refusal with no sentence falls back rather than reporting an empty reason', () => {
  const err = new Error('')
  err.answeredByService = true
  assert.ok(readFailureReason(err), 'an empty message produced an empty reason')
})

for (const [s, n] of results) console.log(`  ${s === 'PASS' ? '✓' : '✗'} ${n}`)
const failed = results.filter(([s]) => s === 'FAIL').length
console.log(failed ? `\nREAD FAILURE REASON FAILED (${failed})` : `\nREAD FAILURE REASON OK — ${results.length} assertions`)
process.exit(failed ? 1 : 0)
