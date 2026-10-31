import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('completed job delegates full reading to the formal document page', async () => {
  const doneSource = await readFile(new URL('../src/pages/workspace/DoneView.tsx', import.meta.url), 'utf8')
  const documentSource = await readFile(new URL('../src/pages/DocumentPage.tsx', import.meta.url), 'utf8')

  assert.match(doneSource, /docHref\(job.document_id \|\| job.id, \{from: 'task'\}\)/)
  assert.doesNotMatch(doneSource, /SummaryTabs/)
  assert.doesNotMatch(doneSource, /复制总结全文/)
  assert.match(documentSource, /<LazyMarkdown markdown=\{markdown\} \/>/)
  assert.match(documentSource, /transcriptToPlainText\(cues\)/)
})

test('completed job actions stay on the toolbar without a more menu', async () => {
  const doneSource = await readFile(new URL('../src/pages/workspace/DoneView.tsx', import.meta.url), 'utf8')

  assert.match(doneSource, /onClick=\{onResummarize\}/)
  assert.match(doneSource, /阅读笔记/)
  assert.match(doneSource, /\{resummarizeBusy \? '重新生成中…' : '重新生成笔记'\}/)
  assert.doesNotMatch(doneSource, /<details/)
  assert.doesNotMatch(doneSource, /更多/)
  assert.doesNotMatch(doneSource, /下载 Markdown/)
  assert.doesNotMatch(doneSource, /onDownload/)
})
