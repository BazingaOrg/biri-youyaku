import assert from 'node:assert/strict'
import test from 'node:test'
import {friendlyError} from '../src/lib/errorMap.ts'

test('Bilibili rate limiting is not reported as an LLM error', () => {
  const error = friendlyError(
    'BILI_RATE_LIMITED',
    'HTTP Error 412: Precondition Failed',
    'DOWNLOADING_AUDIO',
  )

  assert.equal(error.title, 'B 站临时风控')
  assert.equal(error.actionLabel, '稍后重试')
  assert.match(error.message, /10–30 分钟/)
})

test('other Bilibili HTTP errors use the download stage', () => {
  const error = friendlyError(undefined, 'HTTP Error 403: Forbidden', 'DOWNLOADING_AUDIO')

  assert.equal(error.title, 'B 站请求失败')
})

test('LLM-stage HTTP errors retain the provider message', () => {
  const error = friendlyError(undefined, 'HTTP Error 503: Unavailable', 'SUMMARIZING')

  assert.equal(error.title, '大模型接口异常')
})
