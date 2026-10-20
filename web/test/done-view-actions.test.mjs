import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('completed job copy sits on the tab row and follows the active tab', async () => {
  const doneSource = await readFile(new URL('../src/pages/workspace/DoneView.tsx', import.meta.url), 'utf8')
  const tabsSource = await readFile(new URL('../src/pages/workspace/SummaryTabs.tsx', import.meta.url), 'utf8')

  assert.match(tabsSource, /tabs\.push\(\['transcript', '字幕'\]\)/)
  assert.match(tabsSource, /tab === 'notes' \? '复制笔记' : '复制字幕'/)
  assert.match(tabsSource, /ml-auto inline-flex min-h-9/)
  assert.match(tabsSource, /transcriptToPlainText\(job\.transcript/)
  assert.doesNotMatch(doneSource, /复制总结全文/)
  assert.doesNotMatch(doneSource, /onCopy/)
})

test('completed job actions stay on the toolbar without a more menu', async () => {
  const doneSource = await readFile(new URL('../src/pages/workspace/DoneView.tsx', import.meta.url), 'utf8')

  assert.match(doneSource, /onClick=\{onResummarize\}/)
  assert.match(doneSource, /\{resummarizeBusy \? '重新总结中…' : '重新总结'\}/)
  assert.doesNotMatch(doneSource, /<details/)
  assert.doesNotMatch(doneSource, /更多/)
  assert.doesNotMatch(doneSource, /下载 Markdown/)
  assert.doesNotMatch(doneSource, /onDownload/)
})
