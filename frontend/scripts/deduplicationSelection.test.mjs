import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeDeduplicationSelection } from '../src/domains/data_platform/utils/deduplicationSelection.js'

test('drops derived metric_date from user-selected fields when source comes from companion file date', () => {
  const normalized = normalizeDeduplicationSelection(
    ['product_id', 'metric_date'],
    [
      {
        raw_name: '商品 ID',
        semantic_key: 'product_id',
        semantic_review_status: 'confirmed_semantic',
      },
    ],
    [
      {
        target_field: 'metric_date',
        source_column: '__file_date_from__',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ],
  )

  assert.deepEqual(normalized, ['product_id'])
})

test('maps confirmed raw headers to semantic keys and drops unconfirmed fields', () => {
  const normalized = normalizeDeduplicationSelection(
    ['商品 ID', '状态'],
    [
      {
        raw_name: '商品 ID',
        semantic_key: 'product_id',
        semantic_review_status: 'confirmed_semantic',
      },
      {
        raw_name: '状态',
        semantic_key: 'status',
        semantic_review_status: 'confirmed_non_semantic',
      },
    ],
  )

  assert.deepEqual(normalized, ['product_id'])
})
