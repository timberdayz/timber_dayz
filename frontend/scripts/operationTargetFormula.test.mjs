import test from 'node:test'
import assert from 'node:assert/strict'

import { buildOperationTargetPreview } from '../src/domains/business/views/target/operationTargetFormula.js'

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
