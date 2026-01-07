<template>
  <div class="accounts">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>👤 账号管理中心</h1>
      <p>多平台账号管理 • 自动化登录 • 智能监控</p>
    </div>

    <!-- 账号概览 -->
    <el-row :gutter="20" class="overview-cards">
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><User /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ accountsStore.totalAccounts }}</div>
              <div class="card-label">总账号数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Check /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ accountsStore.activeAccounts }}</div>
              <div class="card-label">活跃账号</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Warning /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ accountsStore.problemAccounts }}</div>
              <div class="card-label">问题账号</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="overview-card">
          <div class="card-content">
            <div class="card-icon">
              <el-icon><Clock /></el-icon>
            </div>
            <div class="card-info">
              <div class="card-value">{{ accountsStore.avgLoginTime }}s</div>
              <div class="card-label">平均登录时间</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 账号操作 -->
    <el-row :gutter="20" class="account-actions">
      <el-col :span="8">
        <el-card class="action-card">
          <template #header>
            <span>账号管理</span>
          </template>
          <div class="action-content">
            <el-button 
              type="primary" 
              size="large"
              @click="showAddAccountDialog"
            >
              <el-icon><Plus /></el-icon>
              添加账号
            </el-button>
            <div class="action-description">
              添加新的平台账号
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="action-card">
          <template #header>
            <span>批量操作</span>
          </template>
          <div class="action-content">
            <el-button 
              type="warning" 
              size="large"
              @click="batchLogin"
              :loading="accountsStore.loading"
            >
              <el-icon><Key /></el-icon>
              批量登录
            </el-button>
            <div class="action-description">
              批量登录所有账号
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card class="action-card">
          <template #header>
            <span>健康检查</span>
          </template>
          <div class="action-content">
            <el-button 
              type="info" 
              size="large"
              @click="runHealthCheck"
              :loading="accountsStore.loading"
            >
              <el-icon><Monitor /></el-icon>
              健康检查
            </el-button>
            <div class="action-description">
              检查所有账号状态
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 账号列表 -->
    <el-card class="accounts-table">
      <template #header>
        <div class="card-header">
          <span>账号列表</span>
          <div class="header-actions">
            <el-select v-model="selectedPlatform" placeholder="选择平台" @change="filterAccounts">
              <el-option label="全部平台" value="" />
              <el-option label="SHOPEE" value="SHOPEE" />
              <el-option label="TIKTOK" value="TIKTOK" />
              <el-option label="AMAZON" value="AMAZON" />
              <el-option label="MIAOSHOU" value="MIAOSHOU" />
            </el-select>
            <el-button type="primary" size="small" @click="refreshAccounts">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>
      
      <el-table 
        :data="accountsStore.accounts" 
        style="width: 100%" 
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <el-tag :type="getPlatformTagType(row.platform)">
              {{ row.platform }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" min-width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="lastLogin" label="最后登录" width="180" />
        <el-table-column prop="loginCount" label="登录次数" width="100" />
        <el-table-column prop="healthScore" label="健康度" width="120">
          <template #default="{ row }">
            <el-progress 
              :percentage="row.healthScore" 
              :color="getHealthColor(row.healthScore)"
              :show-text="false"
            />
            <span class="health-text">{{ row.healthScore }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="loginAccount(row)">
              登录
            </el-button>
            <el-button type="warning" size="small" @click="editAccount(row)">
              编辑
            </el-button>
            <el-button type="danger" size="small" @click="deleteAccount(row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 批量操作 -->
      <div v-if="selectedAccounts.length > 0" class="batch-actions">
        <el-alert
          :title="`已选择 ${selectedAccounts.length} 个账号`"
          type="info"
          show-icon
          :closable="false"
        >
          <template #default>
            <div class="batch-buttons">
              <el-button type="primary" size="small" @click="batchLoginSelected">
                <el-icon><Key /></el-icon>
                批量登录
              </el-button>
              <el-button type="warning" size="small" @click="batchCheckHealth">
                <el-icon><Monitor /></el-icon>
                健康检查
              </el-button>
              <el-button type="danger" size="small" @click="batchDeleteSelected">
                <el-icon><Delete /></el-icon>
                批量删除
              </el-button>
            </div>
          </template>
        </el-alert>
      </div>
    </el-card>

    <!-- 添加账号对话框 -->
    <el-dialog
      v-model="addAccountDialogVisible"
      title="添加账号"
      width="500px"
      :before-close="handleCloseDialog"
    >
      <el-form :model="newAccount" :rules="accountRules" ref="accountFormRef" label-width="100px">
        <el-form-item label="平台" prop="platform">
          <el-select v-model="newAccount.platform" placeholder="选择平台">
            <el-option label="SHOPEE" value="SHOPEE" />
            <el-option label="TIKTOK" value="TIKTOK" />
            <el-option label="AMAZON" value="AMAZON" />
            <el-option label="MIAOSHOU" value="MIAOSHOU" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="newAccount.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="newAccount.password" type="password" placeholder="请输入密码" />
        </el-form-item>
        <el-form-item label="登录URL" prop="loginUrl">
          <el-input v-model="newAccount.loginUrl" placeholder="请输入登录URL" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="newAccount.notes" type="textarea" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="addAccountDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="addAccount">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User,
  Check,
  Warning,
  Clock,
  Plus,
  Key,
  Monitor,
  Refresh,
  Delete
} from '@element-plus/icons-vue'

const accountsStore = useAccountsStore()

// 状态
const selectedPlatform = ref('')
const selectedAccounts = ref([])
const addAccountDialogVisible = ref(false)
const accountFormRef = ref(null)

// 新账号表单
const newAccount = ref({
  platform: '',
  username: '',
  password: '',
  loginUrl: '',
  notes: ''
})

// 表单验证规则
const accountRules = {
  platform: [
    { required: true, message: '请选择平台', trigger: 'change' }
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ],
  loginUrl: [
    { required: true, message: '请输入登录URL', trigger: 'blur' }
  ]
}

// 初始化数据
const initData = async () => {
  try {
    await accountsStore.initData()
  } catch (error) {
    ElMessage.error('初始化数据失败')
  }
}

// 显示添加账号对话框
const showAddAccountDialog = () => {
  addAccountDialogVisible.value = true
  // 重置表单
  newAccount.value = {
    platform: '',
    username: '',
    password: '',
    loginUrl: '',
    notes: ''
  }
}

// 关闭对话框
const handleCloseDialog = () => {
  addAccountDialogVisible.value = false
  if (accountFormRef.value) {
    accountFormRef.value.resetFields()
  }
}

// 添加账号
const addAccount = async () => {
  try {
    await accountFormRef.value.validate()
    
    await accountsStore.addAccount(newAccount.value)
    ElMessage.success('账号添加成功')
    addAccountDialogVisible.value = false
  } catch (error) {
    if (error !== false) { // 不是表单验证错误
      ElMessage.error('添加账号失败')
    }
  }
}

// 批量登录
const batchLogin = async () => {
  try {
    await ElMessageBox.confirm('确定要批量登录所有账号吗？', '确认操作', {
      type: 'warning'
    })
    
    await accountsStore.batchLogin()
    ElMessage.success('批量登录完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量登录失败')
    }
  }
}

// 运行健康检查
const runHealthCheck = async () => {
  try {
    await accountsStore.runHealthCheck()
    ElMessage.success('健康检查完成')
  } catch (error) {
    ElMessage.error('健康检查失败')
  }
}

// 筛选账号
const filterAccounts = () => {
  accountsStore.filterAccounts(selectedPlatform.value)
}

// 刷新账号
const refreshAccounts = async () => {
  try {
    await accountsStore.refreshAccounts()
    ElMessage.success('账号列表已刷新')
  } catch (error) {
    ElMessage.error('刷新失败')
  }
}

// 登录账号
const loginAccount = async (account) => {
  try {
    await accountsStore.loginAccount(account.id)
    ElMessage.success(`${account.username} 登录成功`)
  } catch (error) {
    ElMessage.error('登录失败')
  }
}

// 编辑账号
const editAccount = (account) => {
  ElMessage.info(`编辑账号 ${account.username}`)
}

// 删除账号
const deleteAccount = async (account) => {
  try {
    await ElMessageBox.confirm(`确定要删除账号 ${account.username} 吗？`, '确认删除', {
      type: 'warning'
    })
    
    await accountsStore.deleteAccount(account.id)
    ElMessage.success('账号已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 批量操作
const handleSelectionChange = (selection) => {
  selectedAccounts.value = selection
}

const batchLoginSelected = async () => {
  try {
    await ElMessageBox.confirm(`确定要登录选中的 ${selectedAccounts.value.length} 个账号吗？`, '确认操作', {
      type: 'warning'
    })
    
    await accountsStore.batchLoginSelected(selectedAccounts.value)
    ElMessage.success('批量登录完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量登录失败')
    }
  }
}

const batchCheckHealth = async () => {
  try {
    await accountsStore.batchCheckHealth(selectedAccounts.value)
    ElMessage.success('健康检查完成')
  } catch (error) {
    ElMessage.error('健康检查失败')
  }
}

const batchDeleteSelected = async () => {
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedAccounts.value.length} 个账号吗？`, '确认删除', {
      type: 'warning'
    })
    
    await accountsStore.batchDeleteSelected(selectedAccounts.value)
    ElMessage.success('批量删除完成')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

// 工具函数
const getPlatformTagType = (platform) => {
  const typeMap = {
    'SHOPEE': 'success',
    'TIKTOK': 'primary',
    'AMAZON': 'warning',
    'MIAOSHOU': 'info'
  }
  return typeMap[platform] || 'info'
}

const getStatusType = (status) => {
  const typeMap = {
    'online': 'success',
    'offline': 'info',
    'error': 'danger'
  }
  return typeMap[status] || 'info'
}

const getStatusText = (status) => {
  const textMap = {
    'online': '在线',
    'offline': '离线',
    'error': '错误'
  }
  return textMap[status] || status
}

const getHealthColor = (healthScore) => {
  if (healthScore >= 90) return '#27ae60'
  if (healthScore >= 70) return '#f39c12'
  return '#e74c3c'
}

onMounted(() => {
  initData()
})
</script>

<style scoped>
.accounts {
  padding: var(--content-padding);
}

.page-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  background: var(--gradient-primary);
  color: white;
  padding: var(--spacing-2xl);
  border-radius: var(--border-radius-lg);
}

.page-header h1 {
  margin: 0 0 var(--spacing-base) 0;
  font-size: var(--font-size-4xl);
  font-weight: var(--font-weight-bold);
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: var(--font-size-lg);
}

.overview-cards {
  margin-bottom: var(--spacing-2xl);
}

.overview-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.card-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
}

.card-icon {
  font-size: var(--font-size-3xl);
  color: var(--secondary-color);
}

.card-value {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.card-label {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-xs);
}

.account-actions {
  margin-bottom: var(--spacing-2xl);
}

.action-card {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.action-content {
  text-align: center;
}

.action-description {
  margin-top: var(--spacing-base);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.accounts-table {
  border-radius: var(--border-radius-lg);
  box-shadow: var(--shadow-base);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: var(--spacing-base);
  align-items: center;
}

.health-text {
  margin-left: var(--spacing-sm);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

.batch-actions {
  margin-top: var(--spacing-lg);
}

.batch-buttons {
  display: flex;
  gap: var(--spacing-base);
  margin-top: var(--spacing-base);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .accounts {
    padding: var(--spacing-base);
  }
  
  .overview-cards .el-col {
    margin-bottom: var(--spacing-base);
  }
  
  .account-actions .el-col {
    margin-bottom: var(--spacing-base);
  }
}
</style>
