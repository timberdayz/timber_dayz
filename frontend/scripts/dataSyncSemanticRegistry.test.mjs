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
// [*] 批次 E(E-4 / D1): 指标类字段**不再硬性禁止**参与 hash ——
// 能不能进由用户勾选决定, 但默认不参与, 且必须带后果提示。
assert.equal(isHashEligibleSemanticKey('page_views'), true)
assert.equal(isHashEligibleSemanticKey('gmv'), true)
assert.equal(isHashEligibleSemanticKey('live_attributed_gmv'), true)
assert.equal(getSemanticFieldMeta('page_views').default_hash, false)
assert.equal(getSemanticFieldMeta('gmv').default_hash, false)

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
//
// ⚠ 关于「买家支付」—— 它**不在** domainAliasIndex.orders 里, 这是刻意设计, 不是遗漏:
//   源表金额列成对出现(原币列 + (RMB) 列), 实测两列均非零且相差约 3 倍
//   ⇒ 是两个不同的业务事实。字典只登记 (RMB) 变体, 裸名列(原币)不接任何标准字段,
//   否则就是把原币当成人民币(混币种)。
//   中文「买家支付(RMB)」走 orders 域的**逐字**索引(封闭域), 那份索引不下发快照。
//   所以「买家支付」一旦出现在归一化桶里, 就说明原币列被认领成了人民币金额 ⇒ 必须红。
assert.equal('买家支付' in semanticFieldRegistry.domainAliasIndex.orders, false)
assert.equal('买家支付' in semanticFieldRegistry.aliasIndex, false)
// 英文别名(两平台列名一致, 不走平台维度)才进 orders 通用别名桶。
assert.equal(semanticFieldRegistry.domainAliasIndex.orders.paidamount, 'paid_amount')
assert.equal(semanticFieldRegistry.domainAliasIndex.orders.buyerpaid, 'paid_amount')
// 归一化会剥掉币种后缀 —— 锁住这一事实(它是上面那条「不能登记原币列」的前提)。
assert.equal(normalizeSemanticAlias('买家支付(RMB)'), '买家支付')
assert.equal(normalizeSemanticAlias('买家支付（rmb）'), '买家支付')

// 全量守护: 三个别名索引里的**每一个** key 都必须已经是归一化形式,
// **每一个** value 都必须解析得到合法标准字段。
// (原来是 1 条点状断言, 覆盖面只有这一条的零头)
const collectAliasEntries = (index) => {
  const entries = []
  for (const [key, value] of Object.entries(index || {})) {
    if (typeof value === 'string') {
      entries.push([key, value])
    } else {
      for (const [innerKey, innerValue] of Object.entries(value || {})) {
        if (typeof innerValue === 'string') entries.push([innerKey, innerValue])
      }
    }
  }
  return entries
}
const allAliasEntries = [
  ...collectAliasEntries(semanticFieldRegistry.aliasIndex),
  ...collectAliasEntries(semanticFieldRegistry.domainAliasIndex),
  ...collectAliasEntries(semanticFieldRegistry.domainColumnIndex),
]
assert.ok(allAliasEntries.length >= 400, `别名索引条目数偏少: ${allAliasEntries.length}`)
for (const [key, field] of allAliasEntries) {
  assert.equal(normalizeSemanticAlias(key), key, `别名索引的 key 必须已归一化: ${key}`)
  assert.ok(getSemanticFieldMeta(field), `别名必须指向合法标准字段: ${key} -> ${field}`)
}

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
