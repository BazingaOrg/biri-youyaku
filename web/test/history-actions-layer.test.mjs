import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('history bulk delete is a direct control without a popover', async () => {
  const pageSource = await readFile(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8')

  assert.match(pageSource, /bulkDeleteLabel = hasFilters \? '删除筛选结果' : '清理历史'/)
  assert.match(pageSource, /aria-label={bulkDeleteLabel}/)
  assert.doesNotMatch(pageSource, /更多操作/)
  assert.doesNotMatch(pageSource, /openMenuKey/)
  assert.doesNotMatch(pageSource, /data-history-menu-root/)
  assert.doesNotMatch(pageSource, /<section key={group\.weekStart} className="overflow-hidden rounded-2xl/)
  assert.doesNotMatch(pageSource, /<details/)
})
