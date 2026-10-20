import assert from 'node:assert/strict'
import test from 'node:test'
import {transcriptToPlainText} from '../src/lib/subtitle.ts'

test('plain-text transcript copy keeps on-screen timestamps', () => {
  assert.equal(
    transcriptToPlainText([
      {start: 5, end: 8, text: '  开场  '},
      {start: 72, end: 80, text: ''},
      {start: 72, end: 80, text: '正片'},
    ]),
    '0:05  开场\n1:12  正片',
  )
})
