/**
 * 数据格式化工具函数
 */

import dayjs from 'dayjs'

/**
 * 格式化日期
 * @param {Date|string|number} date - 日期
 * @param {string} format - 格式字符串
 * @returns {string} 格式化后的日期
 */
export function formatDate(date, format = 'YYYY-MM-DD') {
  if (!date) return ''
  return dayjs(date).format(format)
}

/**
 * 格式化时间
 * @param {Date|string|number} date - 日期时间
 * @param {string} format - 格式字符串
 * @returns {string} 格式化后的时间
 */
export function formatDateTime(date, format = 'YYYY-MM-DD HH:mm:ss') {
  if (!date) return ''
  return dayjs(date).format(format)
}

/**
 * 格式化相对时间
 * @param {Date|string|number} date - 日期
 * @returns {string} 相对时间
 */
export function formatRelativeTime(date) {
  if (!date) return ''
  return dayjs(date).fromNow()
}

/**
 * 格式化数字
 * @param {number} num - 数字
 * @param {number} decimals - 小数位数
 * @returns {string} 格式化后的数字
 */
export function formatNumber(num, decimals = 2) {
  if (num === null || num === undefined) return '0'
  return Number(num).toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  })
}

/**
 * 格式化金额
 * @param {number} amount - 金额
 * @param {string} currency - 货币符号
 * @returns {string} 格式化后的金额
 */
export function formatCurrency(amount, currency = '¥') {
  if (amount === null || amount === undefined) return `${currency}0.00`
  return `${currency}${formatNumber(amount, 2)}`
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的文件大小
 */
export function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

/**
 * 格式化百分比
 * @param {number} value - 数值
 * @param {number} total - 总数
 * @param {number} decimals - 小数位数
 * @returns {string} 格式化后的百分比
 */
export function formatPercentage(value, total, decimals = 1) {
  if (!total || total === 0) return '0%'
  const percentage = (value / total) * 100
  return `${percentage.toFixed(decimals)}%`
}

/**
 * 格式化状态
 * @param {string} status - 状态
 * @returns {object} 状态配置
 */
export function formatStatus(status) {
  const statusMap = {
    pending: { text: '待处理', type: 'warning' },
    processing: { text: '处理中', type: 'primary' },
    completed: { text: '已完成', type: 'success' },
    failed: { text: '失败', type: 'danger' },
    success: { text: '成功', type: 'success' },
    error: { text: '错误', type: 'danger' },
    warning: { text: '警告', type: 'warning' },
    info: { text: '信息', type: 'info' }
  }
  
  return statusMap[status] || { text: status, type: 'info' }
}

/**
 * 格式化平台名称
 * @param {string} platform - 平台代码
 * @returns {string} 平台名称
 */
export function formatPlatform(platform) {
  const platformMap = {
    shopee: 'Shopee',
    tiktok: 'TikTok',
    amazon: 'Amazon',
    lazada: 'Lazada',
    miaoshou: '妙手ERP',
    unknown: '未知平台'
  }
  
  return platformMap[platform?.toLowerCase()] || platform
}

/**
 * 格式化数据域
 * @param {string} domain - 数据域代码
 * @returns {string} 数据域名称
 */
export function formatDataDomain(domain) {
  const domainMap = {
    orders: '订单数据',
    products: '商品数据',
    traffic: '流量数据',  // ⚠️ 已废弃，保留用于向后兼容
    analytics: '流量数据',  // ⭐ v4.15.0更新：traffic域已统一为analytics域
    service: '服务数据',
    finance: '财务数据',
    unknown: '未知数据域'
  }
  
  return domainMap[domain?.toLowerCase()] || domain
}

/**
 * 格式化置信度
 * @param {number} confidence - 置信度 (0-1)
 * @returns {object} 置信度配置
 */
export function formatConfidence(confidence) {
  const percentage = Math.round(confidence * 100)
  
  if (percentage >= 80) {
    return { text: `${percentage}%`, type: 'success' }
  } else if (percentage >= 60) {
    return { text: `${percentage}%`, type: 'warning' }
  } else {
    return { text: `${percentage}%`, type: 'danger' }
  }
}

/**
 * 截断文本
 * @param {string} text - 文本
 * @param {number} length - 最大长度
 * @returns {string} 截断后的文本
 */
export function truncateText(text, length = 50) {
  if (!text) return ''
  if (text.length <= length) return text
  return text.substring(0, length) + '...'
}

/**
 * 高亮搜索关键词
 * @param {string} text - 原文本
 * @param {string} keyword - 关键词
 * @returns {string} 高亮后的HTML
 */
export function highlightKeyword(text, keyword) {
  if (!text || !keyword) return text
  
  const regex = new RegExp(`(${keyword})`, 'gi')
  return text.replace(regex, '<mark>$1</mark>')
}
