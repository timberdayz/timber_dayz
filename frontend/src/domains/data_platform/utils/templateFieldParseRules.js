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
]

export const DATE_VALUE_KIND_OPTIONS = [
  { label: 'single_date', value: 'single_date' },
  { label: 'date_range', value: 'date_range' },
]

export const DATE_FORMAT_OPTIONS = [
  { label: 'yyyy-mm-dd', value: 'yyyy-mm-dd' },
  { label: 'yyyy/mm/dd', value: 'yyyy/mm/dd' },
  { label: 'yyyy-mm-dd hh:mm:ss', value: 'yyyy-mm-dd hh:mm:ss' },
  { label: 'yyyy/mm/dd hh:mm:ss', value: 'yyyy/mm/dd hh:mm:ss' },
  { label: 'dd-mm-yyyy', value: 'dd-mm-yyyy' },
  { label: 'dd/mm/yyyy', value: 'dd/mm/yyyy' },
  { label: 'dd-mm-yyyy hh:mm:ss', value: 'dd-mm-yyyy hh:mm:ss' },
  { label: 'dd/mm/yyyy hh:mm:ss', value: 'dd/mm/yyyy hh:mm:ss' },
  { label: 'dd-mm-yyyy-dd-mm-yyyy', value: 'dd-mm-yyyy-dd-mm-yyyy' },
  { label: 'dd/mm/yyyy-dd/mm/yyyy', value: 'dd/mm/yyyy-dd/mm/yyyy' },
]

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
