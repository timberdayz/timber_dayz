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

  assert.deepEqual(bindings[0], {
    raw_name: 'Unnamed: 0',
    display_name: '日期',
    semantic_role: 'metric_date',
    aliases: ['日期', '统计日期'],
    position: 0,
    sample_type: 'date',
    confidence: 0.98,
  })
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
