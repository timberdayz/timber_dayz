<template>
  <div class="data-sync-refresh-queue erp-page-container erp-page--admin">
    <PageHeader
      title="刷新队列"
      subtitle="查看 data_ingested 后台刷新队列，排查 pending/running 堵塞并对失败任务执行重试。"
      family="admin"
    />

    <div class="queue-summary">
      <el-card class="summary-card erp-card">
        <div class="summary-label">待执行</div>
        <div class="summary-value summary-pending">{{ stats.pending }}</div>
      </el-card>
      <el-card class="summary-card erp-card">
        <div class="summary-label">执行中</div>
        <div class="summary-value summary-running">{{ stats.running }}</div>
      </el-card>
      <el-card class="summary-card erp-card">
        <div class="summary-label">已完成</div>
        <div class="summary-value summary-completed">{{ stats.completed }}</div>
      </el-card>
      <el-card class="summary-card erp-card">
        <div class="summary-label">失败</div>
        <div class="summary-value summary-failed">{{ stats.failed }}</div>
      </el-card>
      <el-card class="summary-card erp-card">
        <div class="summary-label">总数</div>
        <div class="summary-value">{{ tasks.length }}</div>
      </el-card>
    </div>

    <el-card class="erp-card">
      <div class="toolbar">
        <el-form :inline="true" :model="filters">
          <el-form-item label="状态">
            <el-select
              v-model="filters.status"
              clearable
              placeholder="全部状态"
              class="filter-select"
            >
              <el-option label="Pending" value="pending" />
              <el-option label="Running" value="running" />
              <el-option label="Completed" value="completed" />
              <el-option label="Failed" value="failed" />
            </el-select>
          </el-form-item>
          <el-form-item label="数量">
            <el-select v-model="filters.limit" class="filter-select">
              <el-option :value="50" label="50" />
              <el-option :value="100" label="100" />
              <el-option :value="200" label="200" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-switch
              v-model="autoRefresh"
              inline-prompt
              active-text="自动刷新"
              inactive-text="手动"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="loadTasks" :loading="loading">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <el-table v-loading="loading" :data="tasks" stripe class="queue-table">
        <el-table-column prop="job_id" label="任务ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="pipeline_name" label="Pipeline" width="170" />
        <el-table-column prop="trigger_type" label="触发类型" width="140" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" effect="light">
              {{ formatStatus(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="attempt_count" label="重试次数" width="100" />
        <el-table-column label="目标" min-width="220">
          <template #default="{ row }">
            <span>{{ formatTargets(row.targets_json) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="最近错误" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.last_error || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column prop="started_at" label="开始时间" width="180" />
        <el-table-column prop="finished_at" label="完成时间" width="180" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed'"
              type="warning"
              size="small"
              :loading="retryingIds.includes(row.id)"
              @click="retryTask(row)"
            >
              重试
            </el-button>
            <span v-else class="op-placeholder">-</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'
import PageHeader from '@/components/common/PageHeader.vue'

const loading = ref(false)
const tasks = ref([])
const retryingIds = ref([])
const autoRefresh = ref(true)
const filters = ref({
  status: null,
  limit: 100,
})

let refreshTimer = null

const stats = computed(() => ({
  pending: tasks.value.filter((task) => task.status === 'pending').length,
  running: tasks.value.filter((task) => task.status === 'running').length,
  completed: tasks.value.filter((task) => task.status === 'completed').length,
  failed: tasks.value.filter((task) => task.status === 'failed').length,
}))

const statusTagType = (status) => {
  const mapping = {
    pending: 'warning',
    running: 'primary',
    completed: 'success',
    failed: 'danger',
  }
  return mapping[status] || 'info'
}

const formatStatus = (status) => {
  const mapping = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
  }
  return mapping[status] || status || '-'
}

const formatTargets = (targets) => {
  if (!Array.isArray(targets) || targets.length === 0) {
    return '-'
  }

  const normalized = targets
    .map((item) => {
      if (typeof item === 'string') {
        return item
      }
      if (item && typeof item === 'object') {
        return item.name || item.key || JSON.stringify(item)
      }
      return String(item)
    })
    .filter(Boolean)

  if (normalized.length <= 2) {
    return normalized.join(' / ')
  }

  return `${normalized.slice(0, 2).join(' / ')} 等${normalized.length}项`
}

const loadTasks = async () => {
  loading.value = true
  try {
    const params = {
      limit: filters.value.limit,
    }
    if (filters.value.status) {
      params.status = filters.value.status
    }

    const data = await api.getRefreshQueueTasks(params)
    tasks.value = Array.isArray(data) ? data : []
  } catch (error) {
    console.error('加载 refresh queue 失败:', error)
    ElMessage.error(error.message || '加载刷新队列失败')
  } finally {
    loading.value = false
  }
}

const retryTask = async (row) => {
  retryingIds.value = [...retryingIds.value, row.id]
  try {
    const result = await api.retryRefreshQueueTask(row.id)
    ElMessage.success(result.message || `任务 ${row.job_id} 已重新入队`)
    await loadTasks()
  } catch (error) {
    console.error('重试 refresh queue 任务失败:', error)
    ElMessage.error(error.message || '重试刷新队列任务失败')
  } finally {
    retryingIds.value = retryingIds.value.filter((id) => id !== row.id)
  }
}

const startAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }

  if (!autoRefresh.value) {
    return
  }

  refreshTimer = setInterval(() => {
    loadTasks()
  }, 15000)
}

watch(
  () => autoRefresh.value,
  () => {
    startAutoRefresh()
  }
)

watch(
  () => [filters.value.status, filters.value.limit],
  () => {
    loadTasks()
  }
)

onMounted(async () => {
  await loadTasks()
  startAutoRefresh()
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.data-sync-refresh-queue {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.queue-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
}

.summary-card {
  border-radius: 16px;
}

.summary-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.summary-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 700;
  line-height: 1;
  color: var(--el-text-color-primary);
}

.summary-pending {
  color: #d97706;
}

.summary-running {
  color: #2563eb;
}

.summary-completed {
  color: #059669;
}

.summary-failed {
  color: #dc2626;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-select {
  width: 140px;
}

.queue-table {
  width: 100%;
}

.op-placeholder {
  color: var(--el-text-color-placeholder);
}

@media (max-width: 768px) {
  .summary-value {
    font-size: 24px;
  }
}
</style>
