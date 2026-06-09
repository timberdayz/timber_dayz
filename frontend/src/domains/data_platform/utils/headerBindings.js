function looksLikeUnnamedHeader(columnName) {
  return String(columnName ?? '').trim().toLowerCase().startsWith('unnamed:')
}

export const SYSTEM_HASH_SCOPE_FIELDS = [
  'platform_code',
  'shop_id',
  'data_domain',
  'granularity',
  'sub_domain'
]

export const SEMANTIC_FIELD_META = {
  order_id: {
    label: '订单号',
    description: '识别同一笔订单的稳定身份字段。',
    aliases: ['order_id', '订单号', '订单编号', 'order id'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  product_id: {
    label: '商品 ID',
    description: '平台或系统内识别同一商品的稳定身份字段。',
    aliases: ['product_id', '产品ID', '商品ID', 'product id'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  platform_sku: {
    label: '平台 SKU',
    description: '平台侧商品规格编码，可作为商品身份字段。',
    aliases: ['platform_sku', '平台SKU', '平台 sku', 'product_sku', '产品SKU', '商品SKU'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  sku_id: {
    label: 'SKU 编号',
    description: '订单明细或商品规格粒度的身份字段。',
    aliases: ['sku_id', 'sku id', 'SKU ID', 'SKU编号'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  line_id: {
    label: '订单明细行 ID',
    description: '订单明细行粒度的稳定身份字段。',
    aliases: ['line_id', 'order_line_id', 'line id', 'order line id'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  service_id: {
    label: '服务 ID',
    description: '服务类数据的稳定身份字段。',
    aliases: ['service_id', 'service id', '服务ID', '服务编号'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: true,
  },
  shop_id: {
    label: '店铺 ID',
    description: '系统自动加入 Data Hash 的店铺作用域字段。',
    aliases: ['shop_id', '店铺', '店铺ID', 'shop id'],
    kind: 'identity',
    hash_eligible: true,
    default_hash: false,
    system_scope: true,
  },
  warehouse_name: {
    label: '仓库',
    description: '库存快照区分仓库粒度的维度字段。',
    aliases: ['warehouse_name', 'warehouse', '仓库', '仓库名称', 'warehouse name'],
    kind: 'dimension',
    hash_eligible: true,
    default_hash: true,
  },
  gmv_band: {
    label: 'GMV 区间',
    description: '按 GMV 区间出报表时可作为行粒度维度。',
    aliases: ['gmv_band', 'gmv band', 'gmv range', 'GMV区间', 'GMV 区间'],
    kind: 'dimension',
    hash_eligible: true,
    default_hash: false,
  },
  metric_date: {
    label: '统计日期',
    description: '日/周/月报表定位业务周期的时间字段。',
    aliases: ['metric_date', '日期', '统计日期', 'data_date', 'date'],
    kind: 'time',
    hash_eligible: true,
    default_hash: true,
  },
  period_start_date: {
    label: '周期开始日期',
    description: '区间型报表的开始日期。',
    aliases: ['period_start_date', '开始日期', '周期开始日期'],
    kind: 'time',
    hash_eligible: true,
    default_hash: true,
  },
  period_end_date: {
    label: '周期结束日期',
    description: '区间型报表的结束日期。',
    aliases: ['period_end_date', '结束日期', '周期结束日期'],
    kind: 'time',
    hash_eligible: true,
    default_hash: true,
  },
  order_date: {
    label: '下单日期',
    description: '订单发生日期，通常作为分析维度。',
    aliases: ['order_date', '下单日期', '订单日期', '下单时间'],
    kind: 'time',
    hash_eligible: true,
    default_hash: false,
  },
  product_name: {
    label: '商品名',
    description: '弱身份字段。商品名可能重名或改名，优先使用商品 ID / SKU。',
    aliases: ['product_name', 'item_name', 'product name', 'item name', '商品', '商品名', '商品名称', '产品名称'],
    kind: 'dimension',
    hash_eligible: true,
    default_hash: false,
    identity_strength: 'weak',
    hash_warning: '商品名可能重名或改名，优先使用商品 ID / SKU。',
  },
  item_status: {
    label: '发品状态',
    description: '标准化属性字段，状态变化不应默认改变 Data Hash。',
    aliases: ['item_status', 'product_status', 'listing_status', 'item status', 'product status', '发品状态', '商品状态'],
    kind: 'attribute',
    hash_eligible: false,
    default_hash: false,
  },
  gmv: {
    label: 'GMV',
    description: '指标值，不参与 Data Hash。',
    aliases: ['gmv', 'GMV'],
    kind: 'metric',
    hash_eligible: false,
    default_hash: false,
  },
  sales_amount: {
    label: '销售额',
    description: '指标值，不参与 Data Hash。',
    aliases: ['sales_amount', 'sales amount', 'sales', '销售额', '销售金额'],
    kind: 'metric',
    hash_eligible: false,
    default_hash: false,
  },
  sales_volume: {
    label: '销量',
    description: '指标值，不参与 Data Hash。',
    aliases: ['sales_volume', 'sales volume', 'units sold', '销量', '销售数量'],
    kind: 'metric',
    hash_eligible: false,
    default_hash: false,
  },
  order_count: {
    label: '订单量',
    description: '指标值，不参与 Data Hash。',
    aliases: ['order_count', 'order count', 'orders', '订单量', '订单数'],
    kind: 'metric',
    hash_eligible: false,
    default_hash: false,
  },
}

Object.assign(SEMANTIC_FIELD_META, {
  period_start_time: {
    label: '周期开始时间',
    description: '小时级或更细粒度报表的开始时间，可由用户手动加入 Data Hash。',
    aliases: ['period_start_time', '开始时间', '小时', '时段', 'hour', 'time', 'start time'],
    kind: 'time',
    domain: 'common',
    hash_eligible: true,
    default_hash: false,
  },
  period_end_time: {
    label: '周期结束时间',
    description: '小时级或更细粒度报表的结束时间，可由用户手动加入 Data Hash。',
    aliases: ['period_end_time', '结束时间', '结束小时', 'end hour', 'end time'],
    kind: 'time',
    domain: 'common',
    hash_eligible: true,
    default_hash: false,
  },
  visitor_count: {
    label: '访客数',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['visitor_count', '访客数', 'visitors', 'visitor count'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  product_visitor_count: {
    label: '商品访客数',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['product_visitor_count', '商品访客数', 'product visitors', 'product visitor count'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  page_views: {
    label: '浏览量',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['page_views', '浏览量', 'pv', 'page views', 'views'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  impressions: {
    label: '曝光量',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['impressions', '曝光量', '曝光次数', 'impression', 'impressions'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  clicks: {
    label: '点击量',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['clicks', '点击量', '点击次数', 'click', 'clicks'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  click_rate: {
    label: '点击率',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['click_rate', '点击率', 'click rate', 'ctr'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  conversion_rate: {
    label: '转化率',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['conversion_rate', '转化率', 'conversion rate', 'cvr'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  sku_order_count: {
    label: 'SKU 订单量',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['sku_order_count', 'SKU订单量', 'sku orders', 'sku order count'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  total_transaction_amount: {
    label: '总交易金额',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['total_transaction_amount', '总交易金额', 'total transaction amount'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  bounce_rate: {
    label: '跳失率',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['bounce_rate', '跳失率', 'bounce rate'],
    kind: 'metric',
    domain: 'analytics',
    hash_eligible: false,
    default_hash: false,
  },
  paid_amount: {
    label: '实付金额',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['paid_amount', '实付金额', 'paid amount', 'buyer paid amount'],
    kind: 'metric',
    domain: 'orders',
    hash_eligible: false,
    default_hash: false,
  },
  profit: {
    label: '利润',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['profit', '利润'],
    kind: 'metric',
    domain: 'orders',
    hash_eligible: false,
    default_hash: false,
  },
  purchase_amount: {
    label: '采购金额',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['purchase_amount', '采购金额', 'purchase amount'],
    kind: 'metric',
    domain: 'products',
    hash_eligible: false,
    default_hash: false,
  },
  platform_commission: {
    label: '平台佣金',
    description: '系统语义指标，不参与 Data Hash。',
    aliases: ['platform_commission', '平台佣金', 'platform commission', 'commission'],
    kind: 'metric',
    domain: 'orders',
    hash_eligible: false,
    default_hash: false,
  },
  live_gmv: {
    label: '直播 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['live_gmv', '商家直播 GMV', '直播GMV', 'live gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
  live_attributed_gmv: {
    label: '直播归因 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['live_attributed_gmv', '商家直播归因 GMV', '直播归因GMV', 'live attributed gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
  live_indirect_gmv: {
    label: '直播间接 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['live_indirect_gmv', '商家直播间接 GMV', '直播间接GMV', 'live indirect gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
  video_gmv: {
    label: '视频 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['video_gmv', '商家视频 GMV', '视频GMV', 'video gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
  video_attributed_gmv: {
    label: '视频归因 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['video_attributed_gmv', '商家视频归因 GMV', '视频归因GMV', 'video attributed gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
  video_indirect_gmv: {
    label: '视频间接 GMV',
    description: '渠道归因系统语义指标，不参与 Data Hash。',
    aliases: ['video_indirect_gmv', '商家视频间接 GMV', '视频间接GMV', 'video indirect gmv'],
    kind: 'metric',
    domain: 'attribution',
    hash_eligible: false,
    default_hash: false,
  },
})

const SEMANTIC_FIELD_ALIASES = Object.fromEntries(
  Object.entries(SEMANTIC_FIELD_META).map(([key, meta]) => [key, meta.aliases])
)

export const NON_SEMANTIC_FIELD_VALUE = '__non_semantic__'

export const NON_SEMANTIC_FIELD_OPTION = {
  value: NON_SEMANTIC_FIELD_VALUE,
  label: '仅保留原始字段，不作为系统语义字段',
  description: '保留 raw_data，不参与 Data Hash。',
}

const SEMANTIC_OPTION_GROUPS = [
  { key: 'identity', label: '身份字段' },
  { key: 'time', label: '时间字段' },
  { key: 'traffic_metric', label: '流量指标' },
  { key: 'order_metric', label: '订单指标' },
  { key: 'product_metric', label: '商品指标' },
  { key: 'attribution_metric', label: '渠道归因指标' },
  { key: 'attribute', label: '属性字段' },
]

const ORDER_METRIC_KEYS = new Set([
  'order_count',
  'sku_order_count',
  'sales_amount',
  'sales_volume',
  'paid_amount',
  'profit',
  'platform_commission',
])
const PRODUCT_METRIC_KEYS = new Set(['purchase_amount'])
const ATTRIBUTION_METRIC_KEYS = new Set([
  'live_gmv',
  'live_attributed_gmv',
  'live_indirect_gmv',
  'video_gmv',
  'video_attributed_gmv',
  'video_indirect_gmv',
])

function semanticOptionGroupKey(value, meta) {
  if (meta?.kind === 'time') return 'time'
  if (meta?.kind === 'identity' || meta?.kind === 'dimension') return 'identity'
  if (ATTRIBUTION_METRIC_KEYS.has(value) || meta?.domain === 'attribution') return 'attribution_metric'
  if (ORDER_METRIC_KEYS.has(value) || meta?.domain === 'orders') return 'order_metric'
  if (PRODUCT_METRIC_KEYS.has(value) || meta?.domain === 'products') return 'product_metric'
  if (meta?.kind === 'metric') return 'traffic_metric'
  return 'attribute'
}

const CANONICAL_SEMANTIC_FIELD_OPTIONS = Object.entries(SEMANTIC_FIELD_META).map(([value, meta]) => ({
    value,
    label: `${meta.label} (${value})`,
    description: meta.description,
    aliases: meta.aliases,
    kind: meta.kind,
    domain: meta.domain,
    group: semanticOptionGroupKey(value, meta),
    hash_eligible: meta.hash_eligible,
    default_hash: meta.default_hash === true,
    system_scope: meta.system_scope === true,
    identity_strength: meta.identity_strength,
    hash_warning: meta.hash_warning,
  }))

export const SEMANTIC_FIELD_OPTION_GROUPS = SEMANTIC_OPTION_GROUPS
  .map(group => ({
    label: group.label,
    options: CANONICAL_SEMANTIC_FIELD_OPTIONS.filter(option => option.group === group.key),
  }))
  .filter(group => group.options.length > 0)

export function getSemanticFieldOptionGroupsForDomain(dataDomain = '') {
  const domain = String(dataDomain || '').trim().toLowerCase()
  const domainAliases = new Set([domain])
  if (domain === 'traffic') {
    domainAliases.add('analytics')
  }
  if (domain === 'analytics') {
    domainAliases.add('traffic')
  }

  const isAllowedForDomain = (option) => {
    const optionDomain = String(option?.domain || 'common').trim().toLowerCase()
    if (!optionDomain || optionDomain === 'common') return true
    if (!domain) return true
    return domainAliases.has(optionDomain)
  }

  return SEMANTIC_OPTION_GROUPS
    .map(group => ({
      label: group.label,
      options: CANONICAL_SEMANTIC_FIELD_OPTIONS
        .filter(option => option.group === group.key)
        .filter(isAllowedForDomain),
    }))
    .filter(group => group.options.length > 0)
}

export const SEMANTIC_FIELD_OPTIONS = [
  NON_SEMANTIC_FIELD_OPTION,
  ...CANONICAL_SEMANTIC_FIELD_OPTIONS,
]

export function getSemanticFieldMeta(semanticKey) {
  return SEMANTIC_FIELD_META[semanticKey] || null
}

export function isSystemScopeSemanticKey(semanticKey) {
  return SYSTEM_HASH_SCOPE_FIELDS.includes(String(semanticKey || '').trim())
}

export function isHashEligibleSemanticKey(semanticKey) {
  const meta = getSemanticFieldMeta(semanticKey)
  return Boolean(meta?.hash_eligible) && !isSystemScopeSemanticKey(semanticKey)
}

function inferSemanticKey(...values) {
  for (const rawValue of values) {
    const value = String(rawValue ?? '').trim().toLowerCase()
    if (!value) continue
    for (const [semanticKey, aliases] of Object.entries(SEMANTIC_FIELD_ALIASES)) {
      if (value === semanticKey || aliases.some(alias => String(alias).trim().toLowerCase() === value)) {
        return semanticKey
      }
    }
  }
  return null
}

function semanticRequirements(semanticKey) {
  const meta = getSemanticFieldMeta(semanticKey)
  return {
    required: Boolean(meta?.required),
    hash_participates: false,
    hash_eligible: Boolean(meta?.hash_eligible),
    semantic_kind: meta?.kind || '',
    system_scope: Boolean(meta?.system_scope),
    identity_strength: meta?.identity_strength || '',
    hash_warning: meta?.hash_warning || '',
  }
}

function looksLikeDateValue(rawValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) return false

  const normalized = text.replace(/\//g, '-').replace('Z', '+00:00')
  if (/^\d{4}-\d{1,2}-\d{1,2}(?:[ tT]\d{1,2}:\d{2}(?::\d{2})?)?$/.test(normalized)) {
    return true
  }

  const timestamp = Date.parse(normalized)
  return !Number.isNaN(timestamp)
}

function looksLikeNumberValue(rawValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) return false
  return !Number.isNaN(Number(text.replaceAll(',', '')))
}

export function inferHeaderBindings({
  headerColumns = [],
  sampleData = {},
} = {}) {
  return (Array.isArray(headerColumns) ? headerColumns : []).map((rawName, position) => {
    const sampleValue = sampleData?.[rawName]
    let sampleType = 'string'
    let confidence = 0.5
    let displayName = rawName
    let semanticKey = null
    let semanticRole = null
    let aliases = []

    if (looksLikeDateValue(sampleValue)) {
      sampleType = 'date'
      confidence = 0.98
    } else if (looksLikeNumberValue(sampleValue)) {
      sampleType = 'number'
      confidence = 0.7
    }

    if (looksLikeUnnamedHeader(rawName) && sampleType === 'date') {
      displayName = '日期'
      semanticKey = 'metric_date'
      semanticRole = 'metric_date'
      aliases = ['日期', '统计日期']
    }

    semanticKey = semanticKey || inferSemanticKey(rawName, displayName, ...aliases)
    const meta = semanticKey ? getSemanticFieldMeta(semanticKey) : null
    if (meta?.aliases?.length) {
      aliases = Array.from(new Set([...aliases, ...meta.aliases]))
    }
    const requirements = semanticRequirements(semanticKey)

    return {
      raw_name: rawName,
      display_name: displayName,
      semantic_key: semanticKey,
      semantic_role: semanticRole,
      aliases,
      required: requirements.required,
      hash_participates: requirements.hash_participates,
      hash_eligible: requirements.hash_eligible,
      semantic_kind: requirements.semantic_kind,
      identity_strength: requirements.identity_strength,
      hash_warning: requirements.hash_warning,
      semantic_review_status: semanticKey ? 'confirmed_semantic' : 'pending',
      position,
      sample_type: sampleType,
      confidence,
    }
  })
}

export function updateHeaderBindingSemantic(headerBindings = [], rawName, semanticKey) {
  return (Array.isArray(headerBindings) ? headerBindings : []).map((binding) => {
    if (binding?.raw_name !== rawName) return binding
    if (semanticKey === NON_SEMANTIC_FIELD_VALUE) {
      return {
        ...binding,
        semantic_key: null,
        semantic_role: null,
        aliases: [],
        required: false,
        hash_participates: false,
        hash_eligible: false,
        semantic_kind: '',
        semantic_review_status: 'confirmed_non_semantic',
        display_name: binding?.display_name || binding?.raw_name,
      }
    }
    const normalizedKey = semanticKey || null
    const meta = normalizedKey ? getSemanticFieldMeta(normalizedKey) : null
    const requirements = semanticRequirements(normalizedKey)
    return {
      ...binding,
      semantic_key: normalizedKey,
      semantic_role: normalizedKey === 'metric_date' ? 'metric_date' : binding?.semantic_role || null,
      aliases: meta?.aliases ? [...meta.aliases] : [],
      required: requirements.required,
      hash_participates: requirements.hash_participates,
      hash_eligible: requirements.hash_eligible,
      semantic_kind: requirements.semantic_kind,
      identity_strength: requirements.identity_strength,
      hash_warning: requirements.hash_warning,
      semantic_review_status: normalizedKey ? 'confirmed_semantic' : 'pending',
      display_name: binding?.display_name || binding?.raw_name,
    }
  })
}

export function formatHeaderBindingLabel(field, headerBindings = []) {
  const binding = (Array.isArray(headerBindings) ? headerBindings : []).find(
    item => item?.raw_name === field || item?.semantic_key === field
  )

  if (!binding) return field
  const meta = getSemanticFieldMeta(binding.semantic_key)
  if (meta) {
    return `${meta.label} (${binding.raw_name || field})`
  }
  if (binding.display_name && binding.display_name !== binding.raw_name) {
    return `${binding.display_name} (${binding.raw_name})`
  }
  return binding.raw_name || field
}
