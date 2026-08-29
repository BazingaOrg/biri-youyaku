import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('an open history action menu raises its animated row above later content', async () => {
  const [pageSource, styles] = await Promise.all([
    readFile(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/styles.css', import.meta.url), 'utf8'),
  ])

  assert.match(pageSource, /className="history-job[^"\n]*relative/)
  assert.match(styles, /\.history-job:has\(> details\[open\]\)\s*{\s*z-index:\s*20;/)
})
