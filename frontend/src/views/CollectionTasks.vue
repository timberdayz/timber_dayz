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
          <el-checkbox label="finance">财务</el-checkbox>
          <el-checkbox label="services">服务</el-checkbox>
          <el-checkbox label="inventory">库存</el-checkbox>
        </el-checkbox-group>

        <!-- 服务子域选择（仅当选择 services 时显示） -->
        <div v-if="quickForm.data_domains.includes('services')" class="sub-domain-section">
          <span style="color: white; font-size: 13px;">服务子域：</span>
          <el-checkbox-group v-model="quickForm.sub_domains" class="sub-domain-checkboxes">
            <el-checkbox label="ai_assistant">智能客服</el-checkbox>
            <el-checkbox label="agent">人工客服</el-checkbox>
          </el-checkbox-group>
          <el-tooltip 
            content="如果不选择子域，将采集通用服务数据"
            placement="top"
          >
            <el-icon style="color: #fff9;"><QuestionFilled /></el-icon>
          </el-tooltip>
        </div>

        <el-select v-model="quickForm.date_preset" placeholder="日期范围">
          <el-option label="今天" value="today" />
          <el-option label="昨天" value="yesterday" />
          <el-option label="最近7天" value="last_7_days" />
        </el-select>

        <!-- ⭐ Phase 9.1: 并行模式开关 -->
        <div class="parallel-mode-section">
          <el-checkbox v-model="quickForm.parallel_mode">
            <span style="color: white;">并行采集</span>
            <el-tooltip 
              content="同时采集多个数据域，速度提升3倍！适合采集多个域时使用。"
              placement="top"
            >
              <el-icon style="margin-left: 4px; color: #fff9;"><QuestionFilled /></el-icon>
            </el-tooltip>
          </el-checkbox>
          
          <div v-if="quickForm.parallel_mode" class="parallel-slider">
            <span style="color: white; font-size: 12px;">最大并行数：</span>
            <el-slider 
              v-model="quickForm.max_parallel" 
              :min="1" 
              :max="5" 
              :show-tooltip="true"
              :marks="{ 1: '1', 2: '2', 3: '3', 4: '4', 5: '5' }"
              style="width: 180px; margin-left: 8px;"
            />
            <span style="color: #fff9; font-size: 11px; margin-left: 8px;">
              (建议2-3)
            </span>
          </div>
        </div>

        <el-button 
          type="primary" 
          :loading="creating"
          :disabled="!canCreateTask"
          @click="createQuickTask"
        >
          <el-icon><CaretRight /></el-icon>
          {{ quickForm.parallel_mode ? '并行采集' : '开始采集' }}
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
        <el-table-column label="进度" width="180">
          <template #default="{ row }">
            <div class="progress-cell">
              <el-progress 
                :percentage="row.progress || 0" 
                :status="getProgressStatus(row.status)"
                :stroke-width="6"
              />
              <span class="progress-text">{{ row.current_step || '等待中' }}</span>
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

// v4.7.4: HTTP 轮询（替代 WebSocket）
const pollingIntervals = ref({})

// 快速采集表单
const quickForm = reactive({
  platform: '',
  account_id: '',
  data_domains: [],
  sub_domains: [],      // Phase 5: 服务子域（仅当选择 services 时使用）
  date_preset: 'yesterday',
  // ⭐ Phase 9.1: 并行模式配置
  parallel_mode: false,
  max_parallel: 3  // 默认3个并行
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
    
    // v4.7.4: 为运行中的任务启动 HTTP 轮询
    tasks.value
      .filter(t => t.status === 'running')
      .forEach(t => startPollingTask(t.task_id))
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
    
    // Phase 5: 构建任务参数
    const taskParams = {
      platform: quickForm.platform,
      account_id: quickForm.account_id,
      data_domains: quickForm.data_domains,
      granularity: 'daily',
      date_range: dateRange,
      // ⭐ Phase 9.1: 并行模式参数
      parallel_mode: quickForm.parallel_mode,
      max_parallel: quickForm.parallel_mode ? quickForm.max_parallel : 1
    }
    
    // Phase 5: 如果选择了 services 数据域且有子域，添加 sub_domains 参数
    if (quickForm.data_domains.includes('services') && quickForm.sub_domains.length > 0) {
      taskParams.sub_domains = quickForm.sub_domains
    }
    
    const task = await collectionApi.createTask(taskParams)
    
    ElMessage.success('任务创建成功')
    loadTasks()
    
    // v4.7.4: 启动 HTTP 轮询
    startPollingTask(task.task_id)
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

// v4.7.4: HTTP 轮询替代 WebSocket
const startPollingTask = (taskId) => {
  if (pollingIntervals.value[taskId]) return
  
  const interval = setInterval(async () => {
    try {
      // 获取任务详情（包含进度）
      const taskDetail = await collectionApi.getTask(taskId)
      
      const task = tasks.value.find(t => t.task_id === taskId)
      if (task) {
        task.progress = taskDetail.progress || 0
        task.current_step = taskDetail.current_step || ''
        task.status = taskDetail.status
        task.files_collected = taskDetail.files_collected
      }
      
      // 检查是否完成
      if (['completed', 'failed', 'cancelled'].includes(taskDetail.status)) {
        stopPollingTask(taskId)
        
        if (taskDetail.status === 'completed') {
          ElMessage.success(`任务 ${taskId.slice(0, 8)} 完成，采集 ${taskDetail.files_collected || 0} 个文件`)
        } else if (taskDetail.status === 'failed') {
          ElMessage.error(`任务 ${taskId.slice(0, 8)} 失败: ${taskDetail.error_message || '未知错误'}`)
        }
      }
      
      // 检查是否需要验证码
      if (taskDetail.status === 'paused' && taskDetail.verification_required) {
        stopPollingTask(taskId)
        currentTask.value = task
        verificationScreenshot.value = taskDetail.error_screenshot_path || ''
        verificationDialogVisible.value = true
      }
    } catch (error) {
      console.error('轮询任务状态失败:', error)
      // 继续轮询，不中断
    }
  }, 2000)  // 每2秒轮询一次
  
  pollingIntervals.value[taskId] = interval
}

const stopPollingTask = (taskId) => {
  const interval = pollingIntervals.value[taskId]
  if (interval) {
    clearInterval(interval)
    delete pollingIntervals.value[taskId]
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
    failed: 'danger', cancelled: 'warning', paused: 'warning'
  }
  return types[status] || 'info'
}

const getStatusLabel = (status) => {
  const labels = {
    pending: '等待', queued: '排队', running: '运行中',
    completed: '完成', failed: '失败', cancelled: '已取消', paused: '暂停'
  }
  return labels[status] || status
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return null
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
    // v4.7.4: 停止所有轮询
    Object.keys(pollingIntervals.value).forEach(stopPollingTask)
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

/* Phase 5: 服务子域选择样式 */
.sub-domain-section {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.sub-domain-checkboxes :deep(.el-checkbox__label) {
  color: white;
}

/* ⭐ Phase 9.1: 并行模式样式 */
.parallel-mode-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.parallel-slider {
  display: flex;
  align-items: center;
  padding-left: 24px;
}

.parallel-mode-section :deep(.el-checkbox__label) {
  color: white;
  font-weight: 500;
}

.parallel-mode-section :deep(.el-slider__runway) {
  background-color: rgba(255, 255, 255, 0.3);
}

.parallel-mode-section :deep(.el-slider__bar) {
  background-color: #fff;
}

.parallel-mode-section :deep(.el-slider__button) {
  border-color: #fff;
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

.progress-text {
  font-size: 12px;
  color: #999;
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

