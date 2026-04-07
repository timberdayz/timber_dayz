<template>
  <div class="notification-preferences-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Bell /></el-icon>
          通知偏好设置
        </h1>
        <p class="page-subtitle">管理您的通知偏好和桌面通知设置</p>
      </div>
      <div class="header-actions">
        <el-button @click="requestNotificationPermission" :disabled="notificationPermission !== 'default'">
          <el-icon><Setting /></el-icon>
          请求通知权限
        </el-button>
        <el-button @click="refreshPreferences" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 权限状态提示 -->
    <el-alert
      v-if="notificationPermission === 'denied'"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 20px;"
    >
      <template #title>
        浏览器通知权限已被拒绝
      </template>
      <template #default>
        请在浏览器设置中允许通知权限，以接收桌面通知。
        <el-link type="primary" :underline="false" @click="openBrowserSettings">
          查看如何开启
        </el-link>
      </template>
    </el-alert>

    <el-alert
      v-else-if="notificationPermission === 'granted'"
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 20px;"
    >
      <template #title>
        浏览器通知权限已授予
      </template>
    </el-alert>

    <!-- 通知偏好列表 -->
    <div class="preferences-content">
      <el-card shadow="hover">
        <template #header>
          <div class="card-header">
            <span>通知类型设置</span>
            <el-button type="primary" size="small" @click="saveAllPreferences" :loading="saving">
              保存所有设置
            </el-button>
          </div>
        </template>

        <!-- 加载状态 -->
        <div v-if="loading" class="loading-container">
          <el-skeleton :rows="5" animated />
        </div>

        <!-- 偏好列表 -->
        <div v-else class="preferences-list">
          <div
            v-for="(pref, index) in preferences"
            :key="pref.notification_type"
            class="preference-item"
          >
            <div class="preference-header">
              <div class="preference-title">
                <el-icon><Bell /></el-icon>
                <span>{{ getNotificationTypeLabel(pref.notification_type) }}</span>
              </div>
            </div>
            <div class="preference-controls">
              <el-form-item label="应用内通知">
                <el-switch
                  v-model="pref.enabled"
                  @change="onPreferenceChange(index)"
                />
              </el-form-item>
              <el-form-item label="桌面通知">
                <el-switch
                  v-model="pref.desktop_enabled"
                  :disabled="notificationPermission !== 'granted'"
                  @change="onPreferenceChange(index)"
                />
                <el-tooltip
                  v-if="notificationPermission !== 'granted'"
                  content="需要浏览器通知权限"
                  placement="top"
                >
                  <el-icon class="info-icon"><InfoFilled /></el-icon>
                </el-tooltip>
              </el-form-item>
            </div>
          </div>

          <!-- 空状态 -->
          <el-empty v-if="preferences.length === 0" description="暂无通知偏好设置" />
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Bell, Setting, Refresh, InfoFilled } from '@element-plus/icons-vue'
import usersApi from '@/api/users.js'

// 通知类型标签映射
const notificationTypeLabels = {
  user_registered: '新用户注册',
  user_approved: '用户审批通过',
  user_rejected: '用户审批拒绝',
  user_suspended: '用户被暂停',
  password_reset: '密码重置',
  account_locked: '账户被锁定',
  account_unlocked: '账户已解锁',
  system_alert: '系统告警'
}

// 状态
const loading = ref(false)
const saving = ref(false)
const preferences = ref([])
const notificationPermission = ref('default') // 'default', 'granted', 'denied'

// 获取通知类型标签
const getNotificationTypeLabel = (type) => {
  return notificationTypeLabels[type] || type
}

// 检查浏览器通知权限
const checkNotificationPermission = () => {
  if ('Notification' in window) {
    notificationPermission.value = Notification.permission
  } else {
    notificationPermission.value = 'unsupported'
  }
}

// 请求通知权限
const requestNotificationPermission = async () => {
  if (!('Notification' in window)) {
    ElMessage.warning('您的浏览器不支持通知功能')
    return
  }

  try {
    const permission = await Notification.requestPermission()
    notificationPermission.value = permission
    if (permission === 'granted') {
      ElMessage.success('通知权限已授予')
    } else {
      ElMessage.warning('通知权限被拒绝')
    }
  } catch (error) {
    console.error('[NotificationPreferences] Failed to request permission:', error)
    ElMessage.error('请求通知权限失败')
  }
}

// 打开浏览器设置指南
const openBrowserSettings = () => {
  ElMessage.info('请在浏览器地址栏左侧点击锁图标，然后选择"通知"并允许')
}

// 获取通知偏好列表
const fetchPreferences = async () => {
  loading.value = true
  try {
    const response = await usersApi.getNotificationPreferences()
    if (response && response.items) {
      preferences.value = response.items
    }
  } catch (error) {
    console.error('[NotificationPreferences] Failed to fetch preferences:', error)
    ElMessage.error('获取通知偏好失败')
  } finally {
    loading.value = false
  }
}

// 刷新偏好列表
const refreshPreferences = () => {
  fetchPreferences()
  checkNotificationPermission()
}

// 单个偏好变更
const onPreferenceChange = async (index) => {
  const pref = preferences.value[index]
  saving.value = true
  try {
    await usersApi.updateNotificationPreference(pref.notification_type, {
      enabled: pref.enabled,
      desktop_enabled: pref.desktop_enabled
    })
    ElMessage.success('设置已保存')
  } catch (error) {
    console.error('[NotificationPreferences] Failed to update preference:', error)
    ElMessage.error('保存设置失败')
    // 恢复原值
    await fetchPreferences()
  } finally {
    saving.value = false
  }
}

// 保存所有偏好
const saveAllPreferences = async () => {
  saving.value = true
  try {
    const updates = preferences.value.map(pref => ({
      notification_type: pref.notification_type,
      enabled: pref.enabled,
      desktop_enabled: pref.desktop_enabled
    }))
    await usersApi.updateNotificationPreferences(updates)
    ElMessage.success('所有设置已保存')
  } catch (error) {
    console.error('[NotificationPreferences] Failed to save preferences:', error)
    ElMessage.error('保存设置失败')
  } finally {
    saving.value = false
  }
}

// 生命周期
onMounted(() => {
  checkNotificationPermission()
  fetchPreferences()
})
</script>

<style scoped>
.notification-preferences-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}

.header-content {
  flex: 1;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: #303133;
}

.page-subtitle {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.preferences-content {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.loading-container {
  padding: 20px;
}

.preferences-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.preference-item {
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background-color: #fafafa;
}

.preference-header {
  margin-bottom: 16px;
}

.preference-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.preference-controls {
  display: flex;
  gap: 40px;
}

.preference-controls .el-form-item {
  margin-bottom: 0;
}

.info-icon {
  margin-left: 8px;
  color: #909399;
  cursor: help;
}
</style>

