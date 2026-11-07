import assert from 'node:assert/strict'
import {
  NON_SEMANTIC_FIELD_VALUE,
  getSemanticFieldMeta,
  getSemanticFieldOptionGroupsForDomain,
  isHashEligibleSemanticKey,
  updateHeaderBindingSemantic,
} from '../src/domains/data_platform/utils/headerBindings.js'
import {
  normalizeSemanticAlias,
  semanticFieldRegistry,
} from '../src/domains/data_platform/utils/semanticFieldRegistry.js'
import { SEMANTIC_FIELD_REGISTRY_SNAPSHOT } from '../src/domains/data_platform/utils/semanticFieldRegistrySnapshot.js'
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
  assert.ok(getSemanticFieldMeta(key), `${key} should be a canonical semantic key`)
}

const periodStartTimeMeta = getSemanticFieldMeta('period_start_time')
assert.equal(periodStartTimeMeta.kind, 'time')
assert.equal(periodStartTimeMeta.hash_eligible, true)
assert.equal(periodStartTimeMeta.default_hash, false)
assert.equal(isHashEligibleSemanticKey('period_start_time'), true)
assert.equal(isHashEligibleSemanticKey('period_end_time'), true)
const productNameMeta = getSemanticFieldMeta('product_name')
assert.equal(productNameMeta.kind, 'dimension')
assert.equal(productNameMeta.hash_eligible, true)
assert.equal(productNameMeta.default_hash, false)
assert.equal(productNameMeta.identity_strength, 'weak')
assert.equal(isHashEligibleSemanticKey('product_name'), true)
assert.equal(getSemanticFieldMeta('item_status').kind, 'attribute')
assert.equal(getSemanticFieldMeta('item_status').hash_eligible, false)
assert.equal(isHashEligibleSemanticKey('page_views'), false)
assert.equal(isHashEligibleSemanticKey('gmv'), false)
assert.equal(isHashEligibleSemanticKey('live_attributed_gmv'), false)

// [*] 批次 D: required 必须来自后端定义, 前端不再自算(以前永远是 false)。
assert.equal(getSemanticFieldMeta('order_id').required, true)
assert.equal(getSemanticFieldMeta('product_id').domain, 'common')
assert.equal(getSemanticFieldMeta('product_name').domain, 'products')

const allOptionGroups = getSemanticFieldOptionGroupsForDomain('')
const optionValues = new Set(allOptionGroups.flatMap(group => group.options.map(option => option.value)))
assert.ok(optionValues.has('live_attributed_gmv'))
assert.equal(optionValues.has('商家直播归因 GMV'), false)

const groupedOptions = Object.fromEntries(
  allOptionGroups.map(group => [group.label, group.options.map(option => option.value)])
)
assert.ok(groupedOptions['时间字段'].includes('period_start_time'))
assert.ok(groupedOptions['身份字段'].includes('product_name'))
assert.ok(groupedOptions['流量指标'].includes('page_views'))
assert.ok(groupedOptions['渠道归因指标'].includes('live_attributed_gmv'))

const productDomainOptions = new Set(
  getSemanticFieldOptionGroupsForDomain('products').flatMap(group => group.options.map(option => option.value))
)
assert.equal(productDomainOptions.has('product_id'), true)
assert.equal(productDomainOptions.has('product_name'), true)
assert.equal(productDomainOptions.has('live_attributed_gmv'), false)
assert.equal(productDomainOptions.has('page_views'), false)

// [*] 批次 D: 前后端归一化口径必须一致 —— 快照里带后端生成的样本对。
assert.ok(SEMANTIC_FIELD_REGISTRY_SNAPSHOT.normalization_samples.length > 0)
for (const [raw, normalized] of SEMANTIC_FIELD_REGISTRY_SNAPSHOT.normalization_samples) {
  assert.equal(
    normalizeSemanticAlias(raw),
    normalized,
    `normalizeSemanticAlias(${JSON.stringify(raw)}) should equal backend result ${JSON.stringify(normalized)}`
  )
}

// [*] 批次 D: 别名索引必须是归一化后的, 且能命中「币种后缀 / 全角 / 星号」等写法。
// 「买家支付」是 orders 域的域限定别名 ⇒ 落在 domainAliasIndex 而不是全局索引。
assert.equal(semanticFieldRegistry.domainAliasIndex.orders.买家支付, 'paid_amount')
assert.equal(semanticFieldRegistry.domainColumnIndex.products.商品编号, 'product_id')
assert.equal(semanticFieldRegistry.domainColumnIndex.inventory.商品sku, 'platform_sku')

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
// 批次 E(E-4 / D1): 指标类字段不再硬性禁止参与 hash, 但默认不参与。
assert.equal(updated[0].hash_eligible, true)
// 批次 E(D2): hash_participates 已下线。
assert.equal('hash_participates' in updated[0], false)

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
// 批次 E(D2): hash_participates 已下线。
assert.equal('hash_participates' in productNameUpdated[0], false)

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
