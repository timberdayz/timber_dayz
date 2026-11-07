export const FILE_DATE_SOURCE_OPTIONS = [
  {
    label: '文件开始日期（伴生数据 date_from）',
    value: '__file_date_from__',
    source: 'file_metadata',
  },
  {
    label: '文件结束日期（伴生数据 date_to）',
    value: '__file_date_to__',
    source: 'file_metadata',
  },
]

export const DATE_TARGET_FIELD_OPTIONS = [
  { label: 'metric_date', value: 'metric_date' },
  { label: 'period_start_date', value: 'period_start_date' },
  { label: 'period_end_date', value: 'period_end_date' },
  { label: 'period_start_time', value: 'period_start_time' },
  { label: 'period_end_time', value: 'period_end_time' },
]

export const DATE_VALUE_KIND_OPTIONS = [
  { label: 'single_date', value: 'single_date' },
  { label: 'single_datetime', value: 'single_datetime' },
  { label: 'time_of_day', value: 'time_of_day' },
  { label: 'date_range', value: 'date_range' },
  { label: 'datetime_range', value: 'datetime_range' },
  { label: 'time_range', value: 'time_range' },
]

export const DATE_FORMAT_OPTIONS = [
  { label: '系统根据伴生周期自动判断', value: 'auto_by_companion_period' },
  { label: 'yyyy-mm-dd', value: 'yyyy-mm-dd' },
  { label: 'yyyy/mm/dd', value: 'yyyy/mm/dd' },
  { label: 'yyyy-mm-dd hh:mm', value: 'yyyy-mm-dd hh:mm' },
  { label: 'yyyy-mm-dd hh:mm:ss', value: 'yyyy-mm-dd hh:mm:ss' },
  { label: 'yyyy/mm/dd hh:mm', value: 'yyyy/mm/dd hh:mm' },
  { label: 'yyyy/mm/dd hh:mm:ss', value: 'yyyy/mm/dd hh:mm:ss' },
  { label: 'dd-mm-yyyy', value: 'dd-mm-yyyy' },
  { label: 'dd/mm/yyyy', value: 'dd/mm/yyyy' },
  { label: 'dd-mm-yyyy hh:mm', value: 'dd-mm-yyyy hh:mm' },
  { label: 'dd-mm-yyyy hh:mm:ss', value: 'dd-mm-yyyy hh:mm:ss' },
  { label: 'dd/mm/yyyy hh:mm', value: 'dd/mm/yyyy hh:mm' },
  { label: 'dd/mm/yyyy hh:mm:ss', value: 'dd/mm/yyyy hh:mm:ss' },
  { label: 'mm-dd-yyyy', value: 'mm-dd-yyyy' },
  { label: 'mm/dd/yyyy', value: 'mm/dd/yyyy' },
  { label: 'mm-dd-yyyy hh:mm', value: 'mm-dd-yyyy hh:mm' },
  { label: 'mm-dd-yyyy hh:mm:ss', value: 'mm-dd-yyyy hh:mm:ss' },
  { label: 'mm/dd/yyyy hh:mm', value: 'mm/dd/yyyy hh:mm' },
  { label: 'mm/dd/yyyy hh:mm:ss', value: 'mm/dd/yyyy hh:mm:ss' },
  { label: 'hh:mm', value: 'hh:mm' },
  { label: 'hh:mm:ss', value: 'hh:mm:ss' },
  { label: 'dd-mm-yyyy-dd-mm-yyyy', value: 'dd-mm-yyyy-dd-mm-yyyy' },
  { label: 'dd/mm/yyyy-dd/mm/yyyy', value: 'dd/mm/yyyy-dd/mm/yyyy' },
  { label: 'yyyy-mm-dd-yyyy-mm-dd', value: 'yyyy-mm-dd-yyyy-mm-dd' },
  { label: 'yyyy/mm/dd-yyyy/mm/dd', value: 'yyyy/mm/dd-yyyy/mm/dd' },
]

// ── value_kind → 允许的 date_format ─────────────────────────────
//
// 与后端 `modules/services/smart_date_parser.py` 的
// `_DECLARED_FORMATS_BY_VALUE_KIND` **同口径**。
//
// 为什么按 kind 过滤:
//   value_kind 决定「这个值长什么样」, date_format 决定「怎么读」,
//   两者必须自洽 —— 例如 date_range 不能配 `yyyy-mm-dd` 这种单值格式。
//   以前这里是**平铺**一份列表, 用户能选出不兼容的组合, 一保存就报错。
//   现在按 kind 过滤 ⇒ **从结构上**选不出不兼容组合。
//
// 后端仍然会再校验一次(保存闸门), 两边都要有:
// 前端过滤是为了**不让人选错**, 后端校验是为了**拦住绕过前端的写入**。
const DATE_VALUE_KIND_FORMAT_WHITELIST = {
  single_date: [
    'yyyy-mm-dd', 'yyyy/mm/dd',
    'yyyy-mm-dd hh:mm', 'yyyy-mm-dd hh:mm:ss',
    'yyyy/mm/dd hh:mm', 'yyyy/mm/dd hh:mm:ss',
    'dd-mm-yyyy', 'dd/mm/yyyy',
    'dd-mm-yyyy hh:mm', 'dd-mm-yyyy hh:mm:ss',
    'dd/mm/yyyy hh:mm', 'dd/mm/yyyy hh:mm:ss',
    'mm-dd-yyyy', 'mm/dd/yyyy',
    'mm-dd-yyyy hh:mm', 'mm-dd-yyyy hh:mm:ss',
    'mm/dd/yyyy hh:mm', 'mm/dd/yyyy hh:mm:ss',
  ],
  single_datetime: [
    'yyyy-mm-dd', 'yyyy/mm/dd',
    'yyyy-mm-dd hh:mm', 'yyyy-mm-dd hh:mm:ss',
    'yyyy/mm/dd hh:mm', 'yyyy/mm/dd hh:mm:ss',
    'dd-mm-yyyy', 'dd/mm/yyyy',
    'dd-mm-yyyy hh:mm', 'dd-mm-yyyy hh:mm:ss',
    'dd/mm/yyyy hh:mm', 'dd/mm/yyyy hh:mm:ss',
    'mm-dd-yyyy', 'mm/dd/yyyy',
    'mm-dd-yyyy hh:mm', 'mm-dd-yyyy hh:mm:ss',
    'mm/dd/yyyy hh:mm', 'mm/dd/yyyy hh:mm:ss',
  ],
  datetime_range: [
    'yyyy-mm-dd hh:mm', 'yyyy-mm-dd hh:mm:ss',
    'yyyy/mm/dd hh:mm', 'yyyy/mm/dd hh:mm:ss',
    'dd-mm-yyyy hh:mm', 'dd-mm-yyyy hh:mm:ss',
    'dd/mm/yyyy hh:mm', 'dd/mm/yyyy hh:mm:ss',
    'mm-dd-yyyy hh:mm', 'mm-dd-yyyy hh:mm:ss',
    'mm/dd/yyyy hh:mm', 'mm/dd/yyyy hh:mm:ss',
  ],
  time_of_day: ['hh:mm', 'hh:mm:ss'],
  time_range: ['hh:mm', 'hh:mm:ss'],
  date_range: [
    'dd-mm-yyyy-dd-mm-yyyy', 'dd/mm/yyyy-dd/mm/yyyy',
    'yyyy-mm-dd-yyyy-mm-dd', 'yyyy/mm/dd-yyyy/mm/dd',
  ],
}

// auto_by_companion_period 只对「有候选集」的 value_kind 有效。
const AUTO_COMPANION_SUPPORTED_VALUE_KINDS = [
  'single_date', 'single_datetime', 'datetime_range', 'date_range',
]

export function dateFormatOptionsForValueKind(valueKind = 'single_date') {
  const kind = String(valueKind || '').trim() || 'single_date'
  const allowed = DATE_VALUE_KIND_FORMAT_WHITELIST[kind] || []
  const options = DATE_FORMAT_OPTIONS.filter(
    (option) => option.value === 'auto_by_companion_period'
      ? AUTO_COMPANION_SUPPORTED_VALUE_KINDS.includes(kind)
      : allowed.includes(option.value),
  )
  return options.length > 0 ? options : DATE_FORMAT_OPTIONS
}

export const COMPANION_AUTO_DATE_FORMAT_CANDIDATES = [
  'yyyy-mm-dd',
  'yyyy/mm/dd',
  'dd-mm-yyyy',
  'dd/mm/yyyy',
  'mm-dd-yyyy',
  'mm/dd/yyyy',
  'yyyy-mm-dd hh:mm',
  'yyyy-mm-dd hh:mm:ss',
  'yyyy/mm/dd hh:mm',
  'yyyy/mm/dd hh:mm:ss',
  'dd-mm-yyyy hh:mm',
  'dd-mm-yyyy hh:mm:ss',
  'dd/mm/yyyy hh:mm',
  'dd/mm/yyyy hh:mm:ss',
  'mm-dd-yyyy hh:mm',
  'mm-dd-yyyy hh:mm:ss',
  'mm/dd/yyyy hh:mm',
  'mm/dd/yyyy hh:mm:ss',
]

// 候选集按 value_kind 收敛:
//   single_date 只需要**纯日期**格式 —— 带时分秒的候选对纯日期值
//   永远解析失败, 留着只是白白多试几次。
//   注意: **不能**按「日-月-年 家族」收窄 —— 那样美式报表(m/d/y)
//   会解析不了。真正的歧义(日 vs 月)由**文件伴生周期**消解,
//   候选集必须覆盖全部家族。
export function companionFormatCandidatesForValueKind(valueKind = 'single_date', explicit = null) {
  if (Array.isArray(explicit) && explicit.length > 0) {
    return explicit.map((item) => String(item).trim()).filter(Boolean)
  }
  const kind = String(valueKind || '').trim() || 'single_date'
  if (kind === 'single_date') {
    return COMPANION_AUTO_DATE_FORMAT_CANDIDATES.filter(
      (token) => !token.includes('hh:'),
    )
  }
  if (kind === 'date_range') {
    return [
      'dd-mm-yyyy-dd-mm-yyyy',
      'dd/mm/yyyy-dd/mm/yyyy',
      'yyyy-mm-dd-yyyy-mm-dd',
      'yyyy/mm/dd-yyyy/mm/dd',
    ]
  }
  return COMPANION_AUTO_DATE_FORMAT_CANDIDATES
}

export function buildAutoCompanionFormatPayload(rule = {}) {
  if (String(rule?.date_format || '').trim() !== 'auto_by_companion_period') {
    return {}
  }
  const candidates = companionFormatCandidatesForValueKind(
    rule?.value_kind,
    rule?.format_candidates,
  )
  return {
    format_candidates: candidates,
    resolution_source: 'companion_period',
  }
}

export const DATE_ANCHOR_OPTIONS = [
  { label: '文件开始日期（date_from）', value: '__file_date_from__' },
  { label: '文件结束日期（date_to）', value: '__file_date_to__' },
]

export function fieldParseRuleNeedsRangePick(rule = {}) {
  return ['date_range', 'datetime_range', 'time_range'].includes(String(rule?.value_kind || '').trim())
}

export function fieldParseRuleNeedsDateAnchor(rule = {}) {
  return ['time_of_day', 'time_range'].includes(String(rule?.value_kind || '').trim())
}

export function buildFieldParseSourceOptions(headerColumns = []) {
  const rawHeaderOptions = (Array.isArray(headerColumns) ? headerColumns : [])
    .map(column => String(column ?? '').trim())
    .filter(Boolean)
    .map(column => ({
      label: column,
      value: column,
      source: 'header',
    }))
  return [...FILE_DATE_SOURCE_OPTIONS, ...rawHeaderOptions]
}

export function buildCompanionDateParseRules(mode = 'single') {
  if (mode === 'period') {
    return [
      {
        target_field: 'period_start_date',
        source_column: '__file_date_from__',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
      {
        target_field: 'period_end_date',
        source_column: '__file_date_to__',
        value_kind: 'single_date',
        date_format: 'yyyy-mm-dd',
        strict: true,
      },
    ]
  }

  return [
    {
      target_field: 'metric_date',
      source_column: '__file_date_from__',
      value_kind: 'single_date',
      date_format: 'yyyy-mm-dd',
      strict: true,
    },
  ]
}

export function hasHeaderDateOrTimeSource(headerBindings = [], headerColumns = []) {
  const dateTargets = new Set(DATE_TARGET_FIELD_OPTIONS.map(option => option.value))
  const bindings = Array.isArray(headerBindings) ? headerBindings : []
  if (bindings.some((binding) => {
    const source = String(binding?.raw_name || binding?.display_name || '').trim()
    const semanticKey = String(binding?.semantic_key || '').trim()
    const sampleType = String(binding?.sample_type || '').trim()
    return source && (dateTargets.has(semanticKey) || sampleType === 'date' || sampleType === 'datetime')
  })) {
    return true
  }

  return (Array.isArray(headerColumns) ? headerColumns : []).some((column) => {
    const text = String(column || '').trim().toLowerCase()
    return /date|time|日期|时间|周期|期间/.test(text)
  })
}

export function buildAutoCompanionDateParseRules({
  dataDomain = '',
  granularity = '',
  headerBindings = [],
  headerColumns = [],
  currentRules = [],
} = {}) {
  const domain = String(dataDomain || '').trim().toLowerCase()
  if (domain !== 'products') {
    return []
  }
  if (hasHeaderDateOrTimeSource(headerBindings, headerColumns)) {
    return []
  }
  const existingTargets = new Set(
    (Array.isArray(currentRules) ? currentRules : [])
      .map(rule => String(rule?.target_field || '').trim())
      .filter(Boolean)
  )
  const grain = String(granularity || '').trim().toLowerCase()
  const requiredTargets = grain === 'daily'
    ? ['metric_date']
    : ['period_start_date', 'period_end_date']
  if (requiredTargets.every(target => existingTargets.has(target))) {
    return []
  }
  const mode = grain === 'daily' ? 'single' : 'period'
  return buildCompanionDateParseRules(mode).filter(rule => !existingTargets.has(rule.target_field))
}

export function mergeFieldParseRules(existingRules = [], incomingRules = []) {
  const incomingTargets = new Set(
    (Array.isArray(incomingRules) ? incomingRules : [])
      .map(rule => String(rule?.target_field ?? '').trim())
      .filter(Boolean)
  )
  const retainedRules = (Array.isArray(existingRules) ? existingRules : []).filter((rule) => {
    const targetField = String(rule?.target_field ?? '').trim()
    return targetField && !incomingTargets.has(targetField)
  })
  return [
    ...retainedRules,
    ...(Array.isArray(incomingRules) ? incomingRules : []),
  ]
}
