import assert from 'node:assert/strict'
import test from 'node:test'

import { inferHeaderBindings } from '../src/domains/data_platform/utils/headerBindings.js'
import {
  buildTemplateUpdateFieldParseRulesPayload,
} from '../src/domains/data_platform/utils/templateUpdateFieldParseRules.js'

test('inferHeaderBindings derives a date alias for unnamed date columns', () => {
  const bindings = inferHeaderBindings({
    headerColumns: ['Unnamed: 0', 'GMV'],
    sampleData: {
      'Unnamed: 0': '2026-05-16T00:00:00',
      GMV: '123.45',
    },
  })

  assert.equal(bindings[0].raw_name, 'Unnamed: 0')
  assert.equal(bindings[0].display_name, '日期')
  assert.equal(bindings[0].semantic_key, 'metric_date')
  assert.equal(bindings[0].semantic_role, 'metric_date')
  assert.equal(bindings[0].semantic_review_status, 'confirmed_semantic')
  assert.equal(bindings[0].hash_eligible, true)
  assert.equal(bindings[0].hash_participates, false)
  assert.equal(bindings[0].position, 0)
  assert.equal(bindings[0].sample_type, 'date')
  assert.equal(bindings[0].confidence, 0.98)
  assert.equal(bindings[0].aliases.includes('日期'), true)
  assert.equal(bindings[0].aliases.includes('统计日期'), true)
})

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

test('buildTemplateUpdateFieldParseRulesPayload remaps missing source columns through header bindings', () => {
  const result = buildTemplateUpdateFieldParseRulesPayload({
    currentHeaderColumns: ['统计日期', 'GMV', '订单数'],
    currentHeaderBindings: [
      {
        raw_name: '统计日期',
        display_name: '日期',
        semantic_role: 'metric_date',
        aliases: ['日期', '统计日期'],
      },
    ],
    templateHeaderBindings: [
      {
        raw_name: 'Unnamed: 0',
        display_name: '日期',
        semantic_role: 'metric_date',
        aliases: ['日期', '统计日期'],
      },
    ],
    existingRules: [
      {
        target_field: 'metric_date',
        source_column: 'Unnamed: 0',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ],
  })

  assert.deepEqual(result.rules, [
    {
      target_field: 'metric_date',
      source_column: '统计日期',
      source_label: '日期',
      source_aliases: ['日期', '统计日期'],
      source_semantic_role: 'metric_date',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ])
  assert.deepEqual(result.droppedRules, [])
})

test('buildTemplateUpdateFieldParseRulesPayload preserves time parse rule controls', () => {
  const result = buildTemplateUpdateFieldParseRulesPayload({
    currentHeaderColumns: ['小时'],
    existingRules: [
      {
        target_field: 'period_start_time',
        source_column: '小时',
        value_kind: 'time_of_day',
        date_format: 'hh:mm',
        date_anchor: '__file_date_from__',
        strict: true,
      },
      {
        target_field: 'period_end_time',
        source_column: '小时',
        value_kind: 'time_range',
        date_format: 'hh:mm',
        range_pick: 'end',
        date_anchor: '__file_date_from__',
        strict: true,
      },
    ],
  })

  assert.deepEqual(result.rules, [
    {
      target_field: 'period_start_time',
      source_column: '小时',
      value_kind: 'time_of_day',
      date_format: 'hh:mm',
      strict: true,
      date_anchor: '__file_date_from__',
    },
    {
      target_field: 'period_end_time',
      source_column: '小时',
      value_kind: 'time_range',
      date_format: 'hh:mm',
      strict: true,
      range_pick: 'end',
      date_anchor: '__file_date_from__',
    },
  ])
  assert.deepEqual(result.droppedRules, [])
})
