<!--
数据同步 - 同步任务管理页面
v4.6.0新增：独立的数据同步系统
-->

<template>
  <div class="data-sync-tasks erp-page-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>⚙️ 数据同步 - 同步任务</h1>
      <p>查看和管理数据同步任务</p>
    </div>

    <!-- 任务统计 -->
    <el-row :gutter="16" style="margin-bottom: 20px;">
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">进行中</div>
            <div class="stat-value" style="color: #409EFF;">{{ stats.running }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">疑似卡住</div>
            <div class="stat-value" style="color: #E6A23C;">{{ stats.stale_running }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">已完成</div>
            <div class="stat-value" style="color: #67C23A;">{{ stats.completed }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">失败</div>
            <div class="stat-value" style="color: #F56C6C;">{{ stats.failed }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="24" :md="8" :lg="8">
        <el-card>
          <div class="stat-item">
            <div class="stat-label">总计</div>
            <div class="stat-value">{{ stats.total }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 任务列表 -->
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>任务列表</span>
          <el-button @click="loadTasks" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table
        :data="tasks"
        v-loading="loading"
        stripe
        style="width: 100%"
      >
        <el-table-column prop="task_id" label="任务ID" width="200" />
        <el-table-column prop="task_type" label="任务类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="getSyncTaskTypeMeta(row.task_type).tagType">
              {{ getSyncTaskTypeMeta(row.task_type).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_source" label="触发方式" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="getSyncTriggerMeta(row).tagType">
              {{ getSyncTriggerMeta(row).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.isStaleRunning" type="warning" size="small">
              <el-icon><Warning /></el-icon>
              疑似卡住
            </el-tag>
            <el-tag v-else-if="row.status === 'running'" type="primary" size="small">
              <el-icon><Loading /></el-icon>
              进行中
            </el-tag>
            <el-tag v-else-if="row.status === 'completed'" type="success" size="small">
              <el-icon><Check /></el-icon>
              已完成
            </el-tag>
            <el-tag v-else-if="row.status === 'partial_success'" type="warning" size="small">
              <el-icon><Warning /></el-icon>
              部分成功
            </el-tag>
            <el-tag v-else-if="row.status === 'cancelled'" type="info" size="small">
              <el-icon><Close /></el-icon>
              已取消
            </el-tag>
            <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">
              <el-icon><Close /></el-icon>
              失败
            </el-tag>
            <el-tag v-else type="info" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="row.status === 'failed' ? 'exception' : (row.isStaleRunning ? 'warning' : undefined)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="processed_files" label="已处理文件" width="120" />
        <el-table-column prop="total_files" label="总文件数" width="120" />
        <el-table-column prop="heartbeat_at_display" label="心跳时间" width="180" />
        <el-table-column prop="valid_rows" label="成功行数" width="120" />
        <el-table-column prop="quarantined_rows" label="隔离行数" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewTaskDetail(row.task_id)">
              <el-icon><View /></el-icon>
              查看详情
            </el-button>
            <el-button
              v-if="row.status === 'running'"
              size="small"
              type="danger"
              @click="cancelTask(row)"
            >
              <el-icon><Close /></el-icon>
              取消
            </el-button>
            <el-button
              v-if="row.isStaleRunning"
              size="small"
              type="warning"
              @click="recoverTask(row)"
            >
              <el-icon><Warning /></el-icon>
              强制恢复
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailDialogVisible" title="任务详情" width="900px">
      <div v-if="selectedTask" class="task-detail-panel">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务ID">{{ selectedTask.task_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ selectedTask.status }}</el-descriptions-item>
          <el-descriptions-item label="进度">{{ selectedTask.progress }}%</el-descriptions-item>
          <el-descriptions-item label="心跳时间">{{ selectedTask.heartbeat_at_display || '-' }}</el-descriptions-item>
          <el-descriptions-item label="批量参数">
            {{ selectedTask.task_details?.max_files || '-' }} / {{ selectedTask.task_details?.max_concurrent || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="恢复来源">
            {{ selectedTask.task_details?.recovered_by || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="错误摘要" :span="2">
            {{ selectedTask.error_summary || selectedTask.message || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="task-detail-table">
          <h3>最近文件结果</h3>
          <el-table :data="selectedTask.task_details?.files || []" size="small" max-height="320">
            <el-table-column prop="file_name" label="文件名" min-width="260" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column prop="message" label="说明" min-width="280" />
          </el-table>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { getSyncTaskTypeMeta, getSyncTriggerMeta } from '@/domains/data_platform/utils/syncTaskDisplay'

const STALE_WARNING_MINUTES = 15

const loading = ref(false)
const tasks = ref([])
const stats = ref({
  running: 0,
  stale_running: 0,
  completed: 0,
  failed: 0,
  total: 0
})
const detailDialogVisible = ref(false)
const selectedTask = ref(null)

let refreshInterval = null

const normalizeTaskStatus = (task) => {
  const status = String(task.status || task.canonical_status || '').trim()
  if (status === 'processing' || status === 'waiting') return 'running'
  if (status === 'success') return 'completed'
  if (status === 'error') return 'failed'
  return status
}

const formatHeartbeat = (value) => {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { hour12: false })
}

const isHeartbeatStale = (value) => {
  if (!value) return false
  const heartbeatDate = new Date(value)
  if (Number.isNaN(heartbeatDate.getTime())) return false
  const staleMs = STALE_WARNING_MINUTES * 60 * 1000
  return Date.now() - heartbeatDate.getTime() > staleMs
}

const loadTasks = async () => {
  loading.value = true
  try {
    const data = await api.getSyncHistory({ limit: 100 })
    const taskList = Array.isArray(data) ? data : []

    if (!Array.isArray(data)) {
      ElMessage.warning('任务数据格式异常，请刷新重试')
      tasks.value = []
      updateStats()
      return
    }

    tasks.value = taskList.map(task => {
      const normalizedStatus = normalizeTaskStatus(task)
      const progressPercent = Number(task.progress_percent ?? task.file_progress)
      const fallbackProgress = task.total_files > 0
        ? Math.round((task.processed_files / task.total_files) * 100)
        : 0
      const progress = Number.isFinite(progressPercent) ? Math.round(progressPercent) : fallbackProgress
      const heartbeatAt = task.heartbeat_at || task.updated_at || task.started_at || task.start_time
      const staleRunning = normalizedStatus === 'running' && isHeartbeatStale(heartbeatAt)

      return {
        ...task,
        progress,
        status: normalizedStatus,
        progress_percent: Number.isFinite(progressPercent) ? progressPercent : fallbackProgress,
        heartbeat_at: heartbeatAt,
        heartbeat_at_display: formatHeartbeat(heartbeatAt),
        created_at: task.created_at || task.start_time || task.updated_at,
        current_item: task.current_item || task.current_file || '',
        error_summary: task.error_summary || '',
        isStaleRunning: staleRunning,
        quarantined_rows: task.quarantined_rows || 0,
        valid_rows: task.valid_rows || 0,
        processed_files: task.processed_files || 0,
        total_files: task.total_files || 0,
        task_details: task.task_details || {}
      }
    })
    updateStats()
  } catch (error) {
    console.error('加载任务列表失败:', error)
    ElMessage.error(error.message || '加载任务列表失败')
    tasks.value = []
    updateStats()
  } finally {
    loading.value = false
  }
}

const updateStats = () => {
  stats.value = {
    running: tasks.value.filter(t => t.status === 'running' && !t.isStaleRunning).length,
    stale_running: tasks.value.filter(t => t.isStaleRunning).length,
    completed: tasks.value.filter(t => t.status === 'completed').length,
    failed: tasks.value.filter(t => ['failed', 'partial_success', 'cancelled'].includes(t.status)).length,
    total: tasks.value.length
  }
}

const viewTaskDetail = (taskId) => {
  selectedTask.value = tasks.value.find(task => task.task_id === taskId) || null
  detailDialogVisible.value = true
}

const cancelTask = async (task) => {
  try {
    await api.cancelSyncTask(task.task_id)
    ElMessage.success('任务已取消')
    await loadTasks()
  } catch (error) {
    ElMessage.error(error.message || '取消任务失败')
  }
}

const recoverTask = async (task) => {
  try {
    await api.recoverSyncTask(task.task_id)
    ElMessage.success('任务已强制恢复')
    await loadTasks()
  } catch (error) {
    ElMessage.error(error.message || '强制恢复任务失败')
  }
}

onMounted(() => {
  loadTasks()
  refreshInterval = setInterval(() => {
    loadTasks()
  }, 5000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.data-sync-tasks {
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

.stat-item {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 32px;
  font-weight: 600;
}

.task-detail-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.task-detail-table h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}
</style>
