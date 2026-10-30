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
        :hash-options="effectiveHashOptions"
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
                  <el-button
                    v-if="row.semantic_key && !selectedDeduplicationFieldSet.has(row.semantic_key)"
                    link
                    type="success"
                    @click="confirmBindingMapping(row.raw_name)"
                  >
                    确认映射并加入
                  </el-button>
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

        <div
          v-if="unresolvedDeduplicationFields.length > 0"
          class="template-update-workbench-drawer__unresolved"
        >
          <div class="template-update-workbench-drawer__muted">
            以下字段在当前绑定集中缺少已确认的语义映射。你的选择已保留，确认映射后即可正常保存：
          </div>
          <div class="template-update-workbench-drawer__tags" style="margin-top: 6px;">
            <el-tag
              v-for="item in unresolvedDeduplicationFields"
              :key="item.field"
              size="small"
              type="warning"
            >
              {{ formatFieldLabel(item.field) }}
            </el-tag>
          </div>
          <el-button
            size="small"
            style="margin-top: 8px;"
            :loading="loadingBindings"
            @click="reloadAllBindings"
          >
            重新加载字段绑定
          </el-button>
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
  buildAutoCompanionDateParseRules,
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
  // 父级保存处理器：传入后抽屉会 await 它，从而把 loading 状态覆盖到保存真正结束，
  // 并让失败信息可以在抽屉内展示。未传入时回退到 emit('save')。
  onSave: {
    type: Function,
    default: null,
  },
})

const emit = defineEmits(['save', 'close', 'select-mode'])

const activeContext = ref(null)
const selectedDeduplicationFields = ref([])
// 用户显式编辑过的绑定行（只含被改动的行），与"表格显示基底"解耦。
const editedHeaderBindings = ref([])
// 归一化诊断信息：removed=被剔除且有明确原因；unresolved=保留但当前绑定集缺确认绑定。
const deduplicationDiagnostics = ref({ removed: [], unresolved: [] })
const contextRequestToken = ref(0)
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
const hashOptions = computed(() => workbenchContext.value?.hash_options ?? [])
const updateMode = computed(() => workbenchContext.value?.update_mode ?? 'with-sample')
const headerSource = computed(() => workbenchContext.value?.header_source ?? 'sample-file')
const selectedDeduplicationFieldSet = computed(
  () => new Set(selectedDeduplicationFields.value.map(field => String(field || '').trim()).filter(Boolean))
)
// 保留了用户选择、但当前绑定集中缺少已确认语义映射的字段（需要用户确认）。
const unresolvedDeduplicationFields = computed(() =>
  Array.isArray(deduplicationDiagnostics.value?.unresolved)
    ? deduplicationDiagnostics.value.unresolved
    : [],
)
// 被剔除的字段及原因（明确非法/非语义/派生/不可参与 hash）。
const removedDeduplicationFields = computed(() =>
  Array.isArray(deduplicationDiagnostics.value?.removed)
    ? deduplicationDiagnostics.value.removed
    : [],
)
const fieldParseSourceOptions = computed(() => buildFieldParseSourceOptions(currentHeaderColumns.value))

const fallbackFileId = computed(() => props.context?.row?.sample_file_id ?? null)
const currentFileId = computed(() => workbenchContext.value?.current_file?.id ?? fallbackFileId.value)
const showHeaderRowControl = computed(() => updateMode.value !== 'core-only' && !!currentFileId.value)

const PRODUCTS_STRONG_IDENTITY_KEYS = new Set(['product_id'])

const recommendedStrongIdentityKeys = computed(() => {
  const domain = String(templateContext.value?.data_domain || props.template?.data_domain || props.template?.domain || '').trim().toLowerCase()
  if (domain === 'products') {
    return PRODUCTS_STRONG_IDENTITY_KEYS
  }
  return new Set()
})

function isRecommendedStrongIdentityKey(semanticKey) {
  return recommendedStrongIdentityKeys.value.has(String(semanticKey || '').trim())
}

function buildHashOptionsFromHeaderBindings(headerBindings = []) {
  const domain = String(templateContext.value?.data_domain || props.template?.data_domain || props.template?.domain || '').trim().toLowerCase()
  const seen = new Set()
  return (Array.isArray(headerBindings) ? headerBindings : [])
    .filter(binding => binding?.semantic_review_status === 'confirmed_semantic')
    .map((binding) => {
      const semanticKey = String(binding?.semantic_key || '').trim()
      if (!semanticKey || seen.has(semanticKey)) return null
      seen.add(semanticKey)
      const meta = getSemanticFieldMeta(semanticKey) || {}
      const isProductsLegacyStatus = domain === 'products' && semanticKey === 'item_status'
      const eligible = Boolean(meta.hash_eligible) || isProductsLegacyStatus
      return {
        semantic_key: semanticKey,
        label: meta.label || semanticKey,
        kind: meta.kind || '',
        raw_name: binding?.raw_name || binding?.source_header || binding?.display_name || null,
        eligible,
        recommended: isRecommendedStrongIdentityKey(semanticKey) || Boolean(eligible && meta.default_hash),
        weak_identity: meta.identity_strength === 'weak' || isProductsLegacyStatus,
        legacy_compatible: isProductsLegacyStatus,
        blocked_reason: eligible ? null : 'This semantic field is not configured as a Data Hash identity field.',
        warning: isProductsLegacyStatus
          ? 'item_status is allowed only for products template legacy compatibility; prefer product_id/SKU for new templates.'
          : meta.hash_warning || null,
      }
    })
    .filter(Boolean)
}

const effectiveHashOptions = computed(() => {
  const byKey = new Map()
  for (const option of Array.isArray(hashOptions.value) ? hashOptions.value : []) {
    const key = String(option?.semantic_key || '').trim()
    if (key) byKey.set(key, { ...option })
  }
  for (const option of buildHashOptionsFromHeaderBindings(saveReadyHeaderBindings.value)) {
    const key = String(option?.semantic_key || '').trim()
    if (!key) continue
    const backendOption = byKey.get(key)
    if (!backendOption) {
      byKey.set(key, { ...option })
      continue
    }
    // 策略字段（eligible / blocked_reason / recommended / weak_identity）一律以后端为准，
    // 前端只补充展示信息，避免本地重算覆盖后端规则（如 system_scope / metric 字段）。
    byKey.set(key, {
      ...backendOption,
      raw_name: backendOption.raw_name || option.raw_name,
      label: backendOption.label || option.label,
    })
  }
  return [...byKey.values()]
})

const eligibleHashSemanticKeys = computed(() =>
  effectiveHashOptions.value
    .filter(option => option?.eligible === true)
    .map(option => String(option?.semantic_key || '').trim())
    .filter(Boolean)
)

function mergeRecommendedIdentityFields(fields = [], headerBindings = saveReadyHeaderBindings.value) {
  const next = Array.isArray(fields) ? [...fields] : []
  const seen = new Set(next.map(field => String(field || '').trim()).filter(Boolean))
  for (const binding of Array.isArray(headerBindings) ? headerBindings : []) {
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (
      binding?.semantic_review_status === 'confirmed_semantic' &&
      isRecommendedStrongIdentityKey(semanticKey) &&
      !seen.has(semanticKey)
    ) {
      seen.add(semanticKey)
      next.push(semanticKey)
    }
  }
  return next
}

function buildFieldParseRulesForContext(context, headerBindings = null) {
  const baseRules = Array.isArray(context?.template?.field_parse_rules)
    ? context.template.field_parse_rules.map(rule => ({ strict: true, ...rule }))
    : []
  const bindings = Array.isArray(headerBindings)
    ? headerBindings
    : Array.isArray(context?.full_header_bindings)
    ? context.full_header_bindings
    : Array.isArray(context?.current_header_bindings)
    ? context.current_header_bindings
    : []
  const autoRules = buildAutoCompanionDateParseRules({
    dataDomain: context?.template?.data_domain || props.template?.data_domain || props.template?.domain || '',
    granularity: context?.template?.granularity || props.template?.granularity || '',
    headerBindings: bindings,
    headerColumns: context?.current_header_columns || [],
    currentRules: baseRules,
  })
  return autoRules.length > 0 ? mergeFieldParseRules(baseRules, autoRules) : baseRules
}

function applyAutoCompanionDateRulesForContext(context, headerBindings = null) {
  const autoRules = buildAutoCompanionDateParseRules({
    dataDomain: context?.template?.data_domain || props.template?.data_domain || props.template?.domain || '',
    granularity: context?.template?.granularity || props.template?.granularity || '',
    headerBindings: Array.isArray(headerBindings) ? headerBindings : [],
    headerColumns: context?.current_header_columns || [],
    currentRules: localFieldParseRules.value,
  })
  if (autoRules.length > 0) {
    localFieldParseRules.value = mergeFieldParseRules(localFieldParseRules.value, autoRules)
  }
}

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
    editedHeaderBindings.value = []
    deduplicationDiagnostics.value = { removed: [], unresolved: [] }
    localFieldParseRules.value = buildFieldParseRulesForContext(next)
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

// 显示基底：needs-review 视图只展示待复核行，all 视图展示全量；始终叠加用户已编辑的行。
const activeBindingSource = computed(() => {
  const base =
    bindingsLoaded.value && fullHeaderBindings.value.length > 0 && bindingsViewMode.value === 'all'
      ? fullHeaderBindings.value
      : localHeaderBindings.value
  if (editedHeaderBindings.value.length === 0) {
    return base
  }
  return mergeHeaderBindingsForSave(base, editedHeaderBindings.value)
})

// 提交基底：恒为全量绑定表 + 用户编辑，永不因视图切换而丢行。
// 视图模式只影响"显示哪些行"，绝不能影响"要保存哪些绑定"。
const bindingBase = computed(() => {
  if (fullHeaderBindings.value.length > 0) {
    return fullHeaderBindings.value
  }
  if (Array.isArray(fullContextHeaderBindings.value) && fullContextHeaderBindings.value.length > 0) {
    return fullContextHeaderBindings.value
  }
  return localHeaderBindings.value
})

const saveReadyBindingBase = computed(() => bindingBase.value)

const submissionState = computed(() => {
  return buildTemplateUpdateSubmissionState({
    baseBindings: bindingBase.value,
    editedBindings: editedHeaderBindings.value,
    selectedFields: selectedDeduplicationFields.value,
    fieldParseRules: localFieldParseRules.value,
  })
})
const saveReadyHeaderBindings = computed(() => submissionState.value.headerBindings)

watch(
  [existingDeduplicationFieldsAvailable, recommendedDeduplicationFields, currentHeaderColumns],
  ([available, recommended, currentFields]) => {
    const initialSelection = available.length > 0
      ? [...available]
      : recommended.length > 0
      ? [...recommended]
      : []
    const diagnostics = { removed: [], unresolved: [] }
    selectedDeduplicationFields.value = normalizeDeduplicationSelection(
      mergeRecommendedIdentityFields(initialSelection, submissionState.value.headerBindings),
      submissionState.value.headerBindings,
      localFieldParseRules.value,
      null,
      eligibleHashSemanticKeys.value,
      diagnostics,
    )
    deduplicationDiagnostics.value = diagnostics
  },
  { immediate: true },
)

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
    const diagnostics = { removed: [], unresolved: [] }
    const normalizedSelection = normalizeDeduplicationSelection(
      selectedDeduplicationFields.value,
      saveReadyHeaderBindings.value,
      localFieldParseRules.value,
      null,
      eligibleHashSemanticKeys.value,
      diagnostics,
    )
    deduplicationDiagnostics.value = diagnostics
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
      editedHeaderBindings.value,
    )
    applyAutoCompanionDateRulesForContext(workbenchContext.value, fullHeaderBindings.value)
    bindingsLoaded.value = true
  } catch (error) {
    console.error('Failed to load bindings:', error)
    ElMessage.error(error?.message || 'Failed to load bindings')
  } finally {
    loadingBindings.value = false
  }
}

// 强制重新拉取全量字段绑定：用于"当前绑定集缺少已确认映射"的自我修复场景。
async function reloadAllBindings() {
  if (updateMode.value === 'core-only') {
    ElMessage.warning('核心字段更新模式没有样本文件，无法重新加载字段绑定')
    return
  }
  bindingsLoaded.value = false
  await ensureBindingsLoaded()
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
  // 始终基于全量绑定表定位并替换目标行：视图模式只影响"显示哪些行"，
  // 绝不能影响"编辑哪些行"与"提交哪些绑定"（否则会把全量绑定截断成复核行）。
  const nextBindings = updateHeaderBindingSemantic(bindingBase.value, rawName, semanticKey)
  const changedBinding = nextBindings.find(binding => binding?.raw_name === rawName) || null
  editedHeaderBindings.value = mergeHeaderBindingsForSave(
    editedHeaderBindings.value,
    changedBinding ? [changedBinding] : [],
  )
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0) {
    fullHeaderBindings.value = nextBindings
  }
  const updatedBinding = changedBinding
  const preferredSemanticKey = isRecommendedStrongIdentityKey(updatedBinding?.semantic_key)
    ? String(updatedBinding?.semantic_key || '').trim()
    : null
  const mergedBindings = mergeHeaderBindingsForSave(
    bindingBase.value,
    editedHeaderBindings.value,
  )
  const diagnostics = { removed: [], unresolved: [] }
  const nextDeduplicationFields = normalizeDeduplicationSelection(
    selectedDeduplicationFields.value,
    mergedBindings,
    localFieldParseRules.value,
    preferredSemanticKey,
    eligibleHashSemanticKeys.value,
    diagnostics,
  )
  deduplicationDiagnostics.value = diagnostics
  selectedDeduplicationFields.value = mergeRecommendedIdentityFields(
    nextDeduplicationFields,
    mergedBindings,
  )
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
    // 只增不删：后端归一化结果只用于补充字段，不得收窄用户的既有选择。
    // 收窄会静默抹掉用户已选、且后端已确认的字段（如 order_id），且无法自愈。
    const currentFields = selectedDeduplicationFields.value
    const currentKeys = new Set(
      currentFields.map(field => String(field || '').trim().toLowerCase()),
    )
    const additions = normalizedFields.filter(
      field => !currentKeys.has(String(field || '').trim().toLowerCase()),
    )
    if (additions.length > 0) {
      selectedDeduplicationFields.value = [...currentFields, ...additions]
    }
  }
}

// 显式、幂等地确认某行的语义映射，并按需把它加入去重字段。
// 独立于 el-select 的 change 事件（Element Plus 对同值不 emit，原实现无法触发）。
function confirmBindingMapping(rawName) {
  const targetKey = String(rawName || '').trim()
  const target = bindingBase.value.find(
    binding => String(binding?.raw_name || '').trim() === targetKey,
  )
  if (!target) {
    ElMessage.warning('未找到该字段的绑定记录')
    return
  }
  const semanticKey = String(target.semantic_key || '').trim()
  if (!semanticKey) {
    ElMessage.warning('该字段尚未绑定语义字段，请先在语义字段列选择')
    return
  }
  const confirmedBinding = {
    ...target,
    semantic_review_status: 'confirmed_semantic',
  }
  editedHeaderBindings.value = mergeHeaderBindingsForSave(
    editedHeaderBindings.value,
    [confirmedBinding],
  )
  if (bindingsLoaded.value && fullHeaderBindings.value.length > 0) {
    fullHeaderBindings.value = fullHeaderBindings.value.map(binding =>
      String(binding?.raw_name || '').trim() === targetKey ? confirmedBinding : binding,
    )
  }
  if (!selectedDeduplicationFieldSet.value.has(semanticKey)) {
    selectedDeduplicationFields.value = [...selectedDeduplicationFields.value, semanticKey]
  }
  ElMessage.success(`已确认「${targetKey}」→ ${semanticKey}`)
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
    // 优先展示后端准备好的中文可执行文案，其次才是英文 legacy_error。
    const message =
      hashPolicyPreview.value?.missing_required_groups?.[0]?.message ||
      hashPolicyPreview.value?.blocking_errors?.[0] ||
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
      baseBindings: bindingBase.value,
      editedBindings: editedHeaderBindings.value,
      // 直接使用用户当前选择：归一化已改为"只增不删"，
      // 不能再用后端上一次的归一化结果覆盖，否则会把用户已选字段静默收窄。
      selectedFields: selectedDeduplicationFields.value,
      fieldParseRules: localFieldParseRules.value,
      eligibleSemanticKeys: eligibleHashSemanticKeys.value,
    })
    selectedDeduplicationFields.value = submissionState.deduplicationFields
    deduplicationDiagnostics.value = submissionState.diagnostics
    const payload = {
      deduplicationFields: submissionState.deduplicationFields,
      headerRow: selectedHeaderRow.value,
      headerColumns: [...currentHeaderColumns.value],
      headerBindings: submissionState.headerBindings.map(item => ({ ...item })),
      sampleData: { ...(workbenchContext.value?.sample_data || {}) },
      previewData: Array.isArray(workbenchContext.value?.preview_data)
        ? workbenchContext.value.preview_data.map(row => ({ ...row }))
        : [],
      fieldParseRules: normalizeFieldParseRulesForSave(),
    }
    if (typeof props.onSave === 'function') {
      // 等待父级保存真正结束，loading 状态才能覆盖整个保存过程。
      await props.onSave(payload)
    } else {
      emit('save', payload)
    }
  } finally {
    saving.value = false
  }
}

async function reloadContext() {
  const templateId = templateContext.value?.id
  const fileId = currentFileId.value
  if (!templateId || !fileId) return

  // 请求令牌：只接受最新一次请求的结果，避免快速切换表头时旧响应覆盖新数据。
  const requestToken = ++contextRequestToken.value
  reloadingContext.value = true
  try {
    const context = await api.getTemplateUpdateContext(templateId, {
      mode: updateMode.value,
      fileId,
      headerRow: selectedHeaderRow.value,
    })
    if (requestToken !== contextRequestToken.value) {
      return
    }
    activeContext.value = context
  } catch (error) {
    if (requestToken !== contextRequestToken.value) {
      return
    }
    console.error('Failed to reload context:', error)
    ElMessage.error(error?.message || 'Failed to reload context')
  } finally {
    if (requestToken === contextRequestToken.value) {
      reloadingContext.value = false
    }
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

.template-update-workbench-drawer__unresolved {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #fdf6ec;
  border: 1px solid #f3d19e;
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
