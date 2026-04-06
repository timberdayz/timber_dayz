<template>
  <el-card class="template-deduplication-review-panel" shadow="never">
    <template #header>
      <div class="template-deduplication-review-panel__header">
        <span>核心字段复核</span>
        <el-tag size="small" type="primary">
          {{ currentHeaderColumns.length }} 个候选字段
        </el-tag>
      </div>
    </template>

    <div class="template-deduplication-review-panel__groups">
      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">旧核心字段仍可用</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsAvailable" :key="field" size="small" type="success">
            {{ field }}
          </el-tag>
          <span v-if="existingDeduplicationFieldsAvailable.length === 0" class="template-deduplication-review-panel__muted">无</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">旧核心字段缺失</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsMissing" :key="field" size="small" type="danger">
            {{ field }}
          </el-tag>
          <span v-if="existingDeduplicationFieldsMissing.length === 0" class="template-deduplication-review-panel__muted">无</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">推荐核心字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in recommendedDeduplicationFields" :key="field" size="small" type="warning">
            {{ field }}
          </el-tag>
          <span v-if="recommendedDeduplicationFields.length === 0" class="template-deduplication-review-panel__muted">无</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">当前字段池</div>
        <el-checkbox-group
          :model-value="modelValue"
          class="template-deduplication-review-panel__checkboxes"
          @update:model-value="$emit('update:modelValue', $event)"
        >
          <el-checkbox
            v-for="field in currentHeaderColumns"
            :key="field"
            :label="field"
            :value="field"
          >
            {{ field }}
          </el-checkbox>
        </el-checkbox-group>
      </section>
    </div>
  </el-card>
</template>

<script setup>
defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  deduplicationFields: {
    type: Array,
    default: () => []
  },
  existingDeduplicationFieldsAvailable: {
    type: Array,
    default: () => []
  },
  existingDeduplicationFieldsMissing: {
    type: Array,
    default: () => []
  },
  recommendedDeduplicationFields: {
    type: Array,
    default: () => []
  },
  currentHeaderColumns: {
    type: Array,
    default: () => []
  }
})

defineEmits(['update:modelValue'])
</script>

<style scoped>
.template-deduplication-review-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-deduplication-review-panel__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-deduplication-review-panel__group {
  padding: 12px;
  border-radius: 10px;
  background: #f7f8fa;
}

.template-deduplication-review-panel__group--warning {
  background: #fff4f4;
  border: 1px solid #fbc4c4;
}

.template-deduplication-review-panel__group-title {
  margin-bottom: 8px;
  font-size: 12px;
  color: #606266;
}

.template-deduplication-review-panel__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-deduplication-review-panel__checkboxes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px 12px;
}

.template-deduplication-review-panel__muted {
  color: #909399;
  font-size: 12px;
}
</style>
