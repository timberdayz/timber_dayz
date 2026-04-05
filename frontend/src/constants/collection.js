export const DOMAIN_SUBTYPE_OPTIONS = {
  orders: [
    { label: 'Shopee', value: 'shopee' },
    { label: 'TikTok', value: 'tiktok' }
  ],
  services: [
    { label: '人工客服', value: 'agent' },
    { label: '智能客服', value: 'ai_assistant' }
  ]
}

export const DEFAULT_DOMAIN_OPTIONS = [
  { label: '订单', value: 'orders' },
  { label: '产品', value: 'products' },
  { label: '流量分析', value: 'analytics' },
  { label: '财务', value: 'finance' },
  { label: '服务', value: 'services' },
  { label: '库存', value: 'inventory' }
]

export const getSubtypeOptions = (domain) => DOMAIN_SUBTYPE_OPTIONS[domain] || []

export const buildAutoSelectedSubDomains = (dataDomains = []) => {
  const result = {}
  for (const domain of dataDomains || []) {
    const options = getSubtypeOptions(domain)
    if (options.length > 0) {
      result[domain] = options.map((option) => option.value)
    }
  }
  return result
}

export const getSelectedSubtypeDomains = (dataDomains = []) =>
  (dataDomains || []).filter((domain) => getSubtypeOptions(domain).length > 0)

export const getAvailableDomainOptions = (platform = '') => {
  return DEFAULT_DOMAIN_OPTIONS
}

export const normalizeConfigGranularity = (config = {}) => {
  const explicit = String(config.granularity || '').toLowerCase()
  if (explicit === 'daily' || explicit === 'weekly' || explicit === 'monthly') {
    return explicit
  }

  const preset = String(config.date_range_type || '').toLowerCase()
  if (preset === 'today' || preset === 'yesterday') return 'daily'
  if (preset === 'last_7_days') return 'weekly'
  if (preset === 'last_30_days') return 'monthly'
  return 'daily'
}

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
      end_date: customRange[1]
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

export const buildTimeSelectionPayload = (
  preset,
  {
    customRange = [],
    startTime = '00:00:00',
    endTime = '23:59:59'
  } = {}
) => {
  if (preset === 'custom' && Array.isArray(customRange) && customRange.length === 2) {
    return {
      mode: 'custom',
      start_date: customRange[0],
      end_date: customRange[1],
      start_time: startTime,
      end_time: endTime
    }
  }

  if (preset === 'today' || preset === 'yesterday' || preset === 'last_7_days' || preset === 'last_30_days') {
    return {
      mode: 'preset',
      preset
    }
  }

  return null
}

export const resolveAccountIdsForConfigRun = (config = {}, accounts = []) => {
  const explicit = Array.isArray(config.account_ids) ? config.account_ids.filter(Boolean) : []
  if (explicit.length > 0) {
    return explicit
  }

  const platform = String(config.platform || '').toLowerCase()
  return (accounts || [])
    .filter((account) => String(account.platform || '').toLowerCase() === platform)
    .filter((account) => String(account.status || '').toLowerCase() === 'active')
    .map((account) => account.id)
}
