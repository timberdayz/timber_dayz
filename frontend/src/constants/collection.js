export const DOMAIN_SUBTYPE_OPTIONS = {
  services: [
    { label: '人工客服', value: 'agent' },
    { label: '智能客服', value: 'ai_assistant' },
  ],
}

export const getSubtypeOptions = (domain) => DOMAIN_SUBTYPE_OPTIONS[domain] || []

export const getSelectedSubtypeDomains = (dataDomains = []) =>
  (dataDomains || []).filter((domain) => getSubtypeOptions(domain).length > 0)

export const normalizeDomainSubtypeMap = (rawValue) => {
  if (!rawValue) return {}
  if (Array.isArray(rawValue)) {
    return rawValue.length > 0 ? { services: [...rawValue] } : {}
  }

  const normalized = {}
  for (const [domain, values] of Object.entries(rawValue || {})) {
    if (!Array.isArray(values)) continue
    const filtered = values.filter((value) =>
      getSubtypeOptions(domain).some((option) => option.value === value)
    )
    if (filtered.length > 0) {
      normalized[domain] = filtered
    }
  }
  return normalized
}

export const getDatePresetLabel = (preset, platform = '') => {
  if (preset === 'last_7_days') return '最近7天'
  if (preset === 'last_30_days') {
    return String(platform).toLowerCase() === 'tiktok' ? '最近28天' : '最近30天'
  }
  return preset
}

export const buildDateRangeFromPreset = (
  preset,
  { platform = '', customRange = [] } = {}
) => {
  const today = new Date()
  const formatDate = (value) => value.toISOString().split('T')[0]

  if (preset === 'custom' && Array.isArray(customRange) && customRange.length === 2) {
    return {
      start_date: customRange[0],
      end_date: customRange[1],
    }
  }

  switch (preset) {
    case 'today':
      return { start_date: formatDate(today), end_date: formatDate(today) }
    case 'yesterday': {
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)
      return { start_date: formatDate(yesterday), end_date: formatDate(yesterday) }
    }
    case 'last_7_days': {
      const start = new Date(today)
      start.setDate(start.getDate() - 7)
      return { start_date: formatDate(start), end_date: formatDate(today) }
    }
    case 'last_30_days': {
      const span = String(platform).toLowerCase() === 'tiktok' ? 28 : 30
      const start = new Date(today)
      start.setDate(start.getDate() - span)
      return { start_date: formatDate(start), end_date: formatDate(today) }
    }
    default:
      return {}
  }
}
