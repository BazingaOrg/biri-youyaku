import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('distill confirmation copy is limited to submitted videos and subtitles', async () => {
  const source = await readFile(new URL('../src/pages/up/DistillButton.tsx', import.meta.url), 'utf8')

  assert.match(source, /投稿视频和可用字幕/)
  assert.doesNotMatch(source, /会抓取该 UP 的历史动态/)
})
