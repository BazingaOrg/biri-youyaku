import assert from 'node:assert/strict'
import test from 'node:test'
import {SUMMARY_FLUSH_INTERVAL_MS, createSummaryThrottler} from '../src/lib/summaryThrottle.ts'

test('summary throttle emits only the latest snapshot at each trailing flush', (t) => {
  t.mock.timers.enable({apis: ['setTimeout']})
  const emitted = []
  const throttler = createSummaryThrottler((summary) => emitted.push(summary))

  throttler.push('first')
  t.mock.timers.tick(SUMMARY_FLUSH_INTERVAL_MS - 1)
  throttler.push('first and second')
  assert.deepEqual(emitted, [])

  t.mock.timers.tick(1)
  assert.deepEqual(emitted, ['first and second'])
  throttler.push('third')
  t.mock.timers.tick(SUMMARY_FLUSH_INTERVAL_MS)
  assert.deepEqual(emitted, ['first and second', 'third'])
})

test('summary throttle bounds render frequency and cancels pending output', (t) => {
  t.mock.timers.enable({apis: ['setTimeout']})
  const emitted = []
  const throttler = createSummaryThrottler((summary) => emitted.push(summary))

  for (let index = 1; index <= 32; index += 1) {
    throttler.push(`snapshot ${index}`)
    t.mock.timers.tick(16)
  }
  t.mock.timers.tick(SUMMARY_FLUSH_INTERVAL_MS)
  assert.equal(emitted.length, 4)
  assert.equal(emitted.at(-1), 'snapshot 32')

  throttler.push('must not render')
  throttler.cancel()
  t.mock.timers.tick(SUMMARY_FLUSH_INTERVAL_MS * 2)
  assert.equal(emitted.at(-1), 'snapshot 32')
})
