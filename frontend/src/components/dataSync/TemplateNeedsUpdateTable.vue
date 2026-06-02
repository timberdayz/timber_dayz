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
    <el-table-column prop="update_reason" label="更新原因" min-width="220" show-overflow-tooltip />
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
</script>
