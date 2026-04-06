<template>
  <el-drawer
    :model-value="visible"
    title="Create Template Workbench"
    size="76%"
    destroy-on-close
    @close="handleClose"
  >
    <div class="template-create-workbench-drawer">
      <el-card shadow="never">
        <template #header>
          <div class="template-create-workbench-drawer__header">
            <span>缺少模板待处理项</span>
            <el-tag size="small" type="warning">Create</el-tag>
          </div>
        </template>
        <div class="template-create-workbench-drawer__summary">
          <span>平台: {{ context?.platform || '-' }}</span>
          <span>数据域: {{ context?.domain || '-' }}</span>
          <span>子类型: {{ context?.sub_domain || '-' }}</span>
          <span>粒度: {{ context?.granularity || '-' }}</span>
          <span>待同步文件数: {{ context?.file_count || 0 }}</span>
        </div>
      </el-card>

      <TemplateBuilderWorkspace
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
        :loading-preview="loadingPreview"
        :saving-template="savingTemplate"
        :deduplication-fields="deduplicationFields"
        @platform-change="$emit('platform-change')"
        @domain-change="$emit('domain-change')"
        @file-change="$emit('file-change', $event)"
        @preview="$emit('preview')"
        @repreview="$emit('repreview')"
        @save-template="$emit('save-template')"
        @deduplication-fields-change="$emit('deduplication-fields-change', $event)"
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
  visible: {
    type: Boolean,
    default: false,
  },
  context: {
    type: Object,
    default: () => null,
  },
  fileFilters: {
    type: Object,
    required: true,
  },
  availablePlatforms: {
    type: Array,
    default: () => [],
  },
  availableSubDomains: {
    type: Array,
    default: () => [],
  },
  getPlatformLabel: {
    type: Function,
    default: value => value ?? '',
  },
  availableFiles: {
    type: Array,
    default: () => [],
  },
  selectedFileId: {
    type: [Number, String, null],
    default: null,
  },
  fileInfo: {
    type: Object,
    default: () => ({}),
  },
  headerRow: {
    type: Number,
    default: 0,
  },
  previewData: {
    type: Array,
    default: () => [],
  },
  headerColumns: {
    type: Array,
    default: () => [],
  },
  headerColumnsWithSamples: {
    type: Array,
    default: () => [],
  },
  loadingPreview: {
    type: Boolean,
    default: false,
  },
  savingTemplate: {
    type: Boolean,
    default: false,
  },
  deduplicationFields: {
    type: Array,
    default: () => [],
  },
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
.template-create-workbench-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.template-create-workbench-drawer__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-create-workbench-drawer__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  color: #606266;
  font-size: 13px;
}
</style>
