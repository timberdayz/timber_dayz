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
    <el-table-column prop="update_reason" label="更新原因" min-width="220" show-overflow-tooltip />
    <el-table-column label="操作" width="150" fixed="right">
      <template #default="{ row }">
        <el-button size="small" type="warning" @click="$emit('update-template', row)">
          <el-icon><Edit /></el-icon>
          更新模板
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
</script>
