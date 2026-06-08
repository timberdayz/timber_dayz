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
    description: '标准化属性字段，名称变化不应默认改变 Data Hash。',
    aliases: ['product_name', 'item_name', 'product name', 'item name', '商品名', '商品名称', '产品名称'],
    kind: 'attribute',
    hash_eligible: false,
    default_hash: false,
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

const SEMANTIC_FIELD_ALIASES = Object.fromEntries(
  Object.entries(SEMANTIC_FIELD_META).map(([key, meta]) => [key, meta.aliases])
)

export const NON_SEMANTIC_FIELD_VALUE = '__non_semantic__'

export const SEMANTIC_FIELD_OPTIONS = [
  {
    value: NON_SEMANTIC_FIELD_VALUE,
    label: '仅保留原始字段，不参与 Data Hash',
    description: '保留 raw_data 原始值，不标定为标准语义字段，也不能参与 Data Hash。',
  },
  ...Object.entries(SEMANTIC_FIELD_META).map(([value, meta]) => ({
    value,
    label: `${meta.label} (${value})`,
    description: meta.description,
    aliases: meta.aliases,
    kind: meta.kind,
    hash_eligible: meta.hash_eligible,
    system_scope: meta.system_scope === true,
  })),
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
    hash_participates: Boolean(meta?.default_hash) && !isSystemScopeSemanticKey(semanticKey),
    hash_eligible: Boolean(meta?.hash_eligible),
    semantic_kind: meta?.kind || '',
    system_scope: Boolean(meta?.system_scope),
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
