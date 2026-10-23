import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizeFailedDomains,
  pickPrimaryErrorMessage
} from '../src/domains/collection/views/collection/collectionTaskErrors.js'

test('normalizeFailedDomains 提取域级错误并保留完整 call log', () => {
  const rows = normalizeFailedDomains([
    {
      domain: 'inventory',
      error: 'StepExecutionError: Export failed: Locator.click: Timeout 1500ms exceeded.\nCall log:\n  - <div class="jx-select__selected-item jx-select__placeholder is-transparent"> intercepts pointer events'
    }
  ])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].label, 'inventory')
  assert.match(rows[0].error, /intercepts pointer events/)
})

test('normalizeFailedDomains 兼容字符串形态的失败域', () => {
  const rows = normalizeFailedDomains(['orders'])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].label, 'orders')
  assert.equal(rows[0].error, '')
})

test('normalizeFailedDomains 对非数组输入返回空数组', () => {
  assert.deepEqual(normalizeFailedDomains(null), [])
  assert.deepEqual(normalizeFailedDomains(undefined), [])
})

test('pickPrimaryErrorMessage 在顶层 error_message 为空时回落到域级错误', () => {
  const message = pickPrimaryErrorMessage({
    error_message: null,
    failed_domains: [{ domain: 'inventory', error: 'boom' }]
  })

  assert.equal(message, 'boom')
})

test('pickPrimaryErrorMessage 优先使用顶层 error_message', () => {
  const message = pickPrimaryErrorMessage({
    error_message: '顶层错误',
    failed_domains: [{ domain: 'inventory', error: '域级错误' }]
  })

  assert.equal(message, '顶层错误')
})

test('pickPrimaryErrorMessage 在没有任何错误时返回空串', () => {
  assert.equal(pickPrimaryErrorMessage({ error_message: null, failed_domains: [] }), '')
})
