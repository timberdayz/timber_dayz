export const WEEKDAY_OPTIONS = [
  { key: '1', label: '周一' },
  { key: '2', label: '周二' },
  { key: '3', label: '周三' },
  { key: '4', label: '周四' },
  { key: '5', label: '周五' },
  { key: '6', label: '周六' },
  { key: '7', label: '周日' }
]

export function calculateShopTargetTotals(shops = []) {
  return shops.reduce((acc, shop) => {
    acc.ratioPercent = round(acc.ratioPercent + Number(shop.ratio_percent || 0), 4)
    acc.amount = round(acc.amount + Number(shop.target_amount || 0), 2)
    acc.quantity += Number(shop.target_quantity || 0)
    return acc
  }, { ratioPercent: 0, amount: 0, quantity: 0 })
}

export function splitShopTargetsByPercent(shops = [], companyAmount = 0, companyQuantity = 0) {
  const result = shops.map((shop) => {
    const percent = Number(shop.ratio_percent || 0)
    const ratio = percent / 100
    return {
      ...shop,
      ratio,
      target_amount: round(Number(companyAmount || 0) * ratio, 2),
      target_quantity: Math.floor(Number(companyQuantity || 0) * ratio)
    }
  })

  const totals = calculateShopTargetTotals(result)
  if (Math.abs(totals.ratioPercent - 100) < 0.01 && result.length) {
    const amountDiff = round(Number(companyAmount || 0) - totals.amount, 2)
    const quantityDiff = Number(companyQuantity || 0) - totals.quantity
    result[result.length - 1].target_amount = round(Number(result[result.length - 1].target_amount || 0) + amountDiff, 2)
    result[result.length - 1].target_quantity = Number(result[result.length - 1].target_quantity || 0) + quantityDiff
  }

  return result
}

export function splitShopTargetsEqually(shops = [], companyAmount = 0, companyQuantity = 0) {
  if (!shops.length) return []
  const basePercent = round(100 / shops.length, 2)
  let usedPercent = 0
  const withRatios = shops.map((shop, index) => {
    const ratioPercent = index === shops.length - 1 ? round(100 - usedPercent, 2) : basePercent
    usedPercent = round(usedPercent + ratioPercent, 2)
    return { ...shop, ratio_percent: ratioPercent }
  })
  return splitShopTargetsByPercent(withRatios, companyAmount, companyQuantity)
}

export function normalizeWeekdayRatiosToPercents(ratios = {}) {
  return WEEKDAY_OPTIONS.reduce((result, day) => {
    result[day.key] = round(Number(ratios?.[day.key] ?? (1 / 7)) * 100, 4)
    return result
  }, {})
}

export function buildWeekdayRatiosPayload(weekdayRatioPercents = {}) {
  return WEEKDAY_OPTIONS.reduce((result, day) => {
    result[day.key] = Number(weekdayRatioPercents[day.key] || 0) / 100
    return result
  }, {})
}

export function buildMonthDailyPreview({
  yearMonth,
  amountTotal = 0,
  quantityTotal = 0,
  weekdayRatioPercents = {}
}) {
  const [year, month] = yearMonth.split('-').map(Number)
  const daysInMonth = new Date(year, month, 0).getDate()
  const monthDates = Array.from({ length: daysInMonth }, (_, index) => {
    const date = new Date(year, month - 1, index + 1)
    const weekdayKey = String(date.getDay() === 0 ? 7 : date.getDay())
    return {
      date,
      weekdayKey,
      dateText: `${yearMonth}-${String(index + 1).padStart(2, '0')}`
    }
  })
  const rawWeights = monthDates.map((item) => Number(weekdayRatioPercents[item.weekdayKey] || 0))
  const totalWeight = rawWeights.reduce((sum, value) => sum + value, 0) || 1
  const amounts = rawWeights.map((weight) => round(Number(amountTotal || 0) * weight / totalWeight, 2))
  if (amounts.length) {
    amounts[amounts.length - 1] = round(amounts.at(-1) + round(Number(amountTotal || 0) - amounts.reduce((sum, value) => sum + value, 0), 2), 2)
  }
  const rawQuantities = rawWeights.map((weight) => Number(quantityTotal || 0) * weight / totalWeight)
  const quantities = rawQuantities.map((value) => Math.floor(value))
  let remainder = Number(quantityTotal || 0) - quantities.reduce((sum, value) => sum + value, 0)
  rawQuantities
    .map((value, index) => ({ index, rest: value - Math.floor(value) }))
    .sort((a, b) => b.rest - a.rest)
    .forEach((item) => {
      if (remainder > 0) {
        quantities[item.index] += 1
        remainder -= 1
      }
    })
  return monthDates.map((item, index) => ({
    date: item.dateText,
    day: item.date.getDate(),
    weekdayKey: item.weekdayKey,
    weekday: WEEKDAY_OPTIONS.find((day) => day.key === item.weekdayKey)?.label || '',
    ratioPercent: rawWeights[index],
    amount: amounts[index],
    quantity: quantities[index]
  }))
}

function round(value, precision) {
  const factor = 10 ** precision
  return Math.round((Number(value || 0) + Number.EPSILON) * factor) / factor
}
