import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('history action menus are mutually exclusive and dismissible', async () => {
  const pageSource = await readFile(new URL('../src/pages/HistoryPage.tsx', import.meta.url), 'utf8')

  assert.match(pageSource, /const \[openMenuKey, setOpenMenuKey\]/)
  assert.match(pageSource, /document\.addEventListener\('pointerdown', onPointerDown\)/)
  assert.match(pageSource, /event\.key !== 'Escape'/)
  assert.match(pageSource, /aria-expanded={menuOpen}/)
  assert.match(pageSource, /menuOpen \? 'z-20' : ''/)
  assert.doesNotMatch(pageSource, /<details/)
})
