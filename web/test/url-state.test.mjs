import assert from 'node:assert/strict'
import test from 'node:test'
import {parseSearchScope, readUrlState, writeUrlState, hrefWithQuery, viewStorageKey} from '../src/lib/urlState.ts'

test('readUrlState parses query keys', () => {
  assert.deepEqual(readUrlState('?q=注意力&scope=subs'), {q: '注意力', scope: 'subs'})
  assert.deepEqual(readUrlState('q=hello'), {q: 'hello'})
})

test('writeUrlState patches and removes empty keys', () => {
  assert.equal(writeUrlState('?q=a&scope=all', {scope: 'notes'}), 'q=a&scope=notes')
  assert.equal(writeUrlState('?q=a&from=search', {from: null, tab: 'subs'}), 'q=a&tab=subs')
  assert.equal(writeUrlState('', {q: '注意力', scope: 'all'}), 'q=%E6%B3%A8%E6%84%8F%E5%8A%9B&scope=all')
})

test('parseSearchScope falls back to all', () => {
  assert.equal(parseSearchScope('notes'), 'notes')
  assert.equal(parseSearchScope('subs'), 'subs')
  assert.equal(parseSearchScope('nope'), 'all')
  assert.equal(parseSearchScope(null), 'all')
})

test('hrefWithQuery and viewStorageKey use path plus search', () => {
  assert.equal(hrefWithQuery('/search', {q: 'a', scope: 'all'}), '/search?q=a&scope=all')
  assert.equal(hrefWithQuery('/', {up: null}), '/')
  assert.equal(viewStorageKey('/search', 'q=a&scope=all'), '/search?q=a&scope=all')
  assert.equal(viewStorageKey('/', ''), '/')
})
