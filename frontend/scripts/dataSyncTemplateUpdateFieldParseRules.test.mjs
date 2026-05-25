import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTemplateUpdateFieldParseRulesPayload,
} from '../src/domains/data_platform/utils/templateUpdateFieldParseRules.js'

test('buildTemplateUpdateFieldParseRulesPayload keeps rules whose source columns still exist', () => {
  const result = buildTemplateUpdateFieldParseRulesPayload({
    currentHeaderColumns: ['日期', 'GMV', '订单数'],
    existingRules: [
      {
        target_field: 'metric_date',
        source_column: '日期',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ],
  })

  assert.deepEqual(result.rules, [
    {
      target_field: 'metric_date',
      source_column: '日期',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
  assert.deepEqual(result.droppedRules, [])
})

test('buildTemplateUpdateFieldParseRulesPayload drops rules whose source columns no longer exist', () => {
  const result = buildTemplateUpdateFieldParseRulesPayload({
    currentHeaderColumns: ['统计日期', 'GMV', '订单数'],
    existingRules: [
      {
        target_field: 'metric_date',
        source_column: '日期',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
      {
        target_field: 'period_start_date',
        source_column: '__file_date_from__',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ],
  })

  assert.deepEqual(result.rules, [
    {
      target_field: 'period_start_date',
      source_column: '__file_date_from__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
  assert.deepEqual(result.droppedRules, [
    {
      target_field: 'metric_date',
      source_column: '日期',
    },
  ])
})
