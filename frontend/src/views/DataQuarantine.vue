<template>
  <div class="data-quarantine-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2 class="page-title">📊 数据隔离区</h2>
      <p class="page-subtitle">查看和处理因数据质量问题被隔离的记录</p>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-label">总隔离数据</div>
            <div class="stats-value">{{ stats.total }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-label">今日新增</div>
            <div class="stats-value">{{ stats.today || 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-label">待处理</div>
            <div class="stats-value pending">{{ stats.total }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stats-card">
          <div class="stats-content">
            <div class="stats-label">已处理</div>
            <div class="stats-value success">0</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选和操作 -->
    <el-card class="filter-card">
      <el-row :gutter="20">
        <el-col :span="6">
          <el-select
            v-model="filters.platform"
            placeholder="选择平台"
            clearable
            @change="handleFilterChange"
            style="width: 100%"
          >
            <el-option label="全部平台" value="" />
            <el-option label="Shopee" value="shopee" />
            <el-option label="妙手ERP" value="miaoshou" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
          </el-select>
        </el-col>
        
        <el-col :span="6">
          <el-select
            v-model="filters.data_domain"
            placeholder="选择数据域"
            clearable
            @change="handleFilterChange"
            style="width: 100%"
          >
            <el-option label="全部数据域" value="" />
            <el-option label="订单数据" value="orders" />
            <el-option label="商品数据" value="products" />
            <el-option label="流量数据" value="analytics" />
            <el-option label="服务数据" value="services" />
          </el-select>
        </el-col>
        
        <el-col :span="6">
          <el-select
            v-model="filters.error_type"
            placeholder="选择错误类型"
            clearable
            @change="handleFilterChange"
            style="width: 100%"
          >
            <el-option label="全部错误类型" value="" />
            <el-option label="验证错误" value="validation_error" />
            <el-option label="数据缺失" value="missing_required_field" />
            <el-option label="格式错误" value="format_error" />
            <el-option label="数据全0" value="all_zero_data" />
          </el-select>
        </el-col>
        
        <el-col :span="6">
          <el-button type="primary" @click="loadQuarantineList" :loading="loading">
            刷新数据
          </el-button>
          <el-button 
            type="warning" 
            @click="batchReprocess" 
            :disabled="selectedIds.length === 0"
          >
            批量重新处理 ({{ selectedIds.length }})
          </el-button>
          <el-button 
            type="danger" 
            @click="batchDelete" 
            :disabled="selectedIds.length === 0"
          >
            批量删除 ({{ selectedIds.length }})
          </el-button>
          <el-button 
            type="danger" 
            @click="clearAll" 
            :disabled="stats.total === 0"
            style="margin-left: 10px"
          >
            一键全部清理 ({{ stats.total }})
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 视图切换 -->
    <el-card class="view-switch-card">
      <el-radio-group v-model="viewMode" @change="handleViewModeChange">
        <el-radio-button label="files">按文件查看</el-radio-button>
        <el-radio-button label="rows">按行查看</el-radio-button>
      </el-radio-group>
      
      <el-button 
        v-if="viewMode === 'rows' && currentFileId"
        type="primary" 
        size="small"
        @click="viewMode = 'files'; currentFileId = null"
        style="margin-left: 10px"
      >
        返回文件列表
      </el-button>
    </el-card>

    <!-- 文件列表视图（v4.6.1新增） -->
    <el-card v-if="viewMode === 'files'" class="table-card">
      <el-empty 
        v-if="!loading && fileList.length === 0" 
        description="暂无隔离数据，说明数据质量良好！"
        :image-size="120"
      >
        <template #description>
          <div style="text-align: center; color: #909399;">
            <p style="font-size: 16px; margin-bottom: 10px;">✅ 暂无隔离数据</p>
            <p style="font-size: 14px;">数据隔离区用于存储因数据质量问题被隔离的记录。</p>
            <p style="font-size: 14px;">当数据验证失败、必填字段缺失或数据格式错误时，相关记录会被自动隔离到这里。</p>
          </div>
        </template>
      </el-empty>
      <el-table
        v-else
        :data="fileList"
        v-loading="loading"
        style="width: 100%"
      >
        <el-table-column prop="file_name" label="文件名" min-width="250">
          <template #default="scope">
            <el-tooltip :content="scope.row.file_name" placement="top">
              <span class="file-name">{{ scope.row.file_name }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column prop="platform_code" label="平台" width="100">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.platform_code }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="data_domain" label="数据域" width="100">
          <template #default="scope">
            <el-tag type="info" size="small">{{ scope.row.data_domain }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="error_count" label="错误数量" width="120">
          <template #default="scope">
            <el-tag type="danger" size="small">{{ scope.row.error_count }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="error_types" label="错误类型" min-width="200">
          <template #default="scope">
            <el-tag 
              v-for="(count, type) in scope.row.error_types" 
              :key="type"
              type="warning" 
              size="small"
              style="margin-right: 5px"
            >
              {{ type }}: {{ count }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="首次错误时间" width="160">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button 
              type="primary" 
              size="small" 
              @click="viewFileRows(scope.row.file_id)"
            >
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 数据行列表视图 -->
    <el-card v-if="viewMode === 'rows'" class="table-card">
      <el-empty 
        v-if="!loading && quarantineList.length === 0" 
        description="暂无隔离数据，说明数据质量良好！"
        :image-size="120"
      >
        <template #description>
          <div style="text-align: center; color: #909399;">
            <p style="font-size: 16px; margin-bottom: 10px;">✅ 暂无隔离数据</p>
            <p style="font-size: 14px;">数据隔离区用于存储因数据质量问题被隔离的记录。</p>
            <p style="font-size: 14px;">当数据验证失败、必填字段缺失或数据格式错误时，相关记录会被自动隔离到这里。</p>
          </div>
        </template>
      </el-empty>
      <el-table
        v-else
        :data="quarantineList"
        v-loading="loading"
        @selection-change="handleSelectionChange"
        style="width: 100%"
      >
        <el-table-column type="selection" width="55" />
        
        <el-table-column prop="id" label="ID" width="80" />
        
        <el-table-column prop="file_name" label="文件名" min-width="200">
          <template #default="scope">
            <el-tooltip :content="scope.row.file_name" placement="top">
              <span class="file-name">{{ scope.row.file_name }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column prop="platform_code" label="平台" width="100">
          <template #default="scope">
            <el-tag size="small">{{ scope.row.platform_code }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="data_domain" label="数据域" width="100">
          <template #default="scope">
            <el-tag type="info" size="small">{{ scope.row.data_domain }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="row_index" label="行号" width="80" />
        
        <el-table-column prop="error_type" label="错误类型" width="150">
          <template #default="scope">
            <el-tag type="warning" size="small">{{ scope.row.error_type }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="error_message" label="错误信息" min-width="200">
          <template #default="scope">
            <el-tooltip :content="scope.row.error_message" placement="top">
              <span class="error-message">{{ scope.row.error_message }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="隔离时间" width="160">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="scope">
            <el-button 
              type="primary" 
              size="small" 
              @click="viewDetail(scope.row)"
            >
              查看详情
            </el-button>
            <el-button 
              type="success" 
              size="small" 
              @click="reprocessSingle(scope.row.id)"
            >
              重新处理
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :page-sizes="[10, 20, 50, 100, 200]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handlePageSizeChange"
          @current-change="loadRowList"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="隔离数据详情"
      width="70%"
      :close-on-click-modal="false"
    >
      <div v-if="currentDetail" class="detail-container">
        <!-- 基本信息 -->
        <el-descriptions title="基本信息" :column="2" border>
          <el-descriptions-item label="隔离ID">{{ currentDetail.id }}</el-descriptions-item>
          <el-descriptions-item label="文件名">{{ currentDetail.file_name }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ currentDetail.platform_code }}</el-descriptions-item>
          <el-descriptions-item label="数据域">{{ currentDetail.data_domain }}</el-descriptions-item>
          <el-descriptions-item label="行号">{{ currentDetail.row_index }}</el-descriptions-item>
          <el-descriptions-item label="隔离时间">{{ formatDate(currentDetail.created_at) }}</el-descriptions-item>
        </el-descriptions>

        <!-- 错误信息 -->
        <div class="error-section">
          <h4>错误信息</h4>
          <el-alert
            :title="currentDetail.error_type"
            type="error"
            :description="currentDetail.error_message"
            :closable="false"
          />
        </div>

        <!-- 验证错误详情 -->
        <div v-if="currentDetail.validation_errors && Object.keys(currentDetail.validation_errors).length > 0" class="validation-section">
          <h4>验证错误详情</h4>
          <el-table :data="validationErrorsList" border size="small">
            <el-table-column prop="field" label="字段" width="150" />
            <el-table-column prop="error" label="错误" />
          </el-table>
        </div>

        <!-- 原始数据 -->
        <div class="raw-data-section">
          <h4>原始数据</h4>
          <pre class="raw-data-pre">{{ JSON.stringify(currentDetail.raw_data, null, 2) }}</pre>
        </div>
      </div>

      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="reprocessFromDetail">重新处理</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

// 数据定义
const loading = ref(false)
const quarantineList = ref([])
const selectedIds = ref([])
const detailDialogVisible = ref(false)
const currentDetail = ref(null)

// 统计数据
const stats = reactive({
  total: 0,
  today: 0,
  by_platform: {},
  by_error_type: {},
  by_data_domain: {}
})

// 筛选条件
const filters = reactive({
  platform: '',
  data_domain: '',
  error_type: ''
})

// 分页
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

// ⭐ v4.6.1新增：视图模式（文件列表 or 数据行列表）
const viewMode = ref('files')  // 'files' | 'rows'
const currentFileId = ref(null)  // 当前查看的文件ID
const fileList = ref([])  // 文件列表
const filePagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

// 验证错误列表（用于表格显示）
const validationErrorsList = computed(() => {
  if (!currentDetail.value || !currentDetail.value.validation_errors) {
    return []
  }
  
  return Object.entries(currentDetail.value.validation_errors).map(([field, error]) => ({
    field,
    error
  }))
})

// ==================== 方法 ====================

/**
 * 加载隔离数据列表
 */
async function loadQuarantineList() {
  loading.value = true
  
  try {
    // ⭐ v4.6.1修复：根据viewMode选择不同的API
    if (viewMode.value === 'files') {
      await loadFileList()
    } else {
      await loadRowList()
    }
  } catch (error) {
    console.error('Failed to load quarantine data:', error)
    ElMessage.error(`加载隔离数据失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

/**
 * 加载文件列表（v4.6.1新增）
 */
async function loadFileList() {
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    if (filters.data_domain) params.data_domain = filters.data_domain
    
    const response = await api._get('/data-quarantine/files', { params })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      fileList.value = response.data || response || []
      filePagination.total = response.total || 0
    } else {
      ElMessage.error('加载文件列表失败')
    }
  } catch (error) {
    console.error('Failed to load file list:', error)
    ElMessage.error(`加载文件列表失败：${error.message}`)
  }
}

/**
 * 加载数据行列表（v4.6.1修复分页）
 */
async function loadRowList() {
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size  // ⭐ v4.6.1修复：确保使用正确的page_size
    }
    
    if (currentFileId.value) {
      // 查看指定文件的数据行
      const response = await api._get(`/data-quarantine/files/${currentFileId.value}/rows`, { params })
      // 响应拦截器已提取data字段，直接使用
      if (response) {
        quarantineList.value = response.data || response || []
        pagination.total = response.total || 0
      }
    } else {
      // 查看所有数据行
      if (filters.platform) params.platform = filters.platform
      if (filters.data_domain) params.data_domain = filters.data_domain
      if (filters.error_type) params.error_type = filters.error_type
      
      const response = await api._get('/data-quarantine/list', { params })
      
      // 响应拦截器已提取data字段，直接使用
      if (response) {
        quarantineList.value = response.data || response || []
        pagination.total = response.total || 0
      } else {
        ElMessage.error('加载隔离数据失败')
      }
    }
  } catch (error) {
    console.error('Failed to load row list:', error)
    ElMessage.error(`加载数据行列表失败：${error.message}`)
  }
}

/**
 * 查看文件的数据行（v4.6.1新增）
 */
async function viewFileRows(fileId) {
  currentFileId.value = fileId
  viewMode.value = 'rows'
  pagination.page = 1
  await loadRowList()
}

/**
 * 视图模式切换（v4.6.1新增）
 */
async function handleViewModeChange() {
  if (viewMode.value === 'files') {
    currentFileId.value = null
    await loadFileList()
  } else {
    await loadRowList()
  }
}

/**
 * 加载统计数据
 */
async function loadStats() {
  try {
    const params = {}
    if (filters.platform) params.platform = filters.platform
    
    const response = await api._get('/data-quarantine/stats', { params })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      Object.assign(stats, response)
    }
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

/**
 * 查看详情
 */
async function viewDetail(row) {
  try {
    const response = await api._get(`/data-quarantine/detail/${row.id}`)
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      currentDetail.value = response
      detailDialogVisible.value = true
    } else {
      ElMessage.error('加载详情失败')
    }
  } catch (error) {
    console.error('Failed to load detail:', error)
    ElMessage.error(`加载详情失败：${error.message}`)
  }
}

/**
 * 重新处理单条数据
 */
async function reprocessSingle(quarantineId) {
  try {
    await ElMessageBox.confirm(
      '确认重新处理这条隔离数据？系统将尝试重新入库。',
      '确认重新处理',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await api._post('/data-quarantine/reprocess', {
      quarantine_ids: [quarantineId],
      corrections: null
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(`重新处理成功：成功${response.succeeded || 0}条，失败${response.failed || 0}条`)
      // 刷新列表
      await loadQuarantineList()
      await loadStats()
    } else {
      ElMessage.error('重新处理失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Reprocess failed:', error)
      ElMessage.error(`重新处理失败：${error.message}`)
    }
  }
}

/**
 * 从详情对话框重新处理
 */
async function reprocessFromDetail() {
  if (!currentDetail.value) return
  
  detailDialogVisible.value = false
  await reprocessSingle(currentDetail.value.id)
}

/**
 * 批量重新处理
 */
async function batchReprocess() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要处理的数据')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确认批量重新处理${selectedIds.value.length}条隔离数据？`,
      '确认批量处理',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const response = await api._post('/data-quarantine/reprocess', {
      quarantine_ids: selectedIds.value,
      corrections: null
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(`批量处理完成：成功${response.succeeded || 0}条，失败${response.failed || 0}条`)
      selectedIds.value = []
      // 刷新列表
      await loadQuarantineList()
      await loadStats()
    } else {
      ElMessage.error('批量处理失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Batch reprocess failed:', error)
      ElMessage.error(`批量处理失败：${error.message}`)
    }
  }
}

/**
 * 批量删除隔离数据（v4.6.1新增）
 */
async function batchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的数据')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确认永久删除${selectedIds.value.length}条隔离数据？\n此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'error',
        dangerouslyUseHTMLString: false
      }
    )
    
    const response = await api._post('/data-quarantine/delete', {
      quarantine_ids: selectedIds.value
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(`成功删除${response.deleted || 0}条隔离数据`)
      selectedIds.value = []
      // 刷新列表
      await loadQuarantineList()
      await loadStats()
    } else {
      ElMessage.error('批量删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Batch delete failed:', error)
      ElMessage.error(`批量删除失败：${error.message}`)
    }
  }
}

/**
 * 一键全部清理（v4.6.1新增）
 */
async function clearAll() {
  try {
    await ElMessageBox.confirm(
      `确认永久删除所有${stats.total}条隔离数据？\n此操作不可恢复！`,
      '确认一键全部清理',
      {
        confirmButtonText: '确认清理',
        cancelButtonText: '取消',
        type: 'error',
        dangerouslyUseHTMLString: false
      }
    )
    
    const response = await api._post('/data-quarantine/delete', {
      all: true
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      ElMessage.success(`成功清理${response.deleted || 0}条隔离数据`)
      selectedIds.value = []
      // 刷新列表和统计
      await loadStats()
      if (viewMode.value === 'files') {
        await loadFileList()
      } else {
        await loadRowList()
      }
    } else {
      ElMessage.error('一键清理失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Clear all failed:', error)
      ElMessage.error(`一键清理失败：${error.message}`)
    }
  }
}

/**
 * 处理表格选择变化
 */
function handleSelectionChange(selection) {
  selectedIds.value = selection.map(item => item.id)
}

/**
 * 处理分页大小变化（v4.6.1修复分页问题）
 */
async function handlePageSizeChange() {
  pagination.page = 1  // 重置到第一页
  await loadRowList()
}

/**
 * 处理筛选条件变化（v4.6.1新增）
 */
async function handleFilterChange() {
  pagination.page = 1  // 重置到第一页
  await loadQuarantineList()
  await loadStats()  // 刷新统计
}

/**
 * 格式化日期
 */
function formatDate(dateStr) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

// ==================== 生命周期 ====================

onMounted(async () => {
  // ⭐ v4.6.1修复：初始化时根据viewMode加载对应数据
  if (viewMode.value === 'files') {
    await loadFileList()
  } else {
    await loadRowList()
  }
  await loadStats()
})
</script>

<style scoped>
.data-quarantine-container {
  padding: 20px;
  background: #f5f7fa;
  min-height: calc(100vh - 60px);
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.page-subtitle {
  margin: 8px 0 0;
  font-size: 14px;
  color: #909399;
}

.stats-row {
  margin-bottom: 20px;
}

.stats-card {
  text-align: center;
}

.stats-content {
  padding: 10px 0;
}

.stats-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stats-value {
  font-size: 32px;
  font-weight: 600;
  color: #606266;
}

.stats-value.pending {
  color: #e6a23c;
}

.stats-value.success {
  color: #67c23a;
}

.filter-card {
  margin-bottom: 20px;
}

.table-card {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  max-width: 100%;
}

.error-message {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  max-width: 100%;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.detail-container {
  max-height: 600px;
  overflow-y: auto;
}

.error-section,
.validation-section,
.raw-data-section {
  margin-top: 20px;
}

.error-section h4,
.validation-section h4,
.raw-data-section h4 {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.raw-data-pre {
  background: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 400px;
  overflow: auto;
}

.view-switch-card {
  margin-bottom: 20px;
}
</style>



