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
