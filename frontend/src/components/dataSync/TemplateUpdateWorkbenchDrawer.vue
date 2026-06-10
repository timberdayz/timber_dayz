<template>
  <el-drawer
    :model-value="visible"
    title="模板更新工作台"
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

      <div class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-header">
          <div>
            <div class="template-update-workbench-drawer__section-title">日期解析规则</div>
            <div class="template-update-workbench-drawer__muted">
              源数据没有日期列时，选择文件伴生数据中的日期或周期。
            </div>
          </div>
          <div class="template-update-workbench-drawer__section-actions">
            <el-button size="small" @click="applyCompanionDateRules('single')">使用伴生日期</el-button>
            <el-button size="small" @click="applyCompanionDateRules('period')">使用伴生周期</el-button>
            <el-button size="small" @click="addFieldParseRule">新增规则</el-button>
          </div>
        </div>
        <div v-if="localFieldParseRules.length === 0" class="template-update-workbench-drawer__empty">
          尚未声明日期来源。
        </div>
        <div v-else class="template-update-workbench-drawer__date-rules">
          <div
            v-for="(rule, index) in localFieldParseRules"
            :key="index"
            class="template-update-workbench-drawer__date-rule"
          >
            <el-select v-model="rule.target_field" placeholder="目标字段">
              <el-option
                v-for="option in dateTargetOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select v-model="rule.source_column" placeholder="来源列" filterable>
              <el-option
                v-for="option in fieldParseSourceOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select v-model="rule.value_kind" placeholder="值类型">
              <el-option
                v-for="option in dateValueKindOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select v-model="rule.date_format" placeholder="日期格式" filterable>
              <el-option
                v-for="option in dateFormatOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select
              v-if="fieldParseRuleNeedsDateAnchor(rule)"
              v-model="rule.date_anchor"
              placeholder="日期锚点"
            >
              <el-option
                v-for="option in dateAnchorOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select
              v-if="fieldParseRuleNeedsRangePick(rule)"
              v-model="rule.range_pick"
              placeholder="区间取值"
            >
              <el-option label="start" value="start" />
              <el-option label="end" value="end" />
            </el-select>
            <el-switch
              v-model="rule.strict"
              inline-prompt
              active-text="严格"
              inactive-text="宽松"
            />
            <el-button type="danger" text @click="removeFieldParseRule(index)">删除</el-button>
          </div>
        </div>
      </div>

      <TemplateDeduplicationReviewPanel
        v-model="selectedDeduplicationFields"
        :deduplication-fields="templateContext?.deduplication_fields || []"
        :existing-deduplication-fields-available="existingDeduplicationFieldsAvailable"
        :existing-deduplication-fields-missing="existingDeduplicationFieldsMissing"
        :existing-deduplication-field-matches="existingDeduplicationFieldMatches"
        :recommended-deduplication-fields="recommendedDeduplicationFields"
        :current-header-columns="currentHeaderColumns"
        :current-header-bindings="saveReadyHeaderBindings"
        :data-domain="templateContext?.data_domain || template?.data_domain || template?.domain || ''"
        :granularity="templateContext?.granularity || template?.granularity || ''"
        :sub-domain="templateContext?.sub_domain || template?.sub_domain || null"
        :field-parse-rules="localFieldParseRules"
        :sample-rows="previewData"
        :sample-rows-version="sampleRowsVersion"
        @hash-policy-change="handleHashPolicyChange"
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
            <div class="template-update-workbench-drawer__section-title">语义字段确认</div>
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
              <el-radio-button label="needs-review">待确认</el-radio-button>
              <el-radio-button label="all">全部字段</el-radio-button>
            </el-radio-group>
            <el-button size="small" :loading="loadingBindings" @click="toggleBindingsSection">
              {{ bindingsExpanded ? 'Hide Bindings' : bindingsLoaded ? 'Show Bindings' : 'Load Bindings' }}
            </el-button>
          </div>
        </div>

        <div v-if="!bindingsExpanded" class="template-update-workbench-drawer__muted">
          {{
            summaryBindingRows.length > 0
              ? `There are ${summaryBindingRows.length} key fields that need review.`
              : 'No key fields currently require manual review.'
          }}
          <span v-if="ordinaryPendingFieldCount > 0">
            {{ ordinaryPendingFieldCount }} unrecognized fields will be preserved as raw fields.
          </span>
        </div>

        <template v-else>
          <div
            v-if="bindingsViewMode === 'needs-review' && visibleBindingRows.length === 0"
            class="template-update-workbench-drawer__empty"
          >
            No key fields currently require manual review. Switch to `All Fields` to inspect the full binding set.
          </div>
          <el-table v-else :data="visibleBindingRows" stripe border style="margin-top: 12px;">
            <el-table-column prop="raw_name" label="Source Field" min-width="180" />
            <el-table-column label="Semantic Field" min-width="260">
              <template #default="{ row }">
                <el-select
                  v-if="isBindingEditable(row.raw_name)"
                  :model-value="semanticSelectValue(row)"
                  clearable
                  filterable
                  placeholder="选择语义字段"
                  style="width: 100%;"
                  @change="handleSemanticKeyChange(row.raw_name, $event)"
                >
                  <el-option
                    :key="semanticNonSemanticOption.value"
                    :label="semanticNonSemanticOption.label"
                    :value="semanticNonSemanticOption.value"
                  />
                  <el-option-group
                    v-for="group in semanticFieldOptionGroups"
                    :key="group.label"
                    :label="group.label"
                  >
                    <el-option
                      v-for="option in group.options"
                      :key="option.value"
                      :label="option.label"
                      :value="option.value"
                    />
                  </el-option-group>
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
                  {{ row.meta?.description || '该字段仅保留原始值，不参与 Data Hash。' }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="Rules" width="170">
              <template #default="{ row }">
                <div class="template-update-workbench-drawer__tags">
                  <el-tag v-if="row.needsReview" size="small" type="warning">待确认</el-tag>
                  <el-tag v-if="row.semantic_review_status === 'confirmed_non_semantic'" size="small" type="info">原始保留</el-tag>
                  <el-tag v-if="row.required" size="small" type="danger">Required</el-tag>
                  <el-tag v-if="row.hash_eligible" size="small" type="info">可参与 Data Hash</el-tag>
                  <el-tag
                    v-if="selectedDeduplicationFieldSet.has(row.semantic_key)"
                    size="small"
                    type="success"
                  >
                    已选 Data Hash
                  </el-tag>
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
          :disabled="!workbenchContext || selectedDeduplicationFields.length === 0 || !hashPolicyAllowsSave || saveReadinessLoading || saving"
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
  getSemanticFieldOptionGroupsForDomain,
  getSemanticFieldMeta,
  NON_SEMANTIC_FIELD_OPTION,
  NON_SEMANTIC_FIELD_VALUE,
  updateHeaderBindingSemantic,
} from '@/domains/data_platform/utils/headerBindings'
import {
  DATE_ANCHOR_OPTIONS,
  DATE_FORMAT_OPTIONS,
  DATE_TARGET_FIELD_OPTIONS,
  DATE_VALUE_KIND_OPTIONS,
  buildAutoCompanionFormatPayload,
  buildCompanionDateParseRules,
  buildFieldParseSourceOptions,
  fieldParseRuleNeedsDateAnchor,
  fieldParseRuleNeedsRangePick,
  mergeFieldParseRules,
} from '@/domains/data_platform/utils/templateFieldParseRules'
import {
  buildTemplateUpdateSubmissionState,
  mergeHeaderBindingsForSave,
  normalizeDeduplicationSelection,
} from '@/domains/data_platform/utils/deduplicationSelection'

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
const sampleRowsVersion = ref(0)
const fullHeaderBindings = ref([])
const localHeaderBindings = ref([])
const localFieldParseRules = ref([])
const editingBindingNames = ref([])
const saving = ref(false)
const hashPolicyAllowsSave = ref(false)
const saveReadinessLoading = ref(false)
const hashPolicyPreview = ref(null)
const lastSaveReadinessPreview = ref(null)
const semanticNonSemanticOption = NON_SEMANTIC_FIELD_OPTION
const semanticFieldOptionGroups = computed(() =>
  getSemanticFieldOptionGroupsForDomain(
    templateContext.value?.data_domain || props.template?.data_domain || props.template?.domain || ''
  )
)
const dateTargetOptions = DATE_TARGET_FIELD_OPTIONS
const dateValueKindOptions = DATE_VALUE_KIND_OPTIONS
const dateFormatOptions = DATE_FORMAT_OPTIONS
const dateAnchorOptions = DATE_ANCHOR_OPTIONS

const workbenchContext = computed(() => activeContext.value ?? props.context?.context ?? null)
const templateContext = computed(() => workbenchContext.value?.template ?? props.context?.template ?? {})
const currentHeaderColumns = computed(() => workbenchContext.value?.current_header_columns ?? [])
const reviewHeaderBindings = computed(() => workbenchContext.value?.review_header_bindings ?? [])
const fullContextHeaderBindings = computed(
  () => workbenchContext.value?.full_header_bindings ?? workbenchContext.value?.current_header_bindings ?? [],
)
const templateHeaderColumns = computed(() => workbenchContext.value?.template_header_columns ?? [])
const addedFields = computed(() => workbenchContext.value?.added_fields ?? [])
const removedFields = computed(() => workbenchContext.value?.removed_fields ?? [])
const existingDeduplicationFieldsAvailable = computed(
  () => workbenchContext.value?.existing_deduplication_fields_available ?? [],
)
const existingDeduplicationFieldsMissing = computed(
  () => workbenchContext.value?.existing_deduplication_fields_missing ?? [],
)
const existingDeduplicationFieldMatches = computed(
  () => workbenchContext.value?.existing_deduplication_field_matches ?? [],
)
const recommendedDeduplicationFields = computed(
  () => workbenchContext.value?.recommended_deduplication_fields ?? [],
)
const updateMode = computed(() => workbenchContext.value?.update_mode ?? 'with-sample')
const headerSource = computed(() => workbenchContext.value?.header_source ?? 'sample-file')
const selectedDeduplicationFieldSet = computed(
  () => new Set(selectedDeduplicationFields.value.map(field => String(field || '').trim()).filter(Boolean))
)
const fieldParseSourceOptions = computed(() => buildFieldParseSourceOptions(currentHeaderColumns.value))

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
    localHeaderBindings.value = Array.isArray(next?.review_header_bindings)
      ? next.review_header_bindings.map(item => ({ ...item }))
      : Array.isArray(next?.current_header_bindings)
      ? next.current_header_bindings.map(item => ({ ...item }))
      : []
    localFieldParseRules.value = Array.isArray(next?.template?.field_parse_rules)
      ? next.template.field_parse_rules.map(rule => ({ strict: true, ...rule }))
      : []
    previewExpanded.value = false
    previewLoaded.value = false
    previewData.value = []
    sampleRowsVersion.value = 0
    bindingsExpanded.value = false
    bindingsLoaded.value = false
    fullHeaderBindings.value = []
    editingBindingNames.value = []
    bindingsViewMode.value = 'needs-review'
    hashPolicyAllowsSave.value = false
    saveReadinessLoading.value = false
    hashPolicyPreview.value = null
    lastSaveReadinessPreview.value = null
  },
  { immediate: true },
)

watch(
  [existingDeduplicationFieldsAvailable, recommendedDeduplicationFields, currentHeaderColumns],
  ([available, recommended, currentFields]) => {
    const initialSelection = available.length > 0
      ? [...available]
      : recommended.length > 0
      ? [...recommended]
      : []
    selectedDeduplicationFields.value = normalizeDeduplicationSelection(
      initialSelection,
      submissionState.value.headerBindings,
      localFieldParseRules.value,
    )
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
  existing_deduplication_field_matches: existingDeduplicationFieldMatches.value,
}))

const activeBindingSource = computed(() => {
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0 && bindingsViewMode.value === 'all') {
    return fullHeaderBindings.value
  }
  return localHeaderBindings.value
})

const saveReadyBindingBase = computed(() => {
  if (fullHeaderBindings.value.length > 0) {
    return fullHeaderBindings.value
  }
  if (Array.isArray(fullContextHeaderBindings.value) && fullContextHeaderBindings.value.length > 0) {
    return fullContextHeaderBindings.value
  }
  return activeBindingSource.value
})

const submissionState = computed(() => {
  return buildTemplateUpdateSubmissionState({
    baseBindings: saveReadyBindingBase.value,
    editedBindings: localHeaderBindings.value,
    selectedFields: selectedDeduplicationFields.value,
    fieldParseRules: localFieldParseRules.value,
  })
})
const saveReadyHeaderBindings = computed(() => submissionState.value.headerBindings)

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
const ordinaryPendingFieldCount = computed(() => {
  const reviewed = new Set(summaryBindingRows.value.map(row => String(row?.raw_name || '').trim()).filter(Boolean))
  return saveReadyBindingBase.value.filter((binding) => {
    const rawName = String(binding?.raw_name || '').trim()
    const reviewStatus = binding?.semantic_review_status || (binding?.semantic_key ? 'confirmed_semantic' : 'pending')
    return (
      rawName &&
      !reviewed.has(rawName) &&
      reviewStatus === 'pending' &&
      !binding?.required &&
      !binding?.hash_participates &&
      !binding?.hash_eligible
    )
  }).length
})

const visibleBindingRows = computed(() => {
  if (bindingsViewMode.value === 'all') {
    return bindingRows.value
  }
  return summaryBindingRows.value
})

watch(
  [() => submissionState.value.headerBindings, localFieldParseRules],
  () => {
    const normalizedSelection = normalizeDeduplicationSelection(
      selectedDeduplicationFields.value,
      saveReadyHeaderBindings.value,
      localFieldParseRules.value,
    )
    const currentSignature = JSON.stringify(selectedDeduplicationFields.value)
    const nextSignature = JSON.stringify(normalizedSelection)
    if (currentSignature !== nextSignature) {
      selectedDeduplicationFields.value = normalizedSelection
    }
  },
  { immediate: true, deep: true },
)

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
    sampleRowsVersion.value += 1
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
    const loadedBindings = Array.isArray(data?.full_header_bindings)
      ? data.full_header_bindings.map(item => ({ ...item }))
      : Array.isArray(data?.current_header_bindings)
      ? data.current_header_bindings.map(item => ({ ...item }))
      : []
    fullHeaderBindings.value = mergeHeaderBindingsForSave(
      loadedBindings,
      localHeaderBindings.value,
    )
    bindingsLoaded.value = true
  } catch (error) {
    console.error('Failed to load bindings:', error)
    ElMessage.error(error?.message || 'Failed to load bindings')
  } finally {
    loadingBindings.value = false
  }
}

async function togglePreviewSection() {
  if (previewExpanded.value) {
    previewExpanded.value = false
    return
  }
  if (loadingPreview.value) {
    return
  }
  if (!previewLoaded.value) {
    await ensurePreviewLoaded()
  }
  if (previewLoaded.value) {
    previewExpanded.value = true
  }
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

function handleSemanticKeyChange(rawName, semanticKey) {
  const nextBindings = updateHeaderBindingSemantic(activeBindingSource.value, rawName, semanticKey)
  const nextEditedBindings = mergeHeaderBindingsForSave(
    localHeaderBindings.value,
    nextBindings,
  )
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0) {
    fullHeaderBindings.value = nextBindings
  }
  localHeaderBindings.value = nextEditedBindings
  const updatedBinding = nextBindings.find(binding => binding?.raw_name === rawName)
  const preferredSemanticKey = updatedBinding?.hash_participates
    ? String(updatedBinding?.semantic_key || '').trim()
    : null
  selectedDeduplicationFields.value = buildTemplateUpdateSubmissionState({
    baseBindings: nextBindings,
    editedBindings: nextEditedBindings,
    selectedFields: selectedDeduplicationFields.value,
    fieldParseRules: localFieldParseRules.value,
    preferredSemanticKey,
  }).deduplicationFields
}

function handleHashPolicyChange({ valid, loading, preview }) {
  saveReadinessLoading.value = Boolean(loading)
  hashPolicyAllowsSave.value = Boolean(valid)
  hashPolicyPreview.value = preview || null
  if (preview) {
    lastSaveReadinessPreview.value = preview
  }
  const normalizedFields = Array.isArray(preview?.normalized_deduplication_fields)
    ? preview.normalized_deduplication_fields
    : null
  if (normalizedFields) {
    const currentSignature = JSON.stringify(selectedDeduplicationFields.value)
    const nextSignature = JSON.stringify(normalizedFields)
    if (currentSignature !== nextSignature) {
      selectedDeduplicationFields.value = [...normalizedFields]
    }
  }
}

function formatFieldLabel(field) {
  return formatHeaderBindingLabel(field, saveReadyHeaderBindings.value)
}

function normalizeFieldParseRulesForSave() {
  return localFieldParseRules.value.map(rule => ({
    target_field: rule.target_field || '',
    source_column: rule.source_column || '',
    value_kind: rule.value_kind || 'single_date',
    date_format: rule.date_format || '',
    strict: rule.strict !== false,
    ...buildAutoCompanionFormatPayload(rule),
    ...(fieldParseRuleNeedsRangePick(rule) ? { range_pick: rule.range_pick || '' } : {}),
    ...(fieldParseRuleNeedsDateAnchor(rule) ? { date_anchor: rule.date_anchor || '__file_date_from__' } : {}),
  }))
}

function addFieldParseRule() {
  localFieldParseRules.value.push({
    target_field: 'metric_date',
    source_column: '',
    value_kind: 'single_date',
    date_format: 'auto_by_companion_period',
    strict: true,
  })
}

function applyCompanionDateRules(mode) {
  localFieldParseRules.value = mergeFieldParseRules(
    localFieldParseRules.value,
    buildCompanionDateParseRules(mode)
  )
}

function removeFieldParseRule(index) {
  localFieldParseRules.value.splice(index, 1)
}

async function handleSave() {
  if (!hashPolicyAllowsSave.value) {
    const message =
      hashPolicyPreview.value?.blocking_errors?.[0] ||
      hashPolicyPreview.value?.missing_required_groups?.[0]?.message ||
      '请先补齐 Data Hash 必需的语义字段。'
    ElMessage.warning(message)
    return
  }
  saving.value = true
  try {
    if (updateMode.value !== 'core-only') {
      await ensureBindingsLoaded()
    }
    const submissionState = buildTemplateUpdateSubmissionState({
      baseBindings: saveReadyBindingBase.value,
      editedBindings: localHeaderBindings.value,
      selectedFields: Array.isArray(lastSaveReadinessPreview.value?.normalized_deduplication_fields)
        ? lastSaveReadinessPreview.value.normalized_deduplication_fields
        : selectedDeduplicationFields.value,
      fieldParseRules: localFieldParseRules.value,
    })
    selectedDeduplicationFields.value = submissionState.deduplicationFields
    emit('save', {
      deduplicationFields: submissionState.deduplicationFields,
      headerRow: selectedHeaderRow.value,
      headerBindings: submissionState.headerBindings.map(item => ({ ...item })),
      fieldParseRules: normalizeFieldParseRulesForSave(),
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

.template-update-workbench-drawer__date-rules {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.template-update-workbench-drawer__date-rule {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
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
