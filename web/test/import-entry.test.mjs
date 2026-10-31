import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import test from 'node:test'

test('file import belongs to the home composer and keeps upload safeguards', async () => {
  const browseSource = await readFile(new URL('../src/components/BrowseOmni.tsx', import.meta.url), 'utf8')
  const omniSource = await readFile(new URL('../src/components/OmniBar.tsx', import.meta.url), 'utf8')
  const panelSource = await readFile(new URL('../src/components/ImportPanel.tsx', import.meta.url), 'utf8')

  assert.match(browseSource, /trailing=\{pathname === '\/' \?/)
  assert.match(browseSource, /aria-expanded=\{importOpen\}/)
  assert.match(browseSource, /aria-controls="file-import-panel"/)
  assert.match(browseSource, /event.key !== 'Escape' \|\| importBusy/)
  assert.match(omniSource, /\{trailing\}/)
  assert.match(panelSource, /aria-label="选择音视频或字幕文件"/)
  assert.match(panelSource, /添加标题和来源链接（可选）/)
  assert.match(panelSource, /上传及服务端检查完成前，请不要离开此页/)
})
