<template>
  <div class="deduplication-fields-selector">
    <el-card class="selector-card" shadow="never">
      <template #header>
        <div class="selector-header">
          <span>Data Hash 字段</span>
          <el-tooltip content="仅已确认语义字段可参与 data_hash" placement="top">
            <el-icon class="selector-help"><QuestionFilled /></el-icon>
          </el-tooltip>
        </div>
      </template>

      <div v-if="recommendedFields.length > 0" class="recommended-fields">
        <div class="recommended-title">
          <el-icon><Star /></el-icon>
          推荐语义字段
        </div>
        <div class="recommended-values">{{ recommendedFields.join('、') }}</div>
        <div v-if="recommendationReason" class="selector-muted">{{ recommendationReason }}</div>
      </div>

      <el-checkbox-group v-model="selectedFields" @change="handleFieldChange">
        <div class="fields-grid">
          <el-checkbox
            v-for="option in selectableOptions"
            :key="option.value"
            :label="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </el-checkbox>
        </div>
      </el-checkbox-group>

      <div v-if="selectableOptions.length === 0" class="selector-muted empty-state">
        暂无已确认语义字段
      </div>

      <div v-if="validationWarning" class="validation-warning">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ validationWarning }}</span>
      </div>

      <div v-if="selectedFields.length > 0" class="selected-fields">
        <div class="selected-title">已选择 {{ selectedFields.length }} 个语义字段</div>
        <div class="selected-tags">
          <el-tag
            v-for="field in selectedFields"
            :key="field"
            type="primary"
            size="small"
          >
            {{ field }}
          </el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled, Star, WarningFilled } from '@element-plus/icons-vue'
import api from '@/api'

const props = defineProps({
  availableFields: {
    type: Array,
    required: true,
    default: () => [],
  },
  headerBindings: {
    type: Array,
    default: () => [],
  },
  dataDomain: {
    type: String,
    default: null,
  },
  subDomain: {
    type: String,
    default: null,
  },
  initialFields: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:selectedFields', 'validation-change'])

const selectedFields = ref([])
const recommendedFields = ref([])
const recommendationReason = ref('')
const validationWarning = ref('')

const selectableOptions = computed(() => {
  const semanticBindings = Array.isArray(props.headerBindings)
    ? props.headerBindings.filter(binding =>
      binding?.semantic_review_status === 'confirmed_semantic' &&
      String(binding?.semantic_key || '').trim()
    )
    : []

  if (semanticBindings.length === 0) {
    return props.availableFields.map(field => ({
      value: String(field || '').trim(),
      label: String(field || '').trim(),
    })).filter(option => option.value)
  }

  const seen = new Set()
  return semanticBindings.map((binding) => {
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (!semanticKey || seen.has(semanticKey)) return null
    seen.add(semanticKey)
    const rawName = String(binding?.raw_name || '').trim()
    return {
      value: semanticKey,
      label: rawName ? `${semanticKey} (${rawName})` : semanticKey,
    }
  }).filter(Boolean)
})

const selectableValues = computed(() => new Set(selectableOptions.value.map(option => option.value)))

const loadRecommendedFields = async () => {
  if (!props.dataDomain) return

  try {
    const result = await api.getDefaultDeduplicationFields({
      dataDomain: props.dataDomain,
      subDomain: props.subDomain,
    })

    if (result && result.success && result.data) {
      recommendedFields.value = result.data.fields || []
      recommendationReason.value = result.data.reason || ''
    }
  } catch (error) {
    ElMessage.warning(error?.message || '获取推荐字段失败')
  }
}

const validateFields = () => {
  validationWarning.value = ''

  if (selectedFields.value.length === 0) {
    validationWarning.value = '请至少选择 1 个语义字段'
    emit('validation-change', false)
    return false
  }

  const missingFields = selectedFields.value.filter(field => !selectableValues.value.has(field))
  if (missingFields.length > 0) {
    validationWarning.value = `以下字段不是已确认语义字段：${missingFields.join('、')}`
  }

  const isValid = selectedFields.value.length > 0 && missingFields.length === 0
  emit('validation-change', isValid)
  return isValid
}

const handleFieldChange = () => {
  validateFields()
  emit('update:selectedFields', [...selectedFields.value])
}

watch(
  () => [props.availableFields, props.headerBindings],
  () => {
    validateFields()
  },
  { deep: true },
)

watch(
  () => props.initialFields,
  (newFields) => {
    if (newFields && newFields.length > 0 && selectedFields.value.length === 0) {
      selectedFields.value = [...newFields]
      validateFields()
    }
  },
  { immediate: true },
)

onMounted(() => {
  loadRecommendedFields()
  if (props.initialFields && props.initialFields.length > 0) {
    selectedFields.value = [...props.initialFields]
    validateFields()
  }
})

defineExpose({
  getSelectedFields: () => selectedFields.value,
  validate: validateFields,
  clear: () => {
    selectedFields.value = []
    validateFields()
  },
})
</script>

<style scoped>
.deduplication-fields-selector {
  width: 100%;
}

.selector-card {
  border: 1px solid #e4e7ed;
}

.selector-header,
.recommended-title,
.validation-warning {
  display: flex;
  align-items: center;
  gap: 6px;
}

.selector-help {
  cursor: help;
}

.recommended-fields,
.selected-fields {
  margin-bottom: 15px;
  padding: 10px;
  border-radius: 4px;
  background: #f0f9ff;
}

.recommended-title,
.selected-title {
  margin-bottom: 6px;
  font-weight: 600;
  color: #409eff;
}

.recommended-values,
.selector-muted {
  color: #606266;
  font-size: 13px;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.empty-state {
  margin-top: 10px;
}

.validation-warning {
  margin-top: 15px;
  padding: 10px;
  border-left: 4px solid #f56c6c;
  border-radius: 4px;
  color: #f56c6c;
  background: #fef0f0;
}

.selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
