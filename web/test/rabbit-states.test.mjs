import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('rabbit moods cover empty, miss, error, and loading', async () => {
  const rabbit = await readFile(new URL('../src/components/Rabbit.tsx', import.meta.url), 'utf8')
  const library = await readFile(new URL('../src/pages/LibraryPage.tsx', import.meta.url), 'utf8')
  const tasks = await readFile(new URL('../src/pages/TasksPage.tsx', import.meta.url), 'utf8')
  const search = await readFile(new URL('../src/pages/SearchPage.tsx', import.meta.url), 'utf8')
  const trash = await readFile(new URL('../src/pages/TrashPage.tsx', import.meta.url), 'utf8')
  const spinner = await readFile(new URL('../src/components/Spinner.tsx', import.meta.url), 'utf8')
  const mark = await readFile(new URL('../src/components/BrandMark.tsx', import.meta.url), 'utf8')
  const css = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8')

  for (const mood of ['asleep', 'search', 'wave', 'error', 'loading']) {
    assert.match(rabbit, new RegExp(`mood === '${mood}'`))
  }
  assert.match(library, /mood=\{filtered \? 'search' : 'wave'\}/)
  assert.match(library, /mood="error"/)
  assert.match(tasks, /mood="asleep"/)
  assert.match(search, /mood="search"/)
  assert.match(search, /mood="error"/)
  assert.match(trash, /mood="asleep"/)
  assert.match(spinner, /mood="loading"/)
  assert.match(mark, /rabbit-blink/)
  assert.match(css, /@keyframes rabbit-peek/)
  assert.match(css, /@keyframes rabbit-blink/)
})
