function looksLikeUnnamedHeader(columnName) {
  return String(columnName ?? '').trim().toLowerCase().startsWith('unnamed:')
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
      semanticRole = 'metric_date'
      aliases = ['日期', '统计日期']
    }

    return {
      raw_name: rawName,
      display_name: displayName,
      semantic_role: semanticRole,
      aliases,
      position,
      sample_type: sampleType,
      confidence,
    }
  })
}

export function formatHeaderBindingLabel(field, headerBindings = []) {
  const binding = (Array.isArray(headerBindings) ? headerBindings : []).find(
    item => item?.raw_name === field
  )

  if (!binding) return field
  if (binding.display_name && binding.display_name !== binding.raw_name) {
    return `${binding.display_name} (${binding.raw_name})`
  }
  return binding.raw_name || field
}
