import assert from 'node:assert/strict'
import test from 'node:test'
import {matchByBvid, resolvePasteAction} from '../src/lib/pasteAction.ts'
import {extractBvid} from '../src/lib/biliUrl/bvid.ts'

test('extractBvid finds BV ids in urls and bare ids', () => {
  assert.equal(extractBvid('https://www.bilibili.com/video/BV1Ab4y1Q7aZ?p=1'), 'BV1Ab4y1Q7aZ')
  assert.equal(extractBvid('BV1Np4y1W4gT'), 'BV1Np4y1W4gT')
  assert.equal(extractBvid('hello'), null)
})

test('new link uses generate as the primary action', () => {
  const action = resolvePasteAction({isLink: true, existing: null, trashed: null})
  assert.equal(action.kind, 'new-link')
  assert.equal(action.primary, 'generate')
})

test('existing note uses read as the primary action', () => {
  const existing = {documentId: 'd1', title: '已有笔记', bvid: 'BV1Ab4y1Q7aZ'}
  const action = resolvePasteAction({isLink: true, existing, trashed: null})
  assert.equal(action.kind, 'existing')
  assert.equal(action.primary, 'read')
  assert.equal(action.existing.documentId, 'd1')
})

test('trashed note uses restore as the primary action', () => {
  const trashed = {documentId: 't1', title: '回收站笔记', bvid: 'BV1Np4y1W4gT', daysLeft: 12}
  const action = resolvePasteAction({isLink: true, existing: null, trashed})
  assert.equal(action.kind, 'trashed')
  assert.equal(action.primary, 'restore')
})

test('trash wins over an existing live match', () => {
  const action = resolvePasteAction({
    isLink: true,
    existing: {documentId: 'd1', title: 'live', bvid: 'BV1Np4y1W4gT'},
    trashed: {documentId: 't1', title: 'trashed', bvid: 'BV1Np4y1W4gT'},
  })
  assert.equal(action.primary, 'restore')
  assert.equal(action.kind, 'trashed')
})

test('plain text is not a link action', () => {
  const action = resolvePasteAction({isLink: false})
  assert.equal(action.kind, 'text')
  assert.equal(action.primary, null)
})

test('matchByBvid is case-insensitive', () => {
  const hit = matchByBvid(
    [{bvid: 'BV1Np4y1W4gT', title: 'a'}, {bvid: 'BV1Ab4y1Q7aZ', title: 'b'}],
    'bv1np4y1w4gt',
  )
  assert.equal(hit?.title, 'a')
  assert.equal(matchByBvid([{bvid: 'BV1Ab4y1Q7aZ'}], 'BV1Np4y1W4gT'), null)
})
