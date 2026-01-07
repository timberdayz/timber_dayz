<template>
  <el-popover
    v-model:visible="showPopover"
    placement="bottom-end"
    :width="380"
    trigger="click"
    popper-class="notification-popover"
  >
    <template #reference>
      <el-badge 
        :value="unreadCount" 
        :hidden="unreadCount === 0"
        :max="99"
        class="notification-badge"
      >
        <el-button 
          :icon="Bell" 
          circle 
          class="notification-button"
          :class="{ 'has-unread': unreadCount > 0 }"
        />
      </el-badge>
    </template>
    
    <div class="notification-panel">
      <!-- 面板头部 -->
      <div class="panel-header">
        <span class="title">Notifications</span>
        <el-button 
          v-if="unreadCount > 0"
          type="primary" 
          link 
          size="small"
          @click="handleMarkAllRead"
          :loading="markingAllRead"
        >
          Mark all as read
        </el-button>
      </div>
      
      <!-- 通知列表 -->
      <div class="notification-list" v-loading="loading">
        <template v-if="notifications.length > 0">
          <div
            v-for="notification in notifications"
            :key="notification.notification_id"
            class="notification-item"
            :class="{ 'unread': !notification.is_read }"
            @click="handleNotificationClick(notification)"
          >
            <div class="notification-icon">
              <el-icon :size="20">
                <UserFilled v-if="notification.notification_type === 'user_registered'" />
                <CircleCheck v-else-if="notification.notification_type === 'user_approved'" />
                <CircleClose v-else-if="notification.notification_type === 'user_rejected'" />
                <Warning v-else-if="notification.notification_type === 'system_alert'" />
                <Key v-else-if="notification.notification_type === 'password_reset'" />
                <Bell v-else />
              </el-icon>
            </div>
            <div class="notification-content">
              <div class="notification-title">{{ notification.title }}</div>
              <div class="notification-text">{{ truncateContent(notification.content) }}</div>
              <div class="notification-time">{{ formatTime(notification.created_at) }}</div>
              <!-- v4.19.0: 快速操作按钮 -->
              <div v-if="notification.actions && notification.actions.length > 0" class="notification-actions" @click.stop>
                <el-button
                  v-for="action in notification.actions"
                  :key="action.action_type"
                  :type="getActionButtonType(action.style)"
                  size="small"
                  @click="handleQuickAction(notification, action)"
                  :loading="actionLoading[`${notification.notification_id}_${action.action_type}`]"
                >
                  {{ action.label }}
                </el-button>
              </div>
            </div>
            <div v-if="!notification.is_read" class="unread-dot"></div>
          </div>
        </template>
        <div v-else class="empty-state">
          <el-icon :size="48" color="#c0c4cc"><Bell /></el-icon>
          <p>No notifications</p>
        </div>
      </div>
      
      <!-- 面板底部 -->
      <div class="panel-footer">
        <el-button type="primary" link @click="goToNotifications">
          View all notifications
        </el-button>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { 
  Bell, 
  UserFilled, 
  CircleCheck, 
  CircleClose, 
  Warning,
  Key
} from '@element-plus/icons-vue'
import notificationsApi from '@/api/notifications.js'
import usersApi from '@/api/users.js'
import { useNotificationWebSocket } from '@/services/notificationWebSocket'

const router = useRouter()

// 状态
const showPopover = ref(false)
const loading = ref(false)
const markingAllRead = ref(false)
const notifications = ref([])
const actionLoading = ref({}) // v4.19.0: 快速操作加载状态

// WebSocket 通知流（v4.19.0）
const {
  unreadCount,
  connect: connectNotificationWS,
  disconnect: disconnectNotificationWS,
  subscribe,
  fetchUnreadCountOnce
} = useNotificationWebSocket()

let unsubscribe = null

// v4.19.0: 浏览器原生通知
const notificationPreferences = ref({}) // notification_type -> { enabled, desktop_enabled }
const notificationPermission = ref('default') // 'default', 'granted', 'denied'

// 检查浏览器通知权限
const checkNotificationPermission = () => {
  if ('Notification' in window) {
    notificationPermission.value = Notification.permission
  }
}

// 获取通知偏好
const fetchNotificationPreferences = async () => {
  try {
    const response = await usersApi.getNotificationPreferences()
    if (response && response.items) {
      const prefs = {}
      response.items.forEach(pref => {
        prefs[pref.notification_type] = {
          enabled: pref.enabled,
          desktop_enabled: pref.desktop_enabled
        }
      })
      notificationPreferences.value = prefs
    }
  } catch (error) {
    console.error('[NotificationBell] Failed to fetch preferences:', error)
  }
}

// v4.19.0 P1安全要求：通知内容验证（防止 XSS）
const sanitizeNotificationContent = (text) => {
  if (!text) return ''
  // 移除 HTML 标签
  const div = document.createElement('div')
  div.textContent = text
  let sanitized = div.textContent || div.innerText || ''
  // 转义特殊字符（虽然 textContent 已处理，但额外确保）
  sanitized = sanitized
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
  // 限制长度（标题最多 200 字符，内容最多 1000 字符）
  return sanitized
}

// 显示桌面通知
const showDesktopNotification = (notification) => {
  // 检查浏览器支持
  if (!('Notification' in window)) {
    return
  }

  // 检查权限
  if (Notification.permission !== 'granted') {
    return
  }

  // 检查通知偏好
  const pref = notificationPreferences.value[notification.notification_type]
  if (!pref || !pref.desktop_enabled) {
    return
  }

  // v4.19.0 P1安全要求：验证并清理通知内容
  const title = sanitizeNotificationContent(notification.title).substring(0, 200)
  const body = sanitizeNotificationContent(notification.content).substring(0, 1000)

  try {
    const notificationInstance = new Notification(title, {
      body: body,
      icon: '/favicon.ico', // 可以配置通知图标
      badge: '/favicon.ico',
      tag: `notification-${notification.notification_id}`, // 防止重复通知
      requireInteraction: false,
      silent: false // 可以配置通知声音
    })

    // 通知点击跳转
    notificationInstance.onclick = () => {
      window.focus()
      notificationInstance.close()
      handleNotificationClick(notification)
    }

    // 自动关闭（5秒）
    setTimeout(() => {
      notificationInstance.close()
    }, 5000)
  } catch (error) {
    console.error('[NotificationBell] Failed to show desktop notification:', error)
  }
}

// 获取通知列表
const fetchNotifications = async () => {
  loading.value = true
  try {
    const response = await notificationsApi.getNotifications({
      page: 1,
      page_size: 10
    })
    if (response && response.items) {
      notifications.value = response.items
      // 未读数量以接口返回为准（WebSocket 仅做前端即时增量）
      if (typeof response.unread_count === 'number') {
        unreadCount.value = response.unread_count
      }
    }
  } catch (error) {
    console.error('[NotificationBell] Failed to fetch notifications:', error)
  } finally {
    loading.value = false
  }
}

// 标记所有为已读
const handleMarkAllRead = async () => {
  markingAllRead.value = true
  try {
    await notificationsApi.markAllAsRead()
    // 更新本地状态
    notifications.value = notifications.value.map(n => ({
      ...n,
      is_read: true
    }))
    unreadCount.value = 0
    ElMessage.success('All notifications marked as read')
  } catch (error) {
    console.error('[NotificationBell] Failed to mark all as read:', error)
    ElMessage.error('Failed to mark notifications as read')
  } finally {
    markingAllRead.value = false
  }
}

// 点击单个通知
const handleNotificationClick = async (notification) => {
  // 如果未读，标记为已读
  if (!notification.is_read) {
    try {
      await notificationsApi.markAsRead(notification.notification_id)
      notification.is_read = true
      unreadCount.value = Math.max(0, (unreadCount.value || 0) - 1)
    } catch (error) {
      console.error('[NotificationBell] Failed to mark as read:', error)
    }
  }
  
  // 根据通知类型跳转
  showPopover.value = false
  
  switch (notification.notification_type) {
    case 'user_registered':
      // 跳转到用户审批页面
      router.push('/system-settings/user-approval')
      break
    case 'user_approved':
    case 'user_rejected':
    case 'password_reset':
      // 跳转到通知列表页面
      router.push('/messages/notifications')
      break
    default:
      router.push('/messages/notifications')
  }
}

// 跳转到通知页面
const goToNotifications = () => {
  showPopover.value = false
  router.push('/messages/notifications')
}

// 截断内容
const truncateContent = (content) => {
  if (!content) return ''
  return content.length > 60 ? content.substring(0, 60) + '...' : content
}

// 格式化时间
const formatTime = (dateString) => {
  if (!dateString) return ''
  
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins} min ago`
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  
  return date.toLocaleDateString()
}

// 当 popover 显示时获取完整通知列表
const onPopoverShow = () => {
  fetchNotifications()
}

// v4.19.0: 获取按钮类型
const getActionButtonType = (style) => {
  const styleMap = {
    'primary': 'primary',
    'success': 'success',
    'warning': 'warning',
    'danger': 'danger',
    'default': ''
  }
  return styleMap[style] || ''
}

// v4.19.0: 处理快速操作
const handleQuickAction = async (notification, action) => {
  const loadingKey = `${notification.notification_id}_${action.action_type}`
  
  // 如果需要确认
  if (action.confirm) {
    // 对于拒绝操作，需要输入原因
    if (action.action_type === 'reject_user') {
      const { ElMessageBox } = await import('element-plus')
      try {
        const { value } = await ElMessageBox.prompt(
          action.confirm_message || 'Please provide a reason',
          'Confirm Action',
          {
            confirmButtonText: 'Confirm',
            cancelButtonText: 'Cancel',
            inputPlaceholder: 'Rejection reason',
            inputValidator: (value) => {
              if (!value || value.trim().length === 0) {
                return 'Please provide a reason'
              }
              return true
            }
          }
        )
        await executeQuickAction(notification, action.action_type, value.trim(), loadingKey)
      } catch (e) {
        // 用户取消
        return
      }
    } else {
      // 其他操作的确认对话框
      const { ElMessageBox } = await import('element-plus')
      try {
        await ElMessageBox.confirm(
          action.confirm_message || 'Are you sure?',
          'Confirm Action',
          {
            confirmButtonText: 'Confirm',
            cancelButtonText: 'Cancel',
            type: 'warning'
          }
        )
        await executeQuickAction(notification, action.action_type, null, loadingKey)
      } catch (e) {
        // 用户取消
        return
      }
    }
  } else {
    await executeQuickAction(notification, action.action_type, null, loadingKey)
  }
}

// v4.19.0: 执行快速操作
const executeQuickAction = async (notification, actionType, reason, loadingKey) => {
  actionLoading.value[loadingKey] = true
  
  try {
    const response = await notificationsApi.executeAction(
      notification.notification_id,
      actionType,
      reason
    )
    
    if (response && response.success) {
      ElMessage.success(response.message || 'Operation successful')
      
      // 标记通知为已读并移除操作按钮
      notification.is_read = true
      notification.actions = null
      
      // 更新未读数量
      unreadCount.value = Math.max(0, (unreadCount.value || 0) - 1)
    } else {
      ElMessage.error(response?.message || 'Operation failed')
    }
  } catch (error) {
    console.error('[NotificationBell] Quick action failed:', error)
    ElMessage.error(error.response?.data?.detail || 'Operation failed')
  } finally {
    actionLoading.value[loadingKey] = false
  }
}

// 生命周期
onMounted(() => {
  // v4.19.0: 检查浏览器通知权限
  checkNotificationPermission()
  
  // v4.19.0: 获取通知偏好
  fetchNotificationPreferences()
  
  // 建立 WebSocket 连接并同步一次未读数量
  connectNotificationWS()
  void fetchUnreadCountOnce()

  // 订阅新通知推送，插入到当前列表顶部（仅在已加载列表的情况下）
  unsubscribe = subscribe((notification) => {
    if (Array.isArray(notifications.value) && notifications.value.length > 0) {
      notifications.value = [
        { ...notification, is_read: false },
        ...notifications.value
      ].slice(0, 10)
    }
    
    // v4.19.0: 显示桌面通知
    showDesktopNotification(notification)
  })
})

onUnmounted(() => {
  disconnectNotificationWS()
  if (unsubscribe) {
    unsubscribe()
    unsubscribe = null
  }
})

watch(showPopover, (newVal) => {
  if (newVal) {
    onPopoverShow()
  }
})
</script>

<style scoped>
.notification-badge {
  margin-right: 8px;
}

.notification-button {
  background-color: rgba(255, 255, 255, 0.1);
  border: none;
  color: white;
  transition: all 0.3s;
}

.notification-button:hover {
  background-color: rgba(255, 255, 255, 0.2);
  color: white;
}

.notification-button.has-unread {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(255, 255, 255, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(255, 255, 255, 0);
  }
}

.notification-panel {
  display: flex;
  flex-direction: column;
  max-height: 480px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
}

.panel-header .title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.notification-list {
  flex: 1;
  overflow-y: auto;
  max-height: 360px;
  min-height: 100px;
}

.notification-item {
  display: flex;
  align-items: flex-start;
  padding: 12px 16px;
  cursor: pointer;
  transition: background-color 0.2s;
  border-bottom: 1px solid #f2f3f5;
  position: relative;
}

.notification-item:hover {
  background-color: #f5f7fa;
}

.notification-item.unread {
  background-color: #ecf5ff;
}

.notification-item.unread:hover {
  background-color: #d9ecff;
}

.notification-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: #e6e8eb;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  flex-shrink: 0;
}

.notification-item.unread .notification-icon {
  background-color: #409eff;
  color: white;
}

.notification-content {
  flex: 1;
  min-width: 0;
}

.notification-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.notification-text {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  margin-bottom: 4px;
}

.notification-time {
  font-size: 11px;
  color: #c0c4cc;
}

/* v4.19.0: 快速操作按钮 */
.notification-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.notification-actions .el-button {
  padding: 4px 10px;
  font-size: 12px;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #409eff;
  margin-left: 8px;
  flex-shrink: 0;
  margin-top: 6px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #909399;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

.panel-footer {
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  text-align: center;
}
</style>

<style>
/* 全局样式（不使用 scoped） */
.notification-popover {
  padding: 0 !important;
}

.notification-popover .el-popover__title {
  display: none;
}
</style>

