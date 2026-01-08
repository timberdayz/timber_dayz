<template>
  <div class="system-logs">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Document /></el-icon>
          系统日志
        </h1>
        <p class="page-subtitle">系统操作日志和审计追踪</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="loadLogs" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新日志
        </el-button>
        <el-button type="success" @click="exportLogs" :loading="exporting">
          <el-icon><Download /></el-icon>
          导出日志
        </el-button>
        <el-button type="warning" @click="clearLogs" :loading="clearing">
          <el-icon><Delete /></el-icon>
          清空日志
        </el-button>
      </div>
    </div>

    <!-- 日志筛选 -->
    <el-card class="filter-card" shadow="hover">
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="日志级别">
          <el-select v-model="filters.level" placeholder="全部级别" clearable @change="handleFilterChange">
            <el-option label="全部级别" value=""></el-option>
            <el-option label="ERROR" value="error"></el-option>
            <el-option label="WARN" value="warn"></el-option>
            <el-option label="INFO" value="info"></el-option>
            <el-option label="DEBUG" value="debug"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="模块">
          <el-select v-model="filters.module" placeholder="全部模块" clearable @change="handleFilterChange">
            <el-option label="全部模块" value=""></el-option>
            <el-option label="系统核心" value="core"></el-option>
            <el-option label="数据采集" value="collection"></el-option>
            <el-option label="数据管理" value="management"></el-option>
            <el-option label="用户管理" value="user"></el-option>
            <el-option label="系统管理" value="system"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            @change="handleFilterChange"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="handleFilterChange">
            <el-icon><Search /></el-icon>
            筛选
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><RefreshLeft /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志列表 -->
    <el-card class="table-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>日志列表</span>
          <el-tag>共 {{ pagination.total }} 条记录</el-tag>
        </div>
      </template>

      <el-table
        :data="logs"
        v-loading="loading"
        stripe
        style="width: 100%"
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <el-table-column prop="created_at" label="时间" width="180" sortable>
          <template #default="scope">
            {{ scope.row.created_at ? new Date(scope.row.created_at).toLocaleString('zh-CN') : '-' }}
          </template>
        </el-table-column>
        
        <el-table-column prop="level" label="级别" width="100" sortable>
          <template #default="scope">
            <el-tag :type="getLogLevelType(scope.row.level)" size="small">
              {{ scope.row.level?.toUpperCase() || 'INFO' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="module" label="模块" width="150"></el-table-column>
        
        <el-table-column prop="message" label="消息" min-width="300" show-overflow-tooltip></el-table-column>
        
        <el-table-column prop="user_id" label="用户ID" width="100">
          <template #default="scope">
            {{ scope.row.user_id || '-' }}
          </template>
        </el-table-column>
        
        <el-table-column prop="ip_address" label="IP地址" width="130">
          <template #default="scope">
            {{ scope.row.ip_address || '-' }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="scope">
            <el-button type="primary" size="small" link @click="viewLogDetail(scope.row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="handlePageChange"
        @current-change="handlePageChange"
      />
    </el-card>

    <!-- 日志详情对话框 -->
    <el-dialog
      v-model="detailDialogVisible"
      title="日志详情"
      width="800px"
    >
      <div class="log-detail" v-if="selectedLog">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="日志ID">{{ selectedLog.id }}</el-descriptions-item>
          <el-descriptions-item label="时间">
            {{ selectedLog.created_at ? new Date(selectedLog.created_at).toLocaleString('zh-CN') : '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="级别">
            <el-tag :type="getLogLevelType(selectedLog.level)" size="small">
              {{ selectedLog.level?.toUpperCase() || 'INFO' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="模块">{{ selectedLog.module || '-' }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ selectedLog.user_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="IP地址">{{ selectedLog.ip_address || '-' }}</el-descriptions-item>
          <el-descriptions-item label="消息" :span="2">
            <div class="log-message">{{ selectedLog.message || '-' }}</div>
          </el-descriptions-item>
          <el-descriptions-item label="详细信息" :span="2" v-if="selectedLog.details">
            <pre class="log-details">{{ JSON.stringify(selectedLog.details, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Refresh, Download, Delete, Search, RefreshLeft } from '@element-plus/icons-vue'
import * as systemAPI from '@/api/system'

// 响应式数据
const loading = ref(false)
const exporting = ref(false)
const clearing = ref(false)
const logs = ref([])
const selectedLog = ref(null)
const detailDialogVisible = ref(false)

// 筛选条件
const filters = ref({
  level: '',
  module: '',
  dateRange: null
})

// 分页
const pagination = ref({
  page: 1,
  pageSize: 20,
  total: 0
})

// 加载日志
const loadLogs = async () => {
  try {
    loading.value = true
    const params = {
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
      level: filters.value.level || undefined,
      module: filters.value.module || undefined
    }
    
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_time = filters.value.dateRange[0]
      params.end_time = filters.value.dateRange[1]
    }
    
    const data = await systemAPI.getSystemLogs(params)
    if (data) {
      logs.value = data.logs || []
      pagination.value.total = data.total || 0
    }
  } catch (error) {
    console.error('加载系统日志失败:', error)
    ElMessage.error(error.message || '加载系统日志失败')
  } finally {
    loading.value = false
  }
}

// 导出日志
const exportLogs = async () => {
  try {
    exporting.value = true
    const params = {
      level: filters.value.level || undefined,
      module: filters.value.module || undefined
    }
    
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_time = filters.value.dateRange[0]
      params.end_time = filters.value.dateRange[1]
    }
    
    const blob = await systemAPI.exportSystemLogs(params)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    link.download = `system_logs_${timestamp}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('日志导出成功')
  } catch (error) {
    console.error('导出日志失败:', error)
    ElMessage.error(error.message || '导出日志失败')
  } finally {
    exporting.value = false
  }
}

// 清空日志
const clearLogs = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要清空所有系统日志吗？此操作不可恢复！',
      '警告',
      {
        type: 'warning',
        confirmButtonText: '确定清空',
        cancelButtonText: '取消'
      }
    )
    clearing.value = true
    await systemAPI.clearSystemLogs()
    ElMessage.success('日志已清空')
    await loadLogs()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('清空日志失败:', error)
      ElMessage.error(error.message || '清空日志失败')
    }
  } finally {
    clearing.value = false
  }
}

// 查看日志详情
const viewLogDetail = async (log) => {
  try {
    if (log.id) {
      const data = await systemAPI.getSystemLogDetail(log.id)
      if (data) {
        selectedLog.value = data
      } else {
        selectedLog.value = log
      }
    } else {
      selectedLog.value = log
    }
    detailDialogVisible.value = true
  } catch (error) {
    console.error('获取日志详情失败:', error)
    // 如果获取详情失败，直接显示当前日志
    selectedLog.value = log
    detailDialogVisible.value = true
  }
}

// 筛选
const handleFilterChange = () => {
  pagination.value.page = 1
  loadLogs()
}

// 重置筛选
const resetFilters = () => {
  filters.value = {
    level: '',
    module: '',
    dateRange: null
  }
  handleFilterChange()
}

// 分页变化
const handlePageChange = () => {
  loadLogs()
}

// 获取日志级别类型
const getLogLevelType = (level) => {
  if (!level) return 'info'
  const upperLevel = level.toUpperCase()
  const typeMap = {
    'ERROR': 'danger',
    'WARN': 'warning',
    'WARNING': 'warning',
    'INFO': 'success',
    'DEBUG': 'info',
    'DEBUGGING': 'info'
  }
  return typeMap[upperLevel] || 'info'
}

// 组件挂载
onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.system-logs {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-content {
  flex: 1;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-subtitle {
  margin: 0;
  opacity: 0.9;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-form {
  padding: 10px 0;
}

.table-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.log-detail {
  padding: 10px 0;
}

.log-message {
  word-break: break-word;
  white-space: pre-wrap;
}

.log-details {
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
  word-break: break-word;
  white-space: pre-wrap;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .system-logs {
    padding: 10px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }
  
  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }
  
  .filter-form {
    flex-direction: column;
  }
}
</style>
