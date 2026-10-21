import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('search page scopes and highlights without inventing library-wide totals', async () => {
  const searchSource = await readFile(new URL('../src/pages/SearchPage.tsx', import.meta.url), 'utf8')
  const librarySource = await readFile(new URL('../src/pages/LibraryPage.tsx', import.meta.url), 'utf8')
  const omniSource = await readFile(new URL('../src/components/OmniBar.tsx', import.meta.url), 'utf8')

  assert.match(searchSource, /label: '全部'/)
  assert.match(searchSource, /label: '笔记'/)
  assert.match(searchSource, /label: '字幕'/)
  assert.match(searchSource, /mode="fts"/)
  assert.match(searchSource, /query=\{result\.query\}/)
  assert.match(searchSource, /result\?\.hit_counts\?\.notes \?\? notes/)
  assert.match(searchSource, /已在标题、UP 主、BV 号、标签、笔记和字幕中查找/)
  assert.doesNotMatch(searchSource, /搜索笔记或字幕/)
  assert.match(omniSource, /生成笔记/)
  assert.match(librarySource, /OmniBar/)
  assert.match(librarySource, /grid min-w-0 gap-1/)
  assert.doesNotMatch(librarySource, /开始总结/)
  assert.doesNotMatch(librarySource, /清理历史/)
})
