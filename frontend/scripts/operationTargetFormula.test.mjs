import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildOperationEntryPreview,
  buildOperationTargetPreview
} from '../src/domains/business/views/target/operationTargetFormula.js'

test('buildOperationTargetPreview handles manual score metrics', () => {
  const preview = buildOperationTargetPreview(
    {
      manual_score_enabled: true,
      manual_score_value: 12,
      max_score: 20
    },
    { direction: 'manual_score' }
  )

  assert.equal(preview.calculation, 'manual_score=12.00')
  assert.equal(preview.score, '12.00 分')
})

test('buildOperationTargetPreview handles higher_better metrics', () => {
  const preview = buildOperationTargetPreview(
    {
      target_value: 80,
      achieved_value: 60,
      max_score: 20
    },
    { direction: 'higher_better' }
  )

  assert.equal(preview.score, '15.00 分')
})

test('buildOperationEntryPreview uses snapshot rules for percentage, count, training, and special check', () => {
  assert.deepEqual(
    buildOperationEntryPreview({ input_kind: 'percentage', metric_direction: 'higher_better', target_value: 100, max_score: 20, input_payload: { actual_value: 90 } }),
    { status: 'completed', auto_score: 18, formula: '得分 = 四舍五入(20 × min(实际值 / 目标值 100, 100%))。' }
  )
  assert.equal(
    buildOperationEntryPreview({ input_kind: 'count', metric_direction: 'lower_better', target_value: 3, max_score: 10, input_payload: { actual_value: 6 } }).auto_score,
    5
  )
  assert.equal(
    buildOperationEntryPreview({ input_kind: 'training_counts', max_score: 10, input_payload: { completed_count: 1, required_count: 3 } }).auto_score,
    3
  )
  assert.deepEqual(
    buildOperationEntryPreview({ input_kind: 'special_check', max_score: 7, input_payload: { result: 'partial', note: 'Follow-up' } }),
    { status: 'completed', auto_score: 4, formula: '通过得 7 分，部分完成得四舍五入(7 × 50%) 分，未通过得 0 分。' }
  )
  assert.equal(
    buildOperationEntryPreview({ input_kind: 'special_check', max_score: 7, input_payload: { result: 'failed' } }).status,
    'pending'
  )
})
