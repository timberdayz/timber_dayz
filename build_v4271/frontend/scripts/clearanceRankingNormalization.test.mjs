import assert from 'node:assert/strict'

import {
  normalizeClearanceRankingResponse
} from '../src/utils/businessOverviewData.js'

const wrappedResponse = {
  data: [
    {
      shop_name: 'A店',
      clearance_amount: 1200,
      clearance_quantity: 10,
      incentive_amount: 12,
      total_incentive: 12,
      rank: 1
    }
  ],
  columns: ['shop_name'],
  row_count: 1
}

assert.deepEqual(
  normalizeClearanceRankingResponse(wrappedResponse),
  wrappedResponse.data,
  'should unwrap dashboard clearance response objects into row arrays'
)

assert.deepEqual(
  normalizeClearanceRankingResponse([]),
  [],
  'should keep array responses unchanged'
)

assert.deepEqual(
  normalizeClearanceRankingResponse(null),
  [],
  'should treat null responses as empty arrays'
)

console.log('clearance ranking normalization tests passed')
