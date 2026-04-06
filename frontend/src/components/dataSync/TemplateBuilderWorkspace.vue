<template>
  <div class="template-builder-workspace">
    <el-card class="file-selection-card" style="margin-bottom: 20px;">
      <template #header>
        <span>📁 文件选择</span>
      </template>
      <el-form :inline="true" :model="fileFilters">
        <el-form-item label="选择平台">
          <el-select v-model="fileFilters.platform" placeholder="全部平台" clearable style="width: 150px;" @change="$emit('platform-change')">
            <el-option
              v-for="platform in availablePlatforms"
              :key="platform"
              :label="getPlatformLabel(platform)"
              :value="platform"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择数据域">
          <el-select v-model="fileFilters.domain" placeholder="全部数据域" clearable style="width: 150px;" @change="$emit('domain-change')">
            <el-option label="订单" value="orders" />
            <el-option label="产品" value="products" />
            <el-option label="流量" value="analytics" />
            <el-option label="服务" value="services" />
            <el-option label="库存" value="inventory" />
          </el-select>
        </el-form-item>
        <el-form-item label="选择子类型" v-if="availableSubDomains.length > 0">
          <el-select v-model="fileFilters.sub_domain" placeholder="全部子类型" clearable style="width: 200px;">
            <el-option v-for="sub in availableSubDomains" :key="sub.value" :label="sub.label" :value="sub.value" />
          </el-select>
          <el-tooltip content="子类型用于区分相同数据域下的不同数据来源" placement="top">
            <el-icon style="margin-left: 5px; color: #909399;"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="选择粒度">
          <el-select v-model="fileFilters.granularity" placeholder="全部粒度" clearable style="width: 150px;">
            <el-option label="日度" value="daily" />
            <el-option label="周度" value="weekly" />
            <el-option label="月度" value="monthly" />
          </el-select>
          <el-tooltip content="时序数据:需要数据中包含日期字段" placement="top">
            <el-icon style="margin-left: 5px; color: #909399;"><QuestionFilled /></el-icon>
          </el-tooltip>
        </el-form-item>
        <el-form-item label="选择文件">
          <el-select v-model="selectedFileIdModel" placeholder="请选择文件" clearable filterable style="width: 400px;" @change="$emit('file-change', $event)">
            <el-option
              v-for="file in availableFiles"
              :key="file.id"
              :label="file.file_name"
              :value="file.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="selectedFileId" class="file-info-card" style="margin-bottom: 20px;">
      <template #header>
        <span>📋 文件详情</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="文件名">
          {{ fileInfo.file_name || 'N/A' }}
        </el-descriptions-item>
        <el-descriptions-item label="平台">
          {{ fileInfo.platform || 'N/A' }}
        </el-descriptions-item>
        <el-descriptions-item label="数据域">
          {{ fileInfo.domain || 'N/A' }}
        </el-descriptions-item>
        <el-descriptions-item label="粒度">
          {{ fileInfo.granularity || 'N/A' }}
        </el-descriptions-item>
        <el-descriptions-item label="子类型">
          {{ fileInfo.sub_domain || 'N/A' }}
        </el-descriptions-item>
        <el-descriptions-item label="可用模板">
          <el-tag v-if="fileInfo.has_template" type="success" size="small">
            <el-icon><Check /></el-icon>
            有模板 ({{ fileInfo.template_name }})
          </el-tag>
          <el-tag v-else type="warning" size="small">
            <el-icon><Warning /></el-icon>
            无可用模板
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="selectedFileId" class="preview-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📊 数据预览 ({{ previewData.length }} 行 × {{ headerColumns.length }} 列)</span>
          <div>
            <el-input-number
              v-model="headerRowModel"
              :min="0"
              :max="10"
              :step="1"
              controls-position="right"
              style="width: 150px; margin-right: 10px;"
            />
            <span style="margin-right: 10px;">表头行 (0=Excel第1行)</span>
            <el-button type="primary" @click="$emit('preview')" :loading="loadingPreview">
              <el-icon><View /></el-icon>
              预览数据
            </el-button>
            <el-button v-if="previewData.length > 0" @click="$emit('repreview')" :loading="loadingPreview">
              <el-icon><Refresh /></el-icon>
              重新预览
            </el-button>
          </div>
        </div>
      </template>
      <div v-if="previewData.length > 0" class="preview-table-container">
        <el-table
          :data="previewData"
          stripe
          border
          size="small"
          style="width: max-content; min-width: 100%"
        >
          <el-table-column
            v-for="(column, index) in headerColumns"
            :key="index"
            :prop="column"
            :label="column"
            width="150"
            min-width="120"
            show-overflow-tooltip
            :fixed="index === 0 ? 'left' : false"
          />
        </el-table>
      </div>
      <el-empty v-else description="请选择表头行并点击预览数据" :image-size="100" />
    </el-card>

    <el-card v-if="headerColumns.length > 0" class="header-columns-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📋 原始表头字段列表 ({{ headerColumns.length }} 个字段)</span>
          <el-button type="primary" @click="$emit('save-template')" :loading="savingTemplate" :disabled="headerColumns.length === 0 || deduplicationFields.length === 0">
            <el-icon><Document /></el-icon>
            保存为模板
          </el-button>
        </div>
      </template>
      <el-table :data="headerColumnsWithSamples" stripe border>
        <el-table-column label="序号" type="index" width="60" align="center" />
        <el-table-column label="原始表头字段" min-width="200">
          <template #default="{ row }">
            <div style="font-weight: bold; color: #303133;">{{ row.field }}</div>
          </template>
        </el-table-column>
        <el-table-column label="示例数据" min-width="200">
          <template #default="{ row }">
            <div v-if="row.sample" style="font-size: 12px; color: #909399; font-style: italic; padding: 4px 8px; background: #f5f7fa; border-radius: 4px;">
              {{ row.sample }}
            </div>
            <span v-else style="color: #c0c4cc;">暂无数据</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <DeduplicationFieldsSelector
      v-if="headerColumns.length > 0"
      :available-fields="headerColumns"
      :data-domain="fileFilters.domain"
      :sub-domain="fileFilters.sub_domain"
      @update:selectedFields="$emit('deduplication-fields-change', $event)"
      @validation-change="$emit('validation-change', $event)"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Document, QuestionFilled, Refresh, View, Warning } from '@element-plus/icons-vue'

import DeduplicationFieldsSelector from '@/components/DeduplicationFieldsSelector.vue'

const props = defineProps({
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
])

const selectedFileIdModel = computed({
  get: () => props.selectedFileId,
  set: value => emit('update:selectedFileId', value),
})

const headerRowModel = computed({
  get: () => props.headerRow,
  set: value => emit('update:headerRow', value),
})
</script>
