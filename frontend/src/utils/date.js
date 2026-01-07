/**
 * 日期时间工具函数
 */

import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

// 配置dayjs
dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

/**
 * 获取今天的日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getToday() {
  return dayjs().format('YYYY-MM-DD')
}

/**
 * 获取昨天的日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getYesterday() {
  return dayjs().subtract(1, 'day').format('YYYY-MM-DD')
}

/**
 * 获取明天的日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getTomorrow() {
  return dayjs().add(1, 'day').format('YYYY-MM-DD')
}

/**
 * 获取本周开始日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getWeekStart() {
  return dayjs().startOf('week').format('YYYY-MM-DD')
}

/**
 * 获取本周结束日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getWeekEnd() {
  return dayjs().endOf('week').format('YYYY-MM-DD')
}

/**
 * 获取本月开始日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getMonthStart() {
  return dayjs().startOf('month').format('YYYY-MM-DD')
}

/**
 * 获取本月结束日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getMonthEnd() {
  return dayjs().endOf('month').format('YYYY-MM-DD')
}

/**
 * 获取上个月开始日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getLastMonthStart() {
  return dayjs().subtract(1, 'month').startOf('month').format('YYYY-MM-DD')
}

/**
 * 获取上个月结束日期
 * @returns {string} YYYY-MM-DD格式的日期
 */
export function getLastMonthEnd() {
  return dayjs().subtract(1, 'month').endOf('month').format('YYYY-MM-DD')
}

/**
 * 获取最近N天的日期范围
 * @param {number} days - 天数
 * @returns {object} 包含start和end的日期范围
 */
export function getLastNDays(days) {
  const end = getToday()
  const start = dayjs().subtract(days - 1, 'day').format('YYYY-MM-DD')
  return { start, end }
}

/**
 * 获取最近N周的日期范围
 * @param {number} weeks - 周数
 * @returns {object} 包含start和end的日期范围
 */
export function getLastNWeeks(weeks) {
  const end = getToday()
  const start = dayjs().subtract(weeks - 1, 'week').startOf('week').format('YYYY-MM-DD')
  return { start, end }
}

/**
 * 获取最近N月的日期范围
 * @param {number} months - 月数
 * @returns {object} 包含start和end的日期范围
 */
export function getLastNMonths(months) {
  const end = getToday()
  const start = dayjs().subtract(months - 1, 'month').startOf('month').format('YYYY-MM-DD')
  return { start, end }
}

/**
 * 获取预设的日期范围选项
 * @returns {Array} 日期范围选项数组
 */
export function getDateRangeOptions() {
  return [
    {
      label: '今天',
      value: () => ({ start: getToday(), end: getToday() })
    },
    {
      label: '昨天',
      value: () => ({ start: getYesterday(), end: getYesterday() })
    },
    {
      label: '最近7天',
      value: () => getLastNDays(7)
    },
    {
      label: '最近30天',
      value: () => getLastNDays(30)
    },
    {
      label: '最近90天',
      value: () => getLastNDays(90)
    },
    {
      label: '本周',
      value: () => ({ start: getWeekStart(), end: getWeekEnd() })
    },
    {
      label: '上周',
      value: () => ({
        start: dayjs().subtract(1, 'week').startOf('week').format('YYYY-MM-DD'),
        end: dayjs().subtract(1, 'week').endOf('week').format('YYYY-MM-DD')
      })
    },
    {
      label: '本月',
      value: () => ({ start: getMonthStart(), end: getMonthEnd() })
    },
    {
      label: '上月',
      value: () => ({ start: getLastMonthStart(), end: getLastMonthEnd() })
    },
    {
      label: '最近3个月',
      value: () => getLastNMonths(3)
    },
    {
      label: '最近6个月',
      value: () => getLastNMonths(6)
    },
    {
      label: '最近1年',
      value: () => getLastNMonths(12)
    }
  ]
}

/**
 * 验证日期范围
 * @param {string} startDate - 开始日期
 * @param {string} endDate - 结束日期
 * @returns {boolean} 是否有效
 */
export function validateDateRange(startDate, endDate) {
  if (!startDate || !endDate) return false
  
  const start = dayjs(startDate)
  const end = dayjs(endDate)
  
  return start.isValid() && end.isValid() && start.isBefore(end) || start.isSame(end)
}

/**
 * 获取日期范围的天数
 * @param {string} startDate - 开始日期
 * @param {string} endDate - 结束日期
 * @returns {number} 天数
 */
export function getDateRangeDays(startDate, endDate) {
  if (!startDate || !endDate) return 0
  
  const start = dayjs(startDate)
  const end = dayjs(endDate)
  
  return end.diff(start, 'day') + 1
}

/**
 * 格式化日期范围显示
 * @param {string} startDate - 开始日期
 * @param {string} endDate - 结束日期
 * @returns {string} 格式化后的日期范围
 */
export function formatDateRange(startDate, endDate) {
  if (!startDate || !endDate) return ''
  
  const start = dayjs(startDate)
  const end = dayjs(endDate)
  
  if (start.isSame(end, 'day')) {
    return start.format('YYYY年MM月DD日')
  } else if (start.isSame(end, 'month')) {
    return `${start.format('YYYY年MM月')}${start.format('DD日')} - ${end.format('DD日')}`
  } else if (start.isSame(end, 'year')) {
    return `${start.format('YYYY年MM月DD日')} - ${end.format('MM月DD日')}`
  } else {
    return `${start.format('YYYY年MM月DD日')} - ${end.format('YYYY年MM月DD日')}`
  }
}
