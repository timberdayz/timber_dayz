<template>
  <div class="cloud-sync-management erp-page-container">
    <div class="page-header">
      <div>
        <h1>云端同步管理</h1>
        <p>管理员专用。集中查看 worker、队列、表级 checkpoint 和受控操作。</p>
      </div>
      <div class="header-actions">
        <el-button @click="refreshAll" :loading="isAnyLoading">刷新</el-button>
      </div>
    </div>

    <div class="health-grid">
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Worker</div>
        <div class="health-value" :class="statusClass(store.workerStatus)">
          {{ store.workerStatus }}
        </div>
        <div class="health-meta">
          {{ formatTime(store.health?.worker?.last_heartbeat_at) || '无心跳' }}
        </div>
      </el-card>
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Tunnel</div>
        <div class="health-value" :class="statusClass(store.health?.tunnel?.status)">
          {{ store.health?.tunnel?.status || 'unknown' }}
        </div>
      </el-card>
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Cloud DB</div>
        <div class="health-value" :class="statusClass(store.health?.cloud_db?.status)">
          {{ store.health?.cloud_db?.status || 'unknown' }}
        </div>
      </el-card>
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Pending</div>
        <div class="health-value">{{ store.pendingTaskCount }}</div>
        <div class="health-meta">oldest {{ formatAge(store.health?.queue?.oldest_pending_age_seconds) }}</div>
      </el-card>
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Running</div>
        <div class="health-value">{{ store.runningTaskCount }}</div>
      </el-card>
      <el-card class="health-card" shadow="hover">
        <div class="health-label">Retry Waiting</div>
        <div class="health-value">{{ store.retryWaitingTaskCount }}</div>
      </el-card>
    </div>

    <div class="main-grid">
      <el-card class="tables-panel" shadow="never">
        <template #header>
          <div class="panel-header">
            <div>
              <strong>表级同步状态</strong>
              <span class="panel-subtitle">按表定位问题和执行操作</span>
            </div>
            <el-input
              v-model="tableSearch"
              clearable
              placeholder="搜索 fact_* 表"
              style="width: 240px"
            />
          </div>
        </template>

        <el-table
          :data="filteredTableStates"
          v-loading="store.loading.tables"
          stripe
          height="460"
          @row-click="selectTable"
        >
          <el-table-column prop="source_table_name" label="Source Table" min-width="240" />
          <el-table-column prop="data_domain" label="Domain" width="120" />
          <el-table-column label="Checkpoint" width="120">
            <template #default="{ row }">{{ row.checkpoint?.last_source_id ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="Task Status" width="130">
            <template #default="{ row }">
              <el-tag :type="tagType(row.latest_task?.status)">{{ row.latest_task?.status || 'none' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Projection" width="130">
            <template #default="{ row }">
              <el-tag :type="tagType(row.projection?.status)">{{ row.projection?.status || 'none' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Last Success" width="180">
            <template #default="{ row }">{{ formatTime(row.last_success_at) || '-' }}</template>
          </el-table-column>
          <el-table-column label="Error" min-width="220">
            <template #default="{ row }">
              <span class="error-text">{{ row.latest_error || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card class="operations-panel" shadow="never">
        <template #header>
          <div class="panel-header">
            <div>
              <strong>受控操作</strong>
              <span class="panel-subtitle">所有操作都只针对单表或单任务</span>
            </div>
          </div>
        </template>

        <el-form label-position="top" :model="formState">
          <el-form-item label="Source Table">
            <el-select
              v-model="formState.sourceTableName"
              filterable
              clearable
              placeholder="选择 source table"
              style="width: 100%"
            >
              <el-option
                v-for="row in store.tableStates"
                :key="row.source_table_name"
                :label="row.source_table_name"
                :value="row.source_table_name"
              />
            </el-select>
          </el-form-item>

          <el-form-item label="Batch Size">
            <el-input-number v-model="formState.batchSize" :min="100" :step="100" style="width: 100%" />
          </el-form-item>

          <div class="operation-actions">
            <el-button type="primary" :loading="store.loading.action" @click="handleTriggerSync">立即同步</el-button>
            <el-button :loading="store.loading.action" @click="handleDryRun">Dry Run</el-button>
            <el-button :loading="store.loading.action" @click="handleRepairCheckpoint">Repair Checkpoint</el-button>
            <el-button :loading="store.loading.action" @click="handleRefreshProjection">Refresh Projection</el-button>
          </div>
        </el-form>

        <div class="selected-summary" v-if="store.selectedTableState">
          <div class="summary-title">当前选中</div>
          <div class="summary-value">{{ store.selectedTableState.source_table_name }}</div>
          <div class="summary-meta">latest task {{ store.selectedTableState.latest_task?.status || 'none' }}</div>
        </div>
      </el-card>
    </div>

    <el-card class="tasks-panel" shadow="never">
      <template #header>
        <div class="panel-header">
          <div>
            <strong>任务队列</strong>
            <span class="panel-subtitle">查看任务明细、重试和取消</span>
          </div>
          <div class="task-filters">
            <el-select
              v-model="store.taskFilters.status"
              clearable
              placeholder="状态筛选"
              style="width: 180px"
              @change="reloadTasks"
            >
              <el-option label="pending" value="pending" />
              <el-option label="running" value="running" />
              <el-option label="retry_waiting" value="retry_waiting" />
              <el-option label="failed" value="failed" />
              <el-option label="partial_success" value="partial_success" />
              <el-option label="completed" value="completed" />
            </el-select>
          </div>
        </div>
      </template>

      <el-table :data="store.tasks" v-loading="store.loading.tasks" stripe height="320">
        <el-table-column prop="job_id" label="Job ID" min-width="220" />
        <el-table-column prop="source_table_name" label="Source Table" min-width="200" />
        <el-table-column label="Status" width="130">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempt_count" label="Attempts" width="90" />
        <el-table-column prop="trigger_source" label="Trigger" width="120" />
        <el-table-column label="Last Error" min-width="220">
          <template #default="{ row }">
            <span class="error-text">{{ row.last_error || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openTaskDetail(row)">详情</el-button>
            <el-button
              link
              type="primary"
              :disabled="row.status !== 'failed' && row.status !== 'retry_waiting'"
              @click="handleRetryTask(row.job_id)"
            >
              重试
            </el-button>
            <el-button
              link
              type="danger"
              :disabled="row.status !== 'running'"
              @click="handleCancelTask(row.job_id)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="events-panel" shadow="never">
      <template #header>
        <div class="panel-header">
          <div>
            <strong>最近事件</strong>
            <span class="panel-subtitle">当前后端还未提供独立事件流时，这里允许为空</span>
          </div>
        </div>
      </template>

      <el-empty v-if="!store.events.length" description="暂无事件数据" />
      <div v-else class="event-list">
        <div v-for="(event, index) in store.events" :key="index" class="event-item">
          <div class="event-title">{{ event.title || event.status || 'event' }}</div>
          <div class="event-meta">{{ formatTime(event.created_at || event.timestamp) || '-' }}</div>
        </div>
      </div>
    </el-card>

    <el-drawer v-model="taskDrawerVisible" title="任务详情" size="42%">
      <el-descriptions v-if="activeTask" :column="1" border>
        <el-descriptions-item label="Job ID">{{ activeTask.job_id }}</el-descriptions-item>
        <el-descriptions-item label="Source Table">{{ activeTask.source_table_name }}</el-descriptions-item>
        <el-descriptions-item label="Status">{{ activeTask.status }}</el-descriptions-item>
        <el-descriptions-item label="Attempts">{{ activeTask.attempt_count }}</el-descriptions-item>
        <el-descriptions-item label="Projection Status">{{ activeTask.projection_status || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Claimed By">{{ activeTask.claimed_by || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Heartbeat">{{ formatTime(activeTask.heartbeat_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Started At">{{ formatTime(activeTask.last_attempt_started_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Finished At">{{ formatTime(activeTask.last_attempt_finished_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Last Error">{{ activeTask.last_error || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useCloudSyncStore } from '@/stores/cloudSync'

const store = useCloudSyncStore()
const tableSearch = ref('')
const taskDrawerVisible = ref(false)
const activeTask = ref(null)
const formState = reactive({
  sourceTableName: '',
  batchSize: 1000,
})

let refreshTimer = null

const isAnyLoading = computed(() => Object.values(store.loading).some(Boolean))
const filteredTableStates = computed(() => {
  const keyword = tableSearch.value.trim().toLowerCase()
  if (!keyword) {
    return store.tableStates
  }
  return store.tableStates.filter((row) => row.source_table_name?.toLowerCase().includes(keyword))
})

function formatTime(value) {
  if (!value) return ''
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

function formatAge(seconds) {
  if (seconds === null || seconds === undefined) return '-'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

function tagType(status) {
  if (['completed', 'healthy', 'reachable', 'running'].includes(status)) return 'success'
  if (['partial_success', 'retry_waiting', 'pending'].includes(status)) return 'warning'
  if (['failed', 'unhealthy', 'unreachable', 'error', 'cancelled'].includes(status)) return 'danger'
  return 'info'
}

function statusClass(status) {
  return `is-${tagType(status)}`
}

async function refreshAll() {
  await store.refreshDashboard({ includeEvents: true, showError: true })
}

function selectTable(row) {
  store.setSelectedTableName(row.source_table_name)
  formState.sourceTableName = row.source_table_name
}

async function reloadTasks() {
  await store.loadTasks({}, true)
}

function ensureTableSelected() {
  if (!formState.sourceTableName) {
    ElMessage.warning('请先选择 source table')
    return false
  }
  return true
}

async function withConfirm(message, handler) {
  await ElMessageBox.confirm(message, '确认操作', {
    type: 'warning',
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  await handler()
}

async function handleTriggerSync() {
  if (!ensureTableSelected()) return
  await withConfirm(`确认立即同步 ${formState.sourceTableName} 吗？`, async () => {
    await store.triggerSync(formState.sourceTableName)
  })
}

async function handleDryRun() {
  if (!ensureTableSelected()) return
  await store.dryRunTable(formState.sourceTableName, { batch_size: formState.batchSize })
}

async function handleRepairCheckpoint() {
  if (!ensureTableSelected()) return
  await withConfirm(`确认修复 ${formState.sourceTableName} 的 checkpoint 吗？`, async () => {
    await store.repairCheckpoint(formState.sourceTableName, { batch_size: formState.batchSize })
  })
}

async function handleRefreshProjection() {
  if (!ensureTableSelected()) return
  await withConfirm(`确认刷新 ${formState.sourceTableName} 的 projection 吗？`, async () => {
    await store.refreshProjection(formState.sourceTableName)
  })
}

async function handleRetryTask(jobId) {
  await withConfirm(`确认重试任务 ${jobId} 吗？`, async () => {
    await store.retryTask(jobId)
  })
}

async function handleCancelTask(jobId) {
  await withConfirm(`确认取消任务 ${jobId} 吗？`, async () => {
    await store.cancelTask(jobId)
  })
}

function openTaskDetail(task) {
  activeTask.value = task
  taskDrawerVisible.value = true
}

onMounted(async () => {
  await refreshAll()
  refreshTimer = window.setInterval(() => {
    store.refreshDashboard({ includeEvents: true }).catch(() => {})
  }, 15000)
})

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.cloud-sync-management {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: #606266;
  font-size: 14px;
}

.health-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.health-card {
  min-height: 120px;
}

.health-label {
  font-size: 12px;
  color: #909399;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.health-value {
  margin-top: 10px;
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}

.health-value.is-success {
  color: #67c23a;
}

.health-value.is-warning {
  color: #e6a23c;
}

.health-value.is-danger {
  color: #f56c6c;
}

.health-meta {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 0.9fr);
  gap: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-subtitle {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.operations-panel {
  height: fit-content;
}

.operation-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.selected-summary {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.summary-title {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  margin-top: 8px;
  font-weight: 600;
  color: #303133;
}

.summary-meta {
  margin-top: 6px;
  color: #606266;
  font-size: 13px;
}

.tasks-panel,
.events-panel,
.tables-panel {
  overflow: hidden;
}

.task-filters {
  display: flex;
  align-items: center;
  gap: 12px;
}

.error-text {
  color: #909399;
}

.event-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.event-item {
  padding: 12px 14px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fafafa;
}

.event-title {
  font-weight: 600;
  color: #303133;
}

.event-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

@media (max-width: 1440px) {
  .health-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1080px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .cloud-sync-management {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }

  .health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .operation-actions {
    grid-template-columns: 1fr;
  }
}
</style>
