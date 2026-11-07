<template>
  <div class="deduplication-fields-selector">
    <el-card class="selector-card" shadow="never">
      <template #header>
        <div class="selector-header">
          <span>核心字段（一次勾选，三处同时生效）</span>
          <el-tag size="small" type="info">店铺与日期由系统自动带上</el-tag>
        </div>
      </template>

      <el-alert
        v-if="blockingMessage"
        :title="blockingMessage"
        type="error"
        :closable="false"
        show-icon
      />

      <!-- ── 第一级: 我要哪些数据 ───────────────────────────────────── -->
      <div class="level-section">
        <div class="level-heading">
          <span class="level-index">1</span>
          <div>
            <div class="level-title">我要哪些数据</div>
            <div class="level-hint">
              这些字段会单独落库成列（可查询、可做报表）；其余字段只进原始数据存档。
            </div>
          </div>
        </div>

        <el-checkbox-group v-model="dataFields" @change="handleDataFieldChange">
          <div class="fields-grid">
            <el-checkbox
              v-for="option in dataFieldOptions"
              :key="option.value"
              :label="option.value"
              :value="option.value"
            >
              <span>{{ option.label }}</span>
              <span v-if="option.weakIdentity" class="weak-identity-label">弱身份字段</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>

        <div v-if="dataFieldOptions.length === 0" class="selector-muted empty-state">
          还没有「已确认语义」的字段。先在上方把列的语义确认了，这里才能勾。
        </div>
      </div>

      <!-- ── 第二级: 哪些参与识别同一行 ─────────────────────────────── -->
      <div class="level-section">
        <div class="level-heading">
          <span class="level-index">2</span>
          <div>
            <div class="level-title">哪些参与识别「同一行」</div>
            <div class="level-hint">
              这些字段决定「两行是不是同一行」——去重、指纹按它们算。
              勾得越少，越容易把不同的行当成同一行；勾得越多，越容易把同一行当成不同的行。
            </div>
          </div>
        </div>

        <div class="hash-section">
          <div class="section-title">系统自动带上（不用勾）</div>
          <div class="tag-row">
            <el-tag v-for="field in systemScopeFields" :key="field" size="small" type="info">
              {{ field }}
            </el-tag>
          </div>
        </div>

        <div v-if="autoDateIdentityFields.length > 0" class="hash-section">
          <div class="section-title">系统自动日期身份</div>
          <div class="tag-row">
            <el-tag v-for="field in autoDateIdentityFields" :key="field" size="small" type="success">
              {{ field }}
            </el-tag>
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
              <span v-if="option.weakIdentity" class="weak-identity-label">弱身份字段</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>

        <div v-if="selectableOptions.length === 0" class="selector-muted empty-state">
          暂无可用于识别「同一行」的已确认语义字段。
        </div>
      </div>

      <div class="hash-section">
        <div class="section-title">当前参与识别「同一行」的字段</div>
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
        <div class="section-title">当前缺失要求（说清楚缺什么、为什么、怎么改）</div>
        <div class="requirement-list">
          <div v-for="group in missingGroups" :key="group.key" class="requirement-item">
            <div class="requirement-line">
              <span class="requirement-tag">缺哪个</span>
              <span>{{ missingKeysText(group) }}</span>
            </div>
            <div class="requirement-line">
              <span class="requirement-tag">影响什么</span>
              <span>{{ group.label }}{{ group.message ? `：${group.message}` : '' }}</span>
            </div>
            <div class="requirement-line">
              <span class="requirement-tag">怎么改</span>
              <span>{{ fixHintText(group) }}</span>
            </div>
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
  // [*] 批次 E: 版本级核心字段清单(已有清单优先, 避免重算 raw_name 改口径)
  initialCoreFields: {
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

const emit = defineEmits(['update:selectedFields', 'update:coreFields', 'validation-change'])

const selectedFields = ref([])
const dataFields = ref([])
const hashPolicyPreview = ref(null)
const previewLoading = ref(false)
const validationWarning = ref('')
let previewTimer = null
let previewRequestId = 0

const systemScopeFields = computed(
  () => hashPolicyPreview.value?.effective_components?.system_scope_fields || SYSTEM_HASH_SCOPE_FIELDS
)

const confirmedBindings = computed(() => {
  const seen = new Set()
  const result = []
  for (const binding of Array.isArray(props.headerBindings) ? props.headerBindings : []) {
    if (binding?.semantic_review_status !== 'confirmed_semantic') continue
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (!semanticKey || seen.has(semanticKey)) continue
    seen.add(semanticKey)
    const rawName = String(binding?.raw_name || '').trim()
    const meta = getSemanticFieldMeta(semanticKey)
    result.push({
      semanticKey,
      rawName,
      required: Boolean(binding?.required),
      meta,
      label: rawName ? `${meta?.label || semanticKey} (${rawName})` : `${meta?.label || semanticKey} (${semanticKey})`,
    })
  }
  return result
})

// 第一级候选: 所有「已确认语义」的字段(不受 hash 资格限制 —— 落库与去重是两件事)
const dataFieldOptions = computed(() =>
  confirmedBindings.value.map((item) => ({
    value: item.semanticKey,
    label: item.label,
    weakIdentity: item.meta?.identity_strength === 'weak',
  }))
)

// 第二级候选: 第一级里「可用于识别一行」的字段
const selectableOptions = computed(() =>
  confirmedBindings.value
    .filter(
      (item) =>
        isHashEligibleSemanticKey(item.semanticKey) &&
        !DATE_HASH_KEYS.has(item.semanticKey)
    )
    .map((item) => ({
      value: item.semanticKey,
      label: item.label,
      weakIdentity: item.meta?.identity_strength === 'weak',
    }))
)

const selectableValues = computed(() => new Set(selectableOptions.value.map(option => option.value)))
const autoDateIdentityFields = computed(
  () => hashPolicyPreview.value?.effective_components?.auto_date_identity_fields || []
)
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
    return `不能保存：${invalidKeys.join('、')} 不能参与识别「同一行」。`
  }
  return ''
})

// [*] 批次 E: 清单 = 第一级全集 + 第二级标 in_hash
//     raw_name 取**原始物理列名** —— 它是 hash 载荷的键名,
//     换了键名就等于改了口径(已入库的行会被当成新数据)。
const coreFields = computed(() => {
  const rawNameByKey = new Map(
    confirmedBindings.value.map((item) => [item.semanticKey, item.rawName])
  )
  const hashKeys = new Set(selectedFields.value)
  const existing = new Map(
    (Array.isArray(props.initialCoreFields) ? props.initialCoreFields : []).map((item) => [
      item?.semantic_key || item?.raw_name,
      item,
    ])
  )
  return dataFields.value.map((semanticKey) => {
    const previous = existing.get(semanticKey)
    const rawName = previous?.raw_name || rawNameByKey.get(semanticKey) || null
    return {
      semantic_key: semanticKey,
      raw_name: rawName,
      required: previous ? Boolean(previous.required) : Boolean(
        confirmedBindings.value.find((item) => item.semanticKey === semanticKey)?.required
      ),
      in_hash: hashKeys.has(semanticKey),
    }
  })
})

function emitCoreFields() {
  emit('update:coreFields', coreFields.value.map(item => ({ ...item })))
}

// ── E-7: 保存闸门的错误引导 ────────────────────────────────────────────
// 「缺哪个 / 影响什么 / 怎么改」三段式。
// 文案全部由后端 requirement_groups 推导(不前端自造业务口径)。
function semanticLabel(semanticKey) {
  const meta = getSemanticFieldMeta(semanticKey)
  return meta?.label || semanticKey
}

function missingKeysText(group) {
  const missing = group?.missing_keys || []
  if (missing.length === 0) return group?.label || '（未指明具体字段）'
  return missing.map(key => `${semanticLabel(key)}（${key}）`).join('、')
}

function fixHintText(group) {
  const accepted = group?.accepted_keys || []
  const requirementType = group?.requirement_type === 'all_of' ? '都要' : '任意一个'
  if (accepted.length === 0) {
    return '在上面的列语义确认里把对应列确认后，勾到第 2 级「参与识别同一行」。'
  }
  const names = accepted.map(key => `${semanticLabel(key)}（${key}）`).join(' / ')
  return `把 ${names} 中${requirementType}的字段确认成对应语义后，勾到第 2 级「参与识别同一行」。`
}

function validateFields() {
  validationWarning.value = ''

  const missingFields = selectedFields.value.filter(field => !selectableValues.value.has(field))
  if (missingFields.length > 0) {
    validationWarning.value = `以下字段不能参与识别「同一行」：${missingFields.join('、')}`
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
  emitCoreFields()
  scheduleHashPolicyPreview()
}

function handleDataFieldChange() {
  // 第一级取消的字段, 第二级必须同步取消(否则清单里会出现「不落库但参与去重」)
  const allowed = new Set(dataFields.value)
  const nextHashFields = selectedFields.value.filter(field => allowed.has(field))
  if (nextHashFields.length !== selectedFields.value.length) {
    selectedFields.value = nextHashFields
    emit('update:selectedFields', [...nextHashFields])
  }
  validateFields()
  emitCoreFields()
  scheduleHashPolicyPreview()
}

function scheduleHashPolicyPreview() {
  if (previewTimer) {
    clearTimeout(previewTimer)
  }
  previewTimer = setTimeout(runHashPolicyPreview, 250)
}

async function runHashPolicyPreview() {
  const hasPolicyInput = selectedFields.value.length > 0 || (Array.isArray(props.fieldParseRules) && props.fieldParseRules.length > 0)
  if (!props.dataDomain || !hasPolicyInput) {
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
    ElMessage.warning(error?.message || '识别「同一行」的字段预检失败')
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
    selectedFields.value = (Array.isArray(newFields) ? [...newFields] : []).filter(field => !DATE_HASH_KEYS.has(field))
    validateFields()
    scheduleHashPolicyPreview()
  },
  { immediate: true },
)

// [*] 批次 E: 初始清单 ⇒ 第一级默认全选(保持现有落库行为), 第二级取清单里 in_hash 的。
watch(
  () => [props.initialCoreFields, props.headerBindings],
  () => {
    const manifest = Array.isArray(props.initialCoreFields) ? props.initialCoreFields : []
    if (manifest.length > 0) {
      const keys = manifest.map((item) => item?.semantic_key).filter(Boolean)
      const hashKeys = manifest.filter((item) => item?.in_hash).map((item) => item?.semantic_key).filter(Boolean)
      if (keys.length > 0) {
        dataFields.value = keys
        if (hashKeys.length > 0) {
          selectedFields.value = hashKeys.filter(field => !DATE_HASH_KEYS.has(field))
        }
        emitCoreFields()
        validateFields()
        scheduleHashPolicyPreview()
        return
      }
    }
    // 没有清单 ⇒ 第一级默认全选(与「所有列都落库」的现有行为一致)
    dataFields.value = dataFieldOptions.value.map(option => option.value)
    emitCoreFields()
  },
  { immediate: true, deep: true },
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
  getCoreFields: () => coreFields.value.map(item => ({ ...item })),
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

.level-section {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
}

.level-heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.level-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: 0 0 20px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.level-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.level-hint {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
  line-height: 1.6;
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
  gap: 10px;
  color: #9a5b00;
  font-size: 13px;
}

.requirement-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.requirement-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.requirement-tag {
  flex: 0 0 auto;
  min-width: 56px;
  padding: 1px 6px;
  border-radius: 3px;
  background: #fdf6ec;
  border: 1px solid #f3d19e;
  color: #b88230;
  font-size: 12px;
  text-align: center;
}

.fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  max-height: 240px;
  overflow-y: auto;
  padding: 8px 0;
}

.derived-label,
.weak-identity-label {
  margin-left: 6px;
  color: #909399;
  font-size: 12px;
}

.weak-identity-label {
  color: #b88230;
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
