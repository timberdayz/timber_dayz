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

    <!-- 模板数据治理看板 -->
    <el-card class="governance-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📊 模板数据治理看板</span>
          <el-button size="small" @click="loadGovernanceStats" :loading="governanceLoading">
            <el-icon><Refresh /></el-icon>
            刷新统计
          </el-button>
        </div>
      </template>
      
      <!-- 统计概览 -->
      <div class="governance-stats">
        <div class="stat-item">
          <div class="stat-icon" style="background: #409EFF;">
            <el-icon><Document /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">模板覆盖度</div>
            <div class="stat-value">{{ detailedCoverage.summary?.coverage_percentage || 0 }}%</div>
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-icon" style="background: #67C23A;">
            <el-icon><Check /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">已覆盖</div>
            <div class="stat-value">{{ detailedCoverage.summary?.covered_count || 0 }}</div>
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-icon" style="background: #F56C6C;">
            <el-icon><Warning /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">缺少模板</div>
            <div class="stat-value">{{ detailedCoverage.summary?.missing_count || 0 }}</div>
          </div>
        </div>
        <div class="stat-item">
          <div class="stat-icon" style="background: #E6A23C;">
            <el-icon><Refresh /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-label">需要更新</div>
            <div class="stat-value">{{ detailedCoverage.summary?.needs_update_count || 0 }}</div>
          </div>
        </div>
      </div>

      <!-- 详细覆盖情况表格 -->
      <el-tabs v-model="activeTab" style="margin-top: 20px;">
        <el-tab-pane label="已覆盖模板" name="covered">
          <el-table :data="detailedCoverage.covered || []" stripe border max-height="400">
            <el-table-column prop="platform" label="平台" width="100">
              <template #default="{ row }">
                {{ getPlatformLabel(row.platform) }}
              </template>
            </el-table-column>
            <el-table-column prop="domain" label="数据域" width="100" />
            <el-table-column prop="sub_domain" label="子类型" width="120" />
            <el-table-column prop="granularity" label="粒度" width="100" />
            <el-table-column prop="template_name" label="模板名称" min-width="200" />
            <el-table-column prop="template_version" label="版本" width="80" />
            <el-table-column prop="file_count" label="文件数" width="100" align="center" />
            <el-table-column label="状态" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.needs_update" type="warning" size="small">
                  <el-icon><Refresh /></el-icon>
                  需要更新
                </el-tag>
                <el-tag v-else type="success" size="small">
                  <el-icon><Check /></el-icon>
                  正常
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="update_reason" label="更新原因" min-width="200" show-overflow-tooltip />
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="缺少模板" name="missing">
          <el-table :data="detailedCoverage.missing || []" stripe border max-height="400">
            <el-table-column prop="platform" label="平台" width="100">
              <template #default="{ row }">
                {{ getPlatformLabel(row.platform) }}
              </template>
            </el-table-column>
            <el-table-column prop="domain" label="数据域" width="100" />
            <el-table-column prop="sub_domain" label="子类型" width="120" />
            <el-table-column prop="granularity" label="粒度" width="100" />
            <el-table-column prop="file_count" label="待同步文件数" width="120" align="center" />
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="handleCreateTemplateForMissing(row)">
                  <el-icon><Plus /></el-icon>
                  创建模板
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        
        <el-tab-pane label="需要更新" name="needs_update">
          <el-table :data="detailedCoverage.needs_update || []" stripe border max-height="400">
            <el-table-column prop="platform" label="平台" width="100">
              <template #default="{ row }">
                {{ getPlatformLabel(row.platform) }}
              </template>
            </el-table-column>
            <el-table-column prop="domain" label="数据域" width="100" />
            <el-table-column prop="sub_domain" label="子类型" width="120" />
            <el-table-column prop="granularity" label="粒度" width="100" />
            <el-table-column prop="template_name" label="模板名称" min-width="200" />
            <el-table-column prop="file_count" label="文件数" width="100" align="center" />
            <el-table-column prop="update_reason" label="更新原因" min-width="200" show-overflow-tooltip />
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="warning" @click="handleUpdateTemplate(row)">
                  <el-icon><Edit /></el-icon>
                  更新模板
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 文件选择区域 -->
    <el-card class="file-selection-card" style="margin-bottom: 20px;">
      <template #header>
        <span>📁 文件选择</span>
      </template>
      <el-form :inline="true" :model="fileFilters">
        <el-form-item label="选择平台">
          <el-select v-model="fileFilters.platform" placeholder="全部平台" clearable style="width: 150px;" @change="handlePlatformChange">
            <el-option
              v-for="platform in availablePlatforms"
              :key="platform"
              :label="getPlatformLabel(platform)"
              :value="platform"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择数据域">
          <el-select v-model="fileFilters.domain" placeholder="全部数据域" clearable style="width: 150px;" @change="handleDomainChange">
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
          <el-select v-model="selectedFileId" placeholder="请选择文件" clearable filterable style="width: 400px;" @change="handleFileChange">
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

    <!-- 文件详情区域 -->
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

    <!-- 数据预览区域 -->
    <el-card v-if="selectedFileId" class="preview-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📊 数据预览 ({{ previewData.length }} 行 × {{ headerColumns.length }} 列)</span>
          <div>
            <el-input-number
              v-model="headerRow"
              :min="0"
              :max="10"
              :step="1"
              controls-position="right"
              style="width: 150px; margin-right: 10px;"
            />
            <span style="margin-right: 10px;">表头行 (0=Excel第1行)</span>
            <el-button type="primary" @click="handlePreview" :loading="loadingPreview">
              <el-icon><View /></el-icon>
              预览数据
            </el-button>
            <el-button v-if="previewData.length > 0" @click="handleRepreview" :loading="loadingPreview">
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

    <!-- 原始表头字段列表区域 -->
    <el-card v-if="headerColumns.length > 0" class="header-columns-card" style="margin-bottom: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>📋 原始表头字段列表 ({{ headerColumns.length }} 个字段)</span>
          <el-button type="primary" @click="handleSaveTemplate" :loading="savingTemplate" :disabled="headerColumns.length === 0 || deduplicationFields.length === 0">
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

    <!-- 核心字段选择器（v4.14.0新增） -->
    <DeduplicationFieldsSelector
      v-if="headerColumns.length > 0"
      :available-fields="headerColumns"
      :data-domain="fileFilters.domain"
      :sub-domain="fileFilters.sub_domain"
      @update:selectedFields="handleDeduplicationFieldsChange"
      @validation-change="handleValidationChange"
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { View, Refresh, Search, Delete, Check, Warning, Document, QuestionFilled, Plus, Edit } from '@element-plus/icons-vue'
import api from '@/api'
import DeduplicationFieldsSelector from '@/components/DeduplicationFieldsSelector.vue'

// 状态
const loading = ref(false)
const loadingPreview = ref(false)
const savingTemplate = ref(false)
const governanceLoading = ref(false)
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
const handleCreateTemplateForMissing = (row) => {
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
