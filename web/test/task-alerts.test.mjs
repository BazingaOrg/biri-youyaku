import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import test from 'node:test'
import {
  ACTIVE_TASK_ALERT_REFRESH_MS,
  IDLE_TASK_ALERT_REFRESH_MS,
  createTaskAlertsRefresher,
  taskAlertRefreshDelay,
} from '../src/lib/taskAlerts.ts'
import {isRunning} from '../src/lib/jobStatus.ts'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return {promise, resolve, reject}
}

test('task alerts coalesce concurrent refreshes and publish one filtered snapshot', async () => {
  const active = deferred()
  const terminal = deferred()
  const calls = []
  const updates = []
  const refresher = createTaskAlertsRefresher({
    isRunning,
    loadJobs: (params) => {
      calls.push(params)
      return params.active_only ? active.promise : terminal.promise
    },
    onUpdate: (update) => updates.push(update),
  })

  const first = refresher.refresh()
  const duplicate = refresher.refresh()
  assert.equal(duplicate, first)
  assert.equal(calls.length, 2)

  active.resolve({jobs: [{id: 'running', status: 'SUMMARIZING'}]})
  terminal.resolve({jobs: [
    {id: 'failed', status: 'FAILED'},
    {id: 'completed', status: 'COMPLETED'},
  ]})
  await first

  assert.deepEqual(updates, [{
    running: [{id: 'running', status: 'SUMMARIZING'}],
    failed: [{id: 'failed', status: 'FAILED'}],
  }])
})

test('mutation invalidation chains one trailing snapshot without overlap', async () => {
  const requests = []
  const refresher = createTaskAlertsRefresher({
    isRunning,
    loadJobs: (params) => {
      const request = deferred()
      requests.push({params, ...request})
      return request.promise
    },
    onUpdate: () => {},
  })

  const initial = refresher.refresh()
  const invalidated = refresher.invalidate()
  const duplicateInvalidation = refresher.invalidate()
  assert.equal(requests.length, 2)

  for (const request of requests.slice(0, 2)) request.resolve({jobs: []})
  await initial
  assert.equal(requests.length, 4, 'both invalidations share one trailing request pair')

  for (const request of requests.slice(2)) request.resolve({jobs: []})
  await Promise.all([invalidated, duplicateInvalidation])
  assert.equal(requests.length, 4)
})

test('app has one root task alerts provider for shell and library consumers', () => {
  const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const shell = readFileSync(new URL('../src/components/AppShell.tsx', import.meta.url), 'utf8')
  const library = readFileSync(new URL('../src/pages/LibraryPage.tsx', import.meta.url), 'utf8')
  const hook = readFileSync(new URL('../src/hooks/useTaskAlerts.ts', import.meta.url), 'utf8')

  assert.equal(app.match(/<TaskAlertsProvider>/g)?.length, 1)
  assert.match(shell, /useTaskAlerts\(\)/)
  assert.match(library, /useTaskAlerts\(\)/)
  assert.doesNotMatch(hook, /setInterval|listJobs|createTaskAlertsRefresher/)
})

test('abort permits an immediate StrictMode restart without stale state updates', async () => {
  const requests = []
  const updates = []
  const refresher = createTaskAlertsRefresher({
    isRunning,
    loadJobs: (params) => {
      const request = deferred()
      requests.push({params, ...request})
      return request.promise
    },
    onUpdate: (update) => updates.push(update),
  })

  const aborted = refresher.refresh()
  const invalidated = refresher.invalidate()
  refresher.abort()
  const restarted = refresher.refresh()
  assert.notEqual(restarted, aborted)

  for (const request of requests.slice(0, 2)) {
    request.resolve({jobs: [{id: 'stale', status: 'FAILED'}]})
  }
  await Promise.all([aborted, invalidated])
  assert.equal(refresher.refresh(), restarted, 'aborted completion must not clear the new request')
  assert.equal(requests.length, 4, 'aborted invalidation must not start a trailing request')
  assert.deepEqual(updates, [])

  for (const request of requests.slice(2)) {
    request.resolve({jobs: []})
  }
  await restarted
  assert.deepEqual(updates, [{running: [], failed: []}])
})

test('a failed request pair does not block later recovery', async () => {
  let shouldFail = true
  const updates = []
  const refresher = createTaskAlertsRefresher({
    isRunning,
    loadJobs: async () => {
      if (shouldFail) throw new Error('offline')
      return {jobs: []}
    },
    onUpdate: (update) => updates.push(update),
  })

  await refresher.refresh()
  assert.deepEqual(updates, [])
  shouldFail = false
  await refresher.refresh()
  assert.deepEqual(updates, [{running: [], failed: []}])
})

test('activity refreshes are throttled and polling slows while idle', async () => {
  let now = 1000
  const refresher = createTaskAlertsRefresher({
    isRunning,
    loadJobs: async () => ({jobs: []}),
    onUpdate: () => {},
    now: () => now,
  })

  await refresher.refresh()
  assert.equal(refresher.shouldRefreshOnActivity(), false)
  now += 999
  assert.equal(refresher.shouldRefreshOnActivity(), false)
  now += 1
  assert.equal(refresher.shouldRefreshOnActivity(), true)
  assert.equal(taskAlertRefreshDelay(true), ACTIVE_TASK_ALERT_REFRESH_MS)
  assert.equal(taskAlertRefreshDelay(false), IDLE_TASK_ALERT_REFRESH_MS)
})
