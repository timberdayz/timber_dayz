<template>
  <div class="catch-up-console erp-page-container">
    <section class="hero-panel">
      <div class="hero-copy">
        <p class="hero-kicker">B类数据云端追平控制台</p>
        <h1>让云端 B 类数据始终保持最新状态</h1>
        <p class="hero-subtitle">
          采集环境完成本地清洗入库后，系统将自动追平云端。你只需要关注整体是否最新、是否有异常，以及现在该做什么。
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
      :title="`当前有 ${store.exceptionTaskCount} 个异常同步任务待处理`"
      description="建议先查看最近错误摘要，必要时使用“重试异常任务”或进入高级诊断定位具体原因。"
    />

    <section class="overview-grid">
      <el-card shadow="hover" class="status-card">
        <div class="card-label">自动同步</div>
        <div class="card-value" :class="store.autoSyncEnabled ? 'is-success' : 'is-warning'">
          {{ store.autoSyncEnabled ? '已开启' : '已暂停' }}
        </div>
        <div class="card-meta">
          {{ store.autoSyncEnabled ? '采集完成并完成本地清洗入库后自动追平云端' : '暂停期间继续记录待同步内容，恢复后自动补齐' }}
        </div>
      </el-card>

      <el-card shadow="hover" class="status-card">
        <div class="card-label">同步服务</div>
        <div class="card-value" :class="statusTone(store.workerSummaryStatus)">
          {{ formatWorkerStatus(store.workerSummaryStatus) }}
        </div>
        <div class="card-meta">
          {{ formatTime(store.runtime?.last_heartbeat_at || store.health?.worker?.last_heartbeat_at) || '暂无心跳' }}
        </div>
      </el-card>

      <el-card shadow="hover" class="status-card">
        <div class="card-label">云端连接</div>
        <div class="card-value" :class="statusTone(store.health?.cloud_db?.status)">
          {{ formatConnectionStatus(store.health?.cloud_db?.status) }}
        </div>
        <div class="card-meta">
          {{ store.health?.cloud_db?.error || '连接状态正常' }}
        </div>
      </el-card>

      <el-card shadow="hover" class="status-card">
        <div class="card-label">云端状态</div>
        <div class="card-value" :class="statusTone(store.catchUpStatus)">
          {{ formatCatchUpStatus(store.catchUpStatus) }}
        </div>
        <div class="card-meta">
          待处理 {{ store.pendingTaskCount }} / 执行中 {{ store.runningTaskCount }}
        </div>
      </el-card>

      <el-card shadow="hover" class="status-card">
        <div class="card-label">异常任务</div>
        <div class="card-value" :class="store.exceptionTaskCount > 0 ? 'is-danger' : 'is-success'">
          {{ store.exceptionTaskCount }}
        </div>
        <div class="card-meta">
          失败 {{ store.failedTaskCount }} / 部分成功 {{ store.partialSuccessTaskCount }}
        </div>
      </el-card>

      <el-card shadow="hover" class="status-card">
        <div class="card-label">上次成功同步</div>
        <div class="card-value">
          {{ formatTime(store.lastSuccessAt) || '暂无记录' }}
        </div>
        <div class="card-meta">
          最近错误：{{ store.overview?.latest_error || '无' }}
        </div>
      </el-card>
    </section>

    <section class="primary-grid">
      <el-card shadow="never" class="action-panel">
        <template #header>
          <div class="section-header">
            <div>
              <strong>主操作</strong>
              <span class="section-subtitle">以整体追平为主，不再要求按单表执行首页操作</span>
            </div>
          </div>
        </template>

        <div class="action-block">
          <div class="action-title">立即同步到最新</div>
          <div class="action-desc">立即检查本地与云端差异，并补齐未同步内容。</div>
          <el-button type="primary" :loading="store.loading.action" @click="handleSyncNow">立即同步到最新</el-button>
        </div>

        <div class="action-block">
          <div class="action-title">自动同步</div>
          <div class="action-desc">
            {{ store.autoSyncEnabled ? '当前已开启。采集完成并完成本地清洗入库后，系统会自动追平云端。' : '当前已暂停。暂停期间继续记录待同步内容，恢复后自动补齐。' }}
          </div>
          <el-button
            :type="store.autoSyncEnabled ? 'warning' : 'success'"
            :loading="store.loading.action"
            @click="handleToggleAutoSync"
          >
            {{ store.autoSyncEnabled ? '暂停自动同步' : '恢复自动同步' }}
          </el-button>
        </div>

        <div class="action-block">
          <div class="action-title">异常恢复</div>
          <div class="action-desc">对当前失败或部分成功任务执行统一重试。</div>
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
              <strong>最近同步状态</strong>
              <span class="section-subtitle">关注现在做到哪一步，而不是先看单表细节</span>
            </div>
          </div>
        </template>

        <div class="runtime-list">
          <div class="runtime-item">
            <span class="runtime-label">当前状态</span>
            <span class="runtime-value">{{ store.runtimeRunning ? '正在追平' : formatCatchUpStatus(store.catchUpStatus) }}</span>
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
            <span class="runtime-label">执行中任务数</span>
            <span class="runtime-value">{{ store.runtime?.active_task_count ?? 0 }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">最近心跳</span>
            <span class="runtime-value">{{ formatTime(store.runtime?.last_heartbeat_at || store.health?.worker?.last_heartbeat_at) || '暂无' }}</span>
          </div>
          <div class="runtime-item">
            <span class="runtime-label">最近错误摘要</span>
            <span class="runtime-value runtime-error">{{ store.runtime?.last_error || store.overview?.latest_error || '无' }}</span>
          </div>
        </div>
      </el-card>
    </section>

    <el-card shadow="never" class="history-panel">
      <template #header>
        <div class="section-header">
          <div>
            <strong>最近同步记录</strong>
            <span class="section-subtitle">查看最近几次自动、手动和补偿同步结果</span>
          </div>
        </div>
      </template>

      <el-table :data="store.history" v-loading="store.loading.summary" stripe>
        <el-table-column prop="job_id" label="任务编号" min-width="180" />
        <el-table-column prop="source_table_name" label="来源表" min-width="180" />
        <el-table-column prop="trigger_source" label="发起方式" width="110">
          <template #default="{ row }">{{ formatTrigger(row.trigger_source) }}</template>
        </el-table-column>
        <el-table-column prop="result_status" label="结果" width="110">
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
        <el-table-column prop="last_error" label="错误摘要" min-width="240">
          <template #default="{ row }">{{ row.last_error || '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-collapse v-model="activePanels" class="diagnostics-collapse">
      <el-collapse-item name="diagnostics" title="高级诊断">
        <div class="diagnostics-grid">
          <el-card shadow="never" class="diagnostics-panel">
            <template #header>
              <div class="section-header">
                <div>
                  <strong>表级状态</strong>
                  <span class="section-subtitle">仅用于故障定位，不作为首页主操作入口</span>
                </div>
              </div>
            </template>

            <el-input
              v-model="tableSearch"
              clearable
              placeholder="搜索表名"
              class="diagnostics-search"
            />

            <el-table
              :data="filteredTableStates"
              v-loading="store.loading.diagnostics"
              stripe
              height="360"
              @row-click="selectTable"
            >
              <el-table-column prop="source_table_name" label="来源表" min-width="220" />
              <el-table-column prop="data_domain" label="数据域" width="100" />
              <el-table-column label="同步点" width="100">
                <template #default="{ row }">{{ row.checkpoint?.last_source_id ?? '-' }}</template>
              </el-table-column>
              <el-table-column label="任务状态" width="110">
                <template #default="{ row }">
                  <el-tag :type="statusTag(row.latest_task?.status)">{{ formatResultStatus(row.latest_task?.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="最近错误" min-width="200">
                <template #default="{ row }">{{ row.latest_error || '-' }}</template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" class="diagnostics-panel">
            <template #header>
              <div class="section-header">
                <div>
                  <strong>单表诊断操作</strong>
                  <span class="section-subtitle">仅在排障时使用</span>
                </div>
              </div>
            </template>

            <el-form label-position="top">
              <el-form-item label="来源表">
                <el-select
                  v-model="formState.sourceTableName"
                  filterable
                  clearable
                  placeholder="选择需诊断的表"
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
                <el-button :loading="store.loading.action" @click="handleRepairCheckpoint">修复同步点</el-button>
                <el-button :loading="store.loading.action" @click="handleRefreshProjection">刷新投影</el-button>
              </div>
            </el-form>

            <div class="selected-summary" v-if="store.selectedTableState">
              <div class="summary-label">当前选中</div>
              <div class="summary-value">{{ store.selectedTableState.source_table_name }}</div>
              <div class="summary-meta">最近任务：{{ formatResultStatus(store.selectedTableState.latest_task?.status) }}</div>
            </div>
          </el-card>
        </div>

        <el-card shadow="never" class="tasks-panel">
          <template #header>
            <div class="section-header">
              <div>
                <strong>诊断任务队列</strong>
                <span class="section-subtitle">查看失败、部分成功、运行中任务的细节</span>
              </div>
            </div>
          </template>

          <el-table :data="store.tasks" v-loading="store.loading.diagnostics" stripe height="320">
            <el-table-column prop="job_id" label="任务编号" min-width="180" />
            <el-table-column prop="source_table_name" label="来源表" min-width="180" />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTag(row.status)">{{ formatResultStatus(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="attempt_count" label="次数" width="80" />
            <el-table-column prop="last_error" label="最近错误" min-width="220" />
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTaskDetail(row)">详情</el-button>
                <el-button
                  link
                  type="primary"
                  :disabled="row.status !== 'failed' && row.status !== 'retry_waiting' && row.status !== 'partial_success'"
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
      </el-collapse-item>
    </el-collapse>

    <el-drawer v-model="taskDrawerVisible" title="任务详情" size="42%">
      <el-descriptions v-if="activeTask" :column="1" border>
        <el-descriptions-item label="任务编号">{{ activeTask.job_id }}</el-descriptions-item>
        <el-descriptions-item label="来源表">{{ activeTask.source_table_name }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ formatResultStatus(activeTask.status) }}</el-descriptions-item>
        <el-descriptions-item label="尝试次数">{{ activeTask.attempt_count }}</el-descriptions-item>
        <el-descriptions-item label="执行者">{{ activeTask.claimed_by || '-' }}</el-descriptions-item>
        <el-descriptions-item label="租约到期">{{ formatTime(activeTask.lease_expires_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="下次重试">{{ formatTime(activeTask.next_retry_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="最近心跳">{{ formatTime(activeTask.heartbeat_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="开始时间">{{ formatTime(activeTask.last_attempt_started_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="结束时间">{{ formatTime(activeTask.last_attempt_finished_at) || '-' }}</el-descriptions-item>
        <el-descriptions-item label="投影状态">{{ formatResultStatus(activeTask.projection_status) }}</el-descriptions-item>
        <el-descriptions-item label="最近错误">{{ activeTask.last_error || '-' }}</el-descriptions-item>
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
const activePanels = ref([])
const tableSearch = ref('')
const taskDrawerVisible = ref(false)
const activeTask = ref(null)
const formState = reactive({
  sourceTableName: '',
})

let refreshTimer = null

const isAnyLoading = computed(() => Object.values(store.loading).some(Boolean))
const filteredTableStates = computed(() => {
  const keyword = tableSearch.value.trim().toLowerCase()
  if (!keyword) return store.tableStates
  return store.tableStates.filter((row) => row.source_table_name?.toLowerCase().includes(keyword))
})

function formatTime(value) {
  if (!value) return ''
  return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
}

function formatWorkerStatus(status) {
  const mapping = {
    running: '运行中',
    stopped: '已停止',
    not_started: '未启动',
    not_configured: '配置异常',
    error: '运行异常',
  }
  return mapping[status] || '未知'
}

function formatConnectionStatus(status) {
  const mapping = {
    reachable: '连接正常',
    healthy: '连接正常',
    unreachable: '连接异常',
    unhealthy: '连接异常',
    unknown: '状态未知',
  }
  return mapping[status] || '状态未知'
}

function formatCatchUpStatus(status) {
  const mapping = {
    up_to_date: '已追平最新',
    catching_up: '正在追平',
    backlog: '存在积压',
    degraded: '存在异常',
  }
  return mapping[status] || '状态未知'
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

function formatTrigger(trigger) {
  const mapping = {
    auto_ingest: '自动',
    manual: '手动',
    repair: '修复',
  }
  return mapping[trigger] || trigger || '-'
}

function statusTag(status) {
  if (['completed', 'running', 'updated', 'submitted', 'repaired'].includes(status)) return 'success'
  if (['pending', 'retry_waiting', 'partial_success', 'skipped'].includes(status)) return 'warning'
  if (['failed', 'cancelled', 'degraded', 'unreachable', 'unhealthy', 'error'].includes(status)) return 'danger'
  return 'info'
}

function statusTone(status) {
  if (['running', 'reachable', 'healthy', 'up_to_date'].includes(status)) return 'is-success'
  if (['backlog', 'catching_up', 'not_started'].includes(status)) return 'is-warning'
  if (['failed', 'degraded', 'unreachable', 'unhealthy', 'error', 'not_configured'].includes(status)) return 'is-danger'
  return ''
}

async function refreshAll() {
  await store.refreshDashboard({ includeEvents: true, includeDiagnostics: true, showError: true })
}

function selectTable(row) {
  store.setSelectedTableName(row.source_table_name)
  formState.sourceTableName = row.source_table_name
}

function openTaskDetail(task) {
  activeTask.value = task
  taskDrawerVisible.value = true
}

function ensureTableSelected() {
  if (!formState.sourceTableName) {
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
  await withConfirm('将立即检查本地与云端 B 类数据差异，并对未同步部分执行追平。是否继续？', async () => {
    await store.syncNow()
  })
}

async function handleToggleAutoSync() {
  const enabled = !store.autoSyncEnabled
  await withConfirm(
    enabled ? '确认恢复自动同步吗？恢复后将自动补齐暂停期间积压的数据。' : '确认暂停自动同步吗？暂停期间仍会记录待同步内容。',
    async () => {
      await store.toggleAutoSync(enabled)
    },
  )
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
  await store.dryRunTable(formState.sourceTableName)
}

async function handleRepairCheckpoint() {
  if (!ensureTableSelected()) return
  await withConfirm(`确认修复 ${formState.sourceTableName} 的同步点吗？`, async () => {
    await store.repairCheckpoint(formState.sourceTableName)
  })
}

async function handleRefreshProjection() {
  if (!ensureTableSelected()) return
  await withConfirm(`确认刷新 ${formState.sourceTableName} 的投影吗？`, async () => {
    await store.refreshProjection(formState.sourceTableName)
  })
}

onMounted(async () => {
  await refreshAll()
  refreshTimer = window.setInterval(() => {
    store.refreshDashboard({ includeEvents: false, includeDiagnostics: false }).catch(() => {})
  }, 15000)
})

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
  }
})
</script>

<style scoped>
.catch-up-console {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px 32px;
  border-radius: 20px;
  background:
    linear-gradient(135deg, rgba(31, 111, 235, 0.88), rgba(41, 182, 246, 0.76)),
    linear-gradient(120deg, #0f2744, #14385f);
  color: #fff;
  box-shadow: 0 16px 36px rgba(24, 65, 120, 0.16);
}

.hero-kicker {
  margin: 0 0 10px;
  font-size: 13px;
  letter-spacing: 0.08em;
  opacity: 0.82;
}

.hero-panel h1 {
  margin: 0;
  font-size: 32px;
  line-height: 1.2;
}

.hero-subtitle {
  margin: 12px 0 0;
  max-width: 760px;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.88);
}

.hero-actions {
  display: flex;
  align-items: flex-start;
}

.warning-banner {
  margin-top: -2px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.status-card {
  min-height: 152px;
}

.card-label {
  font-size: 12px;
  color: #7d8798;
  letter-spacing: 0.06em;
}

.card-value {
  margin-top: 12px;
  font-size: 26px;
  font-weight: 700;
  color: #18212f;
}

.card-value.is-success {
  color: #1f8f54;
}

.card-value.is-warning {
  color: #c47a18;
}

.card-value.is-danger {
  color: #d94a4a;
}

.card-meta {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.6;
  color: #607085;
}

.primary-grid,
.diagnostics-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 18px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.section-subtitle {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #7d8798;
}

.action-panel,
.runtime-panel,
.history-panel,
.diagnostics-panel,
.tasks-panel {
  border-radius: 16px;
}

.action-block {
  padding: 14px 0 18px;
  border-bottom: 1px solid #edf1f6;
}

.action-block:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.action-title {
  font-size: 16px;
  font-weight: 600;
  color: #18212f;
}

.action-desc {
  margin: 8px 0 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #607085;
}

.runtime-list {
  display: grid;
  gap: 12px;
}

.runtime-item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px dashed #edf1f6;
}

.runtime-item:last-child {
  border-bottom: none;
}

.runtime-label {
  color: #607085;
}

.runtime-value {
  color: #18212f;
  font-weight: 600;
  text-align: right;
}

.runtime-error {
  max-width: 320px;
  color: #a34848;
}

.diagnostics-collapse {
  background: transparent;
}

.diagnostics-search {
  margin-bottom: 12px;
}

.diag-actions {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.selected-summary {
  margin-top: 18px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #f6f9fc;
}

.summary-label {
  font-size: 12px;
  color: #7d8798;
}

.summary-value {
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #18212f;
}

.summary-meta {
  margin-top: 6px;
  color: #607085;
}

@media (max-width: 1440px) {
  .overview-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1080px) {
  .primary-grid,
  .diagnostics-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .catch-up-console {
    padding: 16px;
  }

  .hero-panel {
    flex-direction: column;
    padding: 22px 20px;
  }

  .hero-panel h1 {
    font-size: 26px;
  }

  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
