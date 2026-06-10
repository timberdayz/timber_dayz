<template>
  <el-card class="template-deduplication-review-panel" shadow="never">
    <template #header>
      <div class="template-deduplication-review-panel__header">
        <span>Data Hash 字段确认</span>
        <div class="template-deduplication-review-panel__actions">
          <el-tag size="small" type="primary">
            {{ semanticHashOptions.length }} 个可选语义字段
          </el-tag>
          <el-button link type="primary" @click="expanded = !expanded">
            {{ expanded ? '收起字段池' : '展开字段池' }}
          </el-button>
        </div>
      </div>
    </template>

    <div class="template-deduplication-review-panel__groups">
      <el-alert
        v-if="blockingMessage"
        :title="blockingMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">系统自动字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in effectiveSystemScopeFields" :key="field" size="small" type="info">
            {{ field }}
          </el-tag>
        </div>
      </section>

      <section v-if="autoDateIdentityFields.length > 0" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">系统自动日期身份</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in autoDateIdentityFields" :key="field" size="small" type="success">
            {{ field }}
          </el-tag>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">用户已选语义字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in modelValue" :key="field" size="small" type="primary">
            {{ field }}
          </el-tag>
          <span v-if="modelValue.length === 0" class="template-deduplication-review-panel__muted">尚未选择</span>
        </div>
      </section>

      <section v-if="passedGroups.length > 0" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">已满足要求</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="group in passedGroups" :key="group.key" size="small" type="success">
            {{ group.label }}已满足：{{ group.selected_keys?.join(' / ') }}
          </el-tag>
        </div>
      </section>

      <section v-if="missingGroups.length > 0" class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">当前缺失要求</div>
        <div class="template-deduplication-review-panel__list">
          <div v-for="group in missingGroups" :key="group.key">
            {{ group.message }}
          </div>
        </div>
      </section>

      <section v-if="previewWarnings.length > 0" class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">样本风险提示</div>
        <div class="template-deduplication-review-panel__list">
          <div v-for="warning in previewWarnings" :key="warning">
            {{ warning }}
          </div>
        </div>
      </section>

      <section v-if="unresolvedDeduplicationFields.length > 0" class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">未绑定到真实字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in unresolvedDeduplicationFields" :key="field" size="small" type="danger">
            {{ field }}
          </el-tag>
        </div>
      </section>

      <section class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">当前模板保留字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsAvailable" :key="field" size="small" type="success">
            {{ field }}
          </el-tag>
          <span v-if="existingDeduplicationFieldsAvailable.length === 0" class="template-deduplication-review-panel__muted">无</span>
        </div>
      </section>

      <section v-if="semanticMatchedHashableFields.length > 0" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">已语义匹配</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag
            v-for="match in semanticMatchedHashableFields"
            :key="`${match.requested_field}-${match.current_field}`"
            size="small"
            type="success"
          >
            {{ formatMatch(match) }}
          </el-tag>
        </div>
      </section>

      <section v-if="semanticMatchedNonHashableFields.length > 0" class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">匹配但不可参与 Data Hash</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag
            v-for="match in semanticMatchedNonHashableFields"
            :key="`${match.requested_field}-${match.current_field}`"
            size="small"
            type="warning"
          >
            {{ formatMatch(match) }}
          </el-tag>
        </div>
      </section>

      <section v-if="existingDeduplicationFieldsMissing.length > 0" class="template-deduplication-review-panel__group template-deduplication-review-panel__group--warning">
        <div class="template-deduplication-review-panel__group-title">真正缺失的旧模板字段</div>
        <div class="template-deduplication-review-panel__tags">
          <el-tag v-for="field in existingDeduplicationFieldsMissing" :key="field" size="small" type="danger">
            {{ field }}
          </el-tag>
        </div>
      </section>

      <section v-if="expanded" class="template-deduplication-review-panel__group">
        <div class="template-deduplication-review-panel__group-title">Data Hash 可选池</div>
        <el-input
          v-model="searchText"
          class="template-deduplication-review-panel__search"
          clearable
          placeholder="搜索语义字段"
        />
        <el-checkbox-group
          :model-value="modelValue"
          class="template-deduplication-review-panel__checkboxes"
          @update:model-value="handleSelectionChange"
        >
          <el-checkbox
            v-for="option in filteredSemanticHashOptions"
            :key="option.semanticKey"
            :label="option.semanticKey"
            :value="option.semanticKey"
          >
            <span>{{ option.label }}</span>
            <span v-if="option.weakIdentity" class="template-deduplication-review-panel__weak">弱身份字段</span>
          </el-checkbox>
        </el-checkbox-group>
        <div v-if="filteredSemanticHashOptions.length === 0" class="template-deduplication-review-panel__muted">
          暂无可参与 Data Hash 的已确认语义字段。
        </div>
      </section>
    </div>
  </el-card>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
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
  existingDeduplicationFieldMatches: {
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
    default: () => SYSTEM_HASH_SCOPE_FIELDS
  },
  dataDomain: {
    type: String,
    default: ''
  },
  granularity: {
    type: String,
    default: ''
  },
  subDomain: {
    type: String,
    default: null
  },
  fieldParseRules: {
    type: Array,
    default: () => []
  },
  sampleRows: {
    type: Array,
    default: () => []
  },
})

const emit = defineEmits(['update:modelValue', 'hash-policy-change'])

const expanded = ref(false)
const searchText = ref('')
const hashPolicyPreview = ref(null)
const previewLoading = ref(false)
let previewTimer = null
let previewRequestId = 0

const semanticHashOptions = computed(() => {
  const seen = new Set()
  const options = (Array.isArray(props.currentHeaderBindings) ? props.currentHeaderBindings : [])
    .filter(binding =>
      binding?.semantic_review_status === 'confirmed_semantic' &&
      isHashEligibleSemanticKey(binding?.semantic_key) &&
      !DATE_HASH_KEYS.has(String(binding?.semantic_key || '').trim())
    )
    .map((binding) => {
      const semanticKey = String(binding?.semantic_key || '').trim()
      if (!semanticKey || seen.has(semanticKey)) return null
      seen.add(semanticKey)
      const rawName = String(binding?.raw_name || '').trim()
      const displayName = String(binding?.display_name || '').trim()
      const meta = getSemanticFieldMeta(semanticKey)
      return {
        semanticKey,
        label: rawName || displayName
          ? `${meta?.label || semanticKey} (${rawName || displayName})`
          : `${meta?.label || semanticKey} (${semanticKey})`,
        weakIdentity: meta?.identity_strength === 'weak',
      }
    })
    .filter(Boolean)
  return options
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

const effectiveSystemScopeFields = computed(
  () => hashPolicyPreview.value?.effective_components?.system_scope_fields || props.systemScopeFields
)
const autoDateIdentityFields = computed(
  () => hashPolicyPreview.value?.effective_components?.auto_date_identity_fields || []
)
const missingGroups = computed(() => hashPolicyPreview.value?.missing_required_groups || [])
const passedGroups = computed(() =>
  (hashPolicyPreview.value?.requirement_groups || []).filter(group => group?.passed)
)
const previewWarnings = computed(() => hashPolicyPreview.value?.warnings || [])
const unresolvedDeduplicationFields = computed(
  () => hashPolicyPreview.value?.unresolved_deduplication_fields || []
)
const semanticMatchedHashableFields = computed(() =>
  (Array.isArray(props.existingDeduplicationFieldMatches) ? props.existingDeduplicationFieldMatches : [])
    .filter(match => match?.status === 'matched_hashable' && match?.match_type === 'semantic_key')
)
const semanticMatchedNonHashableFields = computed(() =>
  (Array.isArray(props.existingDeduplicationFieldMatches) ? props.existingDeduplicationFieldMatches : [])
    .filter(match => match?.status === 'matched_non_hashable')
)
const blockingMessage = computed(() => {
  const blockingError = hashPolicyPreview.value?.blocking_errors?.[0]
  if (blockingError) {
    return `不能保存：${blockingError}`
  }
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

function emitPolicyState() {
  const valid = !previewLoading.value && hashPolicyPreview.value?.can_save === true
  emit('hash-policy-change', {
    valid,
    loading: previewLoading.value,
    preview: hashPolicyPreview.value,
  })
}

function handleSelectionChange(nextValue) {
  emit('update:modelValue', (Array.isArray(nextValue) ? nextValue : []).filter(field => !DATE_HASH_KEYS.has(field)))
}

function formatMatch(match) {
  const requested = match?.requested_field || '-'
  const current = match?.current_field || '-'
  const semanticKey = match?.semantic_key ? ` (${match.semantic_key})` : ''
  return `${requested} -> ${current}${semanticKey}`
}

function scheduleHashPolicyPreview() {
  if (previewTimer) {
    clearTimeout(previewTimer)
  }
  previewTimer = setTimeout(runHashPolicyPreview, 250)
}

async function runHashPolicyPreview() {
  const hasPolicyInput = props.modelValue.length > 0 || (Array.isArray(props.fieldParseRules) && props.fieldParseRules.length > 0)
  if (!props.dataDomain || !hasPolicyInput) {
    hashPolicyPreview.value = null
    emitPolicyState()
    return
  }

  const requestId = ++previewRequestId
  previewLoading.value = true
  emitPolicyState()
  try {
    const response = await api.previewTemplateHashPolicy({
      dataDomain: props.dataDomain,
      granularity: props.granularity,
      subDomain: props.subDomain,
      deduplicationFields: props.modelValue,
      headerBindings: props.currentHeaderBindings,
      fieldParseRules: props.fieldParseRules,
      sampleRows: props.sampleRows.slice(0, 20),
    })
    if (requestId !== previewRequestId) return
    hashPolicyPreview.value = response?.data || response
  } catch (error) {
    if (requestId !== previewRequestId) return
    hashPolicyPreview.value = error?.data?.hash_policy || null
    ElMessage.warning(
      hashPolicyPreview.value?.blocking_errors?.[0] ||
      error?.message ||
      'Data Hash 预检失败'
    )
  } finally {
    if (requestId === previewRequestId) {
      previewLoading.value = false
      emitPolicyState()
    }
  }
}

watch(
  () => [
    props.modelValue,
    props.currentHeaderBindings,
    props.fieldParseRules,
    props.sampleRows,
    props.dataDomain,
    props.granularity,
    props.subDomain,
  ],
  () => {
    emitPolicyState()
    scheduleHashPolicyPreview()
  },
  { immediate: true, deep: true },
)

onBeforeUnmount(() => {
  if (previewTimer) {
    clearTimeout(previewTimer)
  }
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
  border-radius: 6px;
  background: #f7f8fa;
}

.template-deduplication-review-panel__group--warning {
  background: #fdf6ec;
  border: 1px solid #f3d19e;
}

.template-deduplication-review-panel__group-title {
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #606266;
}

.template-deduplication-review-panel__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-deduplication-review-panel__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #9a5b00;
  font-size: 13px;
}

.template-deduplication-review-panel__search {
  margin-bottom: 12px;
}

.template-deduplication-review-panel__checkboxes {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px 12px;
}

.template-deduplication-review-panel__derived,
.template-deduplication-review-panel__weak {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
}

.template-deduplication-review-panel__weak {
  color: #b88230;
}

.template-deduplication-review-panel__muted {
  color: #909399;
  font-size: 12px;
}
</style>
