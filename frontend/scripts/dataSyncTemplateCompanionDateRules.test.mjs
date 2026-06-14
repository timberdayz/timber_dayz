import assert from 'node:assert/strict'
import test from 'node:test'

import {
  COMPANION_AUTO_DATE_FORMAT_CANDIDATES,
  DATE_FORMAT_OPTIONS,
  FILE_DATE_SOURCE_OPTIONS,
  buildAutoCompanionFormatPayload,
  buildAutoCompanionDateParseRules,
  buildCompanionDateParseRules,
  buildFieldParseSourceOptions,
  hasHeaderDateOrTimeSource,
  mergeFieldParseRules,
} from '../src/domains/data_platform/utils/templateFieldParseRules.js'

test('field parse rule sources expose file companion dates before raw headers', () => {
  const options = buildFieldParseSourceOptions(['商品 ID', 'GMV'])

  assert.deepEqual(options.slice(0, 2), FILE_DATE_SOURCE_OPTIONS)
  assert.deepEqual(options.slice(2), [
    { label: '商品 ID', value: '商品 ID', source: 'header' },
    { label: 'GMV', value: 'GMV', source: 'header' },
  ])
})

test('companion date quick rule can map file start date to metric_date', () => {
  assert.deepEqual(buildCompanionDateParseRules('single'), [
    {
      target_field: 'metric_date',
      source_column: '__file_date_from__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
})

test('companion period quick rule maps file date range to period boundaries', () => {
  assert.deepEqual(buildCompanionDateParseRules('period'), [
    {
      target_field: 'period_start_date',
      source_column: '__file_date_from__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
    {
      target_field: 'period_end_date',
      source_column: '__file_date_to__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
})

test('mergeFieldParseRules replaces rules by target field', () => {
  const merged = mergeFieldParseRules(
    [
      {
        target_field: 'metric_date',
        source_column: '日期',
        value_kind: 'single_date',
        date_format: 'yyyy/mm/dd',
        strict: true,
      },
      {
        target_field: 'period_end_date',
        source_column: '__file_date_to__',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ],
    buildCompanionDateParseRules('single'),
  )

  assert.deepEqual(merged, [
    {
      target_field: 'period_end_date',
      source_column: '__file_date_to__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
    {
      target_field: 'metric_date',
      source_column: '__file_date_from__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
})

test('auto companion period format exposes candidates for save payload', () => {
  assert.equal(
    DATE_FORMAT_OPTIONS.some(option => option.value === 'auto_by_companion_period'),
    true,
  )
  assert.deepEqual(
    buildAutoCompanionFormatPayload({ date_format: 'auto_by_companion_period' }),
    {
      format_candidates: COMPANION_AUTO_DATE_FORMAT_CANDIDATES,
      resolution_source: 'companion_period',
    },
  )
})

test('products monthly without source date auto-adds companion period rules', () => {
  const rules = buildAutoCompanionDateParseRules({
    dataDomain: 'products',
    granularity: 'monthly',
    headerColumns: ['商品名', '商品 ID', 'GMV'],
    headerBindings: [
      {
        raw_name: '商品 ID',
        semantic_key: 'product_id',
        semantic_review_status: 'confirmed_semantic',
        sample_type: 'number',
      },
    ],
    currentRules: [],
  })

  assert.deepEqual(rules, buildCompanionDateParseRules('period'))
})

test('products daily without source date auto-adds metric_date companion rule', () => {
  const rules = buildAutoCompanionDateParseRules({
    dataDomain: 'products',
    granularity: 'daily',
    headerColumns: ['商品名', '商品 ID', 'GMV'],
    headerBindings: [],
    currentRules: [],
  })

  assert.deepEqual(rules, buildCompanionDateParseRules('single'))
})

test('source date or time columns prevent companion auto rules from overriding user choice', () => {
  assert.equal(
    hasHeaderDateOrTimeSource(
      [{ raw_name: '统计日期', semantic_key: 'metric_date', sample_type: 'date' }],
      ['统计日期', '商品 ID'],
    ),
    true,
  )
  assert.deepEqual(
    buildAutoCompanionDateParseRules({
      dataDomain: 'products',
      granularity: 'monthly',
      headerColumns: ['统计日期', '商品 ID'],
      headerBindings: [{ raw_name: '统计日期', semantic_key: 'metric_date', sample_type: 'date' }],
      currentRules: [],
    }),
    [],
  )
})

test('auto companion period rules only fill missing date targets', () => {
  const existingRule = {
    target_field: 'period_start_date',
    source_column: 'custom_start',
    value_kind: 'single_date',
    date_format: 'yyyy/mm/dd',
    strict: true,
  }
  const rules = buildAutoCompanionDateParseRules({
    dataDomain: 'products',
    granularity: 'monthly',
    headerColumns: ['鍟嗗搧 ID', 'GMV'],
    headerBindings: [],
    currentRules: [existingRule],
  })

  assert.deepEqual(rules, [
    {
      target_field: 'period_end_date',
      source_column: '__file_date_to__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
})
