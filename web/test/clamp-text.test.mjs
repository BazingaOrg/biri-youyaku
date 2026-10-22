import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('list routes wait with skeletons and a note opens with the rabbit', async () => {
  const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8')
  assert.match(app, /path="\/search"[\s\S]*?<Skeleton count=\{5\} \/>/)
  assert.match(app, /path="\/tasks"[\s\S]*?<Skeleton count=\{6\} \/>/)
  assert.match(app, /path="\/trash"[\s\S]*?<Skeleton count=\{4\} \/>/)
  assert.match(app, /path="\/doc\/:id"[\s\S]*?<PageLoading label="加载笔记…" \/>/)
  assert.match(app, /<Route path="\/">[\s\S]*?<Skeleton count=\{6\} \/>/)
  assert.doesNotMatch(app, /<Route path="\/">[\s\S]*?<PageLoading/)
})

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
  assert.match(clamp, /clientX/)
  assert.match(clamp, /space\.below/)
  assert.match(clamp, /space\.above/)
  assert.match(clamp, /space\.left/)
  assert.match(clamp, /space\.right/)
  for (const source of pages) {
    assert.match(source, /ClampText/)
    assert.doesNotMatch(source, /line-clamp-2/)
  }
})
