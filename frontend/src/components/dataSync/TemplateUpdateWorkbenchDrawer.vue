<template>
  <el-drawer
    :model-value="visible"
    title="Template Update Workbench"
    size="72%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="template-update-workbench-drawer">
      <TemplateChangeSummaryCard :summary="changeSummary" />

      <HeaderDiffViewer
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

      <TemplateRawPreviewPanel :preview-data="previewData" />

      <div class="template-update-workbench-drawer__section">
        <div class="template-update-workbench-drawer__section-title">Selected Deduplication Fields</div>
        <div v-if="selectedDeduplicationFields.length > 0" class="template-update-workbench-drawer__tags">
          <el-tag
            v-for="field in selectedDeduplicationFields"
            :key="field"
            size="small"
            type="primary"
          >
            {{ field }}
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

const workbenchContext = computed(() => props.context?.context ?? null)
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

const selectedDeduplicationFields = ref([])

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
  })
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
