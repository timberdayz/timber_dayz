import assert from 'node:assert/strict'
import {
  NON_SEMANTIC_FIELD_VALUE,
  SEMANTIC_FIELD_META,
  SEMANTIC_FIELD_OPTIONS,
  SEMANTIC_FIELD_OPTION_GROUPS,
  isHashEligibleSemanticKey,
  updateHeaderBindingSemantic,
} from '../src/domains/data_platform/utils/headerBindings.js'
import {
  DATE_FORMAT_OPTIONS,
  DATE_TARGET_FIELD_OPTIONS,
  DATE_VALUE_KIND_OPTIONS,
} from '../src/domains/data_platform/utils/templateFieldParseRules.js'

const requiredSemanticKeys = [
  'metric_date',
  'period_start_date',
  'period_end_date',
  'period_start_time',
  'period_end_time',
  'order_date',
  'order_id',
  'line_id',
  'product_id',
  'product_name',
  'platform_sku',
  'sku_id',
  'service_id',
  'shop_id',
  'warehouse_name',
  'visitor_count',
  'product_visitor_count',
  'page_views',
  'impressions',
  'clicks',
  'click_rate',
  'conversion_rate',
  'order_count',
  'sku_order_count',
  'gmv',
  'total_transaction_amount',
  'bounce_rate',
  'sales_amount',
  'sales_volume',
  'paid_amount',
  'profit',
  'purchase_amount',
  'platform_commission',
  'live_gmv',
  'live_attributed_gmv',
  'live_indirect_gmv',
  'video_gmv',
  'video_attributed_gmv',
  'video_indirect_gmv',
]

for (const key of requiredSemanticKeys) {
  assert.ok(SEMANTIC_FIELD_META[key], `${key} should be a canonical semantic key`)
}

assert.equal(SEMANTIC_FIELD_META.period_start_time.kind, 'time')
assert.equal(SEMANTIC_FIELD_META.period_start_time.hash_eligible, true)
assert.equal(SEMANTIC_FIELD_META.period_start_time.default_hash, false)
assert.equal(isHashEligibleSemanticKey('period_start_time'), true)
assert.equal(isHashEligibleSemanticKey('period_end_time'), true)
assert.equal(SEMANTIC_FIELD_META.product_name.kind, 'dimension')
assert.equal(SEMANTIC_FIELD_META.product_name.hash_eligible, true)
assert.equal(SEMANTIC_FIELD_META.product_name.default_hash, false)
assert.equal(SEMANTIC_FIELD_META.product_name.identity_strength, 'weak')
assert.equal(isHashEligibleSemanticKey('product_name'), true)
assert.equal(SEMANTIC_FIELD_META.item_status.kind, 'attribute')
assert.equal(SEMANTIC_FIELD_META.item_status.hash_eligible, false)
assert.equal(isHashEligibleSemanticKey('page_views'), false)
assert.equal(isHashEligibleSemanticKey('gmv'), false)
assert.equal(isHashEligibleSemanticKey('live_attributed_gmv'), false)

const optionValues = new Set(SEMANTIC_FIELD_OPTIONS.map(option => option.value))
assert.ok(optionValues.has(NON_SEMANTIC_FIELD_VALUE))
assert.ok(optionValues.has('live_attributed_gmv'))
assert.equal(optionValues.has('商家直播归因 GMV'), false)

const groupedOptions = Object.fromEntries(
  SEMANTIC_FIELD_OPTION_GROUPS.map(group => [group.label, group.options.map(option => option.value)])
)
assert.ok(groupedOptions['时间字段'].includes('period_start_time'))
assert.ok(groupedOptions['身份字段'].includes('product_name'))
assert.ok(groupedOptions['流量指标'].includes('page_views'))
assert.ok(groupedOptions['渠道归因指标'].includes('live_attributed_gmv'))

const updated = updateHeaderBindingSemantic(
  [
    {
      raw_name: '商家直播归因 GMV',
      display_name: '商家直播归因 GMV',
      semantic_key: null,
      semantic_review_status: 'pending',
    },
  ],
  '商家直播归因 GMV',
  'live_attributed_gmv'
)
assert.equal(updated[0].semantic_key, 'live_attributed_gmv')
assert.equal(updated[0].hash_eligible, false)
assert.equal(updated[0].hash_participates, false)

const productNameUpdated = updateHeaderBindingSemantic(
  [
    {
      raw_name: '商品名称',
      display_name: '商品名称',
      semantic_key: null,
      semantic_review_status: 'pending',
    },
  ],
  '商品名称',
  'product_name'
)
assert.equal(productNameUpdated[0].semantic_key, 'product_name')
assert.equal(productNameUpdated[0].hash_eligible, true)
assert.equal(productNameUpdated[0].hash_participates, false)

const nonSemantic = updateHeaderBindingSemantic(updated, '商家直播归因 GMV', NON_SEMANTIC_FIELD_VALUE)
assert.equal(nonSemantic[0].semantic_key, null)
assert.equal(nonSemantic[0].semantic_review_status, 'confirmed_non_semantic')

const dateTargetValues = new Set(DATE_TARGET_FIELD_OPTIONS.map(option => option.value))
assert.ok(dateTargetValues.has('metric_date'))
assert.ok(dateTargetValues.has('period_start_time'))
assert.ok(dateTargetValues.has('period_end_time'))

const valueKindValues = new Set(DATE_VALUE_KIND_OPTIONS.map(option => option.value))
for (const valueKind of ['single_date', 'single_datetime', 'time_of_day', 'datetime_range', 'time_range']) {
  assert.ok(valueKindValues.has(valueKind), `${valueKind} should be selectable`)
}

const dateFormatValues = new Set(DATE_FORMAT_OPTIONS.map(option => option.value))
assert.ok(dateFormatValues.has('hh:mm'))
assert.ok(dateFormatValues.has('hh:mm:ss'))
assert.ok(dateFormatValues.has('mm/dd/yyyy'))
assert.ok(dateFormatValues.has('mm-dd-yyyy hh:mm'))

console.log('dataSyncSemanticRegistry.test.mjs passed')
