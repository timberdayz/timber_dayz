import assert from 'node:assert/strict'
import test from 'node:test'

import {
  mergeHeaderBindingsForSave,
  normalizeDeduplicationSelection,
} from '../src/domains/data_platform/utils/deduplicationSelection.js'

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

test('drops confirmed semantic fields that are not hash eligible', () => {
  const normalized = normalizeDeduplicationSelection(
    ['product_name', 'product_id'],
    [
      {
        raw_name: 'Product Name',
        semantic_key: 'product_name',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: false,
      },
      {
        raw_name: 'Product ID',
        semantic_key: 'product_id',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: true,
      },
    ],
  )

  assert.deepEqual(normalized, ['product_id'])
})

test('preserves edited semantic bindings when full bindings are loaded for save', () => {
  const merged = mergeHeaderBindingsForSave(
    [
      {
        raw_name: 'Product ID',
        semantic_key: null,
        semantic_review_status: 'pending',
        hash_eligible: false,
      },
      {
        raw_name: 'GMV',
        semantic_key: 'gmv',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: false,
      },
    ],
    [
      {
        raw_name: 'Product ID',
        semantic_key: 'product_id',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: true,
      },
    ],
  )

  assert.deepEqual(merged[0], {
    raw_name: 'Product ID',
    semantic_key: 'product_id',
    semantic_review_status: 'confirmed_semantic',
    hash_eligible: true,
  })
})
