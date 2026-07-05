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

export const DYNAMIC_DATE_RANGE_TYPE_TO_STRATEGY = {
  auto_prev_day: 'previous_day',
  auto_week_to_date: 'current_week_to_available_day',
  auto_month_to_date: 'current_month_to_available_day'
}

export const DYNAMIC_STRATEGY_TO_UI_DATE_RANGE_TYPE = {
  previous_day: 'dynamic:previous_day',
  current_week_to_available_day: 'dynamic:current_week_to_available_day',
  current_month_to_available_day: 'dynamic:current_month_to_available_day'
}

export const normalizeConfigGranularity = (config = {}) => {
  const explicit = String(config.granularity || '').toLowerCase()
  if (explicit === 'daily' || explicit === 'weekly' || explicit === 'monthly') {
    return explicit
  }

  const preset = String(config.date_range_type || '').toLowerCase()
  if (preset === 'dynamic:previous_day') return 'daily'
  if (preset === 'dynamic:current_week_to_available_day') return 'weekly'
  if (preset === 'dynamic:current_month_to_available_day') return 'monthly'
  if (preset === 'auto_prev_day') return 'daily'
  if (preset === 'auto_week_to_date') return 'weekly'
  if (preset === 'auto_month_to_date') return 'monthly'
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
  if (preset === 'dynamic:previous_day') return '昨天'
  if (preset === 'dynamic:current_week_to_available_day') return '本周累计到最近可采集日'
  if (preset === 'dynamic:current_month_to_available_day') return '本月累计到最近可采集日'
  if (preset === 'auto_prev_day') return '昨天'
  if (preset === 'auto_week_to_date') return '本周累计到最近可采集日'
  if (preset === 'auto_month_to_date') return '本月累计到最近可采集日'
  if (preset === 'last_7_days') return '最近7天'
  if (preset === 'last_30_days') {
    return String(platform).toLowerCase() === 'tiktok' ? '最近28天' : '最近30天'
  }
  return preset
}

export const getDefaultDynamicDateRangeType = (granularity) => {
  if (granularity === 'weekly') return 'dynamic:current_week_to_available_day'
  if (granularity === 'monthly') return 'dynamic:current_month_to_available_day'
  return 'dynamic:previous_day'
}

export const getDynamicStrategyFromDateRangeType = (value) => {
  const normalized = String(value || '').toLowerCase()
  if (DYNAMIC_DATE_RANGE_TYPE_TO_STRATEGY[normalized]) {
    return DYNAMIC_DATE_RANGE_TYPE_TO_STRATEGY[normalized]
  }
  return normalized.startsWith('dynamic:') ? normalized.split(':')[1] : ''
}

export const getUiDateRangeTypeFromTimeSelection = (timeSelection = {}, fallback = '') => {
  if (String(timeSelection?.mode || '').toLowerCase() === 'dynamic') {
    return DYNAMIC_STRATEGY_TO_UI_DATE_RANGE_TYPE[String(timeSelection.strategy || '').toLowerCase()] || fallback
  }
  return fallback
}

const DYNAMIC_PREVIEW_TIME_ZONE = 'Asia/Hong_Kong'

const padDatePart = (value) => String(value).padStart(2, '0')

const formatUtcDate = (value) =>
  `${value.getUTCFullYear()}-${padDatePart(value.getUTCMonth() + 1)}-${padDatePart(value.getUTCDate())}`

const addDays = (value, days) => {
  const next = new Date(value)
  next.setUTCDate(next.getUTCDate() + days)
  return next
}

const getZonedDateParts = (value) => {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: DYNAMIC_PREVIEW_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).formatToParts(value)

  return Object.fromEntries(
    parts
      .filter((part) => part.type !== 'literal')
      .map((part) => [part.type, Number(part.value)])
  )
}

export const buildDynamicTimeWindowPreview = (preset, now = new Date()) => {
  const strategy = getDynamicStrategyFromDateRangeType(preset)
  if (!strategy) return null

  const current = now instanceof Date ? new Date(now) : new Date(now)
  if (Number.isNaN(current.getTime())) return null
  const currentParts = getZonedDateParts(current)

  const cutoffHour = 6
  const cutoffMinute = 0
  const afterCutoff =
    currentParts.hour > cutoffHour
    || (currentParts.hour === cutoffHour && currentParts.minute >= cutoffMinute)
  const currentDate = new Date(Date.UTC(currentParts.year, currentParts.month - 1, currentParts.day))
  const availableDay = addDays(currentDate, afterCutoff ? -1 : -2)

  let start = new Date(availableDay)
  if (strategy === 'current_week_to_available_day') {
    const day = start.getUTCDay()
    const offsetToMonday = day === 0 ? -6 : 1 - day
    start = addDays(start, offsetToMonday)
  } else if (strategy === 'current_month_to_available_day') {
    start = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1))
  }

  return {
    start_date: formatUtcDate(start),
    end_date: formatUtcDate(availableDay),
    available_after_time: '06:00',
    time_window_label: getDatePresetLabel(preset)
  }
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
  const dynamicStrategy = getDynamicStrategyFromDateRangeType(preset)
  if (dynamicStrategy) {
    return {
      mode: 'dynamic',
      strategy: dynamicStrategy,
      available_after_time: '06:00'
    }
  }

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
