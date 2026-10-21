import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('task page deletes job records without bulk history cleanup', async () => {
  const pageSource = await readFile(new URL('../src/pages/TasksPage.tsx', import.meta.url), 'utf8')

  assert.match(pageSource, /管理任务记录/)
  assert.match(pageSource, /deleteJob\(jobId\)/)
  assert.match(pageSource, /deleteJob\(job\.id\)/)
  assert.match(pageSource, /type="checkbox"/)
  assert.match(pageSource, /删除所选/)
  assert.match(pageSource, /笔记还在/)
  assert.match(pageSource, /aria-label="删除"/)
  assert.doesNotMatch(pageSource, /清理历史/)
  assert.doesNotMatch(pageSource, /previewBulkDelete/)
  assert.doesNotMatch(pageSource, /更多操作/)
})
