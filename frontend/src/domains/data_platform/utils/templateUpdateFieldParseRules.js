const FILE_DATE_SOURCE_COLUMNS = new Set(['__file_date_from__', '__file_date_to__'])

export function buildTemplateUpdateFieldParseRulesPayload({
  currentHeaderColumns = [],
  existingRules = [],
} = {}) {
  const headerLookup = new Set(
    (Array.isArray(currentHeaderColumns) ? currentHeaderColumns : []).map(column =>
      String(column ?? '').trim().toLowerCase()
    )
  )

  const rules = []
  const droppedRules = []

  for (const rawRule of Array.isArray(existingRules) ? existingRules : []) {
    if (!rawRule || typeof rawRule !== 'object') {
      continue
    }

    const sourceColumn = String(rawRule.source_column ?? '').trim()
    const targetField = String(rawRule.target_field ?? '').trim()
    if (!sourceColumn || !targetField) {
      continue
    }

    const isFileDateToken = FILE_DATE_SOURCE_COLUMNS.has(sourceColumn)
    const existsInCurrentHeaders = headerLookup.has(sourceColumn.toLowerCase())

    if (!isFileDateToken && !existsInCurrentHeaders) {
      droppedRules.push({
        target_field: targetField,
        source_column: sourceColumn,
      })
      continue
    }

    rules.push({
      target_field: targetField,
      source_column: sourceColumn,
      value_kind: String(rawRule.value_kind ?? 'single_date').trim() || 'single_date',
      date_format: String(rawRule.date_format ?? '').trim(),
      strict: rawRule.strict !== false,
      ...(rawRule.value_kind === 'date_range' && rawRule.range_pick
        ? { range_pick: String(rawRule.range_pick).trim() }
        : {}),
    })
  }

  return { rules, droppedRules }
}
