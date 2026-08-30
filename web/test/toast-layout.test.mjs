import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('toast actions align with readable multi-line content', async () => {
  const source = await readFile(new URL('../src/components/ToastProvider.tsx', import.meta.url), 'utf8')

  assert.match(source, /grid-cols-\[1\.25rem_minmax\(0,1fr\)_2rem\]/)
  assert.match(source, /\[-webkit-line-clamp:2\]/)
  assert.match(source, /col-start-2 col-end-4/)
  assert.match(source, /origin-bottom[^"\n]*sm:origin-top-right/)
})
