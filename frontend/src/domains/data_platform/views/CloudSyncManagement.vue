<template>
  <div class="cloud-sync-page erp-page-container">
    <section class="hero-panel">
      <div class="hero-copy">
        <p class="hero-kicker">B类云端追平控制台</p>
        <h1>让云端 B 类数据始终保持最新状态</h1>
        <p class="hero-subtitle">
          采集环境完成本地清洗入库后，系统会自动追平云端。你只需要关注整体是否健康、是否有积压或异常，以及现在最应该做什么。
        </p>
      </div>
      <div class="hero-actions">
        <el-button plain :loading="isAnyLoading" @click="refreshAll">刷新状态</el-button>
      </div>
    </section>

    <el-alert
      v-if="store.exceptionTaskCount > 0"
      class="warning-banner"
      type="error"
      :closable="false"
      show-icon
      :title="`当前有 ${store.exceptionTaskCount} 个异常任务待处理`"
      description="建议先查看最近错误摘要；如果是短暂环境问题，可直接重试异常任务。"
    />

    <section class="overview-grid">
      <el-card
        v-for="card in statusCards"
        :key="card.key"
        shadow="hover"
        class="status-card"
      >
        <div class="card-label">{{ card.label }}</div>
        <div class="card-value" :class="card.tone">{{ card.value }}</div>
        <div class="card-meta">{{ card.meta }}</div>
      </el-card>
    </section>

    <section class="primary-grid">
      <el-card shadow="never" class="action-panel">
        <template #header>
          <div class="section-header">
            <div>
              <strong>主操作</strong>
              <span class="section-subtitle">首页只保留管理员日常最常用的三类动作</span>
            </div>
          </div>
        </template>

        <div class="action-block">
          <div class="action-title">立即追平到最新</div>
          <div class="action-desc">
            立即检查本地与云端差异，只对未同步部分执行追平。
          </div>
          <el-button type="primary" :loading="store.loading.action" @click="handleSyncNow">
            立即追平到最新
          </el-button>
        </div>

        <div class="action-block">
          <div class="action-title">{{ store.autoSyncEnabled ? '暂停自动追平' : '恢复自动追平' }}</div>
          <div class="action-desc">
            {{
              store.autoSyncEnabled
                ? '暂停期间系统继续记录待同步内容，恢复后会自动补齐。'
                : '恢复后系统将继续自动追平暂停期间积压的内容。'
            }}
          </div>
          <el-button
            :type="store.autoSyncEnabled ? 'warning' : 'success'"
            :loading="store.loading.action"
            @click="handleToggleAutoSync"
          >
            {{ store.autoSyncEnabled ? '暂停自动追平' : '恢复自动追平' }}
          </el-button>
        </div>

        <div class="action-block">
          <div class="action-title">重试异常任务</div>
          <div class="action-desc">
            对当前失败或部分成功的任务执行统一重试。
          </div>
          <el-button
            plain
            :disabled="store.exceptionTaskCount === 0"
            :loading="store.loading.action"
            @click="handleRetryFailed"
          >
            重试异常任务
          </el-button>
        </div>
      </el-card>

      <el-card shadow="never" class="runtime-panel">
        <template #header>
          <div class="section-header">
            <div>
              <strong>当前运行</strong>
              <span class="section-subtitle">关注系统现在做到哪一步，以及下一步建议</span>
            </div>
          </div>
        </template>

        <div class="runtime-list">
          <div class="runtime-item">
            <span class="runtime-label">当前状态</span>
            <span class="runtime-value">{{ runtimeStatusText }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">当前任务</span>
            <span class="runtime-value">{{ store.runtime?.current_job_id || '无' }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">当前表</span>
            <span class="runtime-value">{{ store.runtime?.current_source_table_name || '无' }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">运行中任务数</span>
            <span class="runtime-value">{{ store.runtime?.active_task_count ?? 0 }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">最近心跳</span>
            <span class="runtime-value">{{ formatTime(lastHeartbeatAt) || '暂无' }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">最近错误</span>
            <span class="runtime-value runtime-error">{{ latestErrorText }}</span>
          </div>
        </div>

        <el-alert
          class="guidance-alert"
          type="info"
          :closable="false"
          show-icon
          :title="operationalHint.title"
          :description="operationalHint.description"
        />
      </el-card>
    </section>

    <el-card shadow="never" class="history-panel">
      <template #header>
        <div class="section-header">
          <div>
            <strong>最近记录</strong>
            <span class="section-subtitle">查看最近自动、手动和补偿追平结果</span>
          </div>
        </div>
      </template>

      <el-empty
        v-if="showHistoryEmpty"
        description="当前尚无追平历史。首次执行追平后，这里会显示运行记录。"
      />

      <el-table v-else :data="store.history" v-loading="store.loading.summary" stripe>
        <el-table-column prop="job_id" label="任务编号" min-width="180" />
        <el-table-column prop="source_table_name" label="来源表" min-width="180" />
        <el-table-column prop="trigger_source" label="触发方式" width="120">
          <template #default="{ row }">{{ formatTrigger(row.trigger_source) }}</template>
        </el-table-column>
        <el-table-column prop="result_status" label="结果" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.result_status)">{{ formatResultStatus(row.result_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.started_at) || '-' }}</template>
        </el-table-column>
        <el-table-column label="结束时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.finished_at) || '-' }}</template>
        </el-table-column>
        <el-table-column prop="last_error" label="错误摘要" min-width="260">
          <template #default="{ row }">{{ row.last_error || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-collapse v-model="activePanels" class="diagnostics-collapse">
      <el-collapse-item name="diagnostics" title="高级诊断">
        <div class="diagnostics-intro">
          以下能力仅用于排障，不作为首页主路径操作入口。
        </div>

        <div class="diagnostics-grid">
          <el-card shadow="never" class="diagnostics-panel">
            <template #header>
              <div class="section-header">
                <div>
                  <strong>表级状态</strong>
                  <span class="section-subtitle">查看表级 checkpoint、最新任务和错误</span>
                </div>
              </div>
            </template>

            <el-input
              v-model="tableSearch"
              clearable
              placeholder="搜索来源表"
              class="diagnostics-search"
            />

            <el-empty
              v-if="!store.loading.diagnostics && filteredTableStates.length === 0"
              description="当前没有表级诊断数据。"
            />

            <el-table
              v-else
              :data="filteredTableStates"
              v-loading="store.loading.diagnostics"
              stripe
              height="360"
              @row-click="selectTable"
            >
              <el-table-column prop="source_table_name" label="来源表" min-width="220" />
              <el-table-column prop="data_domain" label="数据域" width="100" />
              <el-table-column label="同步点" width="110">
                <template #default="{ row }">{{ row.checkpoint?.last_source_id ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="任务状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="statusTag(row.latest_task?.status)">
                    {{ formatResultStatus(row.latest_task?.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="最近错误" min-width="220">
                <template #default="{ row }">{{ row.latest_error || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" class="diagnostics-panel">
            <template #header>
              <div class="section-header">
                <div>
                  <strong>单表诊断动作</strong>
                  <span class="section-subtitle">仅在排障时使用</span>
                </div>
              </div>
            </template>

            <el-form label-position="top">
              <el-form-item label="来源表">
                <el-select
                  v-model="selectedTableName"
                  filterable
                  clearable
                  placeholder="选择需要诊断的来源表"
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

              <div class="diag-actions">
                <el-button :loading="store.loading.action" @click="handleDryRun">模拟执行</el-button>
                <el-button :loading="store.loading.action" @click="handleRepairCheckpoint">
                  修复同步点
                </el-button>
                <el-button :loading="store.loading.action" @click="handleRefreshProjection">
                  刷新投影
                </el-button>
              </div>
            </el-form>

            <div v-if="store.selectedTableState" class="selected-summary">
              <div class="summary-label">当前选中</div>
              <div class="summary-value">{{ store.selectedTableState.source_table_name }}</div>
              <div class="summary-meta">
                最近任务：{{ formatResultStatus(store.selectedTableState.latest_task?.status) }}
              </div>
            </div>
          </el-card>
        </div>

        <el-card shadow="never" class="tasks-panel">
          <template #header>
            <div class="section-header">
              <div>
                <strong>诊断任务队列</strong>
                <span class="section-subtitle">查看失败、部分成功和运行中任务</span>
              </div>
            </div>
          </template>

          <el-empty
            v-if="!store.loading.diagnostics && store.tasks.length === 0"
            description="当前没有诊断任务数据。"
          />

          <el-table v-else :data="store.tasks" v-loading="store.loading.diagnostics" stripe height="320">
            <el-table-column prop="job_id" label="任务编号" min-width="180" />
            <el-table-column prop="source_table_name" label="来源表" min-width="180" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)">{{ formatResultStatus(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="attempt_count" label="次数" width="80" />
            <el-table-column prop="last_error" label="最近错误" min-width="220" />
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTaskDetail(row)">详情</el-button>
                <el-button
                  link
                  type="primary"
                  :disabled="!canRetryTask(row.status)"
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

        <el-card shadow="never" class="events-panel">
          <template #header>
            <div class="section-header">
              <div>
                <strong>最近事件</strong>
                <span class="section-subtitle">从任务状态推导出的最近追平事件</span>
              </div>
            </div>
          </template>

          <el-empty
            v-if="!store.loading.events && store.events.length === 0"
            description="当前没有可展示的追平事件。"
          />

          <el-timeline v-else class="event-timeline">
            <el-timeline-item
              v-for="event in store.events"
              :key="`${event.job_id || 'event'}-${event.timestamp}`"
              :timestamp="formatTime(event.timestamp)"
              :type="timelineType(event.status)"
            >
              <div class="event-title">{{ formatEventTitle(event) }}</div>
              <div class="event-meta">{{ event.source_table_name || '-' }}</div>
              <div v-if="event.last_error" class="event-error">{{ event.last_error }}</div>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </el-collapse-item>
    </el-collapse>

    <el-drawer v-model="taskDrawerVisible" title="任务详情" size="42%">
      <el-descriptions v-if="activeTask" :column="1" border>
        <el-descriptions-item label="任务编号">{{ activeTask.job_id }}</el-descriptions-item>
        <el-descriptions-item label="来源表">{{ activeTask.source_table_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ formatResultStatus(activeTask.status) }}</el-descriptions-item>
        <el-descriptions-item label="触发方式">{{ formatTrigger(activeTask.trigger_source) }}</el-descriptions-item>
        <el-descriptions-item label="尝试次数">{{ activeTask.attempt_count ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="执行者">{{ activeTask.claimed_by || '-' }}</el-descriptions-item>
        <el-descriptions-item label="最近心跳">
          {{ formatTime(activeTask.heartbeat_at) || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="开始时间">
          {{ formatTime(activeTask.last_attempt_started_at) || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="结束时间">
          {{ formatTime(activeTask.last_attempt_finished_at) || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="下次重试">
          {{ formatTime(activeTask.next_retry_at) || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="投影状态">
          {{ formatResultStatus(activeTask.projection_status) }}
        </el-descriptions-item>
        <el-descriptions-item label="最近错误">{{ activeTask.last_error || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useCloudSyncStore } from '@/stores/cloudSync'

const store = useCloudSyncStore()
const activePanels = ref([])
const tableSearch = ref('')
const taskDrawerVisible = ref(false)
const activeTask = ref(null)
const selectedTableName = ref('')

let refreshTimer = null

const isAnyLoading = computed(() => Object.values(store.loading).some(Boolean))
const lastHeartbeatAt = computed(
  () => store.runtime?.last_heartbeat_at || store.health?.worker?.last_heartbeat_at || null,
)
const latestErrorText = computed(
  () => store.runtime?.last_error || store.overview?.latest_error || '无',
)
const runtimeStatusText = computed(() =>
  store.runtimeRunning ? '正在追平' : formatCatchUpStatus(store.catchUpStatus),
)
const showHistoryEmpty = computed(() => !store.loading.summary && store.history.length === 0)
const filteredTableStates = computed(() => {
  const keyword = tableSearch.value.trim().toLowerCase()
  if (!keyword) return store.tableStates
  return store.tableStates.filter((row) =>
    row.source_table_name?.toLowerCase().includes(keyword),
  )
})

const operationalHint = computed(() => {
  if (store.workerSummaryStatus === 'not_configured') {
    return {
      title: '当前未启用正式追平 Worker',
      description: '请先检查采集机环境变量、backend-collector 角色配置以及云库地址。',
    }
  }
  if (store.health?.cloud_db?.status === 'unreachable') {
    return {
      title: '云库当前不可达',
      description: '请优先检查 SSH 隧道、云库网络连通性和 CLOUD_DATABASE_URL 配置。',
    }
  }
  if (store.exceptionTaskCount > 0) {
    return {
      title: '当前存在异常任务',
      description: '可先查看最近错误摘要；若判断为环境瞬时异常，可直接重试异常任务。',
    }
  }
  if (store.pendingTaskCount > 0 || store.retryWaitingTaskCount > 0) {
    return {
      title: '当前存在积压任务',
      description: '请确认 Worker 心跳正常；若不是处理中，可手动执行“立即追平到最新”。',
    }
  }
  if (!store.hasHistory) {
    return {
      title: '当前尚无追平历史',
      description: '首次执行追平后，首页会开始展示运行记录和最近成功时间。',
    }
  }
  return {
    title: '当前整体状态正常',
    description: '系统会继续自动追平后续入库数据；如需立刻补齐，可执行“立即追平到最新”。',
  }
})

const statusCards = computed(() => [
  {
    key: 'auto-sync',
    label: '自动追平',
    value: store.autoSyncEnabled ? '已开启' : '已暂停',
    meta: store.autoSyncEnabled
      ? '采集完成并入库后，系统会自动追平云端。'
      : '暂停期间继续记录待同步内容，恢复后自动补齐。',
    tone: store.autoSyncEnabled ? 'is-success' : 'is-warning',
  },
  {
    key: 'worker',
    label: 'Worker 状态',
    value: formatWorkerStatus(store.workerSummaryStatus),
    meta: formatTime(lastHeartbeatAt.value) || '暂无心跳记录',
    tone: statusTone(store.workerSummaryStatus),
  },
  {
    key: 'cloud-db',
    label: '云库连接',
    value: formatConnectionStatus(store.health?.cloud_db?.status),
    meta: store.health?.cloud_db?.error || '连接状态正常',
    tone: statusTone(store.health?.cloud_db?.status),
  },
  {
    key: 'catch-up',
    label: '当前追平状态',
    value: formatCatchUpStatus(store.catchUpStatus),
    meta: `待处理 ${store.pendingTaskCount} / 运行中 ${store.runningTaskCount}`,
    tone: statusTone(store.catchUpStatus),
  },
  {
    key: 'exceptions',
    label: '异常任务',
    value: String(store.exceptionTaskCount),
    meta: `失败 ${store.failedTaskCount} / 部分成功 ${store.partialSuccessTaskCount}`,
    tone: store.exceptionTaskCount > 0 ? 'is-danger' : 'is-success',
  },
  {
    key: 'last-success',
    label: '最近一次成功追平',
    value: formatTime(store.lastSuccessAt) || '暂无记录',
    meta: store.hasHistory ? `最近错误：${latestErrorText.value}` : '当前尚无追平历史',
    tone: '',
  },
])

function formatTime(value) {
  if (!value) return ''
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

function formatWorkerStatus(status) {
  const mapping = {
    running: '运行中',
    stopped: '已停止',
    not_started: '未启动',
    not_configured: '未配置',
    error: '异常',
  }
  return mapping[status] || '未知'
}

function formatConnectionStatus(status) {
  const mapping = {
    reachable: '连接正常',
    healthy: '连接正常',
    unreachable: '连接异常',
    unhealthy: '连接异常',
    unknown: '未知',
  }
  return mapping[status] || '未知'
}

function formatCatchUpStatus(status) {
  const mapping = {
    up_to_date: '已追平最新',
    catching_up: '正在追平',
    backlog: '存在积压',
    degraded: '存在异常',
  }
  return mapping[status] || '未知'
}

function formatResultStatus(status) {
  const mapping = {
    pending: '待处理',
    running: '执行中',
    retry_waiting: '等待重试',
    failed: '失败',
    partial_success: '部分成功',
    completed: '成功',
    cancelled: '已取消',
    submitted: '已提交',
    updated: '已更新',
    repaired: '已修复',
    skipped: '已跳过',
  }
  return mapping[status] || status || '-'
}

function formatEventTitle(event) {
  const statusText = formatResultStatus(event?.status)
  if (event?.source_table_name && statusText !== '-') {
    return `${event.source_table_name} ${statusText}`
  }
  return statusText !== '-' ? statusText : (event?.title || '-')
}

function formatTrigger(trigger) {
  const mapping = {
    auto_ingest: '自动',
    manual: '手动',
    repair: '修复',
    cloud_sync_admin: '管理台',
  }
  return mapping[trigger] || trigger || '-'
}

function statusTag(status) {
  if (['completed', 'running', 'updated', 'submitted', 'repaired'].includes(status)) return 'success'
  if (['pending', 'retry_waiting', 'partial_success', 'skipped', 'catching_up', 'backlog'].includes(status)) {
    return 'warning'
  }
  if (['failed', 'cancelled', 'degraded', 'unreachable', 'unhealthy', 'error', 'not_configured'].includes(status)) {
    return 'danger'
  }
  return 'info'
}

function statusTone(status) {
  if (['running', 'reachable', 'healthy', 'up_to_date'].includes(status)) return 'is-success'
  if (['backlog', 'catching_up', 'not_started', 'unknown'].includes(status)) return 'is-warning'
  if (['failed', 'degraded', 'unreachable', 'unhealthy', 'error', 'not_configured'].includes(status)) {
    return 'is-danger'
  }
  return ''
}

function timelineType(status) {
  if (['completed', 'submitted', 'updated', 'repaired'].includes(status)) return 'success'
  if (['running', 'pending', 'retry_waiting', 'partial_success'].includes(status)) return 'warning'
  if (['failed', 'cancelled'].includes(status)) return 'danger'
  return 'info'
}

function canRetryTask(status) {
  return ['failed', 'retry_waiting', 'partial_success'].includes(status)
}

async function refreshAll() {
  await store.refreshDashboard({ includeEvents: true, includeDiagnostics: true, showError: true })
}

function selectTable(row) {
  selectedTableName.value = row.source_table_name
  store.setSelectedTableName(row.source_table_name)
}

function openTaskDetail(task) {
  activeTask.value = task
  taskDrawerVisible.value = true
}

function ensureTableSelected() {
  if (!selectedTableName.value) {
    ElMessage.warning('请先选择需要诊断的来源表')
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

async function handleSyncNow() {
  await withConfirm(
    '将立即检查本地与云端 B 类数据差异，并对未同步部分执行追平。是否继续？',
    async () => {
      await store.syncNow()
    },
  )
}

async function handleToggleAutoSync() {
  const enabled = !store.autoSyncEnabled
  const message = enabled
    ? '确认恢复自动追平吗？恢复后将自动补齐暂停期间积压的内容。'
    : '确认暂停自动追平吗？暂停期间仍会记录待同步内容。'
  await withConfirm(message, async () => {
    await store.toggleAutoSync(enabled)
  })
}

async function handleRetryFailed() {
  await withConfirm('将对当前失败或部分成功任务执行统一重试。是否继续？', async () => {
    await store.retryFailed()
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

async function handleDryRun() {
  if (!ensureTableSelected()) return
  await withConfirm(`将对 ${selectedTableName.value} 执行模拟追平，不写入云端。是否继续？`, async () => {
    await store.dryRunTable(selectedTableName.value)
  })
}

async function handleRepairCheckpoint() {
  if (!ensureTableSelected()) return
  await withConfirm(`将重置 ${selectedTableName.value} 的同步点。是否继续？`, async () => {
    await store.repairCheckpoint(selectedTableName.value)
  })
}

async function handleRefreshProjection() {
  if (!ensureTableSelected()) return
  await withConfirm(`将刷新 ${selectedTableName.value} 关联投影。是否继续？`, async () => {
    await store.refreshProjection(selectedTableName.value)
  })
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer)
  refreshTimer = setInterval(() => {
    store.refreshDashboard({ includeEvents: false, includeDiagnostics: false, showError: false })
  }, 15000)
}

watch(selectedTableName, (value) => {
  store.setSelectedTableName(value)
})

onMounted(async () => {
  await store.refreshDashboard({ includeEvents: true, includeDiagnostics: true, showError: true })
  startAutoRefresh()
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.cloud-sync-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 24px 28px;
  border-radius: 20px;
  background:
    linear-gradient(135deg, rgba(13, 84, 182, 0.08), rgba(13, 84, 182, 0.02)),
    linear-gradient(180deg, #ffffff, #f6f9fd);
  border: 1px solid rgba(13, 84, 182, 0.12);
}

.hero-copy h1 {
  margin: 6px 0 10px;
  font-size: 28px;
  line-height: 1.2;
  color: #16304d;
}

.hero-kicker {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0d54b6;
  text-transform: uppercase;
}

.hero-subtitle {
  max-width: 760px;
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #54657c;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
}

.warning-banner {
  margin-top: -4px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 16px;
}

.status-card {
  border-radius: 18px;
}

.card-label {
  font-size: 13px;
  color: #62748a;
}

.card-value {
  margin-top: 10px;
  font-size: 24px;
  font-weight: 700;
  color: #20354d;
}

.card-meta {
  margin-top: 10px;
  min-height: 42px;
  font-size: 13px;
  line-height: 1.6;
  color: #60738a;
}

.is-success {
  color: #0b8f55;
}

.is-warning {
  color: #b7791f;
}

.is-danger {
  color: #c53030;
}

.primary-grid,
.diagnostics-grid {
  display: grid;
  grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
  gap: 16px;
}

.action-panel,
.runtime-panel,
.history-panel,
.diagnostics-panel,
.tasks-panel,
.events-panel {
  border-radius: 18px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-subtitle {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #77879a;
}

.action-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.action-block {
  padding: 18px;
  border-radius: 16px;
  background: #f8fbff;
  border: 1px solid #dbe8f6;
}

.action-title {
  font-size: 16px;
  font-weight: 700;
  color: #20354d;
}

.action-desc {
  margin: 8px 0 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #60738a;
}

.runtime-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 18px;
  margin-bottom: 16px;
}

.runtime-item {
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8fbff;
  border: 1px solid #dbe8f6;
}

.runtime-label {
  display: block;
  font-size: 12px;
  color: #708399;
}

.runtime-value {
  display: block;
  margin-top: 6px;
  word-break: break-word;
  font-size: 14px;
  font-weight: 600;
  color: #20354d;
}

.runtime-error {
  color: #c53030;
}

.guidance-alert {
  margin-top: 8px;
}

.diagnostics-collapse {
  border-radius: 18px;
  overflow: hidden;
  background: #fff;
}

.diagnostics-intro {
  margin-bottom: 16px;
  font-size: 13px;
  color: #60738a;
}

.diagnostics-search {
  margin-bottom: 12px;
}

.diag-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.selected-summary {
  margin-top: 18px;
  padding: 16px;
  border-radius: 14px;
  background: #f8fbff;
  border: 1px solid #dbe8f6;
}

.summary-label {
  font-size: 12px;
  color: #708399;
}

.summary-value {
  margin-top: 6px;
  font-size: 15px;
  font-weight: 700;
  color: #20354d;
}

.summary-meta {
  margin-top: 8px;
  font-size: 13px;
  color: #60738a;
}

.event-timeline {
  padding-top: 8px;
}

.event-title {
  font-weight: 700;
  color: #20354d;
}

.event-meta {
  margin-top: 4px;
  font-size: 13px;
  color: #60738a;
}

.event-error {
  margin-top: 6px;
  font-size: 13px;
  color: #c53030;
}

@media (max-width: 1200px) {
  .primary-grid,
  .diagnostics-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .hero-panel {
    flex-direction: column;
    padding: 20px;
  }

  .hero-copy h1 {
    font-size: 24px;
  }

  .runtime-list {
    grid-template-columns: 1fr;
  }
}
</style>
