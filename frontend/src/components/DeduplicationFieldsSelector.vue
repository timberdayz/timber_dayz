<template>
  <div class="deduplication-fields-selector">
    <el-card class="selector-card" shadow="never">
      <template #header>
        <div class="selector-header">
          <span>Data Hash 字段确认</span>
          <el-tag size="small" type="info">系统字段自动参与</el-tag>
        </div>
      </template>

      <el-alert
        v-if="blockingMessage"
        :title="blockingMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <div class="hash-section">
        <div class="section-title">系统自动字段</div>
        <div class="tag-row">
          <el-tag v-for="field in systemScopeFields" :key="field" size="small" type="info">
            {{ field }}
          </el-tag>
        </div>
      </div>

      <div class="hash-section">
        <div class="section-title">用户已选语义字段</div>
        <div class="tag-row">
          <el-tag v-for="field in selectedFields" :key="field" size="small" type="primary">
            {{ field }}
          </el-tag>
          <span v-if="selectedFields.length === 0" class="selector-muted">尚未选择</span>
        </div>
      </div>

      <div v-if="passedGroups.length > 0" class="hash-section">
        <div class="section-title">已满足要求</div>
        <div class="tag-row">
          <el-tag v-for="group in passedGroups" :key="group.key" size="small" type="success">
            {{ group.label }}已满足：{{ group.selected_keys?.join(' / ') }}
          </el-tag>
        </div>
      </div>

      <div v-if="missingGroups.length > 0" class="hash-section hash-section--warning">
        <div class="section-title">当前缺失要求</div>
        <div class="requirement-list">
          <div v-for="group in missingGroups" :key="group.key" class="requirement-item">
            {{ group.message }}
          </div>
        </div>
      </div>

      <div v-if="previewWarnings.length > 0" class="hash-section hash-section--warning">
        <div class="section-title">样本风险提示</div>
        <div class="requirement-list">
          <div v-for="warning in previewWarnings" :key="warning" class="requirement-item">
            {{ warning }}
          </div>
        </div>
      </div>

      <el-checkbox-group v-model="selectedFields" @change="handleFieldChange">
        <div class="fields-grid">
          <el-checkbox
            v-for="option in selectableOptions"
            :key="option.value"
            :label="option.value"
            :value="option.value"
          >
            <span>{{ option.label }}</span>
            <span v-if="option.derived" class="derived-label">由文件伴生日期生成</span>
          </el-checkbox>
        </div>
      </el-checkbox-group>

      <div v-if="selectableOptions.length === 0" class="selector-muted empty-state">
        暂无可参与 Data Hash 的已确认语义字段。
      </div>

      <div v-if="validationWarning" class="validation-warning">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ validationWarning }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import api from '@/api'
import {
  getSemanticFieldMeta,
  isHashEligibleSemanticKey,
  SYSTEM_HASH_SCOPE_FIELDS,
} from '@/domains/data_platform/utils/headerBindings'

const DATE_HASH_KEYS = new Set([
  'metric_date',
  'period_start_date',
  'period_end_date',
  'period_start_time',
  'period_end_time',
])

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
  granularity: {
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
  fieldParseRules: {
    type: Array,
    default: () => [],
  },
  sampleRows: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:selectedFields', 'validation-change'])

const selectedFields = ref([])
const hashPolicyPreview = ref(null)
const previewLoading = ref(false)
const validationWarning = ref('')
let previewTimer = null
let previewRequestId = 0

const systemScopeFields = computed(
  () => hashPolicyPreview.value?.effective_components?.system_scope_fields || SYSTEM_HASH_SCOPE_FIELDS
)

const derivedOptions = computed(() => {
  const seen = new Set()
  return (Array.isArray(props.fieldParseRules) ? props.fieldParseRules : [])
    .map((rule) => {
      const target = String(rule?.target_field || '').trim()
      if (!DATE_HASH_KEYS.has(target) || seen.has(target) || !isHashEligibleSemanticKey(target)) {
        return null
      }
      seen.add(target)
      const meta = getSemanticFieldMeta(target)
      return {
        value: target,
        label: `${meta?.label || target} (${target})`,
        derived: true,
      }
    })
    .filter(Boolean)
})

const selectableOptions = computed(() => {
  const seen = new Set()
  const semanticOptions = (Array.isArray(props.headerBindings) ? props.headerBindings : [])
    .filter(binding =>
      binding?.semantic_review_status === 'confirmed_semantic' &&
      isHashEligibleSemanticKey(binding?.semantic_key)
    )
    .map((binding) => {
      const semanticKey = String(binding?.semantic_key || '').trim()
      if (!semanticKey || seen.has(semanticKey)) return null
      seen.add(semanticKey)
      const rawName = String(binding?.raw_name || '').trim()
      const meta = getSemanticFieldMeta(semanticKey)
      return {
        value: semanticKey,
        label: rawName ? `${meta?.label || semanticKey} (${rawName})` : `${meta?.label || semanticKey} (${semanticKey})`,
        derived: false,
      }
    })
    .filter(Boolean)

  for (const option of derivedOptions.value) {
    if (!seen.has(option.value) && isHashEligibleSemanticKey(option.value)) {
      seen.add(option.value)
      semanticOptions.push(option)
    }
  }
  return semanticOptions
})

const selectableValues = computed(() => new Set(selectableOptions.value.map(option => option.value)))
const missingGroups = computed(() => hashPolicyPreview.value?.missing_required_groups || [])
const passedGroups = computed(() =>
  (hashPolicyPreview.value?.requirement_groups || []).filter(group => group?.passed)
)
const previewWarnings = computed(() => hashPolicyPreview.value?.warnings || [])
const blockingMessage = computed(() => {
  const group = missingGroups.value[0]
  if (group?.message) {
    return `不能保存：${group.message}`
  }
  const invalidKeys = hashPolicyPreview.value?.invalid_keys || []
  if (invalidKeys.length > 0) {
    return `不能保存：${invalidKeys.join('、')} 不能参与 Data Hash。`
  }
  return ''
})

function validateFields() {
  validationWarning.value = ''

  if (selectedFields.value.length === 0) {
    validationWarning.value = '请至少选择 1 个可参与 Data Hash 的语义字段。'
    emit('validation-change', false)
    return false
  }

  const missingFields = selectedFields.value.filter(field => !selectableValues.value.has(field))
  if (missingFields.length > 0) {
    validationWarning.value = `以下字段不是可参与 Data Hash 的已确认语义字段：${missingFields.join('、')}`
    emit('validation-change', false)
    return false
  }

  if (previewLoading.value || hashPolicyPreview.value?.passed !== true) {
    emit('validation-change', false)
    return false
  }

  emit('validation-change', true)
  return true
}

function handleFieldChange() {
  validateFields()
  emit('update:selectedFields', [...selectedFields.value])
  scheduleHashPolicyPreview()
}

function scheduleHashPolicyPreview() {
  if (previewTimer) {
    clearTimeout(previewTimer)
  }
  previewTimer = setTimeout(runHashPolicyPreview, 250)
}

async function runHashPolicyPreview() {
  if (!props.dataDomain || selectedFields.value.length === 0) {
    hashPolicyPreview.value = null
    validateFields()
    return
  }

  const requestId = ++previewRequestId
  previewLoading.value = true
  validateFields()
  try {
    const response = await api.previewTemplateHashPolicy({
      dataDomain: props.dataDomain,
      granularity: props.granularity,
      subDomain: props.subDomain,
      deduplicationFields: selectedFields.value,
      headerBindings: props.headerBindings,
      fieldParseRules: props.fieldParseRules,
      sampleRows: props.sampleRows.slice(0, 20),
    })
    if (requestId !== previewRequestId) return
    hashPolicyPreview.value = response?.data || response
  } catch (error) {
    if (requestId !== previewRequestId) return
    hashPolicyPreview.value = null
    ElMessage.warning(error?.message || 'Data Hash 预检失败')
  } finally {
    if (requestId === previewRequestId) {
      previewLoading.value = false
      validateFields()
    }
  }
}

watch(
  () => props.initialFields,
  (newFields) => {
    selectedFields.value = Array.isArray(newFields) ? [...newFields] : []
    validateFields()
    scheduleHashPolicyPreview()
  },
  { immediate: true },
)

watch(
  () => [
    props.dataDomain,
    props.granularity,
    props.subDomain,
    props.headerBindings,
    props.fieldParseRules,
    props.sampleRows,
  ],
  () => {
    validateFields()
    scheduleHashPolicyPreview()
  },
  { deep: true },
)

onMounted(() => {
  scheduleHashPolicyPreview()
})

onBeforeUnmount(() => {
  if (previewTimer) {
    clearTimeout(previewTimer)
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
.validation-warning {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-header {
  justify-content: space-between;
}

.hash-section {
  margin-top: 12px;
  padding: 10px;
  border-radius: 6px;
  background: #f7f8fa;
}

.hash-section--warning {
  border: 1px solid #f3d19e;
  background: #fdf6ec;
}

.section-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.requirement-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #9a5b00;
  font-size: 13px;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 12px;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.derived-label {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
}

.selector-muted {
  color: #909399;
  font-size: 12px;
}

.empty-state {
  margin-top: 10px;
}

.validation-warning {
  margin-top: 12px;
  padding: 10px;
  border-left: 4px solid #f56c6c;
  border-radius: 4px;
  color: #f56c6c;
  background: #fef0f0;
}
</style>
