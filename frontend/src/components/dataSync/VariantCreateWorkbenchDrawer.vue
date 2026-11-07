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
          <span>建议变体: {{ recommendedVariantKind || '-' }}</span>
        </div>
      </el-card>

      <el-card shadow="never" class="variant-create-workbench-drawer__form">
        <template #header>
          <div class="variant-create-workbench-drawer__header">
            <span>业务形态</span>
            <el-tag size="small" type="info">按业务维度建变体</el-tag>
          </div>
        </template>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="变体按业务形态区分，不再按文件名切分"
          description="形态 = 列集合 + 解析方式 + 表头行 + 工作表名。同一种形态自动归并到同一个变体；换个文件名不会再多出一个变体。账号差异由变体承载，账号变多不会让模板数变多。"
        />

        <el-descriptions :column="3" border size="small" class="variant-create-workbench-drawer__form-desc">
          <el-descriptions-item label="平台">{{ businessForm.platform || '-' }}</el-descriptions-item>
          <el-descriptions-item label="数据域">{{ businessForm.data_domain || '-' }}</el-descriptions-item>
          <el-descriptions-item label="子域">{{ businessForm.sub_domain || '-' }}</el-descriptions-item>
          <el-descriptions-item label="粒度">{{ businessForm.granularity || '-' }}</el-descriptions-item>
          <el-descriptions-item label="表头行">{{ businessForm.header_row ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="列数">{{ businessForm.column_count ?? 0 }}</el-descriptions-item>
          <el-descriptions-item label="工作表名模式">{{ businessForm.sheet_name_pattern || '不限' }}</el-descriptions-item>
          <el-descriptions-item label="形态标识">
            <code class="variant-create-workbench-drawer__form-kind">{{ recommendedVariantKind || '-' }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="日期格式">{{ formatList(businessForm.date_formats) }}</el-descriptions-item>
          <el-descriptions-item label="值形态">{{ formatList(businessForm.value_kinds) }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="existingFormList.length" class="variant-create-workbench-drawer__form-existing">
          <span class="variant-create-workbench-drawer__form-existing-title">已有变体形态</span>
          <el-tag
            v-for="item in existingFormList"
            :key="item.variant_kind || item.variant_key"
            size="small"
            :type="item.variant_kind === recommendedVariantKind ? 'success' : 'info'"
            class="variant-create-workbench-drawer__form-existing-tag"
          >
            {{ item.variant_kind || item.variant_key }}
          </el-tag>
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
        :core-fields="coreFields"
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
import { computed } from 'vue'
import TemplateBuilderWorkspace from './TemplateBuilderWorkspace.vue'

const props = defineProps({
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
  // [*] 批次 E: 版本级核心字段清单
  coreFields: { type: Array, default: () => [] },
  fieldParseRules: { type: Array, default: () => [] },
})

// [*] 批次 G(G-3): 变体按**业务形态**建, 不再按文件名建。
//     形态标识由后端算好(列集合 + 解析方式 + 表头行 + 工作表名)。
const businessForm = computed(() => props.context?.recommended_business_form || {})

const recommendedVariantKind = computed(() => {
  return (
    props.context?.recommended_variant_kind ||
    businessForm.value.variant_kind ||
    ''
  )
})

const existingFormList = computed(() => {
  const list = props.context?.existing_variants
  return Array.isArray(list) ? list : []
})

function formatList(values) {
  if (!Array.isArray(values) || values.length === 0) return '-'
  return values.join(' / ')
}

const emit = defineEmits([
  'close',
  'platform-change',
  'domain-change',
  'file-change',
  'preview',
  'repreview',
  'save-template',
  'deduplication-fields-change',
  'core-fields-change',
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

.variant-create-workbench-drawer__form-desc {
  margin-top: 12px;
}

.variant-create-workbench-drawer__form-kind {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}

.variant-create-workbench-drawer__form-existing {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}

.variant-create-workbench-drawer__form-existing-title {
  color: #606266;
  font-size: 13px;
}

.variant-create-workbench-drawer__form-existing-tag {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
}
</style>
