<template>
  <el-card class="template-raw-preview-panel" shadow="never">
    <template #header>
      <div class="template-raw-preview-panel__header">
        <span>原始样本预览</span>
        <el-tag size="small" type="info">
          {{ previewData.length }} 行
        </el-tag>
      </div>
    </template>

    <div v-if="previewData.length > 0" class="template-raw-preview-panel__table">
      <el-table :data="previewData" size="small" border stripe max-height="260">
        <el-table-column
          v-for="column in previewColumns"
          :key="column"
          :prop="column"
          :label="column"
          min-width="140"
          show-overflow-tooltip
        />
      </el-table>
    </div>
    <div v-else class="template-raw-preview-panel__muted">
      暂无原始样本预览。
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  previewData: {
    type: Array,
    default: () => [],
  },
})

const previewColumns = computed(() => {
  if (!props.previewData.length) return []
  return Object.keys(props.previewData[0] || {})
})
</script>

<style scoped>
.template-raw-preview-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-raw-preview-panel__muted {
  color: #909399;
  font-size: 12px;
}
</style>
