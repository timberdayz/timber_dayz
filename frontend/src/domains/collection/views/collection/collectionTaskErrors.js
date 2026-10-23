/**
 * 采集任务详情页的域级错误展示辅助（纯函数，便于单测）。
 *
 * 背景：域级失败时，后端把完整 Playwright call log 写进
 * `failed_domains[].error`，而顶层 `error_message` 为空。
 * 旧模板只渲染域名，导致已在库中的诊断信息完全不可见。
 */

const asText = (value) => (typeof value === 'string' ? value : '')

/**
 * 把后端的 failed_domains 规整成可渲染的 { key, label, error } 列表。
 * 兼容字符串形态（历史数据里存在裸域名数组）。
 */
export const normalizeFailedDomains = (failedDomains) => {
  if (!Array.isArray(failedDomains)) return []

  return failedDomains.map((item, index) => {
    if (item && typeof item === 'object') {
      const label = asText(item.domain) || asText(item.name) || `域 ${index + 1}`
      return { key: `${label}-${index}`, label, error: asText(item.error) }
    }
    const label = asText(item) || `域 ${index + 1}`
    return { key: `${label}-${index}`, label, error: '' }
  })
}

/**
 * 顶部「错误信息」栏的取值：顶层 error_message 优先，其次回落到首个域级错误。
 */
export const pickPrimaryErrorMessage = (task) => {
  const topLevel = asText(task && task.error_message)
  if (topLevel) return topLevel

  const failed = normalizeFailedDomains(task && task.failed_domains)
  const withError = failed.find((item) => item.error)
  return withError ? withError.error : ''
}
