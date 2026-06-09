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
]

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

export function buildAutoCompanionFormatPayload(rule = {}) {
  if (String(rule?.date_format || '').trim() !== 'auto_by_companion_period') {
    return {}
  }
  const candidates = Array.isArray(rule?.format_candidates) && rule.format_candidates.length > 0
    ? rule.format_candidates
    : COMPANION_AUTO_DATE_FORMAT_CANDIDATES
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
