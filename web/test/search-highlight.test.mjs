import assert from 'node:assert/strict'
import test from 'node:test'
import {splitSearchHighlights} from '../src/lib/searchHighlight.ts'

function highlightedText(text, query, mode) {
  return splitSearchHighlights(text, query, mode)
    .filter((part) => part.highlighted)
    .map((part) => part.text)
}

test('literal history highlighting preserves punctuation semantics', () => {
  assert.deepEqual(highlightedText('C++ 与 C 都出现', 'C++', 'literal'), ['C++'])
})

test('FTS highlighting follows punctuation-insensitive token phrases', () => {
  assert.deepEqual(highlightedText('Use Node js here', 'Node.js', 'fts'), ['Node js'])
  assert.deepEqual(highlightedText('讨论量子、纠缠问题', '量子纠缠', 'fts'), ['量子、纠缠'])
})

test('FTS highlighting treats whitespace groups as separate terms', () => {
  assert.deepEqual(highlightedText('先谈模型，最后讨论产品', '模型 产品', 'fts'), ['模型', '产品'])
})
