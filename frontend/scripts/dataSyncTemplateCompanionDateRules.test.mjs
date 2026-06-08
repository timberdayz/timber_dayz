import assert from 'node:assert/strict'
import test from 'node:test'

import {
  FILE_DATE_SOURCE_OPTIONS,
  buildCompanionDateParseRules,
  buildFieldParseSourceOptions,
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
