import test from 'node:test'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const selectionUtils = await import(
  `file:///${resolve(repoRoot, 'src/domains/data_platform/utils/deduplicationSelection.js').replace(/\\/g, '/')}`
)

test('normalizeDeduplicationSelection keeps policy-eligible weak identity fields', () => {
  const result = selectionUtils.normalizeDeduplicationSelection(
    ['item_status'],
    [
      {
        raw_name: 'Listing Status',
        semantic_key: 'item_status',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: false,
      },
    ],
    [],
    null,
    ['item_status'],
  )

  assert.deepEqual(result, ['item_status'])
})

test('normalizeDeduplicationSelection still drops non-policy ineligible fields', () => {
  const result = selectionUtils.normalizeDeduplicationSelection(
    ['gmv'],
    [
      {
        raw_name: 'GMV',
        semantic_key: 'gmv',
        semantic_review_status: 'confirmed_semantic',
        hash_eligible: false,
      },
    ],
  )

  assert.deepEqual(result, [])
})
