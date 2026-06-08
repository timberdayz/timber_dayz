<template>
  <el-drawer
    :model-value="visible"
    title="Template Update Workbench"
    size="72%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="template-update-workbench-drawer">
      <div v-if="!workbenchContext" class="template-update-workbench-drawer__mode-picker">
        <div class="template-update-workbench-drawer__meta-card">
          <div class="template-update-workbench-drawer__meta-name">
            {{ template?.template_name || 'Unnamed Template' }}
          </div>
          <div class="template-update-workbench-drawer__meta-detail">
            {{ template?.platform || '-' }} / {{ template?.data_domain || template?.domain || '-' }} /
            {{ template?.granularity || '-' }}
          </div>
        </div>

        <div class="template-update-workbench-drawer__mode-grid">
          <el-card shadow="never" class="template-update-workbench-drawer__mode-card">
            <div class="template-update-workbench-drawer__section-title">Core Fields Only</div>
            <div class="template-update-workbench-drawer__muted">
              Directly edit `deduplication_fields` based on the current template field pool.
            </div>
            <el-button
              type="primary"
              :loading="loadingMode === 'core-only'"
              :disabled="!!loadingMode"
              @click="$emit('select-mode', 'core-only')"
            >
              Core Fields Only
            </el-button>
          </el-card>

          <el-card shadow="never" class="template-update-workbench-drawer__mode-card">
            <div class="template-update-workbench-drawer__section-title">Reset From Sample File</div>
            <div class="template-update-workbench-drawer__muted">
              Re-check schema changes against the sample file, then update the template.
            </div>
            <el-button
              :loading="loadingMode === 'with-sample'"
              :disabled="!!loadingMode"
              @click="$emit('select-mode', 'with-sample')"
            >
              Reset From Sample File
            </el-button>
          </el-card>
        </div>
      </div>

      <template v-else>
      <div class="template-update-workbench-drawer__meta">
        <el-tag size="small" type="info">Mode: {{ updateMode }}</el-tag>
        <el-tag size="small">{{ headerSource }}</el-tag>
        <div v-if="showHeaderRowControl" class="template-update-workbench-drawer__header-row">
          <el-input-number
            v-model="selectedHeaderRow"
            :min="0"
            :max="100"
            :step="1"
            size="small"
            controls-position="right"
            style="width: 140px"
            @change="reloadContext"
          />
          <span class="template-update-workbench-drawer__header-row-label">
            Header Row (Excel row {{ selectedHeaderRow + 1 }})
          </span>
          <el-button size="small" :loading="reloadingContext" @click="reloadContext">Reload</el-button>
        </div>
      </div>

      <TemplateChangeSummaryCard :summary="changeSummary" />

      <HeaderDiffViewer
        v-if="updateMode !== 'core-only' || addedFields.length > 0 || removedFields.length > 0"
        :template-header-columns="templateHeaderColumns"
        :current-header-columns="currentHeaderColumns"
        :added-fields="addedFields"
        :removed-fields="removedFields"
      />

      <TemplateDeduplicationReviewPanel
        v-model="selectedDeduplicationFields"
        :deduplication-fields="templateContext?.deduplication_fields || []"
        :existing-deduplication-fields-available="existingDeduplicationFieldsAvailable"
        :existing-deduplication-fields-missing="existingDeduplicationFieldsMissing"
        :recommended-deduplication-fields="recommendedDeduplicationFields"
        :current-header-columns="currentHeaderColumns"
        :current-header-bindings="activeBindingSource"
      />

      <div v-if="updateMode !== 'core-only'" class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-header">
          <div>
            <div class="template-update-workbench-drawer__section-title">Sample Preview</div>
            <div class="template-update-workbench-drawer__muted">
              Preview data is loaded on demand so large files do not block the first render.
            </div>
          </div>
          <el-button size="small" :loading="loadingPreview" @click="togglePreviewSection">
            {{ previewExpanded ? 'Hide Preview' : previewLoaded ? 'Show Preview' : 'Load Preview' }}
          </el-button>
        </div>
        <TemplateRawPreviewPanel
          v-if="previewExpanded && previewLoaded && previewData.length > 0"
          :preview-data="previewData"
        />
        <div v-else-if="previewExpanded && !loadingPreview" class="template-update-workbench-drawer__empty">
          No preview data available.
        </div>
      </div>

      <div class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-header">
          <div>
            <div class="template-update-workbench-drawer__section-title">Semantic Bindings</div>
            <div class="template-update-workbench-drawer__muted">
              The drawer starts with only the fields that need review. Load all bindings only when needed.
            </div>
          </div>
          <div class="template-update-workbench-drawer__section-actions">
            <el-radio-group
              v-model="bindingsViewMode"
              size="small"
              :disabled="!bindingsExpanded"
            >
              <el-radio-button label="needs-review">Needs Review</el-radio-button>
              <el-radio-button label="all">All Fields</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="loadingBindings" @click="toggleBindingsSection">
              {{ bindingsExpanded ? 'Hide Bindings' : bindingsLoaded ? 'Show Bindings' : 'Load Bindings' }}
            </el-button>
          </div>
        </div>

        <div v-if="!bindingsExpanded" class="template-update-workbench-drawer__muted">
          {{ summaryBindingRows.length > 0 ? `There are ${summaryBindingRows.length} fields that need review.` : 'No fields currently require manual review.' }}
        </div>

        <template v-else>
          <el-table :data="visibleBindingRows" stripe border style="margin-top: 12px;">
            <el-table-column prop="raw_name" label="Source Field" min-width="180" />
            <el-table-column label="Semantic Field" min-width="260">
              <template #default="{ row }">
                <el-select
                  v-if="isBindingEditable(row.raw_name)"
                  :model-value="semanticSelectValue(row)"
                  clearable
                  filterable
                  placeholder="Select semantic field"
                  style="width: 100%;"
                  @change="handleSemanticKeyChange(row.raw_name, $event)"
                >
                  <el-option
                    v-for="option in semanticFieldOptions"
                    :key="option.value || '__none__'"
                    :label="option.label"
                    :value="option.value"
                  />
                </el-select>
                <div v-else class="template-update-workbench-drawer__inline-display">
                  <span>{{ row.meta?.label || row.semantic_key || 'Unmapped' }}</span>
                  <el-button link type="primary" @click="startEditingBinding(row.raw_name)">Edit</el-button>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="Description" min-width="260">
              <template #default="{ row }">
                <div class="template-update-workbench-drawer__binding-title">
                  {{ row.meta?.label || 'Non-semantic field' }}
                </div>
                <div class="template-update-workbench-drawer__muted">
                  {{ row.meta?.description || 'This field keeps the raw value only and does not participate in semantic deduplication.' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="Rules" width="170">
              <template #default="{ row }">
                <div class="template-update-workbench-drawer__tags">
                  <el-tag v-if="row.needsReview" size="small" type="warning">Needs Review</el-tag>
                  <el-tag v-if="row.semantic_review_status === 'confirmed_non_semantic'" size="small" type="info">Non-core</el-tag>
                  <el-tag v-if="row.required" size="small" type="danger">Required</el-tag>
                  <el-tag v-if="row.hash_participates" size="small" type="success">Hash</el-tag>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>

      <div class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-title">Selected Deduplication Fields</div>
        <div v-if="selectedDeduplicationFields.length > 0" class="template-update-workbench-drawer__tags">
          <el-tag
            v-for="field in selectedDeduplicationFields"
            :key="field"
            size="small"
            type="primary"
          >
            {{ formatFieldLabel(field) }}
          </el-tag>
        </div>
        <div v-else class="template-update-workbench-drawer__muted">
          No deduplication field selected.
        </div>
      </div>
      </template>
    </div>

    <template #footer>
      <div class="template-update-workbench-drawer__footer">
        <el-button @click="handleClose">Cancel</el-button>
        <el-button
          type="primary"
          :disabled="!workbenchContext || selectedDeduplicationFields.length === 0 || saving"
          :loading="saving"
          @click="handleSave"
        >
          Save Template
        </el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import api from '@/api'
import {
  formatHeaderBindingLabel,
  getSemanticFieldMeta,
  NON_SEMANTIC_FIELD_VALUE,
  SEMANTIC_FIELD_OPTIONS,
  updateHeaderBindingSemantic,
} from '@/domains/data_platform/utils/headerBindings'

import HeaderDiffViewer from './HeaderDiffViewer.vue'
import TemplateChangeSummaryCard from './TemplateChangeSummaryCard.vue'
import TemplateDeduplicationReviewPanel from './TemplateDeduplicationReviewPanel.vue'
import TemplateRawPreviewPanel from './TemplateRawPreviewPanel.vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  context: {
    type: Object,
    default: () => null,
  },
  template: {
    type: Object,
    default: () => null,
  },
  loadingMode: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['save', 'close', 'select-mode'])

const activeContext = ref(null)
const selectedDeduplicationFields = ref([])
const selectedHeaderRow = ref(0)
const reloadingContext = ref(false)
const previewExpanded = ref(false)
const previewLoaded = ref(false)
const loadingPreview = ref(false)
const bindingsExpanded = ref(false)
const bindingsLoaded = ref(false)
const loadingBindings = ref(false)
const bindingsViewMode = ref('needs-review')
const previewData = ref([])
const fullHeaderBindings = ref([])
const localHeaderBindings = ref([])
const editingBindingNames = ref([])
const saving = ref(false)
const semanticFieldOptions = SEMANTIC_FIELD_OPTIONS

const workbenchContext = computed(() => activeContext.value ?? props.context?.context ?? null)
const templateContext = computed(() => workbenchContext.value?.template ?? props.context?.template ?? {})
const currentHeaderColumns = computed(() => workbenchContext.value?.current_header_columns ?? [])
const templateHeaderColumns = computed(() => workbenchContext.value?.template_header_columns ?? [])
const addedFields = computed(() => workbenchContext.value?.added_fields ?? [])
const removedFields = computed(() => workbenchContext.value?.removed_fields ?? [])
const existingDeduplicationFieldsAvailable = computed(
  () => workbenchContext.value?.existing_deduplication_fields_available ?? [],
)
const existingDeduplicationFieldsMissing = computed(
  () => workbenchContext.value?.existing_deduplication_fields_missing ?? [],
)
const recommendedDeduplicationFields = computed(
  () => workbenchContext.value?.recommended_deduplication_fields ?? [],
)
const updateMode = computed(() => workbenchContext.value?.update_mode ?? 'with-sample')
const headerSource = computed(() => workbenchContext.value?.header_source ?? 'sample-file')

const fallbackFileId = computed(() => props.context?.row?.sample_file_id ?? null)
const currentFileId = computed(() => workbenchContext.value?.current_file?.id ?? fallbackFileId.value)
const showHeaderRowControl = computed(() => updateMode.value !== 'core-only' && !!currentFileId.value)

watch(
  () => props.context,
  (next) => {
    activeContext.value = next?.context ?? null
  },
  { immediate: true, deep: true },
)

watch(
  workbenchContext,
  (next) => {
    selectedHeaderRow.value = next?.current_header_row ?? next?.template?.header_row ?? 0
    localHeaderBindings.value = Array.isArray(next?.current_header_bindings)
      ? next.current_header_bindings.map(item => ({ ...item }))
      : []
    previewExpanded.value = false
    previewLoaded.value = false
    previewData.value = []
    bindingsExpanded.value = false
    bindingsLoaded.value = false
    fullHeaderBindings.value = []
    editingBindingNames.value = []
    bindingsViewMode.value = 'needs-review'
  },
  { immediate: true },
)

watch(
  [existingDeduplicationFieldsAvailable, recommendedDeduplicationFields, currentHeaderColumns],
  ([available, recommended, currentFields]) => {
    if (available.length > 0) {
      selectedDeduplicationFields.value = [...available]
      return
    }
    if (recommended.length > 0) {
      selectedDeduplicationFields.value = [...recommended]
      return
    }
    selectedDeduplicationFields.value = []
  },
  { immediate: true },
)

const changeSummary = computed(() => ({
  template_name: templateContext.value?.template_name ?? 'Untitled Template',
  match_rate: workbenchContext.value?.match_rate ?? 0,
  added_fields: addedFields.value,
  removed_fields: removedFields.value,
  update_reason: props.context?.row?.update_reason ?? '',
  deduplication_fields: templateContext.value?.deduplication_fields ?? [],
  existing_deduplication_fields_missing: existingDeduplicationFieldsMissing.value,
}))

const activeBindingSource = computed(() => {
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0) {
    return fullHeaderBindings.value
  }
  return localHeaderBindings.value
})

const bindingRows = computed(() => {
  const counts = new Map()
  for (const binding of activeBindingSource.value) {
    const key = String(binding?.semantic_key || '').trim()
    if (!key) continue
    counts.set(key, (counts.get(key) || 0) + 1)
  }

  return activeBindingSource.value.map((binding) => {
    const semanticKey = String(binding?.semantic_key || '').trim()
    const reviewStatus = binding?.semantic_review_status || (semanticKey ? 'confirmed_semantic' : 'pending')
    const needsReview = reviewStatus === 'pending' || (semanticKey && (counts.get(semanticKey) || 0) > 1)
    return {
      ...binding,
      semantic_review_status: reviewStatus,
      needsReview,
      meta: getSemanticFieldMeta(binding.semantic_key),
    }
  })
})

const summaryBindingRows = computed(() => bindingRows.value.filter(row => row.needsReview))

const visibleBindingRows = computed(() => {
  if (bindingsViewMode.value === 'all') {
    return bindingRows.value
  }
  return summaryBindingRows.value
})

async function ensurePreviewLoaded() {
  if (previewLoaded.value || loadingPreview.value || updateMode.value === 'core-only') {
    return
  }
  const templateId = templateContext.value?.id
  const fileId = currentFileId.value
  if (!templateId || !fileId) return

  loadingPreview.value = true
  try {
    const payload = await api.getTemplateUpdatePreview(templateId, {
      fileId,
      headerRow: selectedHeaderRow.value,
    })
    const data = payload?.data || payload
    previewData.value = data?.preview_data || []
    previewLoaded.value = true
  } catch (error) {
    console.error('Failed to load preview:', error)
    ElMessage.error(error?.message || 'Failed to load preview')
  } finally {
    loadingPreview.value = false
  }
}

async function ensureBindingsLoaded() {
  if (bindingsLoaded.value || loadingBindings.value || updateMode.value === 'core-only') {
    return
  }
  const templateId = templateContext.value?.id
  const fileId = currentFileId.value
  if (!templateId || !fileId) return

  loadingBindings.value = true
  try {
    const payload = await api.getTemplateUpdateBindings(templateId, {
      fileId,
      headerRow: selectedHeaderRow.value,
    })
    const data = payload?.data || payload
    fullHeaderBindings.value = Array.isArray(data?.current_header_bindings)
      ? data.current_header_bindings.map(item => ({ ...item }))
      : []
    bindingsLoaded.value = true
  } catch (error) {
    console.error('Failed to load bindings:', error)
    ElMessage.error(error?.message || 'Failed to load bindings')
  } finally {
    loadingBindings.value = false
  }
}

async function togglePreviewSection() {
  if (!previewExpanded.value) {
    await ensurePreviewLoaded()
  }
  previewExpanded.value = !previewExpanded.value
}

async function toggleBindingsSection() {
  if (!bindingsExpanded.value) {
    await ensureBindingsLoaded()
  }
  bindingsExpanded.value = !bindingsExpanded.value
}

function startEditingBinding(rawName) {
  if (editingBindingNames.value.includes(rawName)) {
    return
  }
  editingBindingNames.value = [...editingBindingNames.value, rawName]
}

function isBindingEditable(rawName) {
  return editingBindingNames.value.includes(rawName)
}

function semanticSelectValue(row) {
  if (row?.semantic_review_status === 'confirmed_non_semantic') {
    return NON_SEMANTIC_FIELD_VALUE
  }
  return row?.semantic_key || null
}

function normalizeDeduplicationSelection(fields, bindings, preferredSemanticKey = null) {
  const bindingByRaw = new Map()
  const semanticKeys = new Set()

  for (const binding of Array.isArray(bindings) ? bindings : []) {
    const rawName = String(binding?.raw_name || '').trim()
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (rawName) {
      bindingByRaw.set(rawName.toLowerCase(), binding)
    }
    if (
      semanticKey &&
      binding?.semantic_review_status === 'confirmed_semantic'
    ) {
      semanticKeys.add(semanticKey)
    }
  }

  const normalized = []
  const seen = new Set()
  const pushField = (field) => {
    const value = String(field || '').trim()
    if (!value) return
    const lowered = value.toLowerCase()
    if (seen.has(lowered)) return
    seen.add(lowered)
    normalized.push(value)
  }

  for (const field of Array.isArray(fields) ? fields : []) {
    const value = String(field || '').trim()
    if (!value) continue

    const rawBinding = bindingByRaw.get(value.toLowerCase())
    if (rawBinding) {
      if (rawBinding.semantic_review_status !== 'confirmed_semantic') {
        continue
      }
      const semanticKey = String(rawBinding.semantic_key || '').trim()
      if (semanticKey) {
        pushField(semanticKey)
      }
      continue
    }

    if (semanticKeys.has(value)) {
      pushField(value)
    }
  }

  if (preferredSemanticKey && semanticKeys.has(preferredSemanticKey) && normalized.length === 0) {
    pushField(preferredSemanticKey)
  }

  return normalized
}

function handleSemanticKeyChange(rawName, semanticKey) {
  const nextBindings = updateHeaderBindingSemantic(activeBindingSource.value, rawName, semanticKey)
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0) {
    fullHeaderBindings.value = nextBindings
  } else {
    localHeaderBindings.value = nextBindings
  }
  const updatedBinding = nextBindings.find(binding => binding?.raw_name === rawName)
  const preferredSemanticKey = updatedBinding?.hash_participates
    ? String(updatedBinding?.semantic_key || '').trim()
    : null
  selectedDeduplicationFields.value = normalizeDeduplicationSelection(
    selectedDeduplicationFields.value,
    nextBindings,
    preferredSemanticKey,
  )
}

function formatFieldLabel(field) {
  return formatHeaderBindingLabel(field, activeBindingSource.value)
}

async function handleSave() {
  saving.value = true
  try {
    if (updateMode.value !== 'core-only') {
      await ensureBindingsLoaded()
    }
    selectedDeduplicationFields.value = normalizeDeduplicationSelection(
      selectedDeduplicationFields.value,
      activeBindingSource.value,
    )
    emit('save', {
      deduplicationFields: [...selectedDeduplicationFields.value],
      headerRow: selectedHeaderRow.value,
      headerBindings: activeBindingSource.value.map(item => ({ ...item })),
    })
  } finally {
    saving.value = false
  }
}

async function reloadContext() {
  const templateId = templateContext.value?.id
  const fileId = currentFileId.value
  if (!templateId || !fileId) return

  reloadingContext.value = true
  try {
    const context = await api.getTemplateUpdateContext(templateId, {
      mode: updateMode.value,
      fileId,
      headerRow: selectedHeaderRow.value,
    })
    activeContext.value = context
  } catch (error) {
    console.error('Failed to reload context:', error)
    ElMessage.error(error?.message || 'Failed to reload context')
  } finally {
    reloadingContext.value = false
  }
}

function handleClose() {
  emit('close')
}
</script>

<style scoped>
.template-update-workbench-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.template-update-workbench-drawer__mode-picker {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.template-update-workbench-drawer__meta-card {
  padding: 16px;
  border-radius: 12px;
  background: #f5f7fa;
}

.template-update-workbench-drawer__meta-name {
  font-size: 20px;
  font-weight: 600;
}

.template-update-workbench-drawer__meta-detail {
  margin-top: 8px;
  color: #606266;
}

.template-update-workbench-drawer__mode-grid {
  display: grid;
  gap: 16px;
}

.template-update-workbench-drawer__mode-card {
  border-radius: 12px;
}

.template-update-workbench-drawer__meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.template-update-workbench-drawer__header-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.template-update-workbench-drawer__header-row-label {
  font-size: 12px;
  color: #606266;
}

.template-update-workbench-drawer__section {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fff;
}

.template-update-workbench-drawer__section-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.template-update-workbench-drawer__section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.template-update-workbench-drawer__section-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.template-update-workbench-drawer__binding-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.template-update-workbench-drawer__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.template-update-workbench-drawer__muted,
.template-update-workbench-drawer__empty {
  color: #909399;
  font-size: 12px;
}

.template-update-workbench-drawer__inline-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.template-update-workbench-drawer__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
