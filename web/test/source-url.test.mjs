import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function loadModule() {
  const source = fs.readFileSync(new URL('../src/lib/sourceUrl.ts', import.meta.url), 'utf8')
  const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020}})
  const module = {exports: {}}
  vm.runInNewContext(compiled.outputText, {exports: module.exports, module, URL})
  return module.exports
}

test('recognizes Bilibili sharing text and canonical YouTube variants', () => {
  const {recognizeSourceUrl} = loadModule()
  assert.equal(recognizeSourceUrl('看看这个 https://www.bilibili.com/video/BV1xx411c7mD/?share_source=copy_web')['provider'], 'bilibili')
  assert.equal(recognizeSourceUrl('https://youtu.be/dQw4w9WgXcQ?t=2').canonicalUrl, 'https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  assert.equal(recognizeSourceUrl('https://example.com/watch?v=dQw4w9WgXcQ'), null)
})

test('creates timestamp playback URLs only for supported remote sources', () => {
  const {playbackUrl} = loadModule()
  assert.equal(playbackUrl('https://www.youtube.com/shorts/dQw4w9WgXcQ', 'youtube', 61), 'https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=61')
  assert.equal(playbackUrl('upload://abc', 'upload', 61), null)
  assert.equal(playbackUrl('file:///tmp/recording.wav', null, 61), null)
})

test('recognizes the mobile Bilibili host and rejects a mismatched source', () => {
  const {recognizeSourceUrl, playbackUrl} = loadModule()
  assert.equal(recognizeSourceUrl('https://m.bilibili.com/video/BV1xx411c7mD?p=2').provider, 'bilibili')
  assert.equal(playbackUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'bilibili', 3), null)
})

test('keeps an ordinary source page without pretending it supports timestamps', () => {
  const {playbackUrl, sourceHref} = loadModule()
  assert.equal(sourceHref('https://course.example/path?lesson=3'), 'https://course.example/path?lesson=3')
  assert.equal(playbackUrl('https://course.example/path?lesson=3', null, 61), null)
  assert.equal(sourceHref('https://user:secret@example.com/path'), null)
})
