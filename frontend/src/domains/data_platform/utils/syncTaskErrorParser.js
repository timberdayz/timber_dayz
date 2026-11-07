export function extractHeaderChangeErrorEntries(task) {
  const errors = Array.isArray(task?.errors) ? task.errors : []
  return errors
    .map((entry) => {
      const message = typeof entry === 'string' ? entry : String(entry?.message || '')
      const match = message.match(/^文件(?<file_id>\d+):\s*(?<detail>.+)$/)
      if (!match?.groups?.detail) return null
      const detail = match.groups.detail
      const hasHeaderChanged = detail.includes('表头字段已变化') || detail.includes('请更新模板后再同步')
      if (!hasHeaderChanged) return null
      return {
        file_id: Number(match.groups.file_id),
        message,
        detail,
        is_header_changed: true,
      }
    })
    .filter(Boolean)
}

export function hasHeaderChangeHints(task) {
  return extractHeaderChangeErrorEntries(task).length > 0
}

/**
 * [*] 批次 B · API-7
 * ---------------------------------------------------------------------------
 * 日期解析失败的结构化错误码。
 *
 * 以前入库失败只有一句自然语言:
 *   "failed to parse metric_date from source_column=日期: 01-10-2026"
 * 前端只能靠字符串猜原因, 于是三种完全不同的处置
 * (换模板 / 查文件期间 / 消歧义) 全都显示成同一句「解析失败」。
 *
 * 现在后端在消息前面带一个 ``[错误码]``, 前端按错误码分流:
 *   [date_format_mismatch]  声明的格式解不出这个值 —— 文件的值形态变了
 *   [date_out_of_period]     能解析出来, 但落在文件期间之外
 *   [date_ambiguous]         多个候选能解出不同的日期 —— 不确定, 不能猜
 *   [date_unsupported_format] 模板声明的格式本身非法
 */

export const DATE_ERROR_CODE_LABELS = {
  date_format_mismatch: '日期格式与模板声明不一致',
  date_out_of_period: '日期超出文件期间',
  date_ambiguous: '日期存在歧义，无法自动判定',
  date_unsupported_format: '模板声明的日期格式不受支持',
}

export const DATE_ERROR_CODE_HINTS = {
  date_format_mismatch: '平台导出格式可能已变更，请在模板更新工作台调整该字段的日期格式。',
  date_out_of_period: '文件期间与文件内容不一致，请核对采集期间或文件本身。',
  date_ambiguous: '同一列在不同候选下会得到不同日期，请收窄候选集或改用固定格式。',
  date_unsupported_format: '模板里的日期格式不被解析器支持，请改为受支持的格式。',
}

const DATE_ERROR_CODE_PATTERN = /\[(date_[a-z_]+)\]/

/**
 * 从一条错误消息里取出日期错误码(没有则返回 null)。
 */
export function parseDateErrorCode(message) {
  const text = typeof message === 'string' ? message : String(message?.message || '')
  const match = text.match(DATE_ERROR_CODE_PATTERN)
  return match && match[1] ? match[1] : null
}

/**
 * 抽取任务里所有「日期解析失败」的条目, 并带上可读的原因与处置建议。
 */
export function extractDateParseErrorEntries(task) {
  const errors = Array.isArray(task?.errors) ? task.errors : []
  return errors
    .map((entry) => {
      const message = typeof entry === 'string' ? entry : String(entry?.message || '')
      const code = parseDateErrorCode(message)
      if (!code) return null
      const match = message.match(/^文件(?<file_id>\d+):\s*(?<detail>.+)$/)
      return {
        file_id: match?.groups?.file_id ? Number(match.groups.file_id) : null,
        message,
        detail: match?.groups?.detail || message,
        error_code: code,
        error_label: DATE_ERROR_CODE_LABELS[code] || code,
        error_hint: DATE_ERROR_CODE_HINTS[code] || '',
        is_date_parse_error: true,
      }
    })
    .filter(Boolean)
}

export function hasDateParseHints(task) {
  return extractDateParseErrorEntries(task).length > 0
}
