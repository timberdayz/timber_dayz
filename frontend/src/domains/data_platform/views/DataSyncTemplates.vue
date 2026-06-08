<template>
  <div class="data-sync-templates erp-page-container">
    <div class="page-header">
      <h1>数据同步 - 模板管理</h1>
      <p>以模板族、版本、变体三层视图管理同步模板，并将更新模板与创建变体拆成独立工作流。</p>
    </div>

    <TemplateGovernancePanel
      :detailed-coverage="detailedCoverage"
      :loading="governanceLoading"
      :active-tab="activeTab"
      :get-platform-label="getPlatformLabel"
      @refresh="loadGovernanceStats"
      @create-missing="handleCreateTemplateForMissing"
      @update-template="handleUpdateTemplate"
      @manual-update="handleManualUpdate"
      @update:active-tab="activeTab = $event"
    />

    <el-card class="template-builder-card" style="margin-bottom: 20px;">
      <template #header>
        <div class="card-header-inline">
          <span>模板工作区</span>
          <el-button text type="primary" @click="showTemplateBuilder = !showTemplateBuilder">
            {{ showTemplateBuilder ? '收起工作区' : '展开工作区' }}
          </el-button>
        </div>
      </template>
      <p class="muted-text">用于缺少模板时创建模板，或在需要时进入旧版手动预览与保存路径。</p>
    </el-card>

    <TemplateBuilderWorkspace
      v-if="showTemplateBuilder && !isCreateWorkbenchVisible && !isVariantWorkbenchVisible && !isWorkbenchVisible"
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
      @platform-change="handlePlatformChange"
      @domain-change="handleDomainChange"
      @file-change="handleFileChange"
      @preview="handlePreview"
      @repreview="handleRepreview"
      @save-template="handleSaveTemplate"
      @deduplication-fields-change="handleDeduplicationFieldsChange"
      @field-parse-rules-change="handleFieldParseRulesChange"
      @header-bindings-change="handleHeaderBindingsChange"
      @validation-change="handleValidationChange"
      @update:selectedFileId="selectedFileId = $event"
      @update:headerRow="headerRow = $event"
    />

    <el-card class="filter-card" style="margin-bottom: 20px;">
      <el-form :inline="true" :model="filters">
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="全部平台" clearable style="width: 150px;">
            <el-option
              v-for="platform in availablePlatforms"
              :key="platform"
              :label="getPlatformLabel(platform)"
              :value="platform"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="数据域">
          <el-select v-model="filters.domain" placeholder="全部数据域" clearable style="width: 150px;">
            <el-option label="订单" value="orders" />
            <el-option label="产品" value="products" />
            <el-option label="分析" value="analytics" />
            <el-option label="服务" value="services" />
            <el-option label="库存" value="inventory" />
          </el-select>
        </el-form-item>
        <el-form-item label="粒度">
          <el-select v-model="filters.granularity" placeholder="全部粒度" clearable style="width: 150px;">
            <el-option label="日度" value="daily" />
            <el-option label="周度" value="weekly" />
            <el-option label="月度" value="monthly" />
            <el-option label="快照" value="snapshot" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadTemplates">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="card-header-inline">
          <span>模板族列表（共 {{ templates.length }} 个）</span>
          <el-button :loading="loading" @click="loadTemplates">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table :data="templates" v-loading="loading" stripe style="width: 100%">
        <el-table-column type="expand" width="56">
          <template #default="{ row }">
            <div class="family-expand">
              <div class="family-section-title">版本</div>
              <el-table :data="row.versions || []" size="small" border style="width: 100%; margin-bottom: 16px;">
                <el-table-column prop="version_no" label="版本" width="90" />
                <el-table-column prop="status" label="状态" width="90" />
                <el-table-column prop="template_name" label="版本模板名" min-width="220" />
                <el-table-column label="核心字段" width="100">
                  <template #default="{ row: versionRow }">
                    {{ versionRow.deduplication_fields?.length || 0 }}
                  </template>
                </el-table-column>
                <el-table-column label="变体数" width="90">
                  <template #default="{ row: versionRow }">
                    {{ versionRow.variant_count || 0 }}
                  </template>
                </el-table-column>
              </el-table>

              <div class="family-section-title">变体</div>
              <el-table :data="flattenVariants(row)" size="small" border style="width: 100%">
                <el-table-column prop="variant_key" label="变体 Key" min-width="180" />
                <el-table-column prop="header_row" label="表头行" width="90" />
                <el-table-column label="日期格式" min-width="180">
                  <template #default="{ row: variantRow }">
                    {{ formatVariantDateFormats(variantRow.parse_profile) }}
                  </template>
                </el-table-column>
                <el-table-column label="字段数" width="90">
                  <template #default="{ row: variantRow }">
                    {{ variantRow.required_headers?.length || 0 }}
                  </template>
                </el-table-column>
                <el-table-column prop="template_name" label="来源模板" min-width="220" />
                <el-table-column label="操作" width="170" fixed="right">
                  <template #default="{ row: variantRow }">
                    <el-button size="small" type="primary" @click="handleManualUpdate(buildManualUpdateRow(row, variantRow))">
                      Manual Update
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="display_name" label="模板族" min-width="240" />
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="{ row }">
            {{ getPlatformLabel(row.platform) }}
          </template>
        </el-table-column>
        <el-table-column prop="data_domain" label="数据域" width="100" />
        <el-table-column prop="granularity" label="粒度" width="90" />
        <el-table-column prop="sub_domain" label="子类型" width="120" />
        <el-table-column label="激活版本" width="90">
          <template #default="{ row }">v{{ row.active_version?.version_no || '-' }}</template>
        </el-table-column>
        <el-table-column label="变体数" width="80">
          <template #default="{ row }">{{ row.variant_count || 0 }}</template>
        </el-table-column>
        <el-table-column label="治理状态" width="120">
          <template #default="{ row }">
            {{ row.display_governance_status || row.governance_status }}
          </template>
        </el-table-column>
        <el-table-column label="文件数" width="80">
          <template #default="{ row }">
            {{ row.current_file_count ?? row.file_count ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :disabled="!canManualUpdateFamily(row)"
              @click="handleManualUpdate(buildManualUpdateRow(row))"
            >
              Manual Update
            </el-button>
            <el-button size="small" @click="viewTemplateDetail(row.id)">
              <el-icon><View /></el-icon>
              查看详情
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!row.active_template_id"
              @click="deleteTemplate(row.active_template_id)"
            >
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <TemplateUpdateWorkbenchDrawer
      :visible="isWorkbenchVisible"
      :context="updateWorkbenchContext"
      :template="pendingManualUpdateTemplate"
      :loading-mode="manualUpdateLoadingMode"
      @save="handleWorkbenchSave"
      @select-mode="handleWorkbenchModeSelect"
      @close="closeTemplateUpdateWorkbench"
    />

    <VariantCreateWorkbenchDrawer
      :visible="isVariantWorkbenchVisible"
      :context="variantCreateContext"
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
      @platform-change="handlePlatformChange"
      @domain-change="handleDomainChange"
      @file-change="handleFileChange"
      @preview="handlePreview"
      @repreview="handleRepreview"
      @save-template="handleSaveVariant"
      @deduplication-fields-change="handleDeduplicationFieldsChange"
      @field-parse-rules-change="handleFieldParseRulesChange"
      @header-bindings-change="handleHeaderBindingsChange"
      @validation-change="handleValidationChange"
      @update:selectedFileId="selectedFileId = $event"
      @update:headerRow="headerRow = $event"
      @update:visible="isVariantWorkbenchVisible = $event"
      @close="closeVariantWorkbench"
    />

    <TemplateCreateWorkbenchDrawer
      :visible="isCreateWorkbenchVisible"
      :context="createWorkbenchContext"
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
      @platform-change="handlePlatformChange"
      @domain-change="handleDomainChange"
      @file-change="handleFileChange"
      @preview="handlePreview"
      @repreview="handleRepreview"
      @save-template="handleSaveTemplate"
      @deduplication-fields-change="handleDeduplicationFieldsChange"
      @field-parse-rules-change="handleFieldParseRulesChange"
      @header-bindings-change="handleHeaderBindingsChange"
      @validation-change="handleValidationChange"
      @update:selectedFileId="selectedFileId = $event"
      @update:headerRow="headerRow = $event"
      @update:visible="isCreateWorkbenchVisible = $event"
      @close="closeTemplateCreateWorkbench"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Refresh, Search, View } from '@element-plus/icons-vue'

import api from '@/api'
import TemplateBuilderWorkspace from '@/components/dataSync/TemplateBuilderWorkspace.vue'
import TemplateCreateWorkbenchDrawer from '@/components/dataSync/TemplateCreateWorkbenchDrawer.vue'
import TemplateGovernancePanel from '@/components/dataSync/TemplateGovernancePanel.vue'
import TemplateUpdateWorkbenchDrawer from '@/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'
import VariantCreateWorkbenchDrawer from '@/components/dataSync/VariantCreateWorkbenchDrawer.vue'
import { inferHeaderBindings } from '@/domains/data_platform/utils/headerBindings'
import { buildTemplateUpdateFieldParseRulesPayload } from '@/domains/data_platform/utils/templateUpdateFieldParseRules'

const loading = ref(false)
const loadingPreview = ref(false)
const savingTemplate = ref(false)
const governanceLoading = ref(false)
const isWorkbenchVisible = ref(false)
const isCreateWorkbenchVisible = ref(false)
const isVariantWorkbenchVisible = ref(false)
const showTemplateBuilder = ref(false)
const manualUpdateLoadingMode = ref('')
const suppressFileListAutoLoad = ref(false)
const workbenchRequestToken = ref(0)

const pendingManualUpdateTemplate = ref(null)
const manualUpdateMode = ref('with-sample')
const createWorkbenchContext = ref(null)
const updateWorkbenchContext = ref(null)
const variantCreateContext = ref(null)

const templates = ref([])
const availablePlatforms = ref([])
const filters = ref({
  platform: null,
  domain: null,
  granularity: null,
})

const fileFilters = ref({
  platform: null,
  domain: null,
  sub_domain: null,
  granularity: null,
})
const availableFiles = ref([])
const selectedFileId = ref(null)
const fileInfo = ref({})
const headerRow = ref(0)
const previewData = ref([])
const headerColumns = ref([])
const sampleData = ref({})
const headerBindings = ref([])
const deduplicationFields = ref([])
const deduplicationFieldsValid = ref(false)
const fieldParseRules = ref([])

const detailedCoverage = ref({
  summary: {
    total_combinations: 0,
    covered_count: 0,
    missing_count: 0,
    needs_update_count: 0,
    coverage_percentage: 0,
  },
  covered: [],
  missing: [],
  needs_update: [],
})
const activeTab = ref('covered')

const getPlatformLabel = (platform) => {
  const labels = {
    shopee: 'Shopee',
    tiktok: 'TikTok',
    amazon: 'Amazon',
    miaoshou: '妙手ERP',
  }
  return labels[platform] || platform
}

const availableSubDomains = computed(() => {
  const domain = fileFilters.value.domain
  if (domain === 'services') {
    return [
      { label: 'AI 服务数据', value: 'ai_assistant' },
      { label: '人工服务数据', value: 'agent' },
    ]
  }
  if (domain === 'inventory') {
    return [
      { label: '全量库存数据', value: 'full_inventory' },
      { label: '店铺库存数据', value: 'shop_inventory' },
    ]
  }
  return []
})

const headerColumnsWithSamples = computed(() =>
  headerColumns.value.map((field) => ({
    field,
    sample: sampleData.value[field] || null,
  }))
)

const flattenVariants = (family) =>
  (family.versions || []).flatMap((version) =>
    (version.variants || []).map((variant) => ({
      ...variant,
      version_no: version.version_no,
    }))
  )

const formatVariantDateFormats = (parseProfile) => {
  const formats = parseProfile?.date_formats || []
  return formats.length > 0 ? formats.join(', ') : '未声明'
}

const findGovernanceRowForFamily = (family) => {
  const rows = [
    ...(detailedCoverage.value?.current_needs_update || detailedCoverage.value?.needs_update || []),
    ...(detailedCoverage.value?.current_covered || detailedCoverage.value?.covered || []),
    ...(detailedCoverage.value?.current_missing || detailedCoverage.value?.missing || []),
  ]
  return (
    rows.find(
      (row) =>
        row.platform === family.platform &&
        row.domain === family.data_domain &&
        (row.sub_domain || 'N/A') === (family.sub_domain || 'N/A') &&
        row.granularity === family.granularity
    ) || null
  )
}

const buildManualUpdateRow = (family, variant = null) => {
  const activeVersion =
    family.activeVersionDetail || family.versions?.find((item) => item.status === 'active') || null
  const governanceRow = findGovernanceRowForFamily(family)
  const fallbackTemplateId =
    variant?.source_legacy_template_id ||
    governanceRow?.template_id ||
    family.active_template_id ||
    activeVersion?.legacy_template_ids?.[0] ||
    null

  return {
    id: family.id,
    family_id: family.id,
    template_id: fallbackTemplateId,
    template_name:
      variant?.template_name || governanceRow?.template_name || activeVersion?.template_name || family.display_name,
    platform: family.platform,
    data_domain: family.data_domain,
    domain: family.data_domain,
    granularity: family.granularity,
    sub_domain: family.sub_domain,
    governance_status: governanceRow?.governance_status || family.governance_status,
    sample_file_id: governanceRow?.sample_file_id || family.sample_file_id || null,
    sample_file_name: governanceRow?.sample_file_name || family.sample_file_name || null,
    update_reason: governanceRow?.update_reason || null,
    variant_key: variant?.variant_key || null,
    field_parse_rules: variant?.field_parse_rules || activeVersion?.field_parse_rules || [],
    header_bindings: activeVersion?.header_bindings || [],
    active_version: activeVersion,
    display_name: family.display_name,
  }
}

const normalizeTemplateActionRow = (row) => {
  if (!row) {
    return row
  }
  const normalizedDomain = row.data_domain || row.domain || null
  return {
    ...row,
    data_domain: normalizedDomain,
    domain: normalizedDomain,
  }
}

const canManualUpdateFamily = (family) => {
  const row = buildManualUpdateRow(family)
  if (row.governance_status === 'missing_variant') {
    return !!row.sample_file_id
  }
  return !!row.template_id
}

const getCurrentWorkbenchSampleFileId = () => updateWorkbenchContext.value?.row?.sample_file_id || null
const isSampleStillInNeedsUpdate = (sampleFileId) =>
  (detailedCoverage.value?.current_needs_update || detailedCoverage.value?.needs_update || []).some(
    (row) => row.sample_file_id === sampleFileId
  )

const loadAvailablePlatforms = async () => {
  try {
    const data = await api.getAvailablePlatforms()
    if (data?.platforms) {
      availablePlatforms.value = data.platforms
    }
  } catch (error) {
    console.error('加载平台列表失败:', error)
  }
}

const loadGovernanceStats = async () => {
  governanceLoading.value = true
  try {
    const detailedData = await api.getDetailedTemplateCoverage()
    if (detailedData) {
      detailedCoverage.value = detailedData
    }
  } catch (error) {
    console.error('加载治理统计失败:', error)
    ElMessage.error(error.message || '加载治理统计失败')
  } finally {
    governanceLoading.value = false
  }
}

const closeTemplateUpdateWorkbench = () => {
  workbenchRequestToken.value += 1
  isWorkbenchVisible.value = false
  updateWorkbenchContext.value = null
  pendingManualUpdateTemplate.value = null
  manualUpdateMode.value = 'with-sample'
  manualUpdateLoadingMode.value = ''
  headerBindings.value = []
}

const closeTemplateCreateWorkbench = () => {
  isCreateWorkbenchVisible.value = false
}

const closeVariantWorkbench = () => {
  isVariantWorkbenchVisible.value = false
  variantCreateContext.value = null
}

const handleManualUpdate = (row) => {
  row = normalizeTemplateActionRow(row)
  if (row?.governance_status === 'missing_variant') {
    handleCreateVariantForFamily(row)
    isWorkbenchVisible.value = false
    return
  }
  workbenchRequestToken.value += 1
  pendingManualUpdateTemplate.value = row
  updateWorkbenchContext.value = null
  manualUpdateMode.value = 'with-sample'
  manualUpdateLoadingMode.value = ''
  isWorkbenchVisible.value = true
}

const handleCreateVariantForFamily = async (row) => {
  row = normalizeTemplateActionRow(row)
  if (!row?.sample_file_id) {
    ElMessage.warning('当前缺少样本文件上下文，请先到文件列表选择一个具体文件再创建变体')
    return
  }

  fileFilters.value.platform = row.platform
  fileFilters.value.domain = row.domain || row.data_domain
  fileFilters.value.sub_domain = row.sub_domain === 'N/A' ? null : row.sub_domain
  fileFilters.value.granularity = row.granularity
  await loadAvailableFiles()
  selectedFileId.value = row.sample_file_id

  try {
    const familyId = row.family_id || row.id
    const context = await api.getTemplateVariantCreateContext(familyId, {
      fileId: row.sample_file_id,
      headerRow: headerRow.value,
    })
    variantCreateContext.value = context?.data || context
    headerBindings.value = variantCreateContext.value?.current_header_bindings || []
    isVariantWorkbenchVisible.value = true
    ElMessage.info('当前缺少变体，请基于样本文件预览结果创建新变体')
  } catch (error) {
    console.error('加载变体创建上下文失败:', error)
    ElMessage.error(error.message || '加载变体创建上下文失败')
  }
}

const chooseManualUpdateMode = async (mode, requestToken = workbenchRequestToken.value) => {
  manualUpdateMode.value = mode
  if (!pendingManualUpdateTemplate.value) {
    manualUpdateLoadingMode.value = ''
    return
  }
  if (mode === 'with-sample' && !pendingManualUpdateTemplate.value.sample_file_id) {
    ElMessage.warning('当前模板没有可直接使用的样本文件，建议先使用 Core Fields Only')
    return
  }
  await openTemplateUpdateWorkbench(pendingManualUpdateTemplate.value, mode, requestToken)
}

const handleWorkbenchModeSelect = async (mode) => {
  if (manualUpdateLoadingMode.value) {
    return
  }
  const requestToken = workbenchRequestToken.value + 1
  workbenchRequestToken.value = requestToken
  manualUpdateLoadingMode.value = mode
  try {
    await chooseManualUpdateMode(mode, requestToken)
  } catch (error) {
    isWorkbenchVisible.value = false
    throw error
  } finally {
    if (workbenchRequestToken.value === requestToken) {
      manualUpdateLoadingMode.value = ''
    }
  }
}

const openTemplateUpdateWorkbench = async (row, mode = 'with-sample', requestToken = workbenchRequestToken.value) => {
  row = normalizeTemplateActionRow(row)
  const templateId = row.template_id || row.id || null
  if (!templateId) {
    ElMessage.error('缺少可更新的模板 ID')
    return
  }

  try {
    const context = await api.getTemplateUpdateContext(templateId, {
      mode,
      fileId: mode === 'with-sample' ? row.sample_file_id || null : null,
    })
    if (workbenchRequestToken.value !== requestToken) {
      return
    }
    updateWorkbenchContext.value = {
      template: row,
      row,
      context: context?.data || context,
    }
    headerBindings.value = updateWorkbenchContext.value?.context?.current_header_bindings || []
    isWorkbenchVisible.value = true
  } catch (error) {
    console.error('加载模板更新上下文失败:', error)
    ElMessage.error(error.message || '加载模板更新上下文失败')
    isWorkbenchVisible.value = false
    return
  }
}

const handleCreateTemplateForMissing = (row) => {
  showTemplateBuilder.value = true
  createWorkbenchContext.value = row
  isCreateWorkbenchVisible.value = true
  headerBindings.value = []
  fileFilters.value.platform = row.platform
  fileFilters.value.domain = row.domain
  fileFilters.value.sub_domain = row.sub_domain === 'N/A' ? null : row.sub_domain
  fileFilters.value.granularity = row.granularity
  loadAvailableFiles()
  ElMessage.info('已设置筛选条件，请选择文件并创建模板')
}

const handleUpdateTemplate = (row) => {
  handleManualUpdate(row)
  suppressFileListAutoLoad.value = true
  fileFilters.value.platform = row.platform
  fileFilters.value.domain = row.domain
  fileFilters.value.sub_domain = row.sub_domain === 'N/A' ? null : row.sub_domain
  fileFilters.value.granularity = row.granularity
  queueMicrotask(() => {
    suppressFileListAutoLoad.value = false
  })
}

const loadAvailableFiles = async () => {
  try {
    const params = { status: 'pending', limit: 1000 }
    if (fileFilters.value.platform) params.platform = fileFilters.value.platform
    if (fileFilters.value.domain) params.domain = fileFilters.value.domain
    if (fileFilters.value.granularity) params.granularity = fileFilters.value.granularity
    if (fileFilters.value.sub_domain) params.sub_domain = fileFilters.value.sub_domain
    const data = await api.getDataSyncFiles(params)
    availableFiles.value = data.files || []
  } catch (error) {
    console.error('加载文件列表失败:', error)
    ElMessage.error(error.message || '加载文件列表失败')
  }
}

const handlePlatformChange = () => {
  fileFilters.value.domain = null
  fileFilters.value.sub_domain = null
  fileFilters.value.granularity = null
  selectedFileId.value = null
  loadAvailableFiles()
}

const handleDomainChange = () => {
  fileFilters.value.sub_domain = null
  fileFilters.value.granularity = null
  selectedFileId.value = null
  loadAvailableFiles()
}

const handleFileChange = async (fileId) => {
  if (!fileId) {
    fileInfo.value = {}
    previewData.value = []
    headerColumns.value = []
    headerBindings.value = []
    fieldParseRules.value = []
    return
  }

  const file = availableFiles.value.find((item) => item.id === fileId)
  if (file) {
    fileInfo.value = file
    fieldParseRules.value = []
    headerRow.value =
      file.has_template && file.template_header_row !== undefined && file.template_header_row !== null
        ? file.template_header_row
        : 0
  }
}

watch([() => fileFilters.value.sub_domain, () => fileFilters.value.granularity], () => {
  if (suppressFileListAutoLoad.value) {
    return
  }
  loadAvailableFiles()
})

const handlePreview = async () => {
  if (!selectedFileId.value) {
    ElMessage.warning('请先选择文件')
    return
  }
  loadingPreview.value = true
  try {
    const data = await api.previewFileWithHeaderRow(selectedFileId.value, headerRow.value)
    if (data) {
      previewData.value = data.preview_data || []
      headerColumns.value = data.header_columns || []
      sampleData.value = data.sample_data || {}
      headerBindings.value = data.header_bindings || inferHeaderBindings({
        headerColumns: data.header_columns || [],
        sampleData: data.sample_data || {},
      })
      ElMessage.success('预览成功')
    }
  } catch (error) {
    console.error('预览失败:', error)
    ElMessage.error(error.message || '预览失败')
  } finally {
    loadingPreview.value = false
  }
}

const handleRepreview = () => {
  handlePreview()
}

const showTemplateGovernanceSummary = (result) => {
  const checks = result?.data?.governance_checks || result?.governance_checks
  if (!checks) return

  const aliasCount = Array.isArray(checks.registered_aliases) ? checks.registered_aliases.length : 0
  const resolvedCount = Array.isArray(checks.required_fields_resolved)
    ? checks.required_fields_resolved.length
    : 0
  const hashStatus = checks.hash_policy_status === 'passed' ? '去重规则通过' : '去重规则需检查'
  ElMessage.success(`${hashStatus}；已登记 ${aliasCount} 个字段别名；字段标准化覆盖 ${resolvedCount} 项`)

  const warnings = Array.isArray(checks.warnings) ? checks.warnings : []
  if (warnings.length > 0) {
    ElMessage.warning(warnings[0])
  }
}

const getHashPolicyFailureMessage = (preview) => {
  const missingGroup = preview?.missing_required_groups?.[0]
  if (missingGroup?.message) {
    return missingGroup.message
  }
  const invalidKeys = preview?.invalid_keys || []
  if (invalidKeys.length > 0) {
    return `${invalidKeys.join('、')} 不能参与 Data Hash`
  }
  return preview?.blocking_errors?.[0] || 'Data Hash 字段还不满足安全保存要求'
}

const ensureHashPolicyPreviewPassed = async ({
  dataDomain,
  granularity,
  subDomain,
  selectedFields,
  selectedHeaderBindings,
  selectedFieldParseRules,
  sampleRows = [],
}) => {
  try {
    const preview = await api.previewTemplateHashPolicy({
      dataDomain,
      granularity,
      subDomain,
      deduplicationFields: selectedFields,
      headerBindings: selectedHeaderBindings,
      fieldParseRules: selectedFieldParseRules,
      sampleRows,
    })
    if (preview?.passed === false) {
      ElMessage.warning(`不能保存：${getHashPolicyFailureMessage(preview)}`)
      return false
    }
    return true
  } catch (error) {
    const preview = error?.data?.hash_policy
    ElMessage.warning(preview ? `不能保存：${getHashPolicyFailureMessage(preview)}` : (error.message || 'Data Hash 预检失败'))
    return false
  }
}

const handleWorkbenchSave = async ({ deduplicationFields: selectedFields, headerRow: selectedHeaderRow, headerBindings: selectedHeaderBindings }) => {
  const context = updateWorkbenchContext.value?.context
  const template = updateWorkbenchContext.value?.template
  if (!template || !context?.current_header_columns?.length) {
    ElMessage.warning('当前缺少模板或表头上下文，无法保存')
    return
  }

  savingTemplate.value = true
  try {
    const { rules: nextFieldParseRules, droppedRules } = buildTemplateUpdateFieldParseRulesPayload({
      currentHeaderColumns: context.current_header_columns,
      currentHeaderBindings: selectedHeaderBindings || [],
      templateHeaderBindings: template.header_bindings || [],
      existingRules: template.field_parse_rules || [],
    })
    const templatePlatform = template.platform || context?.template?.platform || null
    const templateDataDomain =
      template.data_domain || template.domain || context?.template?.data_domain || context?.template?.domain || null
    const nextHeaderBindings =
      Array.isArray(selectedHeaderBindings) && selectedHeaderBindings.length > 0
        ? selectedHeaderBindings
        : headerBindings.value.length > 0
        ? headerBindings.value
        : inferHeaderBindings({
            headerColumns: context.current_header_columns,
            sampleData: context.sample_data || {},
          })
    const hashPolicyPassed = await ensureHashPolicyPreviewPassed({
      dataDomain: templateDataDomain,
      granularity: template.granularity,
      subDomain: template.sub_domain,
      selectedFields,
      selectedHeaderBindings: nextHeaderBindings,
      selectedFieldParseRules: nextFieldParseRules,
      sampleRows: context.preview_data || [],
    })
    if (!hashPolicyPassed) return

    const result = await api.saveTemplate({
      platform: templatePlatform,
      dataDomain: templateDataDomain,
      subDomain: template.sub_domain,
      granularity: template.granularity,
      saveMode: 'new_version',
      baseTemplateId: template.template_id || template.id,
      headerRow: selectedHeaderRow ?? context?.current_header_row ?? template.header_row ?? 0,
      headerColumns: context.current_header_columns,
      deduplicationFields: selectedFields,
      headerBindings: nextHeaderBindings,
      sampleData: context.sample_data || {},
      fieldParseRules: nextFieldParseRules,
    })

    if (!(result && (result.success || result.template_id))) {
      ElMessage.error(result?.message || '模板更新失败')
      return
    }

    if (droppedRules.length > 0) {
      const droppedSummary = droppedRules
        .map((rule) => `${rule.target_field} <- ${rule.source_column}`)
        .join(', ')
      ElMessage.warning(`已自动移除失效日期规则: ${droppedSummary}`)
    }

    const sampleFileId = getCurrentWorkbenchSampleFileId()
    await loadTemplates()
    await loadGovernanceStats()

    if (sampleFileId && isSampleStillInNeedsUpdate(sampleFileId)) {
      ElMessage.warning('模板已保存，但该样本文件仍未通过治理复核，请继续检查字段差异')
    } else {
      showTemplateGovernanceSummary(result)
      ElMessage.success(result.message || '模板更新成功，治理已通过')
      isWorkbenchVisible.value = false
    }
  } catch (error) {
    console.error('模板更新失败:', error)
    const preview = error?.data?.hash_policy
    ElMessage.error(preview ? getHashPolicyFailureMessage(preview) : (error.message || '模板更新失败'))
  } finally {
    savingTemplate.value = false
  }
}

const handleSaveVariant = async () => {
  const context = variantCreateContext.value
  if (!context?.family || !selectedFileId.value || headerColumns.value.length === 0) {
    ElMessage.warning('请先选择样本文件并完成预览，再创建变体')
    return
  }
  if (!deduplicationFields.value || deduplicationFields.value.length === 0) {
    ElMessage.warning('请至少选择 1 个可参与 Data Hash 的语义字段')
    return
  }
  if (!deduplicationFieldsValid.value) {
    ElMessage.warning('Data Hash 字段还未通过预检')
    return
  }

  savingTemplate.value = true
  try {
    const family = context.family
    const activeVersion = context.active_version
    const templateName =
      `${family.platform}_${family.data_domain}_${family.sub_domain || 'default'}_${family.granularity}_${context.recommended_variant_key}`
    const nextHeaderBindings =
      headerBindings.value.length > 0
        ? headerBindings.value
        : inferHeaderBindings({
            headerColumns: headerColumns.value,
            sampleData: sampleData.value,
          })
    const hashPolicyPassed = await ensureHashPolicyPreviewPassed({
      dataDomain: family.data_domain,
      granularity: family.granularity,
      subDomain: family.sub_domain,
      selectedFields: deduplicationFields.value,
      selectedHeaderBindings: nextHeaderBindings,
      selectedFieldParseRules: fieldParseRules.value,
      sampleRows: previewData.value,
    })
    if (!hashPolicyPassed) return

    const result = await api.saveTemplate({
      platform: family.platform,
      dataDomain: family.data_domain,
      subDomain: family.sub_domain,
      granularity: family.granularity,
      templateName,
      saveMode: 'create',
      baseTemplateId: activeVersion?.legacy_template_ids?.[0] || null,
      headerRow: headerRow.value,
      headerColumns: headerColumns.value,
      deduplicationFields: deduplicationFields.value,
      headerBindings: nextHeaderBindings,
      sampleData: sampleData.value,
      fieldParseRules: fieldParseRules.value,
    })

    if (!(result && (result.success || result.template_id))) {
      ElMessage.error(result?.message || '创建变体失败')
      return
    }

    await loadTemplates()
    await loadGovernanceStats()
    await loadAvailableFiles()
    ElMessage.success(result.message || '变体创建成功')
    isVariantWorkbenchVisible.value = false
  } catch (error) {
    console.error('创建变体失败:', error)
    const preview = error?.data?.hash_policy
    ElMessage.error(preview ? getHashPolicyFailureMessage(preview) : (error.message || '创建变体失败'))
  } finally {
    savingTemplate.value = false
  }
}

const handleSaveTemplate = async () => {
  if (!selectedFileId.value || headerColumns.value.length === 0) {
    ElMessage.warning('请先预览文件数据')
    return
  }
  if (!fileFilters.value.platform || !fileFilters.value.domain) {
    ElMessage.warning('请先选择平台和数据域')
    return
  }
  if (!deduplicationFields.value || deduplicationFields.value.length === 0) {
    ElMessage.warning('请至少选择 1 个可参与 Data Hash 的语义字段')
    return
  }
  if (!deduplicationFieldsValid.value) {
    ElMessage.warning('Data Hash 字段还未通过预检')
    return
  }

  savingTemplate.value = true
  try {
    const nextHeaderBindings =
      headerBindings.value.length > 0
        ? headerBindings.value
        : inferHeaderBindings({
            headerColumns: headerColumns.value,
            sampleData: sampleData.value,
          })
    const hashPolicyPassed = await ensureHashPolicyPreviewPassed({
      dataDomain: fileFilters.value.domain,
      granularity: fileFilters.value.granularity,
      subDomain: fileFilters.value.sub_domain,
      selectedFields: deduplicationFields.value,
      selectedHeaderBindings: nextHeaderBindings,
      selectedFieldParseRules: fieldParseRules.value,
      sampleRows: previewData.value,
    })
    if (!hashPolicyPassed) return

    const result = await api.saveTemplate({
      platform: fileFilters.value.platform,
      dataDomain: fileFilters.value.domain,
      subDomain: fileFilters.value.sub_domain,
      granularity: fileFilters.value.granularity,
      saveMode: 'create',
      headerRow: headerRow.value,
      headerColumns: headerColumns.value,
      deduplicationFields: deduplicationFields.value,
      headerBindings: nextHeaderBindings,
      sampleData: sampleData.value,
      fieldParseRules: fieldParseRules.value,
    })
    if (result && (result.success || result.template_id)) {
      showTemplateGovernanceSummary(result)
      ElMessage.success(result.message || '模板保存成功')
      await loadTemplates()
      await loadGovernanceStats()
      await loadAvailableFiles()
    } else {
      ElMessage.error(result?.message || '模板保存失败')
    }
  } catch (error) {
    console.error('保存模板失败:', error)
    const preview = error?.data?.hash_policy
    ElMessage.error(preview ? getHashPolicyFailureMessage(preview) : (error.message || '模板保存失败'))
  } finally {
    savingTemplate.value = false
  }
}

const handleDeduplicationFieldsChange = (fields) => {
  deduplicationFields.value = fields
}

const handleFieldParseRulesChange = (rules) => {
  fieldParseRules.value = Array.isArray(rules) ? rules : []
}

const handleHeaderBindingsChange = (bindings) => {
  headerBindings.value = Array.isArray(bindings) ? bindings : []
}

const handleValidationChange = (isValid) => {
  deduplicationFieldsValid.value = isValid
}

const loadTemplates = async () => {
  loading.value = true
  try {
    const params = {}
    if (filters.value.platform) params.platform = filters.value.platform
    if (filters.value.domain) params.dataDomain = filters.value.domain

    const familyData = await api.getTemplateFamilies(params)
    let families = familyData?.families || familyData?.data?.families || []
    if (filters.value.granularity) {
      families = families.filter((item) => item.granularity === filters.value.granularity)
    }

    const hydratedFamilies = await Promise.all(
      families.map(async (family) => {
        try {
          const versionPayload = await api.getTemplateFamilyVersions(family.id)
          const versions = versionPayload?.versions || versionPayload?.data?.versions || []
          const hydratedVersions = await Promise.all(
            versions.map(async (version) => {
              const variantPayload = await api.getTemplateVersionVariants(version.id)
              const variants = variantPayload?.variants || variantPayload?.data?.variants || []
              return { ...version, variants }
            })
          )
          const activeVersionDetail =
            hydratedVersions.find((item) => item.status === 'active') || hydratedVersions[0] || null
          return {
            ...family,
            versions: hydratedVersions,
            activeVersionDetail,
          }
        } catch (error) {
          console.error('加载模板族明细失败:', family.id, error)
          return {
            ...family,
            versions: [],
            activeVersionDetail: null,
          }
        }
      })
    )

    templates.value = hydratedFamilies
  } catch (error) {
    console.error('加载模板族列表失败:', error)
    ElMessage.error(error.message || '加载模板族列表失败')
    templates.value = []
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.value = {
    platform: null,
    domain: null,
    granularity: null,
  }
  loadTemplates()
}

const viewTemplateDetail = (familyId) => {
  const family = templates.value.find((item) => item.id === familyId)
  if (!family) return

  const activeVersion = family.activeVersionDetail
  const versionText = activeVersion
    ? `激活版本: v${activeVersion.version_no}\n变体数: ${activeVersion.variant_count || 0}`
    : '激活版本: 无'
  const dedupText = activeVersion?.deduplication_fields?.length
    ? activeVersion.deduplication_fields.map((field, index) => `  ${index + 1}. ${field}`).join('\n')
    : '  未配置'

  ElMessageBox.alert(
    `模板族: ${family.display_name}\n平台: ${getPlatformLabel(family.platform)}\n数据域: ${family.data_domain}\n粒度: ${family.granularity}\n子类型: ${family.sub_domain || 'N/A'}\n${versionText}\n治理状态: ${family.governance_status}\n\n核心字段:\n${dedupText}`,
    '模板族详情',
    {
      confirmButtonText: '确定',
      dangerouslyUseHTMLString: false,
    }
  )
}

const deleteTemplate = async (templateId) => {
  try {
    await ElMessageBox.confirm('确定要删除这个兼容模板记录吗？删除后无法恢复。', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const result = await api.deleteTemplate(templateId)
    if (result && result.success !== false) {
      ElMessage.success('模板已删除')
      await loadTemplates()
      await loadGovernanceStats()
    } else {
      ElMessage.error(result?.message || '删除模板失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除模板失败:', error)
      ElMessage.error(error.message || '删除模板失败')
    }
  }
}

onMounted(() => {
  loadAvailablePlatforms()
  loadTemplates()
  loadAvailableFiles()
  loadGovernanceStats()
})
</script>

<style scoped>
.data-sync-templates {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.card-header-inline {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.muted-text {
  margin: 0;
  color: #606266;
  font-size: 13px;
}

.family-expand {
  padding: 4px 0 8px;
}

.family-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}
</style>
