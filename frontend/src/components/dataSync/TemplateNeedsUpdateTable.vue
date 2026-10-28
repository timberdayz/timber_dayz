<template>
  <el-table :data="rows" stripe border max-height="400">
    <el-table-column prop="platform" label="平台" width="100">
      <template #default="{ row }">
        {{ getPlatformLabel(row.platform) }}
      </template>
    </el-table-column>
    <el-table-column prop="domain" label="数据域" width="100" />
    <el-table-column prop="sub_domain" label="子类型" width="120" />
    <el-table-column prop="granularity" label="粒度" width="100" />
    <el-table-column prop="template_name" label="模板名称" min-width="200" />
    <el-table-column prop="file_count" label="文件数" width="100" align="center" />
    <el-table-column label="待更新文件" width="110" align="center">
      <template #default="{ row }">
        <el-tag v-if="row.drift_file_count" type="danger" size="small">
          {{ row.drift_file_count }} 个
        </el-tag>
        <span v-else>-</span>
      </template>
    </el-table-column>
    <el-table-column prop="sample_file_name" label="样本文件" min-width="220" show-overflow-tooltip />
    <el-table-column label="治理状态" width="120">
      <template #default="{ row }">
        <el-tag v-if="row.governance_status === 'missing_variant'" type="danger" size="small">
          缺少变体
        </el-tag>
        <el-tag v-else type="warning" size="small">
          需新版本
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="update_reason" label="更新原因" min-width="220" show-overflow-tooltip>
      <template #default="{ row }">
        <el-tooltip :content="buildDriftDetail(row)" placement="top" :disabled="!hasDriftDetail(row)">
          <span>{{ row.update_reason || '-' }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="150" fixed="right">
      <template #default="{ row }">
        <el-button
          size="small"
          type="warning"
          :disabled="isActionDisabled(row)"
          @click="$emit('update-template', row)"
        >
          <el-icon><Edit /></el-icon>
          {{ getActionLabel(row) }}
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { Edit } from '@element-plus/icons-vue'

defineProps({
  rows: {
    type: Array,
    default: () => [],
  },
  getPlatformLabel: {
    type: Function,
    default: value => value ?? '',
  },
})

defineEmits(['update-template'])

function getActionLabel(row) {
  if (isActionDisabled(row)) {
    return row?.governance_status === 'missing_variant' ? '等待样本' : '上下文缺失'
  }
  return row?.governance_status === 'missing_variant' ? 'Create Variant' : 'Manual Update'
}

function isActionDisabled(row) {
  if (!row) {
    return true
  }
  if (row.governance_status === 'missing_variant') {
    return !(row.family_id || row.id) || !row.sample_file_id
  }
  return !row.template_id
}

function getDriftFields(row, key) {
  const snapshot = row?.drift_snapshot
  if (!snapshot) {
    return []
  }
  const values = snapshot[key]
  return Array.isArray(values) ? values : []
}

function hasDriftDetail(row) {
  return getDriftFields(row, 'added_fields').length > 0
    || getDriftFields(row, 'removed_fields').length > 0
}

function buildDriftDetail(row) {
  const parts = []
  const added = getDriftFields(row, 'added_fields')
  const removed = getDriftFields(row, 'removed_fields')
  if (added.length) {
    parts.push(`新增字段：${added.join('、')}`)
  }
  if (removed.length) {
    parts.push(`删除字段：${removed.join('、')}`)
  }
  const snapshot = row?.drift_snapshot
  if (snapshot?.template_name) {
    parts.push(`漂移时的模板：${snapshot.template_name} v${snapshot.template_version ?? '-'}`)
  }
  return parts.join('\n')
}
</script>
