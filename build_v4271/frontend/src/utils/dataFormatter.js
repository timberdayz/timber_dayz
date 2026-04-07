/**
 * 数据格式化工具函数（仅处理空数据，不处理API错误）
 * 
 * 重要区分：
 * - 空数据：API成功返回（success: true），但数据为空 → 显示"-"
 * - API错误：API返回错误（success: false）或请求失败 → 显示错误信息（由errorHandler处理）
 * 
 * 使用场景：仅在API成功时使用这些函数处理空数据
 * 
 * 极简原则：
 * - 日期格式化请使用 @/utils/format.js 或 @/utils/date.js（基于 dayjs）
 * - 安全访问属性请使用 JavaScript 原生可选链 ?.
 */

/**
 * 格式化值（处理null/undefined/空字符串）
 * @param {*} value - 要格式化的值
 * @param {string} defaultValue - 默认值（默认"-"）
 * @returns {string} 格式化后的值
 */
export function formatValue(value, defaultValue = '-') {
  if (value === null || value === undefined || value === '') {
    return defaultValue
  }
  return String(value)
}

/**
 * 格式化数字（处理null/undefined，0值正常显示）
 * @param {*} value - 要格式化的数字
 * @param {number} decimals - 小数位数（默认2）
 * @param {string} defaultValue - 默认值（默认"-"）
 * @returns {string} 格式化后的数字
 */
export function formatNumber(value, decimals = 2, defaultValue = '-') {
  if (value === null || value === undefined || value === '') {
    return defaultValue
  }
  
  const num = Number(value)
  if (isNaN(num)) {
    return defaultValue
  }
  
  // 0值正常显示，不显示"-"
  if (num === 0) {
    return '0'
  }
  
  return num.toFixed(decimals)
}

/**
 * 格式化百分比（处理null/undefined）
 * @param {*} value - 要格式化的百分比值（0-100或0-1的小数）
 * @param {number} decimals - 小数位数（默认2）
 * @param {string} defaultValue - 默认值（默认"-"）
 * @param {boolean} isDecimal - 是否为小数格式（0-1），如果是则乘以100（默认false）
 * @returns {string} 格式化后的百分比
 */
export function formatPercent(value, decimals = 2, defaultValue = '-', isDecimal = false) {
  if (value === null || value === undefined || value === '') {
    return defaultValue
  }
  
  const num = Number(value)
  if (isNaN(num)) {
    return defaultValue
  }
  
  // 如果是小数格式（0-1），转换为百分比（0-100）
  const percentValue = isDecimal ? num * 100 : num
  
  // 0值正常显示
  if (percentValue === 0) {
    return '0%'
  }
  
  return `${percentValue.toFixed(decimals)}%`
}

/**
 * 格式化整数（添加千分位，处理null/undefined）
 * @param {*} value - 要格式化的整数
 * @param {string} defaultValue - 默认值（默认"-"）
 * @returns {string} 格式化后的整数
 */
export function formatInteger(value, defaultValue = '-') {
  if (value === null || value === undefined || value === '') {
    return defaultValue
  }
  
  const num = Number(value)
  if (isNaN(num)) {
    return defaultValue
  }
  
  // 0值正常显示
  if (num === 0) {
    return '0'
  }
  
  // 转换为整数并添加千分位（使用原生 Intl API）
  return Math.floor(num).toLocaleString('zh-CN')
}

/**
 * 格式化货币（处理null/undefined）
 * @param {*} value - 要格式化的金额
 * @param {string} currency - 货币符号（默认"¥"）
 * @param {number} decimals - 小数位数（默认2）
 * @param {string} defaultValue - 默认值（默认"-"）
 * @returns {string} 格式化后的货币
 */
export function formatCurrency(value, currency = '¥', decimals = 2, defaultValue = '-') {
  if (value === null || value === undefined || value === '') {
    return defaultValue
  }
  
  const num = Number(value)
  if (isNaN(num)) {
    return defaultValue
  }
  
  // 0值正常显示
  if (num === 0) {
    return `${currency}0.00`
  }
  
  // 使用原生 Intl API 添加千分位
  const formatted = num.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
  return `${currency}${formatted}`
}

/**
 * 格式化列表为空状态提示（仅API成功时）
 * @param {array} list - 列表数据
 * @param {string} emptyText - 空状态提示文本（默认"暂无数据"）
 * @returns {array|string} 列表数据或空状态提示
 */
export function formatList(list, emptyText = '暂无数据') {
  if (!Array.isArray(list) || list.length === 0) {
    return emptyText
  }
  return list
}
