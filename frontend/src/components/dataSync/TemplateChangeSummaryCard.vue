<template>
  <el-card class="template-change-summary-card" shadow="never">
    <template #header>
      <div class="template-change-summary-card__header">
        <span>更新摘要</span>
        <el-tag :type="summaryTagType" size="small">
          匹配率 {{ matchRate }}%
        </el-tag>
      </div>
    </template>

    <div class="template-change-summary-card__grid">
      <div class="template-change-summary-card__metric">
        <span class="template-change-summary-card__label">模板</span>
        <strong>{{ templateName }}</strong>
      </div>
      <div class="template-change-summary-card__metric">
        <span class="template-change-summary-card__label">新增字段</span>
        <strong>{{ addedFields.length }}</strong>
      </div>
      <div class="template-change-summary-card__metric">
        <span class="template-change-summary-card__label">删除字段</span>
        <strong>{{ removedFields.length }}</strong>
      </div>
      <div class="template-change-summary-card__metric">
        <span class="template-change-summary-card__label">旧核心字段缺失</span>
        <strong>{{ missingDeduplicationFields.length }}</strong>
      </div>
    </div>

    <div class="template-change-summary-card__section">
      <div class="template-change-summary-card__label">更新原因</div>
      <div>{{ updateReason || '当前模板与最新文件表头存在差异，需要人工确认。' }}</div>
    </div>

    <div class="template-change-summary-card__section">
      <div class="template-change-summary-card__label">旧核心字段</div>
      <div class="template-change-summary-card__tags">
        <el-tag
          v-for="field in deduplicationFields"
          :key="field"
          size="small"
          type="primary"
        >
          {{ field }}
        </el-tag>
        <span v-if="deduplicationFields.length === 0" class="template-change-summary-card__muted">
          未配置
        </span>
      </div>
    </div>

    <div
      v-if="existingDeduplicationFieldsMissing.length > 0"
      class="template-change-summary-card__warning"
    >
      <div class="template-change-summary-card__label">旧核心字段缺失</div>
      <div class="template-change-summary-card__tags">
        <el-tag
          v-for="field in existingDeduplicationFieldsMissing"
          :key="field"
          size="small"
          type="danger"
        >
          {{ field }}
        </el-tag>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  summary: {
    type: Object,
    default: () => ({})
  }
})

const matchRate = computed(() => props.summary.match_rate ?? props.summary.matchRate ?? 0)
const templateName = computed(() => props.summary.template_name ?? props.summary.templateName ?? '未命名模板')
const addedFields = computed(() => props.summary.added_fields ?? props.summary.addedFields ?? [])
const removedFields = computed(() => props.summary.removed_fields ?? props.summary.removedFields ?? [])
const updateReason = computed(() => props.summary.update_reason ?? props.summary.updateReason ?? '')
const deduplicationFields = computed(() => props.summary.deduplication_fields ?? props.summary.deduplicationFields ?? [])
const existingDeduplicationFieldsMissing = computed(
  () => props.summary.existing_deduplication_fields_missing ?? props.summary.existingDeduplicationFieldsMissing ?? []
)
const missingDeduplicationFields = existingDeduplicationFieldsMissing

const summaryTagType = computed(() => {
  if (matchRate.value >= 95) return 'success'
  if (matchRate.value >= 80) return 'warning'
  return 'danger'
})
</script>

<style scoped>
.template-change-summary-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-change-summary-card__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.template-change-summary-card__metric,
.template-change-summary-card__section,
.template-change-summary-card__warning {
  padding: 12px;
  border-radius: 10px;
  background: #f7f8fa;
}

.template-change-summary-card__warning {
  background: #fff4f4;
  border: 1px solid #fbc4c4;
}

.template-change-summary-card__label {
  margin-bottom: 6px;
  color: #606266;
  font-size: 12px;
}

.template-change-summary-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-change-summary-card__muted {
  color: #909399;
  font-size: 12px;
}
</style>
