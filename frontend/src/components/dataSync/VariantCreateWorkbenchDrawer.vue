<template>
  <el-drawer
    :model-value="visible"
    title="Variant Create Workbench"
    size="76%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="variant-create-workbench-drawer">
      <el-card shadow="never">
        <template #header>
          <div class="variant-create-workbench-drawer__header">
            <span>缺少变体待处理项</span>
            <el-tag size="small" type="danger">Missing Variant</el-tag>
          </div>
        </template>
        <div class="variant-create-workbench-drawer__summary">
          <span>模板族: {{ context?.family?.display_name || '-' }}</span>
          <span>激活版本: v{{ context?.active_version?.version_no || '-' }}</span>
          <span>样本文件: {{ context?.current_file?.file_name || '-' }}</span>
          <span>建议变体: {{ context?.recommended_variant_key || '-' }}</span>
        </div>
      </el-card>

      <TemplateBuilderWorkspace
        v-if="visible"
        :file-filters="fileFilters"
        :available-platforms="availablePlatforms"
        :available-sub-domains="availableSubDomains"
        :get-platform-label="getPlatformLabel"
        :available-files="availableFiles"
        :selected-file-id="selectedFileId"
        :file-info="fileInfo"
        :header-row="headerRow"
        :preview-data="previewData"
        :header-columns="headerColumns"
        :header-columns-with-samples="headerColumnsWithSamples"
        :header-bindings="headerBindings"
        :loading-preview="loadingPreview"
        :saving-template="savingTemplate"
        :deduplication-fields="deduplicationFields"
        :field-parse-rules="fieldParseRules"
        @platform-change="$emit('platform-change')"
        @domain-change="$emit('domain-change')"
        @file-change="$emit('file-change', $event)"
        @preview="$emit('preview')"
        @repreview="$emit('repreview')"
        @save-template="$emit('save-template')"
        @deduplication-fields-change="$emit('deduplication-fields-change', $event)"
        @field-parse-rules-change="$emit('field-parse-rules-change', $event)"
        @header-bindings-change="$emit('header-bindings-change', $event)"
        @validation-change="$emit('validation-change', $event)"
        @update:selectedFileId="$emit('update:selectedFileId', $event)"
        @update:headerRow="$emit('update:headerRow', $event)"
      />
    </div>
  </el-drawer>
</template>

<script setup>
import TemplateBuilderWorkspace from './TemplateBuilderWorkspace.vue'

defineProps({
  visible: { type: Boolean, default: false },
  context: { type: Object, default: () => null },
  fileFilters: { type: Object, required: true },
  availablePlatforms: { type: Array, default: () => [] },
  availableSubDomains: { type: Array, default: () => [] },
  getPlatformLabel: { type: Function, default: (value) => value ?? '' },
  availableFiles: { type: Array, default: () => [] },
  selectedFileId: { type: [Number, String, null], default: null },
  fileInfo: { type: Object, default: () => ({}) },
  headerRow: { type: Number, default: 0 },
  previewData: { type: Array, default: () => [] },
  headerColumns: { type: Array, default: () => [] },
  headerColumnsWithSamples: { type: Array, default: () => [] },
  headerBindings: { type: Array, default: () => [] },
  loadingPreview: { type: Boolean, default: false },
  savingTemplate: { type: Boolean, default: false },
  deduplicationFields: { type: Array, default: () => [] },
  fieldParseRules: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'close',
  'platform-change',
  'domain-change',
  'file-change',
  'preview',
  'repreview',
  'save-template',
  'deduplication-fields-change',
  'field-parse-rules-change',
  'header-bindings-change',
  'validation-change',
  'update:selectedFileId',
  'update:headerRow',
  'update:visible',
])

function handleClose() {
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped>
.variant-create-workbench-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.variant-create-workbench-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.variant-create-workbench-drawer__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: #606266;
  font-size: 13px;
}
</style>
