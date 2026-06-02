<template>
  <el-drawer
    :model-value="visible"
    title="Template Update Workbench"
    size="72%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="template-update-workbench-drawer">
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
            表头行 (Excel第{{ selectedHeaderRow + 1 }}行)
          </span>
          <el-button size="small" :loading="reloadingContext" @click="reloadContext">重新加载</el-button>
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
      />

      <TemplateRawPreviewPanel v-if="updateMode !== 'core-only' && previewData.length > 0" :preview-data="previewData" />

      <div class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-title">语义核心字段确认</div>
        <div class="template-update-workbench-drawer__muted">
          系统会自动推荐语义字段；如当前样本和主模板的字段别名不同，请在这里人工修正。
        </div>
        <el-table :data="semanticBindingRows" stripe border style="margin-top: 12px;">
          <el-table-column prop="raw_name" label="源字段" min-width="180" />
          <el-table-column label="语义字段" min-width="240">
            <template #default="{ row }">
              <el-select
                :model-value="row.semantic_key"
                clearable
                filterable
                placeholder="请选择语义字段"
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
            </template>
          </el-table-column>
          <el-table-column label="中文说明" min-width="260">
            <template #default="{ row }">
              <div class="template-update-workbench-drawer__binding-title">
                {{ row.meta?.label || '非语义核心字段' }}
              </div>
              <div class="template-update-workbench-drawer__muted">
                {{ row.meta?.description || '该字段仅保留原始值，不参与语义去重。' }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="规则" width="150">
            <template #default="{ row }">
              <div class="template-update-workbench-drawer__tags">
                <el-tag v-if="row.required" size="small" type="danger">必需</el-tag>
                <el-tag v-if="row.hash_participates" size="small" type="success">参与去重</el-tag>
              </div>
            </template>
          </el-table-column>
        </el-table>
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
    </div>

    <template #footer>
      <div class="template-update-workbench-drawer__footer">
        <el-button @click="$emit('update:visible', false)">Cancel</el-button>
        <el-button
          type="primary"
          :disabled="selectedDeduplicationFields.length === 0"
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
})

const emit = defineEmits(['update:visible', 'save', 'close'])

const activeContext = ref(null)
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
const previewData = computed(() => workbenchContext.value?.preview_data ?? [])
const currentHeaderBindings = computed(() => workbenchContext.value?.current_header_bindings ?? [])
const updateMode = computed(() => workbenchContext.value?.update_mode ?? 'with-sample')
const headerSource = computed(() => workbenchContext.value?.header_source ?? 'sample-file')

const selectedDeduplicationFields = ref([])
const selectedHeaderRow = ref(0)
const reloadingContext = ref(false)
const localHeaderBindings = ref([])
const semanticFieldOptions = SEMANTIC_FIELD_OPTIONS

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
    selectedDeduplicationFields.value = currentFields.slice(0, 1)
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

function handleSave() {
  emit('save', {
    deduplicationFields: [...selectedDeduplicationFields.value],
    headerRow: selectedHeaderRow.value,
    headerBindings: localHeaderBindings.value.map(item => ({ ...item })),
  })
}

function formatFieldLabel(field) {
  return formatHeaderBindingLabel(field, currentHeaderBindings.value)
}

function handleSemanticKeyChange(rawName, semanticKey) {
  localHeaderBindings.value = updateHeaderBindingSemantic(localHeaderBindings.value, rawName, semanticKey)
}

const semanticBindingRows = computed(() =>
  localHeaderBindings.value.map((binding) => ({
    ...binding,
    meta: getSemanticFieldMeta(binding.semantic_key),
  }))
)

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
    console.error('重新加载模板更新上下文失败:', error)
    ElMessage.error(error?.message || '重新加载失败')
  } finally {
    reloadingContext.value = false
  }
}

function handleClose() {
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped>
.template-update-workbench-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.template-update-workbench-drawer__section-title {
  margin-bottom: 12px;
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

.template-update-workbench-drawer__muted {
  color: #909399;
  font-size: 12px;
}

.template-update-workbench-drawer__footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
