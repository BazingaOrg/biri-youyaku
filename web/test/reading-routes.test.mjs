import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('completion opens the formal document only after a running task finishes', async () => {
  const source = await readFile(new URL('../src/pages/Workspace.tsx', import.meta.url), 'utf8')

  assert.match(source, /pendingReadJobRef.current = jobId/)
  assert.match(source, /if \(pendingReadJobRef.current !== jobId\) return/)
  assert.match(source, /navigate\(docHref\(job.document_id, \{from: 'task'\}\), \{replace: true\}\)/)
  assert.match(source, /navigate\(docHref\(jobId, \{from: 'task'\}\)\)/)
})

test('job-based reading fallbacks canonicalize to the document id', async () => {
  const source = await readFile(new URL('../src/pages/DocumentPage.tsx', import.meta.url), 'utf8')

  assert.match(source, /response.job.document_id && response.job.document_id !== id/)
  assert.match(source, /docHref\(response.job.document_id\)/)
  assert.match(source, /\{replace: true\}/)
  assert.match(source, /setLegacyJob\(response.job\)/)
})

test('home, import, and UP reading actions use the formal document route', async () => {
  const composerSource = await readFile(new URL('../src/hooks/useOmniComposer.ts', import.meta.url), 'utf8')
  const browseSource = await readFile(new URL('../src/components/BrowseOmni.tsx', import.meta.url), 'utf8')
  const videoSource = await readFile(new URL('../src/pages/up/VideoRow.tsx', import.meta.url), 'utf8')

  assert.match(composerSource, /if \(response.deduped\) \{\s+navigate\(docHref\(response.job_id\)\)/)
  assert.match(browseSource, /deduped \? docHref\(jobId, \{from: 'task'\}\) : `\/jobs\/\$\{jobId\}`/)
  assert.match(videoSource, /video.document_id \|\| jobId/)
  assert.match(videoSource, /docHref\(readId, \{from: 'up'\}\)/)
  assert.match(videoSource, /阅读笔记/)
})
