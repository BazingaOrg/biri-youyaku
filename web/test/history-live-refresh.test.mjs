import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('history refreshes active jobs while the page remains open', async () => {
  const pageSource = await readFile(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8')

  assert.match(pageSource, /const ACTIVE_REFRESH_INTERVAL_MS = 2000/)
  assert.match(pageSource, /listJobs\(\{active_only: true, \.\.\.historyFilters\}, \{signal: controller\.signal\}\)/)
  assert.match(pageSource, /getJob\(jobId, \{signal: controller\.signal\}\)/)
  assert.match(pageSource, /window\.setInterval\(refresh, ACTIVE_REFRESH_INTERVAL_MS\)/)
  assert.match(pageSource, /document\.addEventListener\('visibilitychange', onVisibilityChange\)/)
  assert.match(pageSource, /window\.addEventListener\('focus', refresh\)/)
})
