function looksLikeUnnamedHeader(columnName) {
  return String(columnName ?? '').trim().toLowerCase().startsWith('unnamed:')
}

export const SEMANTIC_FIELD_META = {
  order_id: {
    label: '订单唯一标识',
    description: '用于识别同一笔订单，参与语义去重。',
    aliases: ['order_id', '订单号', '订单编号', 'order id'],
  },
  product_id: {
    label: '产品 ID',
    description: '用于识别同一商品，通常与 SKU 一起参与去重。',
    aliases: ['product_id', '产品ID', '商品ID', 'product id'],
  },
  platform_sku: {
    label: '平台 SKU',
    description: '平台侧商品规格编号，常用于跨店铺或跨地区的商品识别。',
    aliases: ['platform_sku', '平台SKU', '平台 sku', 'product_sku', '产品SKU', '商品SKU'],
  },
  sku_id: {
    label: 'SKU 内部编号',
    description: '平台或系统内部的 SKU 编号，可参与去重。',
    aliases: ['sku_id', 'sku id', 'SKU ID', 'SKU编号'],
  },
  shop_id: {
    label: '店铺标识',
    description: '用于区分不同店铺，是重要的去重边界。',
    aliases: ['shop_id', '店铺', '店铺ID', 'shop id'],
  },
  warehouse_name: {
    label: '仓库标识',
    description: '用于区分同一 SKU 在不同仓库的库存快照，可参与去重。',
    aliases: ['warehouse_name', 'warehouse', '仓库', '仓库名称', 'warehouse name'],
  },
  metric_date: {
    label: '统计日期',
    description: '用于日级、周级、月级统计的时间定位。',
    aliases: ['metric_date', '日期', '统计日期', 'date'],
  },
  order_date: {
    label: '下单日期',
    description: '订单发生日期，可作为订单时间维度。',
    aliases: ['order_date', '下单日期', '订单日期', '下单时间'],
  },
  period_start_date: {
    label: '周期开始日期',
    description: '区间型报表的开始日期。',
    aliases: ['period_start_date', '开始日期', '周期开始日期'],
  },
  period_end_date: {
    label: '周期结束日期',
    description: '区间型报表的结束日期。',
    aliases: ['period_end_date', '结束日期', '周期结束日期'],
  },
}

const SEMANTIC_FIELD_ALIASES = Object.fromEntries(
  Object.entries(SEMANTIC_FIELD_META).map(([key, meta]) => [key, meta.aliases])
)

export const NON_SEMANTIC_FIELD_VALUE = '__non_semantic__'

export const SEMANTIC_FIELD_OPTIONS = [
  {
    value: NON_SEMANTIC_FIELD_VALUE,
    label: '不作为语义核心字段',
    description: '仅保留原始字段，不参与语义去重。',
  },
  ...Object.entries(SEMANTIC_FIELD_META).map(([value, meta]) => ({
    value,
    label: `${meta.label} (${value})`,
    description: meta.description,
    aliases: meta.aliases,
  })),
]

export function getSemanticFieldMeta(semanticKey) {
  return SEMANTIC_FIELD_META[semanticKey] || null
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
  const hashKeys = new Set([
    'order_id',
    'product_id',
    'platform_sku',
    'sku_id',
    'shop_id',
    'warehouse_name',
    'metric_date',
    'order_date',
  ])
  return {
    required: semanticKey === 'order_id',
    hash_participates: hashKeys.has(semanticKey),
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
