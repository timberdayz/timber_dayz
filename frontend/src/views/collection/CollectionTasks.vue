<template>
  <div class="collection-tasks">
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
        </el-checkbox-group>

        <el-select v-model="quickForm.date_preset" placeholder="日期范围">
          <el-option label="今天" value="today" />
          <el-option label="昨天" value="yesterday" />
          <el-option label="最近7天" value="last_7_days" />
        </el-select>

        <div class="debug-mode-switch">
          <el-switch 
            v-model="quickForm.debugMode" 
            active-text="调试模式"
            inactive-text=""
          />
          <el-tooltip placement="top">
            <template #content>
              调试模式将使用有头浏览器<br/>便于观察采集过程（生产环境可用）
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
        v-loading="loading" 
        :data="tasks" 
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
              style="margin-right: 4px"
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
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button 
              v-if="row.status === 'running' || row.status === 'queued'"
              size="small" 
              type="warning"
              @click="cancelTask(row)"
            >
              取消
            </el-button>
            <el-button 
              v-if="row.status === 'paused'"
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
              size="small"
              @click="showLogsDialog(row)"
            >
              日志
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

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

    <!-- 验证码对话框 -->
    <el-dialog 
      v-model="verificationDialogVisible" 
      title="需要验证"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="verification-content">
        <el-alert 
          type="warning" 
          :closable="false"
          title="任务需要验证码才能继续"
        />
        
        <img 
          v-if="verificationScreenshot" 
          :src="verificationScreenshot" 
          class="verification-screenshot"
        />
        
        <el-form>
          <el-form-item label="验证码">
            <el-input 
              v-model="verificationCode" 
              placeholder="请输入验证码"
            />
          </el-form-item>
        </el-form>
      </div>
      
      <template #footer>
        <el-button @click="skipVerification">跳过</el-button>
        <el-button type="primary" @click="submitVerification">
          提交验证码
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CaretRight, Refresh, QuestionFilled } from '@element-plus/icons-vue'
import collectionApi from '@/api/collection'

// 状态
const loading = ref(false)
const accountsLoading = ref(false)
const creating = ref(false)
const tasks = ref([])
const accounts = ref([])
const taskLogs = ref([])
const statusFilter = ref('')
const logsDialogVisible = ref(false)
const verificationDialogVisible = ref(false)
const verificationScreenshot = ref('')
const verificationCode = ref('')
const currentTask = ref(null)

// WebSocket连接
const wsConnections = ref({})

// 快速采集表单（v4.7.0）
const quickForm = reactive({
  platform: '',
  account_id: '',
  data_domains: [],
  date_preset: 'yesterday',
  debugMode: false  // v4.7.0: 调试模式
})

// 计算属性
const filteredAccounts = computed(() => {
  if (!quickForm.platform) return accounts.value
  return accounts.value.filter(acc => 
    acc.platform?.toLowerCase() === quickForm.platform.toLowerCase()
  )
})

const canCreateTask = computed(() => {
  return quickForm.platform && 
         quickForm.account_id && 
         quickForm.data_domains.length > 0
})

// 方法
const loadTasks = async () => {
  loading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    
    tasks.value = await collectionApi.getTasks(params)
    
    // 为运行中的任务建立WebSocket连接
    tasks.value
      .filter(t => t.status === 'running')
      .forEach(t => connectTaskWebSocket(t.task_id))
  } catch (error) {
    ElMessage.error('加载任务失败: ' + error.message)
  } finally {
    loading.value = false
  }
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
    const dateRange = getDateRange(quickForm.date_preset)
    
    // v4.7.0: 添加debugMode参数
    const task = await collectionApi.createTask({
      platform: quickForm.platform,
      account_id: quickForm.account_id,
      data_domains: quickForm.data_domains,
      sub_domains: [],  // v4.7.0: 子域数组
      granularity: 'daily',
      date_range: dateRange,
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
  verificationScreenshot.value = row.error_screenshot_path || ''
  verificationDialogVisible.value = true
}

const submitVerification = async () => {
  if (!currentTask.value) return
  
  try {
    await collectionApi.resumeTask(currentTask.value.task_id, verificationCode.value)
    ElMessage.success('任务已恢复')
    verificationDialogVisible.value = false
    loadTasks()
  } catch (error) {
    ElMessage.error('恢复失败: ' + error.message)
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
      }
      
      if (message.status === 'completed') {
        ElMessage.success(`任务 ${taskId.slice(0, 8)} 完成，采集 ${message.files_collected} 个文件`)
      } else if (message.status === 'failed') {
        ElMessage.error(`任务 ${taskId.slice(0, 8)} 失败: ${message.error_message}`)
      }
      
      disconnectTaskWebSocket(taskId)
    },
    onVerification: (message) => {
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.status = 'paused'
        currentTask.value = task
        verificationScreenshot.value = message.screenshot_path || ''
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
}

const getDateRange = (preset) => {
  const today = new Date()
  const formatDate = (d) => d.toISOString().split('T')[0]
  
  switch (preset) {
    case 'today':
      return { start_date: formatDate(today), end_date: formatDate(today) }
    case 'yesterday':
      const yesterday = new Date(today)
      yesterday.setDate(yesterday.getDate() - 1)
      return { start_date: formatDate(yesterday), end_date: formatDate(yesterday) }
    case 'last_7_days':
      const last7 = new Date(today)
      last7.setDate(last7.getDate() - 7)
      return { start_date: formatDate(last7), end_date: formatDate(today) }
    default:
      return {}
  }
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
    failed: 'danger', cancelled: 'warning', paused: 'warning',
    partial_success: 'warning'  // v4.7.0: 部分成功显示为warning
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    pending: '等待', queued: '排队', running: '运行中',
    completed: '完成', failed: '失败', cancelled: '已取消', paused: '暂停',
    partial_success: '部分成功'  // v4.7.0: 新状态
  }
  return labels[status] || status
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

// 生命周期
onMounted(() => {
  loadTasks()
  loadAccounts()
  
  // 定时刷新
  const interval = setInterval(loadTasks, 30000)
  onUnmounted(() => {
    clearInterval(interval)
    // 关闭所有WebSocket连接
    Object.keys(wsConnections.value).forEach(disconnectTaskWebSocket)
  })
})
</script>

<style scoped>
.collection-tasks {
  padding: 20px;
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

.tasks-section {
  background: white;
  border-radius: 12px;
  padding: 20px;
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
</style>

