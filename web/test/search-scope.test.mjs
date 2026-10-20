import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('history and knowledge searches communicate separate scopes', async () => {
  const historySource = await readFile(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8')
  const knowledgeSource = await readFile(new URL('../src/pages/KnowledgePage.tsx', import.meta.url), 'utf8')

  assert.match(historySource, /筛选标题、UP 主、BV 号或标签/)
  assert.match(historySource, /<SearchHighlight text={job\.title \|\| job\.url}/)
  assert.match(historySource, /命中视频链接/)
  assert.match(historySource, /aria-label="删除"/)
  assert.doesNotMatch(historySource, /查看总结/)
  assert.doesNotMatch(historySource, /重新总结/)
  assert.match(knowledgeSource, /搜索笔记或字幕/)
  assert.match(knowledgeSource, /mode="fts"/)
  assert.match(knowledgeSource, /snippet !== full/)
  assert.match(knowledgeSource, /query={searchedQuery}/)
})
