<template>
  <div class="collection-history">
    <!-- 页面标题和统计 -->
    <div class="page-header">
      <h2>采集历史</h2>
      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-value">{{ stats?.total_tasks || 0 }}</span>
          <span class="stat-label">总任务数</span>
        </div>
        <div class="stat-item success">
          <span class="stat-value">{{ stats?.by_status?.completed || 0 }}</span>
          <span class="stat-label">完全成功</span>
        </div>
        <div class="stat-item warning">
          <span class="stat-value">{{ stats?.by_status?.partial_success || 0 }}</span>
          <span class="stat-label">部分成功</span>
        </div>
        <div class="stat-item danger">
          <span class="stat-value">{{ stats?.by_status?.failed || 0 }}</span>
          <span class="stat-label">失败</span>
        </div>
        <div class="stat-item info">
          <span class="stat-value">{{ stats?.success_rate || 0 }}%</span>
          <span class="stat-label">成功率</span>
        </div>
      </div>
    </div>

    <!-- 筛选工具栏 -->
    <div class="filter-bar">
      <el-select 
        v-model="filters.platform" 
        placeholder="平台" 
        clearable
        @change="loadHistory"
      >
        <el-option label="Shopee" value="shopee" />
        <el-option label="TikTok" value="tiktok" />
        <el-option label="妙手ERP" value="miaoshou" />
      </el-select>
      
      <el-select 
        v-model="filters.status" 
        placeholder="状态" 
        clearable
        @change="loadHistory"
      >
        <el-option label="成功" value="completed" />
        <el-option label="部分成功" value="partial_success" />
        <el-option label="失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      
      <el-date-picker
        v-model="filters.date_range"
        type="daterange"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        value-format="YYYY-MM-DD"
        @change="loadHistory"
      />
      
      <el-button @click="loadHistory">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      
      <el-button type="primary" @click="exportHistory">
        <el-icon><Download /></el-icon>
        导出
      </el-button>
    </div>

    <!-- 历史列表 -->
    <el-table 
      v-loading="loading" 
      :data="history" 
      stripe
    >
      <el-table-column label="任务ID" width="140">
        <template #default="{ row }">
          <span class="task-id">{{ row.task_id?.slice(0, 12) }}...</span>
        </template>
      </el-table-column>
      <el-table-column prop="platform" label="平台" width="100">
        <template #default="{ row }">
          <el-tag :type="getPlatformTagType(row.platform)" size="small">
            {{ row.platform }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="account" label="账号" min-width="120" />
      <el-table-column label="数据域" min-width="150">
        <template #default="{ row }">
          <el-tag 
            v-for="domain in row.data_domains" 
            :key="domain"
            size="small"
            style="margin-right: 4px"
          >
            {{ getDomainLabel(domain) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="日期范围" width="180">
        <template #default="{ row }">
          <span v-if="row.date_range">
            {{ row.date_range.start_date }} ~ {{ row.date_range.end_date }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusTagType(row.status)">
            {{ getStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="150">
        <template #default="{ row }">
          <div v-if="row.total_domains" class="domain-progress">
            {{ row.completed_domains?.length || 0 }}/{{ row.total_domains }}个域
            <span v-if="row.failed_domains?.length > 0" class="failed-count">
              ({{ row.failed_domains.length }}个失败)
            </span>
          </div>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="文件数" width="80">
        <template #default="{ row }">
          {{ row.files_collected || 0 }}
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">
          {{ formatDuration(row.duration_seconds) }}
        </template>
      </el-table-column>
      <el-table-column label="完成时间" width="160">
        <template #default="{ row }">
          {{ formatTime(row.updated_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button 
            v-if="row.status === 'failed'"
            size="small" 
            type="primary"
            @click="retryTask(row)"
          >
            重试
          </el-button>
          <el-button 
            size="small"
            @click="showDetails(row)"
          >
            详情
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadHistory"
        @current-change="loadHistory"
      />
    </div>

    <!-- 详情对话框 -->
    <el-dialog 
      v-model="detailDialogVisible" 
      title="任务详情"
      width="700px"
    >
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务ID">
          {{ currentTask?.task_id }}
        </el-descriptions-item>
        <el-descriptions-item label="平台">
          {{ currentTask?.platform }}
        </el-descriptions-item>
        <el-descriptions-item label="账号">
          {{ currentTask?.account }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTagType(currentTask?.status)">
            {{ getStatusLabel(currentTask?.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="数据域" :span="2">
          <el-tag 
            v-for="domain in currentTask?.data_domains" 
            :key="domain"
            size="small"
            style="margin-right: 4px"
          >
            {{ getDomainLabel(domain) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="日期范围">
          {{ currentTask?.date_range?.start_date }} ~ {{ currentTask?.date_range?.end_date }}
        </el-descriptions-item>
        <el-descriptions-item label="粒度">
          {{ currentTask?.granularity }}
        </el-descriptions-item>
        <el-descriptions-item label="采集文件数">
          {{ currentTask?.files_collected || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="耗时">
          {{ formatDuration(currentTask?.duration_seconds) }}
        </el-descriptions-item>
        
        <!-- v4.7.0: 域级别统计 -->
        <el-descriptions-item v-if="currentTask?.total_domains" label="总数据域" :span="2">
          {{ currentTask.total_domains }}个
        </el-descriptions-item>
        <el-descriptions-item v-if="currentTask?.completed_domains" label="成功域" :span="2">
          <el-tag 
            v-for="domain in currentTask.completed_domains" 
            :key="domain"
            type="success"
            size="small"
            style="margin-right: 4px"
          >
            {{ domain }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item v-if="currentTask?.failed_domains?.length > 0" label="失败域" :span="2">
          <div v-for="failure in currentTask.failed_domains" :key="failure.domain" class="failed-domain-item">
            <el-tag type="danger" size="small">{{ failure.domain }}</el-tag>
            <span class="error-text">{{ failure.error }}</span>
          </div>
        </el-descriptions-item>
        
        <el-descriptions-item label="创建时间">
          {{ formatTime(currentTask?.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="完成时间">
          {{ formatTime(currentTask?.updated_at) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="currentTask?.error_message" label="错误信息" :span="2">
          <el-alert type="error" :closable="false">
            {{ currentTask?.error_message }}
          </el-alert>
        </el-descriptions-item>
      </el-descriptions>

      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button 
          v-if="currentTask?.status === 'failed'"
          type="primary" 
          @click="retryTask(currentTask)"
        >
          重试任务
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Download } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'

// 状态
const loading = ref(false)
const history = ref([])
const stats = ref({})
const detailDialogVisible = ref(false)
const currentTask = ref(null)

// 筛选条件
const filters = reactive({
  platform: '',
  status: '',
  date_range: []
})

// 分页
const pagination = reactive({
  page: 1,
  pageSize: 20,
  total: 0
})

// 方法
const loadHistory = async () => {
  loading.value = true
  try {
    const params = {
      limit: pagination.pageSize,
      offset: (pagination.page - 1) * pagination.pageSize
    }
    
    if (filters.platform) params.platform = filters.platform
    if (filters.status) params.status = filters.status
    if (filters.date_range?.length === 2) {
      params.start_date = filters.date_range[0]
      params.end_date = filters.date_range[1]
    }
    
    const result = await collectionApi.getHistory(params)
    history.value = result.items || result
    pagination.total = result.total || result.length
  } catch (error) {
    ElMessage.error('加载历史失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const loadStats = async () => {
  try {
    stats.value = await collectionApi.getStats()
  } catch (error) {
    console.error('Failed to load stats:', error)
  }
}

const showDetails = (row) => {
  currentTask.value = row
  detailDialogVisible.value = true
}

const retryTask = async (row) => {
  try {
    await collectionApi.retryTask(row.task_id)
    ElMessage.success('已创建重试任务')
    detailDialogVisible.value = false
  } catch (error) {
    ElMessage.error('重试失败: ' + error.message)
  }
}

const exportHistory = () => {
  // 导出为CSV
  const headers = ['任务ID', '平台', '账号', '数据域', '状态', '文件数', '耗时', '完成时间']
  const rows = history.value.map(row => [
    row.task_id,
    row.platform,
    row.account,
    row.data_domains?.join(','),
    row.status,
    row.files_collected || 0,
    formatDuration(row.duration_seconds),
    formatTime(row.updated_at)
  ])
  
  const csvContent = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `采集历史_${new Date().toISOString().split('T')[0]}.csv`
  link.click()
  URL.revokeObjectURL(url)
  
  ElMessage.success('导出成功')
}

const getPlatformTagType = (platform) => {
  const types = { shopee: 'warning', tiktok: 'danger', miaoshou: 'success' }
  return types[platform?.toLowerCase()] || 'info'
}

const getDomainLabel = (domain) => {
  const labels = {
    orders: '订单', products: '产品', analytics: '流量',
    finance: '财务', services: '服务', inventory: '库存'
  }
  return labels[domain] || domain
}

const getStatusTagType = (status) => {
  const types = {
    completed: 'success', 
    partial_success: 'warning',  // v4.7.0
    failed: 'danger', 
    cancelled: 'warning'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    completed: '成功', 
    partial_success: '部分成功',  // v4.7.0
    failed: '失败', 
    cancelled: '已取消'
  }
  return labels[status] || status
}

const formatDuration = (seconds) => {
  if (!seconds) return '-'
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分${seconds % 60}秒`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}小时${mins}分`
}

const formatTime = (time) => {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

// 生命周期
onMounted(() => {
  loadHistory()
  loadStats()
})
</script>

<style scoped>
.collection-history {
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0 0 16px 0;
  font-size: 20px;
  font-weight: 600;
}

.stats-row {
  display: flex;
  gap: 24px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 24px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stat-item.success {
  background: #f0f9eb;
}

.stat-item.warning {
  background: #fdf6ec;
}

.stat-item.danger {
  background: #fef0f0;
}

.stat-item.info {
  background: #ecf5ff;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.stat-item.success .stat-value {
  color: #67c23a;
}

.stat-item.warning .stat-value {
  color: #e6a23c;
}

.stat-item.danger .stat-value {
  color: #f56c6c;
}

.stat-item.info .stat-value {
  color: #409eff;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.filter-bar .el-select {
  width: 130px;
}

.task-id {
  font-family: monospace;
  color: #666;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* v4.7.0: 域级别进度显示 */
.domain-progress {
  font-size: 12px;
  color: #606266;
}

.failed-count {
  color: #f56c6c;
  font-weight: 500;
  margin-left: 4px;
}

.failed-domain-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.failed-domain-item:last-child {
  margin-bottom: 0;
}

.error-text {
  font-size: 12px;
  color: #909399;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
