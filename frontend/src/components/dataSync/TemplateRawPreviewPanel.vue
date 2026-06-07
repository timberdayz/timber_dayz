<template>
  <el-card class="template-raw-preview-panel" shadow="never">
    <template #header>
      <div class="template-raw-preview-panel__header">
        <span>原始样本预览</span>
        <div class="template-raw-preview-panel__actions">
          <el-tag size="small" type="info">
            {{ previewData.length }} 行
          </el-tag>
          <el-tag size="small">
            {{ previewColumns.length }} / {{ allColumns.length }} 列
          </el-tag>
          <el-button
            v-if="allColumns.length > columnLimit"
            link
            type="primary"
            @click="showAllColumns = !showAllColumns"
          >
            {{ showAllColumns ? '收起多余列' : `显示全部 ${allColumns.length} 列` }}
          </el-button>
        </div>
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
      暂无可展示的样本预览数据。
    </div>
  </el-card>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const columnLimit = 20

const props = defineProps({
  previewData: {
    type: Array,
    default: () => [],
  },
})

const showAllColumns = ref(false)

watch(
  () => props.previewData,
  () => {
    showAllColumns.value = false
  },
  { deep: true }
)

const allColumns = computed(() => {
  if (!props.previewData.length) return []
  return Object.keys(props.previewData[0] || {})
})

const previewColumns = computed(() => {
  if (showAllColumns.value) {
    return allColumns.value
  }
  return allColumns.value.slice(0, columnLimit)
})
</script>

<style scoped>
.template-raw-preview-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-raw-preview-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.template-raw-preview-panel__muted {
  color: #909399;
  font-size: 12px;
}
</style>
