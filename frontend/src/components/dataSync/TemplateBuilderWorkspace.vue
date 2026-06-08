<template>
  <div class="template-builder-workspace">
    <el-card class="file-selection-card" style="margin-bottom: 20px;">
      <template #header>
        <span>文件选择</span>
      </template>
      <el-form :inline="true" :model="fileFilters">
        <el-form-item label="平台">
          <el-select v-model="fileFilters.platform" placeholder="全部平台" clearable style="width: 150px;" @change="$emit('platform-change')">
            <el-option
              v-for="platform in availablePlatforms"
              :key="platform"
              :label="getPlatformLabel(platform)"
              :value="platform"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据域">
          <el-select v-model="fileFilters.domain" placeholder="全部数据域" clearable style="width: 150px;" @change="$emit('domain-change')">
            <el-option label="订单" value="orders" />
            <el-option label="产品" value="products" />
            <el-option label="流量" value="analytics" />
            <el-option label="服务" value="services" />
            <el-option label="库存" value="inventory" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="availableSubDomains.length > 0" label="子类型">
          <el-select v-model="fileFilters.sub_domain" placeholder="全部子类型" clearable style="width: 200px;">
            <el-option v-for="sub in availableSubDomains" :key="sub.value" :label="sub.label" :value="sub.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="粒度">
          <el-select v-model="fileFilters.granularity" placeholder="全部粒度" clearable style="width: 150px;">
            <el-option label="日度" value="daily" />
            <el-option label="周度" value="weekly" />
            <el-option label="月度" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件">
          <el-select
            v-model="selectedFileIdModel"
            placeholder="请选择文件"
            clearable
            filterable
            style="width: 420px;"
            @change="$emit('file-change', $event)"
          >
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
        <span>文件详情</span>
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
        <el-descriptions-item label="模板状态">
          <el-tag v-if="fileInfo.has_template" type="success" size="small">有模板</el-tag>
          <el-tag v-else type="warning" size="small">无可用模板</el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="selectedFileId" class="preview-card" style="margin-bottom: 20px;">
      <template #header>
        <div class="template-builder-workspace__header">
          <span>数据预览 ({{ previewData.length }} 行 × {{ headerColumns.length }} 列)</span>
          <div class="template-builder-workspace__actions">
            <el-input-number
              v-model="headerRowModel"
              :min="0"
              :max="10"
              :step="1"
              controls-position="right"
              style="width: 150px;"
            />
            <span class="template-builder-workspace__hint">表头行 (0 = Excel 第 1 行)</span>
            <el-button type="primary" :loading="loadingPreview" @click="$emit('preview')">预览数据</el-button>
            <el-button v-if="previewData.length > 0" :loading="loadingPreview" @click="$emit('repreview')">重新预览</el-button>
          </div>
        </div>
      </template>
      <div v-if="previewData.length > 0" class="preview-table-container">
        <el-table :data="previewData" stripe border size="small" style="width: max-content; min-width: 100%">
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
        <div class="template-builder-workspace__header">
          <span>原始表头字段列表 ({{ headerColumns.length }} 个字段)</span>
          <el-button
            type="primary"
            :loading="savingTemplate"
            :disabled="headerColumns.length === 0 || deduplicationFields.length === 0"
            @click="$emit('save-template')"
          >
            保存为模板
          </el-button>
        </div>
      </template>
      <el-table :data="headerColumnsWithSamples" stripe border>
        <el-table-column label="序号" type="index" width="60" align="center" />
        <el-table-column label="原始表头字段" min-width="220">
          <template #default="{ row }">
            <div class="template-builder-workspace__field-name">{{ row.field }}</div>
          </template>
        </el-table-column>
        <el-table-column label="示例数据" min-width="220">
          <template #default="{ row }">
            <div v-if="row.sample" class="template-builder-workspace__sample">{{ row.sample }}</div>
            <span v-else class="template-builder-workspace__muted">暂无数据</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="headerColumns.length > 0" class="semantic-bindings-card" style="margin-bottom: 20px;">
      <template #header>
        <div class="template-builder-workspace__header">
          <span>语义核心字段确认</span>
          <span class="template-builder-workspace__muted">
            系统会先自动推断语义字段；如判断不准，请在这里手工修正。
          </span>
        </div>
      </template>

      <div class="semantic-summary">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            核心字段决定去重逻辑。建议优先确认 `order_id / product_id / platform_sku / sku_id / shop_id` 是否映射正确。
          </template>
        </el-alert>
      </div>

      <el-table :data="semanticBindingRows" stripe border>
        <el-table-column label="源字段" min-width="180">
          <template #default="{ row }">
            <div class="template-builder-workspace__field-name">{{ row.raw_name }}</div>
            <div v-if="row.sample" class="template-builder-workspace__sample">{{ row.sample }}</div>
          </template>
        </el-table-column>
        <el-table-column label="语义字段" min-width="240">
          <template #default="{ row }">
            <el-select
              :model-value="semanticSelectValue(row)"
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
            <div class="template-builder-workspace__field-name">
              {{ row.meta?.label || '非语义核心字段' }}
            </div>
            <div class="template-builder-workspace__description">
              {{ row.meta?.description || '该字段仅保留原始值，不参与语义去重。' }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="常见源字段示例" min-width="260">
          <template #default="{ row }">
            <div v-if="row.meta?.aliases?.length" class="template-builder-workspace__tags">
              <el-tag v-for="alias in row.meta.aliases" :key="alias" size="small">{{ alias }}</el-tag>
            </div>
            <span v-else class="template-builder-workspace__muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="规则" width="150">
          <template #default="{ row }">
            <div class="template-builder-workspace__rules">
              <el-tag v-if="row.required" size="small" type="danger">必需</el-tag>
              <el-tag v-if="row.hash_participates" size="small" type="success">参与去重</el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="headerColumns.length > 0" class="field-parse-rules-card" style="margin-bottom: 20px;">
      <template #header>
        <div class="template-builder-workspace__header">
          <span>日期解析规则（可选但建议配置）</span>
          <el-button size="small" @click="addFieldParseRule">新增规则</el-button>
        </div>
      </template>
      <el-empty
        v-if="localFieldParseRules.length === 0"
        description="如模板需要 metric_date，请在这里声明来源列和日期格式。"
        :image-size="80"
      />
      <div v-else class="field-parse-rules-list">
        <el-card
          v-for="(rule, index) in localFieldParseRules"
          :key="index"
          shadow="never"
          class="field-parse-rules-item"
        >
          <div class="field-parse-rules-grid">
            <el-select v-model="rule.target_field" placeholder="目标字段" @change="emitFieldParseRulesChange">
              <el-option label="metric_date" value="metric_date" />
              <el-option label="period_start_date" value="period_start_date" />
              <el-option label="period_end_date" value="period_end_date" />
            </el-select>
            <el-select v-model="rule.source_column" placeholder="来源列" filterable @change="emitFieldParseRulesChange">
              <el-option v-for="column in headerColumns" :key="column" :label="column" :value="column" />
            </el-select>
            <el-select v-model="rule.value_kind" placeholder="值类型" @change="emitFieldParseRulesChange">
              <el-option label="single_date" value="single_date" />
              <el-option label="date_range" value="date_range" />
            </el-select>
            <el-select v-model="rule.date_format" placeholder="日期格式" filterable @change="emitFieldParseRulesChange">
              <el-option label="yyyy-mm-dd" value="yyyy-mm-dd" />
              <el-option label="yyyy/mm/dd" value="yyyy/mm/dd" />
              <el-option label="yyyy-mm-dd hh:mm:ss" value="yyyy-mm-dd hh:mm:ss" />
              <el-option label="yyyy/mm/dd hh:mm:ss" value="yyyy/mm/dd hh:mm:ss" />
              <el-option label="dd-mm-yyyy" value="dd-mm-yyyy" />
              <el-option label="dd/mm/yyyy" value="dd/mm/yyyy" />
              <el-option label="dd-mm-yyyy hh:mm:ss" value="dd-mm-yyyy hh:mm:ss" />
              <el-option label="dd/mm/yyyy hh:mm:ss" value="dd/mm/yyyy hh:mm:ss" />
              <el-option label="dd-mm-yyyy-dd-mm-yyyy" value="dd-mm-yyyy-dd-mm-yyyy" />
              <el-option label="dd/mm/yyyy-dd/mm/yyyy" value="dd/mm/yyyy-dd/mm/yyyy" />
            </el-select>
            <el-select
              v-if="rule.value_kind === 'date_range'"
              v-model="rule.range_pick"
              placeholder="区间取值"
              @change="emitFieldParseRulesChange"
            >
              <el-option label="start" value="start" />
              <el-option label="end" value="end" />
            </el-select>
            <el-switch
              v-model="rule.strict"
              inline-prompt
              active-text="严格"
              inactive-text="宽松"
              @change="emitFieldParseRulesChange"
            />
            <el-button type="danger" text @click="removeFieldParseRule(index)">删除</el-button>
          </div>
        </el-card>
      </div>
    </el-card>

    <DeduplicationFieldsSelector
      v-if="headerColumns.length > 0"
      :available-fields="headerColumns"
      :header-bindings="localHeaderBindings"
      :data-domain="fileFilters.domain"
      :sub-domain="fileFilters.sub_domain"
      :initial-fields="deduplicationFields"
      @update:selectedFields="$emit('deduplication-fields-change', $event)"
      @validation-change="$emit('validation-change', $event)"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Check, Document, Refresh, View, Warning } from '@element-plus/icons-vue'

import DeduplicationFieldsSelector from '@/components/DeduplicationFieldsSelector.vue'
import {
  NON_SEMANTIC_FIELD_VALUE,
  SEMANTIC_FIELD_OPTIONS,
  getSemanticFieldMeta,
  inferHeaderBindings,
  updateHeaderBindingSemantic,
} from '@/domains/data_platform/utils/headerBindings'

const props = defineProps({
  fileFilters: { type: Object, required: true },
  availablePlatforms: { type: Array, default: () => [] },
  availableSubDomains: { type: Array, default: () => [] },
  getPlatformLabel: { type: Function, default: value => value ?? '' },
  availableFiles: { type: Array, default: () => [] },
  selectedFileId: { type: [Number, String, null], default: null },
  fileInfo: { type: Object, default: () => ({}) },
  headerRow: { type: Number, default: 0 },
  previewData: { type: Array, default: () => [] },
  headerColumns: { type: Array, default: () => [] },
  headerColumnsWithSamples: { type: Array, default: () => [] },
  loadingPreview: { type: Boolean, default: false },
  savingTemplate: { type: Boolean, default: false },
  deduplicationFields: { type: Array, default: () => [] },
  fieldParseRules: { type: Array, default: () => [] },
  headerBindings: { type: Array, default: () => [] },
})

const emit = defineEmits([
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
])

const selectedFileIdModel = computed({
  get: () => props.selectedFileId,
  set: value => emit('update:selectedFileId', value),
})

const headerRowModel = computed({
  get: () => props.headerRow,
  set: value => emit('update:headerRow', value),
})

const localFieldParseRules = ref([])
const localHeaderBindings = ref([])

const semanticFieldOptions = SEMANTIC_FIELD_OPTIONS

const sampleDataLookup = computed(() =>
  Object.fromEntries((props.headerColumnsWithSamples || []).map(item => [item.field, item.sample || null]))
)

const semanticBindingRows = computed(() =>
  localHeaderBindings.value.map((binding) => ({
    ...binding,
    meta: getSemanticFieldMeta(binding.semantic_key),
    sample: sampleDataLookup.value[binding.raw_name] || null,
  }))
)

watch(
  () => props.fieldParseRules,
  (value) => {
    localFieldParseRules.value = Array.isArray(value)
      ? value.map(rule => ({ strict: true, ...rule }))
      : []
  },
  { immediate: true, deep: true }
)

watch(
  [() => props.headerBindings, () => props.headerColumns, sampleDataLookup],
  ([bindings, headerColumns, sampleLookup]) => {
    if (Array.isArray(bindings) && bindings.length > 0) {
      localHeaderBindings.value = bindings.map(item => ({ ...item }))
      return
    }
    localHeaderBindings.value = inferHeaderBindings({
      headerColumns,
      sampleData: sampleLookup,
    })
  },
  { immediate: true, deep: true }
)

watch(
  localHeaderBindings,
  (value) => {
    emit('header-bindings-change', value.map(item => ({ ...item })))
  },
  { deep: true }
)

function handleSemanticKeyChange(rawName, semanticKey) {
  localHeaderBindings.value = updateHeaderBindingSemantic(localHeaderBindings.value, rawName, semanticKey)
}

function semanticSelectValue(row) {
  if (row?.semantic_review_status === 'confirmed_non_semantic') {
    return NON_SEMANTIC_FIELD_VALUE
  }
  return row?.semantic_key || null
}

function emitFieldParseRulesChange() {
  emit(
    'field-parse-rules-change',
    localFieldParseRules.value.map(rule => ({
      target_field: rule.target_field || '',
      source_column: rule.source_column || '',
      value_kind: rule.value_kind || 'single_date',
      date_format: rule.date_format || '',
      strict: rule.strict !== false,
      ...(rule.value_kind === 'date_range' ? { range_pick: rule.range_pick || '' } : {}),
    }))
  )
}

function addFieldParseRule() {
  localFieldParseRules.value.push({
    target_field: 'metric_date',
    source_column: '',
    value_kind: 'single_date',
    date_format: 'yyyy-mm-dd',
    strict: true,
  })
  emitFieldParseRulesChange()
}

function removeFieldParseRule(index) {
  localFieldParseRules.value.splice(index, 1)
  emitFieldParseRulesChange()
}
</script>

<style scoped>
.template-builder-workspace__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.template-builder-workspace__actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.template-builder-workspace__hint,
.template-builder-workspace__muted,
.template-builder-workspace__description {
  color: #909399;
  font-size: 12px;
}

.template-builder-workspace__field-name {
  font-weight: 600;
  color: #303133;
}

.template-builder-workspace__sample {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
  padding: 4px 8px;
  background: #f5f7fa;
  border-radius: 4px;
  display: inline-block;
}

.template-builder-workspace__tags,
.template-builder-workspace__rules {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.semantic-summary {
  margin-bottom: 16px;
}

.field-parse-rules-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-parse-rules-item {
  border: 1px dashed #dcdfe6;
}

.field-parse-rules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  align-items: center;
}
</style>
