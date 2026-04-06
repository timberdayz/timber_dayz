<!--
数据同步 - 模板管理页面（增强版）
v4.6.0新增：独立的数据同步系统
包含：模板数据治理看板、文件选择、文件详情、数据预览、原始表头字段列表、模板列表
-->

<template>
  <div class="data-sync-templates erp-page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>📚 数据同步 - 模板管理</h1>
      <p>管理表头模板，支持编辑、删除、查看详情</p>
    </div>

    <TemplateGovernancePanel
      :detailed-coverage="detailedCoverage"
      :loading="governanceLoading"
      :active-tab="activeTab"
      :get-platform-label="getPlatformLabel"
      @refresh="loadGovernanceStats"
      @create-missing="handleCreateTemplateForMissing"
      @update-template="handleUpdateTemplate"
      @update:active-tab="activeTab = $event"
    />

    <el-card class="template-builder-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>模板工作区</span>
          <el-button text type="primary" @click="showTemplateBuilder = !showTemplateBuilder">
            {{ showTemplateBuilder ? '收起工作区' : '展开工作区' }}
          </el-button>
        </div>
      </template>
      <p style="margin: 0; color: #606266; font-size: 13px;">
        用于缺少模板时创建模板，或在需要时进入旧版手动预览与保存路径。
      </p>
    </el-card>

    <TemplateBuilderWorkspace
      v-show="showTemplateBuilder && !isCreateWorkbenchVisible"
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
      @platform-change="handlePlatformChange"
      @domain-change="handleDomainChange"
      @file-change="handleFileChange"
      @preview="handlePreview"
      @repreview="handleRepreview"
      @save-template="handleSaveTemplate"
      @deduplication-fields-change="handleDeduplicationFieldsChange"
      @validation-change="handleValidationChange"
      @update:selectedFileId="selectedFileId = $event"
      @update:headerRow="headerRow = $event"
    />

    <!-- 筛选器 -->
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
            <el-option label="流量" value="analytics" />
            <el-option label="服务" value="services" />
            <el-option label="库存" value="inventory" />
          </el-select>
        </el-form-item>
        <el-form-item label="粒度">
          <el-select v-model="filters.granularity" placeholder="全部粒度" clearable style="width: 150px;">
            <el-option label="日度" value="daily" />
            <el-option label="周度" value="weekly" />
            <el-option label="月度" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadTemplates" :loading="loading">
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

    <!-- 模板列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>模板列表（共 {{ templates.length }} 个）</span>
          <el-button @click="loadTemplates" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="templates"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="template_name" label="模板名称" min-width="200" />
        <el-table-column prop="platform" label="平台" width="100">
          <template #default="{ row }">
            {{ getPlatformLabel(row.platform) }}
          </template>
        </el-table-column>
        <el-table-column prop="data_domain" label="数据域" width="100" />
        <el-table-column prop="granularity" label="粒度" width="100" />
        <el-table-column prop="sub_domain" label="子类型" width="120" />
        <el-table-column label="表头行" width="100">
          <template #default="{ row }">
            {{ row.header_row }} (Excel第{{ row.header_row + 1 }}行)
          </template>
        </el-table-column>
        <el-table-column label="字段数量" width="100">
          <template #default="{ row }">
            {{ row.header_columns?.length || row.field_count || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="核心字段" width="120">
          <template #default="{ row }">
            <el-tooltip v-if="row.deduplication_fields && row.deduplication_fields.length > 0" placement="top">
              <template #content>
                <div style="max-width: 300px;">
                  <div style="font-weight: bold; margin-bottom: 5px;">核心字段列表：</div>
                  <div v-for="field in row.deduplication_fields" :key="field" style="margin: 2px 0;">
                    • {{ field }}
                  </div>
                </div>
              </template>
              <el-tag type="primary" size="small">
                {{ row.deduplication_fields.length }}个字段
              </el-tag>
            </el-tooltip>
            <el-tag v-else type="info" size="small">
              未配置
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewTemplateDetail(row.id)">
              <el-icon><View /></el-icon>
              查看详情
            </el-button>
            <el-button size="small" type="danger" @click="deleteTemplate(row.id)">
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
      @save="handleWorkbenchSave"
      @update:visible="isWorkbenchVisible = $event"
      @close="closeTemplateUpdateWorkbench"
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
      :loading-preview="loadingPreview"
      :saving-template="savingTemplate"
      :deduplication-fields="deduplicationFields"
      @platform-change="handlePlatformChange"
      @domain-change="handleDomainChange"
      @file-change="handleFileChange"
      @preview="handlePreview"
      @repreview="handleRepreview"
      @save-template="handleSaveTemplate"
      @deduplication-fields-change="handleDeduplicationFieldsChange"
      @validation-change="handleValidationChange"
      @update:selectedFileId="selectedFileId = $event"
      @update:headerRow="headerRow = $event"
      @update:visible="isCreateWorkbenchVisible = $event"
      @close="closeTemplateCreateWorkbench"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { View, Refresh, Search, Delete, Check, Warning, Document } from '@element-plus/icons-vue'
import api from '@/api'
import TemplateBuilderWorkspace from '@/components/dataSync/TemplateBuilderWorkspace.vue'
import TemplateCreateWorkbenchDrawer from '@/components/dataSync/TemplateCreateWorkbenchDrawer.vue'
import TemplateGovernancePanel from '@/components/dataSync/TemplateGovernancePanel.vue'
import TemplateUpdateWorkbenchDrawer from '@/components/dataSync/TemplateUpdateWorkbenchDrawer.vue'

// 状态
const loading = ref(false)
const loadingPreview = ref(false)
const savingTemplate = ref(false)
const governanceLoading = ref(false)
const isWorkbenchVisible = ref(false)
const isCreateWorkbenchVisible = ref(false)
const showTemplateBuilder = ref(false)
const createWorkbenchContext = ref(null)
const updateWorkbenchContext = ref(null)
const templates = ref([])
const availablePlatforms = ref([])
const filters = ref({
  platform: null,
  domain: null,
  granularity: null
})

// 文件选择相关
const fileFilters = ref({
  platform: null,
  domain: null,
  sub_domain: null,
  granularity: null
})
const availableFiles = ref([])
const selectedFileId = ref(null)
const fileInfo = ref({})
const headerRow = ref(0)
const previewData = ref([])
const headerColumns = ref([])
const sampleData = ref({})
const deduplicationFields = ref([])  // v4.14.0新增：核心字段列表
const deduplicationFieldsValid = ref(false)  // v4.14.0新增：核心字段验证状态

// 数据治理统计
const governanceStats = ref({
  template_coverage: 0,
  missing_templates_count: 0
})
const missingTemplates = ref([])
const detailedCoverage = ref({
  summary: {
    total_combinations: 0,
    covered_count: 0,
    missing_count: 0,
    needs_update_count: 0,
    coverage_percentage: 0
  },
  covered: [],
  missing: [],
  needs_update: []
})
const activeTab = ref('covered')

// 平台标签映射
const getPlatformLabel = (platform) => {
  const labels = {
    'shopee': 'Shopee',
    'tiktok': 'TikTok',
    'amazon': 'Amazon',
    'miaoshou': '妙手ERP'
  }
  return labels[platform] || platform
}

// 子类型选项（根据数据域动态变化）
const availableSubDomains = computed(() => {
  const domain = fileFilters.value.domain
  if (domain === 'services') {
    return [
      { label: 'AI服务数据', value: 'ai_assistant' },
      { label: '人工服务数据', value: 'agent' }
    ]
  } else if (domain === 'inventory') {
    return [
      { label: '全量库存数据', value: 'full_inventory' },
      { label: '店铺库存数据', value: 'shop_inventory' }
    ]
  }
  return []
})

// 计算属性
const headerColumnsWithSamples = computed(() => {
  return headerColumns.value.map(field => ({
    field,
    sample: sampleData.value[field] || null
  }))
})

// 加载可用平台列表
const loadAvailablePlatforms = async () => {
  try {
    const data = await api.getAvailablePlatforms()
    if (data && data.platforms) {
      availablePlatforms.value = data.platforms
    }
  } catch (error) {
    console.error('加载平台列表失败:', error)
  }
}

// 加载数据治理统计
const loadGovernanceStats = async () => {
  governanceLoading.value = true
  try {
    // 加载详细覆盖统计
    const detailedData = await api.getDetailedTemplateCoverage()
    if (detailedData) {
      detailedCoverage.value = detailedData
    }
    
    // 兼容旧API（保留）
    const coverageData = await api.getTemplateCoverage()
    if (coverageData) {
      governanceStats.value = {
        template_coverage: coverageData.template_coverage || 0,
        missing_templates_count: coverageData.missing_templates_count || 0
      }
    }
    
    const missingData = await api.getMissingTemplates()
    if (missingData && Array.isArray(missingData)) {
      missingTemplates.value = missingData
    }
  } catch (error) {
    console.error('加载数据治理统计失败:', error)
    ElMessage.error(error.message || '加载数据治理统计失败')
  } finally {
    governanceLoading.value = false
  }
}

// 为缺少模板的组合创建模板
const closeTemplateUpdateWorkbench = () => {
  isWorkbenchVisible.value = false
}

const closeTemplateCreateWorkbench = () => {
  isCreateWorkbenchVisible.value = false
}

const openTemplateUpdateWorkbench = async (row) => {
  const templateId = row.template_id || row.id || null
  const template = templates.value.find(item => item.id === templateId) || row
  updateWorkbenchContext.value = {
    template,
    row
  }

  if (templateId) {
    try {
      const context = await api.getTemplateUpdateContext(templateId, row.sample_file_id || null)
      updateWorkbenchContext.value = {
        ...updateWorkbenchContext.value,
        context
      }
    } catch (error) {
      console.error('加载模板更新上下文失败:', error)
    }
  }

  isWorkbenchVisible.value = true
}

const handleCreateTemplateForMissing = (row) => {
  showTemplateBuilder.value = true
  createWorkbenchContext.value = row
  isCreateWorkbenchVisible.value = true
  // 设置文件筛选条件
  fileFilters.value.platform = row.platform
  fileFilters.value.domain = row.domain
  fileFilters.value.sub_domain = row.sub_domain === 'N/A' ? null : row.sub_domain
  fileFilters.value.granularity = row.granularity
  
  // 加载文件列表
  loadAvailableFiles()
  
  // 滚动到文件选择区域
  setTimeout(() => {
    const fileSelectionCard = document.querySelector('.file-selection-card')
    if (fileSelectionCard) {
      fileSelectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, 100)
  
  ElMessage.info('已设置筛选条件，请选择文件并创建模板')
}

// 更新需要更新的模板
const handleUpdateTemplate = (row) => {
  showTemplateBuilder.value = true
  openTemplateUpdateWorkbench(row)
  // 设置文件筛选条件
  fileFilters.value.platform = row.platform
  fileFilters.value.domain = row.domain
  fileFilters.value.sub_domain = row.sub_domain === 'N/A' ? null : row.sub_domain
  fileFilters.value.granularity = row.granularity
  
  // 加载文件列表
  loadAvailableFiles()
  
  // 滚动到文件选择区域
  setTimeout(() => {
    const fileSelectionCard = document.querySelector('.file-selection-card')
    if (fileSelectionCard) {
      fileSelectionCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, 100)
  
  ElMessage.info('已设置筛选条件，请选择文件并更新模板')
}

// 加载文件列表（优化：默认显示全部，逐步筛选）
const loadAvailableFiles = async () => {
  try {
    const params = {
      status: 'pending',
      limit: 1000  // 增加限制以显示更多文件
    }
    
    // 逐步添加筛选条件
    if (fileFilters.value.platform) {
      params.platform = fileFilters.value.platform
    }
    if (fileFilters.value.domain) {
      params.domain = fileFilters.value.domain
    }
    if (fileFilters.value.granularity) {
      params.granularity = fileFilters.value.granularity
    }
    if (fileFilters.value.sub_domain) {
      params.sub_domain = fileFilters.value.sub_domain
    }
    
    const data = await api.getDataSyncFiles(params)
    availableFiles.value = data.files || []
  } catch (error) {
    console.error('加载文件列表失败:', error)
    ElMessage.error(error.message || '加载文件列表失败')
  }
}

// 平台变化
const handlePlatformChange = () => {
  fileFilters.value.domain = null
  fileFilters.value.sub_domain = null
  fileFilters.value.granularity = null
  selectedFileId.value = null
  loadAvailableFiles()
}

// 数据域变化
const handleDomainChange = () => {
  fileFilters.value.sub_domain = null
  fileFilters.value.granularity = null
  selectedFileId.value = null
  loadAvailableFiles()
}

// 文件变化
const handleFileChange = async (fileId) => {
  if (!fileId) {
    fileInfo.value = {}
    previewData.value = []
    headerColumns.value = []
    return
  }

  const file = availableFiles.value.find(f => f.id === fileId)
  if (file) {
    fileInfo.value = file
    // 如果有模板，使用模板的表头行
    if (file.has_template && file.template_header_row !== undefined && file.template_header_row !== null) {
      headerRow.value = file.template_header_row
    } else {
      headerRow.value = 0
    }
  }
}

// 监听筛选条件变化
watch([() => fileFilters.value.sub_domain, () => fileFilters.value.granularity], () => {
  loadAvailableFiles()
})

// 预览数据
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
      ElMessage.success('预览成功')
    }
  } catch (error) {
    console.error('预览失败:', error)
    ElMessage.error(error.message || '预览失败')
  } finally {
    loadingPreview.value = false
  }
}

// 重新预览
const handleRepreview = () => {
  handlePreview()
}

// 保存模板
const handleWorkbenchSave = async ({ deduplicationFields: selectedFields }) => {
  const context = updateWorkbenchContext.value?.context
  const template = context?.template

  if (!template || !context?.current_header_columns?.length) {
    ElMessage.warning('当前缺少模板或表头上下文，无法保存')
    return
  }

  savingTemplate.value = true
  try {
    const result = await api.saveTemplate({
      platform: template.platform,
      dataDomain: template.data_domain,
      subDomain: template.sub_domain,
      granularity: template.granularity,
      headerRow: template.header_row ?? 0,
      headerColumns: context.current_header_columns,
      deduplicationFields: selectedFields
    })

    if (result && (result.success || result.template_id)) {
      ElMessage.success(result.message || '模板更新成功')
      isWorkbenchVisible.value = false
      await loadTemplates()
      await loadGovernanceStats()
      await loadAvailableFiles()
    } else {
      ElMessage.error(result?.message || '模板更新失败')
    }
  } catch (error) {
    console.error('模板更新失败:', error)
    ElMessage.error(error.message || '模板更新失败')
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

  // v4.14.0新增：验证核心字段必填
  if (!deduplicationFields.value || deduplicationFields.value.length === 0) {
    ElMessage.warning('请至少选择1个核心字段用于数据去重')
    return
  }

  savingTemplate.value = true
  try {
    const result = await api.saveTemplate({
      platform: fileFilters.value.platform,
      dataDomain: fileFilters.value.domain,  // 使用dataDomain参数名
      subDomain: fileFilters.value.sub_domain,
      granularity: fileFilters.value.granularity,
      headerRow: headerRow.value,
      headerColumns: headerColumns.value,
      deduplicationFields: deduplicationFields.value  // v4.14.0新增：核心字段列表（必填）
    })

    // 检查响应结果
    if (result && (result.success || result.template_id)) {
      ElMessage.success(result.message || '模板保存成功')
      // 刷新模板列表
      await loadTemplates()
      // 刷新数据治理统计
      await loadGovernanceStats()
      // 刷新文件列表以更新模板状态
      await loadAvailableFiles()
      // 重新加载文件信息以更新"可用模板"状态
      if (selectedFileId.value) {
        // 重新查找文件并更新fileInfo
        const file = availableFiles.value.find(f => f.id === selectedFileId.value)
        if (file) {
          fileInfo.value = file
          // 检查模板状态
          if (file.has_template) {
            fileInfo.value.has_template = true
            fileInfo.value.template_name = file.template_name
          }
        }
      }
    } else {
      ElMessage.error(result?.message || '模板保存失败：未知错误')
    }
  } catch (error) {
    console.error('保存模板失败:', error)
    // 显示详细错误信息
    const errorMessage = error.message || error.detail || '保存模板失败'
    ElMessage.error(`模板保存失败: ${errorMessage}`)
  } finally {
    savingTemplate.value = false
  }
}

// v4.14.0新增：处理核心字段变化
const handleDeduplicationFieldsChange = (fields) => {
  deduplicationFields.value = fields
}

// v4.14.0新增：处理验证状态变化
const handleValidationChange = (isValid) => {
  deduplicationFieldsValid.value = isValid
}

// 加载模板列表（优化：全部为空时查询全部）
const loadTemplates = async () => {
  loading.value = true
  try {
    const params = {}
    
    // 只有设置了筛选条件才传递参数（避免传递undefined）
    if (filters.value.platform) {
      params.platform = filters.value.platform
    }
    if (filters.value.domain) {
      params.dataDomain = filters.value.domain
    }
    
    const data = await api.getTemplatesList(params)
    if (data && data.templates) {
      // 如果设置了粒度筛选，在前端过滤
      let filteredTemplates = data.templates
      if (filters.value.granularity) {
        filteredTemplates = filteredTemplates.filter(t => t.granularity === filters.value.granularity)
      }
      templates.value = filteredTemplates
    } else if (Array.isArray(data)) {
      // 兼容直接返回数组的情况
      let filteredTemplates = data
      if (filters.value.granularity) {
        filteredTemplates = filteredTemplates.filter(t => t.granularity === filters.value.granularity)
      }
      templates.value = filteredTemplates
    } else {
      templates.value = []
    }
  } catch (error) {
    console.error('加载模板列表失败:', error)
    ElMessage.error(error.message || '加载模板列表失败')
    templates.value = []
  } finally {
    loading.value = false
  }
}

// 重置筛选器
const resetFilters = () => {
  filters.value = {
    platform: null,
    domain: null,
    granularity: null
  }
  loadTemplates()
}

// 查看模板详情
const viewTemplateDetail = (templateId) => {
  const template = templates.value.find(t => t.id === templateId)
  if (template) {
    // v4.14.0新增：显示核心字段信息
    let detailText = `模板名称: ${template.template_name}\n平台: ${getPlatformLabel(template.platform)}\n数据域: ${template.data_domain}\n粒度: ${template.granularity}\n子类型: ${template.sub_domain || 'N/A'}\n表头行: ${template.header_row}\n字段数量: ${template.field_count || template.header_columns?.length || 0}`
    
    // 添加核心字段信息
    if (template.deduplication_fields && template.deduplication_fields.length > 0) {
      detailText += `\n\n核心字段（${template.deduplication_fields.length}个）:`
      template.deduplication_fields.forEach((field, index) => {
        detailText += `\n  ${index + 1}. ${field}`
      })
      detailText += '\n\n说明: 核心字段用于数据去重，确保每行数据唯一'
    } else {
      detailText += '\n\n核心字段: 未配置（将使用默认配置）'
    }
    
    ElMessageBox.alert(
      detailText,
      '模板详情',
      {
        confirmButtonText: '确定',
        dangerouslyUseHTMLString: false
      }
    )
  }
}

// 删除模板
const deleteTemplate = async (templateId) => {
  try {
    await ElMessageBox.confirm(
      '确定要删除这个模板吗？删除后无法恢复。',
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
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

// 初始化
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

.governance-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #f5f7fa;
  border-radius: 8px;
  flex: 1;
  min-width: 200px;
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 24px;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

/* ⭐ v4.16.0优化：确保页面容器不会超出视口宽度 */
.data-sync-templates {
  max-width: 100%;
  overflow-x: hidden;
}

/* ⭐ v4.16.0优化：确保预览卡片不会超出页面宽度 */
.preview-card {
  max-width: 100%;
  width: 100%;
  overflow: visible; /* 允许子元素显示滚动条 */
}

.preview-card :deep(.el-card__body) {
  max-width: 100%;
  width: 100%;
  overflow: visible; /* 允许子元素显示滚动条 */
  padding: 20px;
  box-sizing: border-box;
}

/* 数据预览表格容器 - 固定宽度，防止页面过宽 */
.preview-table-container {
  width: 100%;
  max-width: 100%;
  height: 500px;
  overflow-x: auto; /* 横向滚动 */
  overflow-y: auto; /* 纵向滚动 */
  border: 1px solid #ebeef5;
  border-radius: 4px;
  box-sizing: border-box;
  /* ⭐ v4.16.0优化：确保容器不会超出页面宽度 */
  position: relative;
  /* 优化滚动条样式 */
  scrollbar-width: thin;
  scrollbar-color: #c1c1c1 #f1f1f1;
}

/* Webkit浏览器滚动条样式 */
.preview-table-container::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

.preview-table-container::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.preview-table-container::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.preview-table-container::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

.preview-table-container .el-table {
  width: max-content !important;
  min-width: 100%;
  /* ⭐ v4.16.0优化：确保表格在容器内正确显示 */
  table-layout: auto;
}

/* 确保表格容器内的表格能够正确显示横向滚动 */
.preview-table-container :deep(.el-table__body-wrapper) {
  overflow-x: auto;
  overflow-y: auto;
}

/* 兼容旧类名 */
.table-scroll-container-wrapper {
  width: 100%;
  max-width: 100%;
  height: 500px;
  overflow-x: auto;
  overflow-y: auto;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  box-sizing: border-box;
}

.table-scroll-container {
  width: max-content;
  min-width: 100%;
}
</style>
