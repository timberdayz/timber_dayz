const FILE_DATE_SOURCE_COLUMNS = new Set(['__file_date_from__', '__file_date_to__'])

function normalizeTokens(values) {
  return Array.from(
    new Set(
      (Array.isArray(values) ? values : [])
        .map(value => String(value ?? '').trim())
        .filter(Boolean)
        .map(value => value.toLowerCase())
    )
  )
}

function findBindingByRawName(headerBindings, rawName) {
  return (Array.isArray(headerBindings) ? headerBindings : []).find(
    binding => String(binding?.raw_name ?? '').trim() === String(rawName ?? '').trim()
  )
}

function findRemappedBinding({ currentHeaderBindings, templateBinding, rawRule }) {
  const semanticRole = String(
    templateBinding?.semantic_role ?? rawRule?.source_semantic_role ?? ''
  ).trim()
  const aliasTokens = normalizeTokens([
    templateBinding?.display_name,
    rawRule?.source_label,
    ...(templateBinding?.aliases || []),
    ...(rawRule?.source_aliases || []),
  ])

  return (Array.isArray(currentHeaderBindings) ? currentHeaderBindings : []).find(binding => {
    const bindingRole = String(binding?.semantic_role ?? '').trim()
    if (semanticRole && bindingRole && semanticRole === bindingRole) {
      return true
    }

    const bindingTokens = normalizeTokens([binding?.display_name, ...(binding?.aliases || [])])
    return aliasTokens.some(token => bindingTokens.includes(token))
  })
}

export function buildTemplateUpdateFieldParseRulesPayload({
  currentHeaderColumns = [],
  currentHeaderBindings = [],
  templateHeaderBindings = [],
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
    let resolvedSourceColumn = sourceColumn
    const existsInCurrentHeaders = headerLookup.has(sourceColumn.toLowerCase())
    const templateBinding = findBindingByRawName(templateHeaderBindings, sourceColumn)

    if (!isFileDateToken && !existsInCurrentHeaders) {
      const remappedBinding = findRemappedBinding({
        currentHeaderBindings,
        templateBinding,
        rawRule,
      })
      if (!remappedBinding?.raw_name) {
        droppedRules.push({
          target_field: targetField,
          source_column: sourceColumn,
        })
        continue
      }
      resolvedSourceColumn = remappedBinding.raw_name
    }

    const resolvedBinding =
      findBindingByRawName(currentHeaderBindings, resolvedSourceColumn) ||
      templateBinding

    const sourceLabel =
      resolvedBinding?.display_name || String(rawRule.source_label ?? '').trim() || ''
    const sourceAliases = normalizeTokens([
      ...(resolvedBinding?.aliases || []),
      ...(rawRule.source_aliases || []),
    ])
    const sourceSemanticRole = String(
      resolvedBinding?.semantic_role ?? rawRule.source_semantic_role ?? ''
    ).trim()

    rules.push({
      target_field: targetField,
      source_column: resolvedSourceColumn,
      ...(sourceLabel ? { source_label: sourceLabel } : {}),
      ...(sourceAliases.length > 0 ? { source_aliases: sourceAliases } : {}),
      ...(sourceSemanticRole ? { source_semantic_role: sourceSemanticRole } : {}),
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
