<template>
  <div class="notifications-page">
    <el-card class="notifications-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <h2>System Notifications</h2>
            <span class="unread-badge" v-if="unreadCount > 0">
              {{ unreadCount }} unread
            </span>
          </div>
          <div class="header-actions">
            <el-button 
              v-if="unreadCount > 0"
              type="primary" 
              @click="handleMarkAllRead"
              :loading="markingAllRead"
              :icon="Check"
            >
              Mark all as read
            </el-button>
            <el-button 
              @click="handleDeleteAllRead"
              :loading="deletingRead"
              :icon="Delete"
            >
              Delete read
            </el-button>
            <el-button 
              @click="fetchNotifications"
              :loading="loading"
              :icon="Refresh"
            >
              Refresh
            </el-button>
          </div>
        </div>
      </template>
      
      <!-- 视图切换和过滤器 -->
      <div class="filters">
        <!-- v4.19.0: 视图切换 -->
        <el-radio-group v-model="viewMode" @change="handleViewModeChange" style="margin-right: 16px;">
          <el-radio-button label="list">
            <el-icon><List /></el-icon> List
          </el-radio-button>
          <el-radio-button label="grouped">
            <el-icon><Folder /></el-icon> Grouped
          </el-radio-button>
        </el-radio-group>
        
        <el-radio-group v-model="filterStatus" @change="handleFilterChange" v-if="viewMode === 'list'">
          <el-radio-button label="all">All</el-radio-button>
          <el-radio-button label="unread">Unread</el-radio-button>
          <el-radio-button label="read">Read</el-radio-button>
        </el-radio-group>
        
        <el-select 
          v-model="filterType" 
          placeholder="Filter by type" 
          clearable
          @change="handleFilterChange"
          style="width: 180px;"
          v-if="viewMode === 'list'"
        >
          <el-option label="User Registration" value="user_registered" />
          <el-option label="User Approved" value="user_approved" />
          <el-option label="User Rejected" value="user_rejected" />
          <el-option label="Password Reset" value="password_reset" />
          <el-option label="System Alert" value="system_alert" />
        </el-select>
        
        <!-- v4.19.0: 优先级过滤 -->
        <el-select 
          v-model="filterPriority" 
          placeholder="Filter by priority" 
          clearable
          @change="handleFilterChange"
          style="width: 160px;"
          v-if="viewMode === 'list'"
        >
          <el-option label="High Priority" value="high">
            <span class="priority-option priority-high">High</span>
          </el-option>
          <el-option label="Medium Priority" value="medium">
            <span class="priority-option priority-medium">Medium</span>
          </el-option>
          <el-option label="Low Priority" value="low">
            <span class="priority-option priority-low">Low</span>
          </el-option>
        </el-select>
      </div>
      
      <!-- v4.19.0: 分组视图 -->
      <div class="notifications-grouped" v-if="viewMode === 'grouped'" v-loading="loadingGroups">
        <template v-if="notificationGroups.length > 0">
          <el-collapse v-model="expandedGroups">
            <el-collapse-item
              v-for="group in notificationGroups"
              :key="group.notification_type"
              :name="group.notification_type"
            >
              <template #title>
                <div class="group-header">
                  <el-icon :size="20">
                    <UserFilled v-if="group.notification_type === 'user_registered'" />
                    <CircleCheck v-else-if="group.notification_type === 'user_approved'" />
                    <CircleClose v-else-if="group.notification_type === 'user_rejected'" />
                    <Warning v-else-if="group.notification_type === 'system_alert'" />
                    <Key v-else-if="group.notification_type === 'password_reset'" />
                    <Bell v-else />
                  </el-icon>
                  <span class="group-title">{{ group.type_label }}</span>
                  <el-badge :value="group.unread_count" :hidden="group.unread_count === 0" class="group-badge" />
                  <span class="group-count">{{ group.total_count }} notifications</span>
                </div>
              </template>
              
              <div class="group-content">
                <div v-if="group.latest_notification" class="latest-notification">
                  <div class="notification-title">{{ group.latest_notification.title }}</div>
                  <div class="notification-text">{{ group.latest_notification.content }}</div>
                  <div class="notification-time">{{ formatTime(group.latest_notification.created_at) }}</div>
                </div>
                <div class="group-actions">
                  <el-button 
                    type="primary" 
                    size="small"
                    @click="handleViewGroupNotifications(group.notification_type)"
                  >
                    View All
                  </el-button>
                  <el-button 
                    v-if="group.unread_count > 0"
                    size="small"
                    @click="handleMarkGroupRead(group.notification_type)"
                    :loading="markingGroupRead === group.notification_type"
                  >
                    Mark All Read
                  </el-button>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </template>
        
        <div v-else class="empty-state">
          <el-icon :size="64" color="#c0c4cc"><Bell /></el-icon>
          <h3>No notifications</h3>
          <p>You don't have any notifications yet.</p>
        </div>
      </div>
      
      <!-- 通知列表 -->
      <div class="notifications-list" v-loading="loading" v-if="viewMode === 'list'">
        <template v-if="notifications.length > 0">
          <div
            v-for="notification in notifications"
            :key="notification.notification_id"
            class="notification-card"
            :class="{ 
              'unread': !notification.is_read,
              'high-priority': notification.priority === 'high'
            }"
          >
            <div class="notification-icon">
              <el-icon :size="24">
                <UserFilled v-if="notification.notification_type === 'user_registered'" />
                <CircleCheck v-else-if="notification.notification_type === 'user_approved'" />
                <CircleClose v-else-if="notification.notification_type === 'user_rejected'" />
                <Warning v-else-if="notification.notification_type === 'system_alert'" />
                <Key v-else-if="notification.notification_type === 'password_reset'" />
                <Bell v-else />
              </el-icon>
            </div>
            
            <div class="notification-body">
              <div class="notification-header">
                <span class="notification-title">{{ notification.title }}</span>
                <!-- v4.19.0: 优先级标识 -->
                <el-tag 
                  v-if="notification.priority === 'high'"
                  type="danger"
                  size="small"
                  class="priority-tag"
                >
                  High
                </el-tag>
                <el-tag 
                  :type="getTypeTagColor(notification.notification_type)"
                  size="small"
                >
                  {{ getTypeLabel(notification.notification_type) }}
                </el-tag>
              </div>
              <div class="notification-content">{{ notification.content }}</div>
              <div class="notification-meta">
                <span class="notification-time">
                  <el-icon><Clock /></el-icon>
                  {{ formatTime(notification.created_at) }}
                </span>
                <span v-if="notification.related_username" class="notification-user">
                  <el-icon><User /></el-icon>
                  {{ notification.related_username }}
                </span>
              </div>
            </div>
            
            <div class="notification-actions">
              <el-button
                v-if="!notification.is_read"
                type="primary"
                link
                size="small"
                @click="handleMarkRead(notification)"
              >
                Mark read
              </el-button>
              <el-button
                type="danger"
                link
                size="small"
                @click="handleDelete(notification)"
              >
                Delete
              </el-button>
            </div>
          </div>
        </template>
        
        <div v-else class="empty-state">
          <el-icon :size="64" color="#c0c4cc"><Bell /></el-icon>
          <h3>No notifications</h3>
          <p>You don't have any notifications yet.</p>
        </div>
      </div>
      
      <!-- 分页 -->
      <div class="pagination-wrapper" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  Bell, 
  UserFilled, 
  CircleCheck, 
  CircleClose, 
  Warning,
  Key,
  Check,
  Delete,
  Refresh,
  Clock,
  User,
  List,
  Folder
} from '@element-plus/icons-vue'
import notificationsApi from '@/api/notifications.js'

// 状态
const loading = ref(false)
const markingAllRead = ref(false)
const deletingRead = ref(false)
const notifications = ref([])
const total = ref(0)
const unreadCount = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const filterStatus = ref('all')
const filterType = ref('')
const filterPriority = ref('') // v4.19.0: 优先级过滤

// v4.19.0: 分组视图状态
const viewMode = ref('list') // 'list' | 'grouped'
const loadingGroups = ref(false)
const notificationGroups = ref([])
const expandedGroups = ref([])
const markingGroupRead = ref(null)

// 获取通知列表
const fetchNotifications = async () => {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    
    // 应用过滤条件
    if (filterStatus.value === 'unread') {
      params.is_read = false
    } else if (filterStatus.value === 'read') {
      params.is_read = true
    }
    
    if (filterType.value) {
      params.notification_type = filterType.value
    }
    
    // v4.19.0: 优先级过滤
    if (filterPriority.value) {
      params.priority = filterPriority.value
    }
    
    const response = await notificationsApi.getNotifications(params)
    if (response) {
      notifications.value = response.items || []
      total.value = response.total || 0
      unreadCount.value = response.unread_count || 0
    }
  } catch (error) {
    console.error('[SystemNotifications] Failed to fetch notifications:', error)
    ElMessage.error('Failed to load notifications')
  } finally {
    loading.value = false
  }
}

// 标记单个为已读
const handleMarkRead = async (notification) => {
  try {
    await notificationsApi.markAsRead(notification.notification_id)
    notification.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    ElMessage.success('Notification marked as read')
  } catch (error) {
    console.error('[SystemNotifications] Failed to mark as read:', error)
    ElMessage.error('Failed to mark notification as read')
  }
}

// 标记所有为已读
const handleMarkAllRead = async () => {
  markingAllRead.value = true
  try {
    await notificationsApi.markAllAsRead()
    notifications.value = notifications.value.map(n => ({
      ...n,
      is_read: true
    }))
    unreadCount.value = 0
    ElMessage.success('All notifications marked as read')
  } catch (error) {
    console.error('[SystemNotifications] Failed to mark all as read:', error)
    ElMessage.error('Failed to mark all notifications as read')
  } finally {
    markingAllRead.value = false
  }
}

// 删除单个通知
const handleDelete = async (notification) => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to delete this notification?',
      'Delete Notification',
      {
        confirmButtonText: 'Delete',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )
    
    await notificationsApi.deleteNotification(notification.notification_id)
    
    // 从列表中移除
    const index = notifications.value.findIndex(
      n => n.notification_id === notification.notification_id
    )
    if (index > -1) {
      notifications.value.splice(index, 1)
      total.value = Math.max(0, total.value - 1)
      if (!notification.is_read) {
        unreadCount.value = Math.max(0, unreadCount.value - 1)
      }
    }
    
    ElMessage.success('Notification deleted')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[SystemNotifications] Failed to delete notification:', error)
      ElMessage.error('Failed to delete notification')
    }
  }
}

// 删除所有已读通知
const handleDeleteAllRead = async () => {
  try {
    await ElMessageBox.confirm(
      'Are you sure you want to delete all read notifications?',
      'Delete Read Notifications',
      {
        confirmButtonText: 'Delete',
        cancelButtonText: 'Cancel',
        type: 'warning'
      }
    )
    
    deletingRead.value = true
    const response = await notificationsApi.deleteAllReadNotifications()
    
    if (response && response.deleted_count > 0) {
      ElMessage.success(`Deleted ${response.deleted_count} read notifications`)
      // 重新获取列表
      await fetchNotifications()
    } else {
      ElMessage.info('No read notifications to delete')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('[SystemNotifications] Failed to delete read notifications:', error)
      ElMessage.error('Failed to delete read notifications')
    }
  } finally {
    deletingRead.value = false
  }
}

// 处理过滤器变化
const handleFilterChange = () => {
  currentPage.value = 1
  fetchNotifications()
}

// 处理分页变化
const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  fetchNotifications()
}

const handlePageChange = (page) => {
  currentPage.value = page
  fetchNotifications()
}

// 获取类型标签颜色
const getTypeTagColor = (type) => {
  const colors = {
    'user_registered': 'warning',
    'user_approved': 'success',
    'user_rejected': 'danger',
    'password_reset': 'info',
    'system_alert': 'danger'
  }
  return colors[type] || 'info'
}

// 获取类型标签文本
const getTypeLabel = (type) => {
  const labels = {
    'user_registered': 'Registration',
    'user_approved': 'Approved',
    'user_rejected': 'Rejected',
    'password_reset': 'Password',
    'system_alert': 'System'
  }
  return labels[type] || type
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
  if (diffMins < 60) return `${diffMins} minutes ago`
  if (diffHours < 24) return `${diffHours} hours ago`
  if (diffDays < 7) return `${diffDays} days ago`
  
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}

// v4.19.0: 获取分组列表
const fetchNotificationGroups = async () => {
  loadingGroups.value = true
  try {
    const response = await notificationsApi.getNotificationsGrouped()
    if (response) {
      notificationGroups.value = response.groups || []
      unreadCount.value = response.total_unread || 0
      // 默认展开有未读通知的分组
      expandedGroups.value = response.groups
        .filter(g => g.unread_count > 0)
        .map(g => g.notification_type)
    }
  } catch (error) {
    console.error('[SystemNotifications] Failed to fetch notification groups:', error)
    ElMessage.error('Failed to load notification groups')
  } finally {
    loadingGroups.value = false
  }
}

// v4.19.0: 视图切换
const handleViewModeChange = (mode) => {
  if (mode === 'grouped') {
    fetchNotificationGroups()
  } else {
    fetchNotifications()
  }
}

// v4.19.0: 查看分组内的通知
const handleViewGroupNotifications = (notificationType) => {
  viewMode.value = 'list'
  filterType.value = notificationType
  filterStatus.value = 'all'
  currentPage.value = 1
  fetchNotifications()
}

// v4.19.0: 标记分组内所有通知为已读
const handleMarkGroupRead = async (notificationType) => {
  markingGroupRead.value = notificationType
  try {
    // 获取该类型的所有未读通知ID
    const response = await notificationsApi.getNotifications({
      notification_type: notificationType,
      is_read: false,
      page_size: 100
    })
    
    if (response && response.items && response.items.length > 0) {
      const ids = response.items.map(n => n.notification_id)
      await notificationsApi.markAllAsRead(ids)
      
      // 更新分组统计
      const group = notificationGroups.value.find(g => g.notification_type === notificationType)
      if (group) {
        group.unread_count = 0
      }
      
      // 更新总未读数
      unreadCount.value = Math.max(0, unreadCount.value - response.items.length)
      
      ElMessage.success(`Marked ${response.items.length} notifications as read`)
    } else {
      ElMessage.info('No unread notifications in this group')
    }
  } catch (error) {
    console.error('[SystemNotifications] Failed to mark group as read:', error)
    ElMessage.error('Failed to mark notifications as read')
  } finally {
    markingGroupRead.value = null
  }
}

// 生命周期
onMounted(() => {
  fetchNotifications()
})
</script>

<style scoped>
.notifications-page {
  padding: 20px;
}

.notifications-card {
  max-width: 1000px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.unread-badge {
  background-color: #409eff;
  color: white;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filters {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.notifications-list {
  min-height: 200px;
}

.notification-card {
  display: flex;
  align-items: flex-start;
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.notification-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.notification-card.unread {
  background-color: #ecf5ff;
  border-color: #b3d8ff;
}

.notification-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  flex-shrink: 0;
}

.notification-card.unread .notification-icon {
  background-color: #409eff;
  color: white;
}

.notification-body {
  flex: 1;
  min-width: 0;
}

.notification-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.notification-title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.notification-content {
  font-size: 14px;
  color: #606266;
  line-height: 1.5;
  margin-bottom: 8px;
}

.notification-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #909399;
}

.notification-time,
.notification-user {
  display: flex;
  align-items: center;
  gap: 4px;
}

.notification-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-left: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #909399;
}

.empty-state h3 {
  margin: 16px 0 8px;
  color: #606266;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

/* v4.19.0: 分组视图样式 */
.notifications-grouped {
  min-height: 200px;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.group-title {
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.group-badge {
  margin-left: 8px;
}

.group-count {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
  padding-right: 20px;
}

.group-content {
  padding: 16px;
  background-color: #fafafa;
  border-radius: 4px;
}

.latest-notification {
  margin-bottom: 16px;
}

.latest-notification .notification-title {
  font-weight: 500;
  color: #303133;
  margin-bottom: 4px;
}

.latest-notification .notification-text {
  color: #606266;
  font-size: 14px;
  margin-bottom: 4px;
}

.latest-notification .notification-time {
  color: #909399;
  font-size: 12px;
}

.group-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

/* v4.19.0: 优先级样式 */
.priority-tag {
  margin-right: 8px;
}

.priority-option {
  display: flex;
  align-items: center;
}

.priority-option::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
}

.priority-high::before {
  background-color: #f56c6c;
}

.priority-medium::before {
  background-color: #e6a23c;
}

.priority-low::before {
  background-color: #909399;
}

/* 高优先级通知卡片特殊样式 */
.notification-card.high-priority {
  border-left: 4px solid #f56c6c;
}
</style>
