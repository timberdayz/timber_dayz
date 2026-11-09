/**
 * 整月批量确认工资单的前端辅助。
 *
 * 后端行为：POST /hr/payroll-records/confirm-batch
 *   * 全部校验通过才整体提交，不会出现「确认了一个人、其他人全被锁死」；
 *   * 校验不通过时返回 data.issues 清单，每条说明「谁、缺什么」：
 *       { employee_code, record_id, reason }
 *
 * 前端的职责只是把这份清单完整地翻译给运营，
 * 而不是只弹一个「确认失败」。
 */

/**
 * 从各种错误形态里把 issues 清单取出来。
 *
 * 兼容三种来源：
 *   1. api 拦截器包装过的错误：error.data.issues
 *   2. 原始 axios 错误：error.response.data.data.issues
 *   3. 直接给到的响应体：response.data.issues
 */
export function extractBatchConfirmIssues(source) {
  if (!source) return []
  const candidates = [
    source?.data?.issues,
    source?.response?.data?.data?.issues,
    source?.response?.data?.issues,
    source?.issues
  ]
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate
        .filter((item) => item && typeof item === 'object')
        .map((item) => ({
          employee_code: String(item.employee_code ?? ''),
          record_id: item.record_id ?? null,
          reason: String(item.reason ?? '').trim() || '未说明原因'
        }))
    }
  }
  return []
}

/** 单条待办的文案：「谁 + 缺什么」。 */
export function formatBatchConfirmIssue(issue) {
  const who = String(issue?.employee_code ?? '').trim() || '未知员工'
  const reason = String(issue?.reason ?? '').trim() || '未说明原因'
  return `${who}：${reason}`
}

/** 待办清单的逐行文案，直接可以丢进 MessageBox 展示。 */
export function formatBatchConfirmIssueLines(issues = []) {
  return (Array.isArray(issues) ? issues : []).map(formatBatchConfirmIssue)
}

/**
 * 转义文本，避免把后端返回的原因当成 HTML 执行。
 */
export function escapeHtmlText(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 待办清单的 HTML 版本：每条一行。
 * MessageBox 默认会把换行折叠成一行，所以这里用已转义的 <p> 保证逐条可见。
 */
export function formatBatchConfirmIssueHtml(issues = []) {
  return (Array.isArray(issues) ? issues : [])
    .map((issue) => `<p>${escapeHtmlText(formatBatchConfirmIssue(issue))}</p>`)
    .join('')
}

/** 批量确认成功的张数。 */
export function extractBatchConfirmSuccessCount(response) {
  const data = response?.data ?? response ?? {}
  const count = Number(data.confirmed_count ?? 0)
  return Number.isFinite(count) ? count : 0
}
