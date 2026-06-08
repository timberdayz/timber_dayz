const TASK_TYPE_META = {
  auto_ingest: { text: '自动入库', tagType: 'success' },
  single_file: { text: '单文件同步', tagType: 'info' },
  bulk_ingest: { text: '批量同步', tagType: 'primary' },
  batch_ingest: { text: '批量同步', tagType: 'primary' },
  batch_sync_all: { text: '全量同步', tagType: 'primary' }
}

const TRIGGER_SOURCE_META = {
  auto_ingest: { text: '自动', tagType: 'success' },
  manual: { text: '手动', tagType: 'info' },
  sync_now: { text: '手动', tagType: 'info' },
  repair: { text: '修复', tagType: 'warning' },
  cloud_sync_admin: { text: '管理台', tagType: 'primary' }
}

export function getSyncTaskTypeMeta(taskType) {
  const normalized = String(taskType || '').trim()
  if (!normalized) {
    return { text: '-', tagType: 'info' }
  }
  return TASK_TYPE_META[normalized] || { text: normalized, tagType: 'info' }
}

export function resolveSyncTriggerSource(task = {}) {
  const explicitSource = String(task.trigger_source || '').trim()
  if (explicitSource) {
    return explicitSource
  }

  const taskType = String(task.task_type || '').trim()
  const taskId = String(task.task_id || '').trim()
  if (taskType === 'auto_ingest' || taskId.startsWith('auto_ingest_')) {
    return 'auto_ingest'
  }

  return 'manual'
}

export function getSyncTriggerMeta(task = {}) {
  const source = resolveSyncTriggerSource(task)
  const meta = TRIGGER_SOURCE_META[source] || { text: source || '-', tagType: 'info' }
  return {
    source,
    ...meta
  }
}
