<template>
  <div class="collection-tasks erp-page-container erp-page--admin">
    <PageHeader
      title="采集任务"
      subtitle="创建快速采集任务、查看任务进度、日志与步骤时间线。"
      family="admin"
    />

    <!-- 快速采集面板 -->
    <div class="quick-collect-panel">
      <h3>快速采集</h3>
      <div class="quick-form">
        <el-select 
          v-model="quickForm.platform" 
          placeholder="选择平台"
          @change="onPlatformChange"
        >
          <el-option label="Shopee" value="shopee" />
          <el-option label="TikTok" value="tiktok" />
          <el-option label="妙手ERP" value="miaoshou" />
        </el-select>

        <el-select 
          v-model="quickForm.account_id" 
          placeholder="选择账号"
          :loading="accountsLoading"
        >
          <el-option 
            v-for="acc in filteredAccounts" 
            :key="acc.id"
            :label="acc.name"
            :value="acc.id"
          />
        </el-select>

        <el-checkbox-group v-model="quickForm.data_domains" class="domain-checkboxes">
          <el-checkbox label="orders">订单</el-checkbox>
          <el-checkbox label="products">产品</el-checkbox>
          <el-checkbox label="analytics">流量</el-checkbox>
          <el-checkbox label="inventory">库存</el-checkbox>
          <el-checkbox label="finance">财务</el-checkbox>
          <el-checkbox label="services">服务</el-checkbox>
        </el-checkbox-group>

        <div
          v-for="domain in selectedSubtypeDomains"
          :key="`quick-subtype-${domain}`"
          class="sub-domain-section"
        >
          <span class="sub-domain-label">{{ getDomainLabel(domain) }}子类型</span>
          <el-checkbox-group v-model="quickForm.sub_domains[domain]" class="sub-domain-checkboxes">
            <el-checkbox
              v-for="option in getSubtypeOptions(domain)"
              :key="option.value"
              :label="option.value"
            >
              {{ option.label }}
            </el-checkbox>
          </el-checkbox-group>
        </div>

        <el-select v-model="quickForm.date_preset" placeholder="日期范围" class="erp-w-120">
          <el-option label="今天" value="today" />
          <el-option label="昨天" value="yesterday" />
          <el-option :label="getDatePresetLabel('last_7_days', quickForm.platform)" value="last_7_days" />
          <el-option :label="getDatePresetLabel('last_30_days', quickForm.platform)" value="last_30_days" />
          <el-option label="自定义" value="custom" />
        </el-select>
        <el-date-picker
          v-if="quickForm.date_preset === 'custom'"
          v-model="quickForm.customDateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          class="erp-w-240"
        />
        <el-select
          v-if="quickForm.date_preset === 'custom'"
          v-model="quickForm.granularity"
          placeholder="选择粒度"
          class="erp-w-120"
        >
          <el-option label="日报" value="daily" />
          <el-option label="周报" value="weekly" />
          <el-option label="月报" value="monthly" />
        </el-select>

        <div class="debug-mode-switch">
          <el-switch 
            v-model="quickForm.debugMode" 
            active-text="有头模式"
            inactive-text=""
          />
          <el-tooltip placement="top">
            <template #content>
              开启后会在<strong>运行后端的电脑</strong>上打开浏览器窗口，便于观察采集过程。<br/>
              若看不到窗口，请确认已执行 <code>playwright install chromium</code> 且后端单进程；任务一直「等待」时请检查任务队列是否正常。
            </template>
            <el-icon><QuestionFilled /></el-icon>
          </el-tooltip>
        </div>

        <el-button 
          type="primary" 
          :loading="creating"
          :disabled="!canCreateTask"
          @click="createQuickTask"
        >
          <el-icon><CaretRight /></el-icon>
          开始采集
        </el-button>
      </div>
    </div>

    <!-- 采集执行说明：任务为何一直「等待」、如何真正执行 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="collect-tip"
    >
      <template #title>
        <span>如何真正执行采集？</span>
      </template>
      <div class="collect-tip-body">
        点击「开始采集」会创建任务，执行由<strong>后端同一进程</strong>在后台启动。若任务一直处于「等待」、进度 0%，请检查：
        <ul>
          <li><strong>单进程启动</strong>：使用 <code>python run.py</code> 或 <code>python run.py --local</code> 或 <code>uvicorn ... --workers 1</code> 启动后端；多 worker 时后台任务可能未在收到请求的进程内执行。</li>
          <li><strong>后端日志</strong>：查看运行后端的终端是否有异常（账号加载失败、Playwright 未安装等）。</li>
          <li><strong>Playwright</strong>：有头模式需本机执行 <code>playwright install</code> 或 <code>playwright install chromium</code>（勿仅安装 <code>--only-shell</code>）；本地观察采集请开启「有头模式」。</li>
        </ul>
      </div>
    </el-alert>

    <div v-if="activeConfigId" class="active-config-banner">
      当前正在查看由配置 #{{ activeConfigId }} 创建的任务。
      <el-button size="small" text @click="clearConfigFilter">清除筛选</el-button>
    </div>

    <div v-if="pendingVerificationItems.length" class="pending-verification-panel">
      <div class="section-header">
        <h3>待处理队列</h3>
      </div>
      <div class="verification-summary">
        <div class="verification-summary-card">
          <div class="summary-value">{{ verificationSummary.total }}</div>
          <div class="summary-label">待处理总数</div>
        </div>
        <div class="verification-summary-card">
          <div class="summary-value">{{ verificationSummary.graphical }}</div>
          <div class="summary-label">验证码</div>
        </div>
        <div class="verification-summary-card">
          <div class="summary-value">{{ verificationSummary.manual }}</div>
          <div class="summary-label">人工处理</div>
        </div>
      </div>
      <div
        v-for="group in groupedPendingVerificationItems"
        :key="group.key"
        class="pending-group"
      >
        <div class="pending-group-title">{{ group.title }}</div>
        <div class="pending-verification-list">
          <div
            v-for="item in group.items"
            :key="item.task_id"
            class="pending-verification-item"
          >
            <div class="pending-verification-meta">
              <el-tag :type="getPlatformTagType(item.platform)" size="small">
                {{ item.platform }}
              </el-tag>
              <span>{{ item.account || item.account_id }}</span>
              <span>{{ item.task_id?.slice(0, 8) }}...</span>
              <span>{{ getStatusLabel(item.status) }}</span>
              <span>{{ item.verification_message || item.current_step || '等待处理' }}</span>
            </div>
            <div class="pending-verification-actions">
              <el-button size="small" @click="copyTaskId(item.task_id)">
                复制任务ID
              </el-button>
              <el-button size="small" @click="focusTaskRow(item.task_id)">
                定位任务
              </el-button>
              <el-button size="small" type="primary" @click="showResumeDialog(item)">
                立即处理
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="tasks-section">
      <div class="section-header">
        <h3>采集任务</h3>
        <div class="header-actions">
          <el-radio-group v-model="statusFilter" @change="loadTasks">
            <el-radio-button label="">全部</el-radio-button>
            <el-radio-button label="running">运行中</el-radio-button>
            <el-radio-button label="queued">排队中</el-radio-button>
            <el-radio-button label="completed">已完成</el-radio-button>
            <el-radio-button label="failed">失败</el-radio-button>
          </el-radio-group>
          <el-button @click="loadTasks">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </div>
      </div>

      <el-table
        ref="taskTableRef"
        v-loading="loading" 
        :data="tasks" 
        :row-key="row => row.task_id"
        :row-class-name="getTaskRowClassName"
        stripe
      >
        <el-table-column label="任务ID" width="120">
          <template #default="{ row }">
            <span class="task-id">{{ row.task_id?.slice(0, 8) }}...</span>
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
              class="erp-mr-xs"
            >
              {{ getDomainLabel(domain) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="240">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress 
                :percentage="getTaskProgress(row)" 
                :status="getProgressStatus(row.status)"
                :stroke-width="6"
              />
              <div class="progress-details">
                <span class="progress-text">{{ getProgressText(row) }}</span>
                <span v-if="row.current_domain" class="current-domain">
                  {{ row.current_domain }}
                </span>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件数" width="80">
          <template #default="{ row }">
            {{ row.files_collected || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button 
              v-if="['pending', 'queued', 'running'].includes(row.status)"
              size="small" 
              type="warning"
              @click="cancelTask(row)"
            >
              取消
            </el-button>
            <el-button 
              v-if="['verification_required', 'paused', 'manual_intervention_required'].includes(row.status)"
              size="small" 
              type="success"
              @click="showResumeDialog(row)"
            >
              继续
            </el-button>
            <el-button 
              v-if="row.status === 'failed'"
              size="small" 
              type="primary"
              @click="retryTask(row)"
            >
              重试
            </el-button>
            <el-button 
              v-if="isTerminalStatus(row.status)"
              size="small" 
              type="danger"
              link
              @click="deleteTask(row)"
            >
              删除
            </el-button>
            <el-button 
              size="small"
              type="primary"
              link
              @click="showDetailDrawer(row)"
            >
              详情
            </el-button>
            <el-button 
              size="small"
              @click="showLogsDialog(row)"
            >
              日志
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 任务详情抽屉：元信息 + 步骤时间线 -->
    <el-drawer
      v-model="detailDrawerVisible"
      title="任务详情"
      size="520px"
      direction="rtl"
    >
      <template v-if="detailTask">
        <div class="task-detail-meta">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="平台">
              <el-tag :type="getPlatformTagType(detailTask.platform)" size="small">{{ detailTask.platform }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="账号">{{ detailTask.account }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="getStatusTagType(detailTask.status)">{{ getStatusLabel(detailTask.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(detailTask.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="开始时间">{{ formatTime(detailTask.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="结束时间">{{ formatTime(detailTask.completed_at) }}</el-descriptions-item>
            <el-descriptions-item label="总耗时">{{ formatDuration(detailTask) }}</el-descriptions-item>
            <el-descriptions-item label="来源配置">{{ detailTask.config_id || '-' }}</el-descriptions-item>
            <el-descriptions-item label="执行模式">{{ getExecutionModeLabel(detailTask.execution_mode) }}</el-descriptions-item>
            <el-descriptions-item label="数据域">
              <el-tag v-for="d in (detailTask.data_domains || [])" :key="d" size="small" class="erp-mr-xs">{{ getDomainLabel(d) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item v-if="detailTask.completed_domains?.length" label="已完成域">
              {{ (detailTask.completed_domains || []).join(', ') }}
            </el-descriptions-item>
            <el-descriptions-item v-if="detailTask.failed_domains?.length" label="失败域">
              <span class="text-danger">{{ (detailTask.failed_domains || []).map(d => typeof d === 'object' ? d.domain || d.name : d).join(', ') }}</span>
            </el-descriptions-item>
            <el-descriptions-item v-if="detailTask.error_message" label="错误信息">
              <span class="text-danger">{{ detailTask.error_message }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <div class="task-detail-timeline">
          <h4>步骤时间线</h4>
          <div v-loading="detailLogsLoading" class="timeline-list">
            <div
              v-for="log in sortedDetailLogs"
              :key="log.id"
              :class="['timeline-item', `timeline-${log.level}`]"
            >
              <div class="timeline-item-head">
                <span class="timeline-time">{{ formatTime(log.timestamp) }}</span>
                <el-tag :type="getLogTagType(log.level)" size="small">{{ log.level }}</el-tag>
                <span v-if="getStepLabel(log)" class="timeline-step">{{ getStepLabel(log) }}</span>
              </div>
              <div class="timeline-message">{{ log.message }}</div>
              <el-collapse v-if="log.details && (log.details.error || log.level === 'error')">
                <el-collapse-item v-if="log.details?.error" name="error">
                  <template #title>
                    <span class="text-danger">错误详情</span>
                  </template>
                  <pre class="detail-error">{{ log.details.error }}</pre>
                </el-collapse-item>
                <el-collapse-item v-else-if="log.details && Object.keys(log.details).length" name="details">
                  <template #title>details</template>
                  <pre class="detail-json">{{ JSON.stringify(log.details, null, 2) }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
            <el-empty v-if="!detailLogsLoading && sortedDetailLogs.length === 0" description="暂无步骤日志" />
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 日志对话框 -->
    <el-dialog 
      v-model="logsDialogVisible" 
      title="任务日志"
      width="800px"
    >
      <div class="logs-container">
        <div 
          v-for="log in taskLogs" 
          :key="log.id"
          :class="['log-item', `log-${log.level}`]"
        >
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <el-tag :type="getLogTagType(log.level)" size="small">
            {{ log.level }}
          </el-tag>
          <span class="log-message">{{ log.message }}</span>
        </div>
        <el-empty v-if="taskLogs.length === 0" description="暂无日志" />
      </div>
    </el-dialog>

    <VerificationResumeDialog
      :visible="verificationDialogVisible"
      :verification-type="verificationType"
      :verification-input-mode="verificationInputMode"
      :screenshot-url="verificationScreenshotUrl"
      :submitting="false"
      :message="currentTask?.verification_message || currentTask?.current_step || ''"
      :error-message="''"
      :expires-at="currentTask?.verification_expires_at || ''"
      title="任务验证码回填"
      subtitle="当前采集任务已暂停，请先完成验证或人工处理后继续。"
      submit-text="提交并继续"
      cancel-text="取消任务"
      @submit="submitVerification"
      @cancel="skipVerification"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, Refresh, QuestionFilled } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'
import PageHeader from '@/components/common/PageHeader.vue'
import VerificationResumeDialog from '@/components/verification/VerificationResumeDialog.vue'
import {
  buildTimeSelectionPayload,
  getDatePresetLabel,
  getSelectedSubtypeDomains,
  getSubtypeOptions
} from '@/constants/collection'

const route = useRoute()
const router = useRouter()
const activeConfigId = computed(() => route.query.config_id || '')
const activeTaskIds = computed(() =>
  String(route.query.task_ids || '')
    .split(',')
    .map(id => id.trim())
    .filter(Boolean)
)

const clearConfigFilter = async () => {
  await router.push({
    name: 'CollectionTasks',
    query: {}
  })
}

// 状态
const loading = ref(false)
const accountsLoading = ref(false)
const creating = ref(false)
const tasks = ref([])
const verificationItems = ref([])
const accounts = ref([])
const taskLogs = ref([])
const statusFilter = ref('')
const logsDialogVisible = ref(false)
const detailDrawerVisible = ref(false)
const detailTask = ref(null)
const detailLogs = ref([])
const detailLogsLoading = ref(false)
const taskTableRef = ref(null)
const highlightedTaskId = ref('')
const verificationDialogVisible = ref(false)
const verificationScreenshot = ref('')
const verificationScreenshotUrl = ref('')
const verificationType = ref('')
const verificationInputMode = ref('')
const verificationCode = ref('')
const currentTask = ref(null)

// WebSocket连接
const wsConnections = ref({})
const DEFAULT_GRANULARITY = 'daily'
const ACTIVE_TASK_POLL_INTERVAL = 3000
const IDLE_TASK_POLL_INTERVAL = 30000
const ACTIVE_TASK_STATUSES = ['pending', 'queued', 'running', 'verification_required', 'verification_submitted', 'paused', 'manual_intervention_required']
let tasksRefreshTimer = null

// 快速采集表单（v4.7.0 + 扩展：日期自定义）
const quickForm = reactive({
  platform: '',
  account_id: '',
  data_domains: [],
  sub_domains: {},
  date_preset: 'yesterday',
  customDateRange: [],  // [start, end] 仅当 date_preset === 'custom' 时使用
  granularity: DEFAULT_GRANULARITY,
  debugMode: false  // v4.7.0: 调试模式
})

// 计算属性
const filteredAccounts = computed(() => {
  if (!quickForm.platform) return accounts.value
  return accounts.value.filter(acc => 
    acc.platform?.toLowerCase() === quickForm.platform.toLowerCase()
  )
})

const selectedSubtypeDomains = computed(() =>
  getSelectedSubtypeDomains(quickForm.data_domains)
)

const pendingVerificationItems = computed(() => verificationItems.value || [])

const sortedPendingVerificationItems = computed(() =>
  [...pendingVerificationItems.value].sort((a, b) => {
    const aManual = String(a.verification_type || '').toLowerCase() === 'manual_intervention' ? 0 : 1
    const bManual = String(b.verification_type || '').toLowerCase() === 'manual_intervention' ? 0 : 1
    if (aManual !== bManual) {
      return aManual - bManual
    }
    return String(a.created_at || '').localeCompare(String(b.created_at || ''))
  })
)

const groupedPendingVerificationItems = computed(() => {
  const groups = [
    {
      key: 'manual',
      title: '人工处理',
      items: sortedPendingVerificationItems.value.filter(
        (item) => String(item.verification_type || '').toLowerCase() === 'manual_intervention'
      ),
    },
    {
      key: 'captcha',
      title: '验证码处理',
      items: sortedPendingVerificationItems.value.filter(
        (item) => String(item.verification_type || '').toLowerCase() !== 'manual_intervention'
      ),
    },
  ]
  return groups.filter((group) => group.items.length > 0)
})

const verificationSummary = computed(() => {
  const items = pendingVerificationItems.value
  return {
    total: items.length,
    graphical: items.filter((item) => String(item.verification_type || '').toLowerCase() !== 'manual_intervention').length,
    manual: items.filter((item) => String(item.verification_type || '').toLowerCase() === 'manual_intervention').length,
  }
})

const isLegacyVerificationStatus = (task) =>
  ['verification_required', 'paused', 'manual_intervention_required'].includes(task.status) && task.verification_type

watch(
  () => [...quickForm.data_domains],
  (domains) => {
    const allowedDomains = new Set(getSelectedSubtypeDomains(domains))
    for (const domain of Object.keys(quickForm.sub_domains || {})) {
      if (!allowedDomains.has(domain)) {
        delete quickForm.sub_domains[domain]
      }
    }
  }
)

const canCreateTask = computed(() => {
  if (!quickForm.platform || !quickForm.account_id || quickForm.data_domains.length === 0) return false
  if (quickForm.date_preset === 'custom') {
    return Array.isArray(quickForm.customDateRange)
      && quickForm.customDateRange.length === 2
      && Boolean(quickForm.granularity)
  }
  return true
})

const hasActiveTasks = (taskList = tasks.value) =>
  (taskList || []).some(task => ACTIVE_TASK_STATUSES.includes(task.status))

const scheduleTaskRefresh = (taskList = tasks.value) => {
  if (tasksRefreshTimer) {
    clearTimeout(tasksRefreshTimer)
  }
  const nextInterval = hasActiveTasks(taskList) ? ACTIVE_TASK_POLL_INTERVAL : IDLE_TASK_POLL_INTERVAL
  tasksRefreshTimer = setTimeout(() => {
    void loadTasks()
  }, nextInterval)
}

// 任务详情抽屉：步骤日志按时间排序
const sortedDetailLogs = computed(() => {
  const list = [...(detailLogs.value || [])]
  list.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
  return list
})

// 方法
const loadTasks = async () => {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (route.query.config_id) params.config_id = route.query.config_id
    
    tasks.value = await collectionApi.getTasks(params)
    if (tasks.value.length === 0 && activeTaskIds.value.length > 0) {
      const unfiltered = await collectionApi.getTasks(statusFilter.value ? { status: statusFilter.value } : {})
      tasks.value = (unfiltered || []).filter(task => activeTaskIds.value.includes(task.task_id))
    }
    verificationItems.value = await collectionApi.getVerificationItems()
    if (route.query.task_ids) {
      const taskIds = String(route.query.task_ids).split(',').filter(Boolean)
      const matchedTask = tasks.value.find((task) => taskIds.includes(task.task_id))
      if (matchedTask) {
        await focusTaskRow(matchedTask.task_id)
      }
    }
    syncVerificationDialogFromTasks(tasks.value)
    
    // 为运行中的任务建立WebSocket连接
    tasks.value
      .filter(t => ACTIVE_TASK_STATUSES.includes(t.status))
      .forEach(t => connectTaskWebSocket(t.task_id))
  } catch (error) {
    ElMessage.error('加载任务失败: ' + error.message)
  } finally {
    loading.value = false
    scheduleTaskRefresh(tasks.value)
  }
}

const syncVerificationDialogFromTasks = (taskList) => {
  const verificationTask = (taskList || []).find(
    (task) => isLegacyVerificationStatus(task)
      || (task.status === 'manual_intervention_required' && task.verification_type)
  )
  if (!verificationTask) {
    return
  }

  if (verificationDialogVisible.value && currentTask.value?.task_id === verificationTask.task_id) {
    return
  }

  showResumeDialog(verificationTask)
}

const copyTaskId = async (taskId) => {
  const value = String(taskId || '').trim()
  if (!value) return
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    }
    ElMessage.success('任务ID已复制')
  } catch (error) {
    ElMessage.error('复制失败: ' + (error.message || '未知错误'))
  }
}

const getTaskRowClassName = ({ row }) =>
  row?.task_id && row.task_id === highlightedTaskId.value ? 'task-row-highlight' : ''

const focusTaskRow = async (taskId) => {
  highlightedTaskId.value = taskId
  await nextTick()
  const row = document.querySelector('.task-row-highlight')
  row?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
}

const loadAccounts = async () => {
  accountsLoading.value = true
  try {
    accounts.value = await collectionApi.getAccounts()
  } catch (error) {
    ElMessage.error('加载账号失败: ' + error.message)
  } finally {
    accountsLoading.value = false
  }
}

const createQuickTask = async () => {
  creating.value = true
  try {
    const timeSelection = buildTimeSelectionPayload(quickForm.date_preset, {
      customRange: quickForm.customDateRange
    })
    if (!timeSelection) {
      ElMessage.warning('请选择有效的日期范围')
      creating.value = false
      return
    }
    // v4.7.0: 添加debugMode参数
    const task = await collectionApi.createTask({
      platform: quickForm.platform,
      account_id: quickForm.account_id,
      data_domains: quickForm.data_domains,
      sub_domains: quickForm.sub_domains,
      granularity: quickForm.date_preset === 'custom' ? quickForm.granularity : undefined,
      time_selection: buildTimeSelectionPayload(quickForm.date_preset, {
        customRange: quickForm.customDateRange
      }),
      debug_mode: quickForm.debugMode  // v4.7.0: 调试模式
    })
    
    ElMessage.success('任务创建成功')
    loadTasks()
    
    // 建立WebSocket连接
    connectTaskWebSocket(task.task_id)
  } catch (error) {
    ElMessage.error('创建任务失败: ' + error.message)
  } finally {
    creating.value = false
  }
}

const cancelTask = async (row) => {
  try {
    await ElMessageBox.confirm('确定要取消此任务吗？', '确认')
    await collectionApi.cancelTask(row.task_id)
    ElMessage.success('任务已取消')
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('取消失败: ' + error.message)
    }
  }
}

// 终态状态（可删除记录）
const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'partial_success']
const isTerminalStatus = (status) => TERMINAL_STATUSES.includes(status)

const deleteTask = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除此任务记录吗？删除后不可恢复。', '确认删除')
    await collectionApi.deleteTask(row.task_id)
    ElMessage.success('任务已删除')
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + error.message)
    }
  }
}

const retryTask = async (row) => {
  try {
    await collectionApi.retryTask(row.task_id)
    ElMessage.success('已创建重试任务')
    loadTasks()
  } catch (error) {
    ElMessage.error('重试失败: ' + error.message)
  }
}

const showResumeDialog = (row) => {
  currentTask.value = row
  verificationCode.value = ''
  verificationType.value = row.verification_type || ''
  verificationInputMode.value = row.verification_input_mode || ''
  verificationScreenshot.value = row.verification_screenshot || row.error_screenshot_path || ''
  verificationScreenshotUrl.value = row.task_id ? collectionApi.getTaskScreenshotUrl(row.task_id) : ''
  verificationDialogVisible.value = true
}

const submitVerification = async (submitted) => {
  if (!currentTask.value) return
  const code = String(submitted?.value || '').trim()
  if (verificationInputMode.value !== 'manual_continue' && !code) {
    ElMessage.warning('请输入验证码')
    return
  }
  const isOtp = (verificationType.value || '').toLowerCase() === 'otp' || /^(sms|email_code)$/i.test(verificationType.value)
  const payload = verificationInputMode.value === 'manual_continue'
    ? { manual_completed: true }
    : (isOtp ? { otp: code } : { captcha_code: code })
  try {
    await collectionApi.resumeTask(currentTask.value.task_id, payload)
    ElMessage.success('已提交，任务将自动继续')
    verificationDialogVisible.value = false
    loadTasks()
  } catch (error) {
    ElMessage.error('提交失败: ' + (error.response?.data?.detail || error.message))
  }
}

const skipVerification = async () => {
  if (!currentTask.value) return
  
  try {
    await collectionApi.cancelTask(currentTask.value.task_id)
    ElMessage.info('任务已跳过')
    verificationDialogVisible.value = false
    loadTasks()
  } catch (error) {
    ElMessage.error('操作失败: ' + error.message)
  }
}

const showDetailDrawer = async (row) => {
  detailTask.value = null
  detailLogs.value = []
  detailDrawerVisible.value = true
  try {
    detailTask.value = await collectionApi.getTask(row.task_id)
  } catch (e) {
    detailTask.value = row
  }
  detailLogsLoading.value = true
  try {
    detailLogs.value = await collectionApi.getTaskLogs(row.task_id) || []
  } catch (error) {
    detailLogs.value = []
    ElMessage.error('加载步骤日志失败: ' + error.message)
  } finally {
    detailLogsLoading.value = false
  }
}

const showLogsDialog = async (row) => {
  currentTask.value = row
  logsDialogVisible.value = true
  
  try {
    taskLogs.value = await collectionApi.getTaskLogs(row.task_id)
  } catch (error) {
    taskLogs.value = []
    ElMessage.error('加载日志失败: ' + error.message)
  }
}

const connectTaskWebSocket = (taskId) => {
  if (wsConnections.value[taskId]) return
  
  const ws = collectionApi.createTaskWebSocket(taskId, null, {
    onProgress: (message) => {
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.progress = message.progress
        task.current_step = message.current_step
        task.status = message.status
      }
    },
    onLog: (message) => {
      if (currentTask.value?.task_id === taskId) {
        taskLogs.value.push(message)
      }
    },
    onComplete: (message) => {
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.status = message.status
        task.files_collected = message.files_collected
        task.progress = ['completed', 'partial_success'].includes(message.status) ? 100 : task.progress
      }
      
      if (message.status === 'completed') {
        ElMessage.success(`任务 ${taskId.slice(0, 8)} 完成，采集 ${message.files_collected} 个文件`)
      } else if (message.status === 'failed') {
        ElMessage.error(`任务 ${taskId.slice(0, 8)} 失败: ${message.error_message}`)
      }
      
      disconnectTaskWebSocket(taskId)
      void loadTasks()
    },
    onVerification: (message) => {
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.status = message.verification_input_mode === 'manual_continue'
          ? 'manual_intervention_required'
          : 'verification_required'
        task.verification_type = message.verification_type || ''
        task.verification_input_mode = message.verification_input_mode || ''
        task.verification_screenshot = message.screenshot_path || ''
        currentTask.value = task
        verificationType.value = task.verification_type || ''
        verificationInputMode.value = task.verification_input_mode || ''
        verificationScreenshotUrl.value = collectionApi.getTaskScreenshotUrl(taskId)
        verificationDialogVisible.value = true
      }
    },
    onError: () => {
      disconnectTaskWebSocket(taskId)
    }
  })
  
  wsConnections.value[taskId] = ws
}

const disconnectTaskWebSocket = (taskId) => {
  const ws = wsConnections.value[taskId]
  if (ws) {
    ws.close()
    delete wsConnections.value[taskId]
  }
}

const onPlatformChange = () => {
  quickForm.account_id = ''
  quickForm.sub_domains = {}
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
    running: 'primary', queued: 'info', completed: 'success',
    failed: 'danger', cancelled: 'warning',
    verification_required: 'warning',
    verification_submitted: 'info',
    paused: 'warning',
    partial_success: 'warning'  // v4.7.0: 部分成功显示为warning
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    pending: '等待', queued: '排队', running: '运行中',
    completed: '完成', failed: '失败', cancelled: '已取消',
    verification_required: '等待验证码',
    verification_submitted: '验证码已提交',
    paused: '等待验证码',
    partial_success: '部分成功'  // v4.7.0: 新状态
  }
  return labels[status] || status
}

const getExecutionModeLabel = (mode) => {
  return mode === 'headed' ? '有头模式' : '无头模式'
}

const MAIN_ACCOUNT_COORDINATION_STEP_LABELS = {
  waiting_for_main_account_session: '等待主账号会话',
  preparing_main_account_session: '准备主账号会话',
  switching_target_shop: '切换目标店铺',
  target_shop_ready: '目标店铺已就绪'
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  if (status === 'partial_success') return 'warning'  // v4.7.0
  return null
}

// ========== v4.7.0: 任务粒度优化显示 ==========

const getTaskProgress = (task) => {
  // v4.7.0: 使用total_domains和completed_domains计算进度
  if (task.total_domains && task.total_domains > 0) {
    const completed = task.completed_domains?.length || 0
    return Math.floor((completed / task.total_domains) * 100)
  }
  // 降级：使用原progress字段
  return task.progress || 0
}

const getProgressText = (task) => {
  // v4.7.0: 显示域级别进度
  if (task.total_domains && task.total_domains > 0) {
    const completed = task.completed_domains?.length || 0
    const failed = task.failed_domains?.length || 0
    
    if (failed > 0) {
      return `${completed}/${task.total_domains}个数据域（${failed}个失败）`
    }
    return `${completed}/${task.total_domains}个数据域`
  }
  // 降级：使用原current_step
  return task.current_step || '等待中'
}

const getLogTagType = (level) => {
  const types = { info: 'info', warning: 'warning', error: 'danger' }
  return types[level] || 'info'
}

const formatTime = (time) => {
  if (!time) return '-'
  return new Date(time).toLocaleString('zh-CN')
}

const formatDuration = (task) => {
  if (task.duration_seconds != null) return `${task.duration_seconds} 秒`
  if (task.started_at && task.completed_at) {
    const s = Math.round((new Date(task.completed_at) - new Date(task.started_at)) / 1000)
    return `${s} 秒`
  }
  return '-'
}

const getStepLabel = (log) => {
  const d = log.details
  if (!d) return ''
  if (d.step_id) return d.step_id
  if (d.component) return d.component
  if (d.data_domain) return `域: ${d.data_domain}`
  return ''
}

// 生命周期
onMounted(() => {
  loadTasks()
  loadAccounts()
})

onUnmounted(() => {
  if (tasksRefreshTimer) {
    clearTimeout(tasksRefreshTimer)
    tasksRefreshTimer = null
  }
  Object.keys(wsConnections.value).forEach(disconnectTaskWebSocket)
})
</script>

<style scoped>
.collection-tasks {
  min-height: calc(100vh - var(--header-height));
}

.quick-collect-panel {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
  color: white;
}

.quick-collect-panel h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
}

.quick-form {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

/* v4.7.0: 调试模式开关 */
.debug-mode-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
}

.debug-mode-switch .el-icon {
  color: rgba(255, 255, 255, 0.7);
  cursor: help;
}

.quick-form .el-select {
  width: 150px;
}

.domain-checkboxes {
  display: flex;
  gap: 8px;
}

.domain-checkboxes :deep(.el-checkbox__label) {
  color: white;
}

.collect-tip {
  margin-bottom: 16px;
}
.collect-tip-body {
  margin-top: 6px;
}
.collect-tip-body ul {
  margin: 8px 0 0;
  padding-left: 20px;
}
.collect-tip-body code {
  background: rgba(0, 0, 0, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.active-config-banner {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #ecf5ff;
  border: 1px solid #b3d8ff;
  color: #1f4e79;
  font-size: 13px;
}

.tasks-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
}

.pending-verification-panel {
  margin-bottom: 20px;
  padding: 16px;
  background: #fff7e6;
  border: 1px solid #f5d19a;
  border-radius: 12px;
}

.pending-verification-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pending-group {
  margin-bottom: 14px;
}

.pending-group-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #8c5700;
}

.verification-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.verification-summary-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid #f2e3c2;
}

.summary-value {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.summary-label {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.pending-verification-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid #f2e3c2;
  border-radius: 10px;
}

.pending-verification-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: #606266;
  font-size: 13px;
}

.pending-verification-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

:deep(.task-row-highlight) {
  --el-table-tr-bg-color: #fff7e6;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.task-id {
  font-family: monospace;
  color: #666;
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.progress-text {
  font-size: 12px;
  color: #606266;
  font-weight: 500;
}

/* v4.7.0: 当前域显示 */
.current-domain {
  font-size: 11px;
  color: #909399;
  font-style: italic;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logs-container {
  max-height: 400px;
  overflow-y: auto;
}

.log-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px;
  border-bottom: 1px solid #eee;
}

.log-time {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

.log-message {
  flex: 1;
  font-size: 13px;
}

.log-error {
  background: #fef0f0;
}

.log-warning {
  background: #fdf6ec;
}

.verification-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.verification-screenshot {
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid #eee;
}

/* 任务详情抽屉 */
.task-detail-meta {
  margin-bottom: 20px;
}

.task-detail-timeline h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #303133;
}

.timeline-list {
  max-height: 60vh;
  overflow-y: auto;
}

.timeline-item {
  padding: 10px 12px;
  border-left: 3px solid #dcdfe6;
  margin-bottom: 8px;
  background: #fafafa;
  border-radius: 0 8px 8px 0;
}

.timeline-item.timeline-error {
  border-left-color: #f56c6c;
  background: #fef0f0;
}

.timeline-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.timeline-time {
  font-size: 12px;
  color: #909399;
}

.timeline-step {
  font-size: 12px;
  font-weight: 500;
  color: #606266;
}

.timeline-message {
  font-size: 13px;
  color: #303133;
}

.detail-error,
.detail-json {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.text-danger {
  color: #f56c6c;
}
</style>

