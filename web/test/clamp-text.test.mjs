import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('clamped titles use one line and a panel tooltip', async () => {
  const clamp = await readFile(new URL('../src/components/ClampText.tsx', import.meta.url), 'utf8')
  const pages = await Promise.all(
    ['LibraryPage.tsx', 'TrashPage.tsx', 'workspace/MetaBar.tsx', 'up/VideoRow.tsx'].map((name) =>
      readFile(new URL(`../src/pages/${name}`, import.meta.url), 'utf8'),
    ),
  )
  assert.match(clamp, /line-clamp-1/)
  assert.match(clamp, /bg-panel/)
  assert.match(clamp, /role="tooltip"/)
  for (const source of pages) {
    assert.match(source, /ClampText/)
    assert.doesNotMatch(source, /line-clamp-2/)
  }
})
