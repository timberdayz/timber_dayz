<template>
  <div class="personal-settings">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><User /></el-icon>
          个人设置
        </h1>
        <p class="page-subtitle">管理您的个人信息和偏好设置</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="saveSettings">
          <el-icon><Check /></el-icon>
          保存设置
        </el-button>
        <el-button @click="resetSettings">
          <el-icon><RefreshLeft /></el-icon>
          重置
        </el-button>
      </div>
    </div>

    <!-- 功能导航区域 -->
    <div class="function-nav">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="👤 个人信息" name="profile">
          <!-- 个人信息内容 -->
          <div class="profile-content">
            <el-row :gutter="20">
              <el-col :span="8">
                <el-card class="profile-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>头像设置</span>
                    </div>
                  </template>
                  <div class="avatar-section">
                    <div class="avatar-container">
                      <el-avatar :size="120" :src="userProfile.avatar" @click="selectAvatar">
                        <el-icon><User /></el-icon>
                      </el-avatar>
                      <div class="avatar-actions">
                        <el-button type="primary" size="small" @click="selectAvatar">
                          更换头像
                        </el-button>
                        <el-button size="small" @click="removeAvatar">
                          移除头像
                        </el-button>
                      </div>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="16">
                <el-card class="profile-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>基本信息</span>
                    </div>
                  </template>
                  <div class="profile-form">
                    <el-form :model="userProfile" label-width="100px">
                      <el-form-item label="用户名">
                        <el-input v-model="userProfile.username" disabled></el-input>
                      </el-form-item>
                      <el-form-item label="姓名">
                        <el-input v-model="userProfile.name" placeholder="请输入姓名"></el-input>
                      </el-form-item>
                      <el-form-item label="邮箱">
                        <el-input v-model="userProfile.email" placeholder="请输入邮箱"></el-input>
                      </el-form-item>
                      <el-form-item label="电话">
                        <el-input v-model="userProfile.phone" placeholder="请输入电话"></el-input>
                      </el-form-item>
                      <el-form-item label="部门">
                        <el-select v-model="userProfile.department" placeholder="请选择部门">
                          <el-option label="技术部" value="tech"></el-option>
                          <el-option label="运营部" value="operation"></el-option>
                          <el-option label="财务部" value="finance"></el-option>
                          <el-option label="人事部" value="hr"></el-option>
                          <el-option label="市场部" value="marketing"></el-option>
                        </el-select>
                      </el-form-item>
                      <el-form-item label="职位">
                        <el-input v-model="userProfile.position" placeholder="请输入职位"></el-input>
                      </el-form-item>
                    </el-form>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="🔐 安全设置" name="security">
          <!-- 安全设置内容 -->
          <div class="security-content">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-card class="security-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>修改密码</span>
                    </div>
                  </template>
                  <div class="password-form">
                    <el-form :model="passwordForm" :rules="passwordRules" ref="passwordFormRef" label-width="100px">
                      <el-form-item label="当前密码" prop="currentPassword">
                        <el-input v-model="passwordForm.currentPassword" type="password" placeholder="请输入当前密码"></el-input>
                      </el-form-item>
                      <el-form-item label="新密码" prop="newPassword">
                        <el-input v-model="passwordForm.newPassword" type="password" placeholder="请输入新密码"></el-input>
                      </el-form-item>
                      <el-form-item label="确认密码" prop="confirmPassword">
                        <el-input v-model="passwordForm.confirmPassword" type="password" placeholder="请再次输入新密码"></el-input>
                      </el-form-item>
                      <el-form-item>
                        <el-button type="primary" @click="changePassword">修改密码</el-button>
                        <el-button @click="resetPasswordForm">重置</el-button>
                      </el-form-item>
                    </el-form>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="security-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>登录安全</span>
                    </div>
                  </template>
                  <div class="security-settings">
                    <div class="security-item">
                      <div class="security-info">
                        <div class="security-label">双因子认证</div>
                        <div class="security-desc">为您的账号添加额外的安全保护</div>
                      </div>
                      <el-switch v-model="securitySettings.twoFactorAuth" @change="toggleTwoFactor"></el-switch>
                    </div>
                    <div class="security-item">
                      <div class="security-info">
                        <div class="security-label">登录通知</div>
                        <div class="security-desc">当账号在新设备登录时发送通知</div>
                      </div>
                      <el-switch v-model="securitySettings.loginNotification" @change="toggleLoginNotification"></el-switch>
                    </div>
                    <div class="security-item">
                      <div class="security-info">
                        <div class="security-label">会话超时</div>
                        <div class="security-desc">设置自动登出的时间</div>
                      </div>
                      <el-select v-model="securitySettings.sessionTimeout" style="width: 120px;">
                        <el-option label="30分钟" value="30"></el-option>
                        <el-option label="1小时" value="60"></el-option>
                        <el-option label="2小时" value="120"></el-option>
                        <el-option label="4小时" value="240"></el-option>
                        <el-option label="8小时" value="480"></el-option>
                      </el-select>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="⚙️ 偏好设置" name="preferences">
          <!-- 偏好设置内容 -->
          <div class="preferences-content">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-card class="preference-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>界面设置</span>
                    </div>
                  </template>
                  <div class="preference-settings">
                    <div class="preference-item">
                      <div class="preference-info">
                        <div class="preference-label">主题模式</div>
                        <div class="preference-desc">选择您喜欢的界面主题</div>
                      </div>
                      <el-select v-model="preferences.theme" style="width: 120px;">
                        <el-option label="浅色主题" value="light"></el-option>
                        <el-option label="深色主题" value="dark"></el-option>
                        <el-option label="自动切换" value="auto"></el-option>
                      </el-select>
                    </div>
                    <div class="preference-item">
                      <div class="preference-info">
                        <div class="preference-label">语言设置</div>
                        <div class="preference-desc">选择系统显示语言</div>
                      </div>
                      <el-select v-model="preferences.language" style="width: 120px;">
                        <el-option label="简体中文" value="zh-CN"></el-option>
                        <el-option label="English" value="en-US"></el-option>
                        <el-option label="繁體中文" value="zh-TW"></el-option>
                      </el-select>
                    </div>
                    <div class="preference-item">
                      <div class="preference-info">
                        <div class="preference-label">时区设置</div>
                        <div class="preference-desc">设置您所在的时区</div>
                      </div>
                      <el-select v-model="preferences.timezone" style="width: 200px;">
                        <el-option label="北京时间 (UTC+8)" value="Asia/Shanghai"></el-option>
                        <el-option label="纽约时间 (UTC-5)" value="America/New_York"></el-option>
                        <el-option label="伦敦时间 (UTC+0)" value="Europe/London"></el-option>
                        <el-option label="东京时间 (UTC+9)" value="Asia/Tokyo"></el-option>
                      </el-select>
                    </div>
                    <div class="preference-item">
                      <div class="preference-info">
                        <div class="preference-label">货币设置</div>
                        <div class="preference-desc">设置默认显示货币</div>
                      </div>
                      <el-select v-model="preferences.currency" style="width: 120px;">
                        <el-option label="人民币 (CNY)" value="CNY"></el-option>
                        <el-option label="美元 (USD)" value="USD"></el-option>
                        <el-option label="欧元 (EUR)" value="EUR"></el-option>
                        <el-option label="日元 (JPY)" value="JPY"></el-option>
                      </el-select>
                    </div>
                  </div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card class="preference-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>通知设置</span>
                    </div>
                  </template>
                  <div class="notification-settings">
                    <div class="notification-item">
                      <div class="notification-info">
                        <div class="notification-label">邮件通知</div>
                        <div class="notification-desc">接收系统邮件通知</div>
                      </div>
                      <el-switch v-model="notifications.email" @change="toggleEmailNotification"></el-switch>
                    </div>
                    <div class="notification-item">
                      <div class="notification-info">
                        <div class="notification-label">系统通知</div>
                        <div class="notification-desc">接收系统内通知</div>
                      </div>
                      <el-switch v-model="notifications.system" @change="toggleSystemNotification"></el-switch>
                    </div>
                    <div class="notification-item">
                      <div class="notification-info">
                        <div class="notification-label">数据更新通知</div>
                        <div class="notification-desc">数据同步完成时通知</div>
                      </div>
                      <el-switch v-model="notifications.dataUpdate" @change="toggleDataUpdateNotification"></el-switch>
                    </div>
                    <div class="notification-item">
                      <div class="notification-info">
                        <div class="notification-label">错误告警</div>
                        <div class="notification-desc">系统错误时立即通知</div>
                      </div>
                      <el-switch v-model="notifications.errorAlert" @change="toggleErrorAlert"></el-switch>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>

        <el-tab-pane label="📊 使用统计" name="statistics">
          <!-- 使用统计内容 -->
          <div class="statistics-content">
            <el-row :gutter="20">
              <el-col :span="24">
                <el-card class="statistics-card" shadow="hover">
                  <template #header>
                    <div class="card-header">
                      <span>使用统计</span>
                    </div>
                  </template>
                  <div class="statistics-info">
                    <el-row :gutter="20">
                      <el-col :span="6">
                        <div class="stat-item">
                          <div class="stat-icon">
                            <el-icon><Calendar /></el-icon>
                          </div>
                          <div class="stat-content">
                            <div class="stat-label">注册时间</div>
                            <div class="stat-value">{{ userStats.registerDate }}</div>
                          </div>
                        </div>
                      </el-col>
                      <el-col :span="6">
                        <div class="stat-item">
                          <div class="stat-icon">
                            <el-icon><Clock /></el-icon>
                          </div>
                          <div class="stat-content">
                            <div class="stat-label">最后登录</div>
                            <div class="stat-value">{{ userStats.lastLogin }}</div>
                          </div>
                        </div>
                      </el-col>
                      <el-col :span="6">
                        <div class="stat-item">
                          <div class="stat-icon">
                            <el-icon><View /></el-icon>
                          </div>
                          <div class="stat-content">
                            <div class="stat-label">登录次数</div>
                            <div class="stat-value">{{ userStats.loginCount }}</div>
                          </div>
                        </div>
                      </el-col>
                      <el-col :span="6">
                        <div class="stat-item">
                          <div class="stat-icon">
                            <el-icon><Timer /></el-icon>
                          </div>
                          <div class="stat-content">
                            <div class="stat-label">在线时长</div>
                            <div class="stat-value">{{ userStats.onlineTime }}</div>
                          </div>
                        </div>
                      </el-col>
                    </el-row>
                  </div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
// 图标已通过main.js全局注册
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()

// 响应式数据
const activeTab = ref('profile')
const passwordFormRef = ref(null)

// 用户资料数据
const userProfile = reactive({
  username: 'admin',
  name: '管理员',
  email: 'admin@xihong-erp.com',
  phone: '13800138000',
  department: 'tech',
  position: '系统管理员',
  avatar: ''
})

// 密码修改表单
const passwordForm = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})

// 密码验证规则
const passwordRules = {
  currentPassword: [
    { required: true, message: '请输入当前密码', trigger: 'blur' }
  ],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.newPassword) {
          callback(new Error('两次输入密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

// 安全设置
const securitySettings = reactive({
  twoFactorAuth: false,
  loginNotification: true,
  sessionTimeout: '60'
})

// 偏好设置
const preferences = reactive({
  theme: 'light',
  language: 'zh-CN',
  timezone: 'Asia/Shanghai',
  currency: 'CNY'
})

// 通知设置
const notifications = reactive({
  email: true,
  system: true,
  dataUpdate: false,
  errorAlert: true
})

// 用户统计
const userStats = reactive({
  registerDate: '2024-01-01',
  lastLogin: '2024-01-16 10:30',
  loginCount: 156,
  onlineTime: '2小时30分钟'
})

// 方法
const handleTabChange = (tabName) => {
  console.log('切换到标签页:', tabName)
}

const saveSettings = () => {
  ElMessage.success('设置保存成功')
  // 这里可以调用API保存设置
}

const resetSettings = () => {
  ElMessageBox.confirm('确定要重置所有设置吗？', '确认重置', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    ElMessage.success('设置已重置')
    // 重置所有设置到默认值
  })
}

const selectAvatar = () => {
  ElMessage.info('头像选择功能开发中')
}

const removeAvatar = () => {
  userProfile.avatar = ''
  ElMessage.success('头像已移除')
}

const changePassword = () => {
  passwordFormRef.value.validate((valid) => {
    if (valid) {
      ElMessage.success('密码修改成功')
      resetPasswordForm()
    } else {
      ElMessage.error('请检查输入信息')
    }
  })
}

const resetPasswordForm = () => {
  passwordForm.currentPassword = ''
  passwordForm.newPassword = ''
  passwordForm.confirmPassword = ''
  passwordFormRef.value?.resetFields()
}

const toggleTwoFactor = (value) => {
  ElMessage.success(`双因子认证已${value ? '开启' : '关闭'}`)
}

const toggleLoginNotification = (value) => {
  ElMessage.success(`登录通知已${value ? '开启' : '关闭'}`)
}

const toggleEmailNotification = (value) => {
  ElMessage.success(`邮件通知已${value ? '开启' : '关闭'}`)
}

const toggleSystemNotification = (value) => {
  ElMessage.success(`系统通知已${value ? '开启' : '关闭'}`)
}

const toggleDataUpdateNotification = (value) => {
  ElMessage.success(`数据更新通知已${value ? '开启' : '关闭'}`)
}

const toggleErrorAlert = (value) => {
  ElMessage.success(`错误告警已${value ? '开启' : '关闭'}`)
}

// 组件挂载
onMounted(() => {
  console.log('个人设置页面已加载')
  // 从用户store加载用户信息
  if (userStore.userInfo) {
    Object.assign(userProfile, userStore.userInfo)
  }
})
</script>

<style scoped>
.personal-settings {
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
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-description {
  margin: 8px 0 0 0;
  opacity: 0.9;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.function-nav {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.profile-card, .security-card, .preference-card, .statistics-card {
  border-radius: 8px;
  border: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.profile-card:hover, .security-card:hover, .preference-card:hover, .statistics-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #303133;
}

.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0;
}

.avatar-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 15px;
}

.avatar-actions {
  display: flex;
  gap: 10px;
}

.profile-form {
  padding: 10px 0;
}

.password-form {
  padding: 10px 0;
}

.security-settings, .preference-settings, .notification-settings {
  padding: 10px 0;
}

.security-item, .preference-item, .notification-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 0;
  border-bottom: 1px solid #f0f0f0;
}

.security-item:last-child, .preference-item:last-child, .notification-item:last-child {
  border-bottom: none;
}

.security-info, .preference-info, .notification-info {
  flex: 1;
}

.security-label, .preference-label, .notification-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}

.security-desc, .preference-desc, .notification-desc {
  font-size: 12px;
  color: #909399;
}

.statistics-info {
  padding: 20px 0;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.stat-item:hover {
  background: #e9ecef;
  transform: translateY(-2px);
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 18px;
}

.stat-content {
  flex: 1;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .personal-settings {
    padding: 10px;
  }
  
  .page-header {
    padding: 15px;
  }
  
  .page-title {
    font-size: 20px;
  }
  
  .header-actions {
    flex-direction: column;
    gap: 5px;
  }
  
  .avatar-actions {
    flex-direction: column;
    width: 100%;
  }
  
  .security-item, .preference-item, .notification-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
