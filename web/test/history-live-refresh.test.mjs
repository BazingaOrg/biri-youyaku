import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('task list refreshes active jobs while the page remains open', async () => {
  const pageSource = await readFile(new URL('../src/pages/TasksPage.tsx', import.meta.url), 'utf8')

  assert.match(pageSource, /const ACTIVE_REFRESH_INTERVAL_MS = 2000/)
  assert.match(pageSource, /listJobs\(\{active_only: true\}, \{signal: controller\.signal\}\)/)
  assert.match(pageSource, /getJob\(jobId, \{signal: controller\.signal, lite: true\}\)/)
  assert.match(pageSource, /activeJobs\.length > 0 \? window\.setInterval\(refresh, ACTIVE_REFRESH_INTERVAL_MS\)/)
  assert.match(pageSource, /document\.addEventListener\('visibilitychange', onVisibilityChange\)/)
  assert.match(pageSource, /window\.addEventListener\('focus', refresh\)/)
  assert.match(pageSource, /if \(loading \|\| activeRefreshRef\.current\) return/)
  assert.match(pageSource, /now - lastActiveRefreshAtRef\.current < ACTIVE_REFRESH_THROTTLE_MS/)
  assert.match(pageSource, /ACTIVE_REFRESH_THROTTLE_MS = 1000/)
  assert.doesNotMatch(pageSource, /activeRefreshRef\.current\?\.abort\(\)\s*\n\s*const controller/)
})
