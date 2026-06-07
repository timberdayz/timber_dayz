<template>
  <el-card class="template-deduplication-review-panel" shadow="never">
    <template #header>
      <div class="template-deduplication-review-panel__header">
        <span>Deduplication Review</span>
        <div class="template-deduplication-review-panel__actions">
          <el-tag size="small" type="primary">
            {{ currentHeaderColumns.length }} candidate fields
          </el-tag>
          <el-button link type="primary" @click="expanded = !expanded">
            {{ expanded ? 'Hide Field Pool' : 'Show Field Pool' }}
          </el-button>
        </div>
      </div>
    </template>

    <div class="template-deduplication-review-panel__groups">
      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Selected Fields</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in modelValue" :key="field" size="small" type="primary">
            {{ field }}
          </el-tag>
          <span v-if="modelValue.length === 0" class="template-deduplication-review-panel__muted">None</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Still Available</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsAvailable" :key="field" size="small" type="success">
            {{ field }}
          </el-tag>
          <span v-if="existingDeduplicationFieldsAvailable.length === 0" class="template-deduplication-review-panel__muted">None</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">Missing Old Fields</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsMissing" :key="field" size="small" type="danger">
            {{ field }}
          </el-tag>
          <span v-if="existingDeduplicationFieldsMissing.length === 0" class="template-deduplication-review-panel__muted">None</span>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Recommended Fields</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in recommendedDeduplicationFields" :key="field" size="small" type="warning">
            {{ field }}
          </el-tag>
          <span v-if="recommendedDeduplicationFields.length === 0" class="template-deduplication-review-panel__muted">None</span>
        </div>
      </section>

      <section v-if="expanded" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Field Pool</div>
        <el-input
          v-model="searchText"
          class="template-deduplication-review-panel__search"
          clearable
          placeholder="Search fields"
        />
        <el-checkbox-group
          :model-value="modelValue"
          class="template-deduplication-review-panel__checkboxes"
          @update:model-value="$emit('update:modelValue', $event)"
        >
          <el-checkbox
            v-for="field in filteredHeaderColumns"
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
import { computed, ref } from 'vue'

const props = defineProps({
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

const expanded = ref(false)
const searchText = ref('')

const filteredHeaderColumns = computed(() => {
  const keyword = String(searchText.value || '').trim().toLowerCase()
  if (!keyword) {
    return props.currentHeaderColumns
  }
  return props.currentHeaderColumns.filter(field =>
    String(field || '').toLowerCase().includes(keyword)
  )
})
</script>

<style scoped>
.template-deduplication-review-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-deduplication-review-panel__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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

.template-deduplication-review-panel__search {
  margin-bottom: 12px;
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
