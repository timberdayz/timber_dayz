<template>
  <el-card class="template-deduplication-review-panel" shadow="never">
    <template #header>
      <div class="template-deduplication-review-panel__header">
        <span>Deduplication Review</span>
        <div class="template-deduplication-review-panel__actions">
          <el-tag size="small" type="primary">
            {{ semanticHashOptions.length }} semantic fields
          </el-tag>
          <el-button link type="primary" @click="expanded = !expanded">
            {{ expanded ? 'Hide Semantic Fields' : 'Show Semantic Fields' }}
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
        <div class="template-deduplication-review-panel__group-title">System Scope Fields</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in systemScopeFields" :key="field" size="small" type="info">
            {{ field }}
          </el-tag>
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

      <el-alert
        v-if="modelValue.length === 0"
        title="At least one semantic hash field is required."
        type="warning"
        :closable="false"
        show-icon
      />

      <section v-if="expanded" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Semantic Field Pool</div>
        <el-input
          v-model="searchText"
          class="template-deduplication-review-panel__search"
          clearable
          placeholder="Search semantic fields"
        />
        <el-checkbox-group
          :model-value="modelValue"
          class="template-deduplication-review-panel__checkboxes"
          @update:model-value="$emit('update:modelValue', $event)"
        >
          <el-checkbox
            v-for="option in filteredSemanticHashOptions"
            :key="option.semanticKey"
            :label="option.semanticKey"
            :value="option.semanticKey"
          >
            {{ option.label }}
          </el-checkbox>
        </el-checkbox-group>
        <div v-if="filteredSemanticHashOptions.length === 0" class="template-deduplication-review-panel__muted">
          No confirmed semantic fields available.
        </div>
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
  },
  currentHeaderBindings: {
    type: Array,
    default: () => []
  },
  systemScopeFields: {
    type: Array,
    default: () => ['platform_code', 'shop_id', 'data_domain', 'granularity', 'sub_domain']
  }
})

defineEmits(['update:modelValue'])

const expanded = ref(false)
const searchText = ref('')

const semanticHashOptions = computed(() => {
  const seen = new Set()
  return (Array.isArray(props.currentHeaderBindings) ? props.currentHeaderBindings : [])
    .filter(binding => binding?.semantic_review_status === 'confirmed_semantic')
    .map((binding) => {
      const semanticKey = String(binding?.semantic_key || '').trim()
      if (!semanticKey || seen.has(semanticKey)) return null
      seen.add(semanticKey)
      const rawName = String(binding?.raw_name || '').trim()
      const displayName = String(binding?.display_name || '').trim()
      return {
        semanticKey,
        label: rawName || displayName ? `${semanticKey} (${rawName || displayName})` : semanticKey,
      }
    })
    .filter(Boolean)
})

const filteredSemanticHashOptions = computed(() => {
  const keyword = String(searchText.value || '').trim().toLowerCase()
  if (!keyword) {
    return semanticHashOptions.value
  }
  return semanticHashOptions.value.filter(option =>
    option.semanticKey.toLowerCase().includes(keyword) ||
    option.label.toLowerCase().includes(keyword)
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
