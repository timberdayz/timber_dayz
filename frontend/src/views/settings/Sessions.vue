<template>
  <div class="sessions-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <el-icon><Monitor /></el-icon>
          会话管理
        </h1>
        <p class="page-subtitle">查看和管理您的活跃登录会话</p>
      </div>
      <div class="header-actions">
        <el-button type="danger" @click="revokeAllOtherSessions" :loading="revokingAll">
          <el-icon><SwitchButton /></el-icon>
          登出所有其他设备
        </el-button>
        <el-button @click="refreshSessions" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 会话列表 -->
    <div class="sessions-content">
      <el-card shadow="hover">
        <template #header>
          <div class="card-header">
            <span>活跃会话列表</span>
            <el-tag type="info" size="small">{{ sessions.length }} 个活跃会话</el-tag>
          </div>
        </template>

        <!-- 加载状态 -->
        <div v-if="loading" class="loading-container">
          <el-skeleton :rows="3" animated />
        </div>

        <!-- 空状态 -->
        <el-empty v-else-if="sessions.length === 0" description="暂无活跃会话" />

        <!-- 会话列表 -->
        <div v-else class="sessions-list">
          <div
            v-for="session in sessions"
            :key="session.session_id"
            class="session-item"
            :class="{ 'current-session': session.is_current }"
          >
            <div class="session-info">
              <div class="session-header">
                <div class="session-title">
                  <el-icon class="device-icon"><Monitor /></el-icon>
                  <span class="device-name">{{ formatDeviceInfo(session.device_info) }}</span>
                  <el-tag v-if="session.is_current" type="success" size="small" class="current-tag">
                    当前设备
                  </el-tag>
                </div>
                <el-button
                  v-if="!session.is_current"
                  type="danger"
                  size="small"
                  @click="revokeSession(session.session_id)"
                  :loading="revokingSessions.includes(session.session_id)"
                >
                  <el-icon><SwitchButton /></el-icon>
                  登出此设备
                </el-button>
              </div>

              <div class="session-details">
                <div class="detail-item">
                  <el-icon><Location /></el-icon>
                  <span class="label">IP地址:</span>
                  <span class="value">{{ session.ip_address || '未知' }}</span>
                </div>
                <div class="detail-item">
                  <el-icon><Clock /></el-icon>
                  <span class="label">登录时间:</span>
                  <span class="value">{{ formatDateTime(session.created_at) }}</span>
                </div>
                <div class="detail-item">
                  <el-icon><Timer /></el-icon>
                  <span class="label">最后活跃:</span>
                  <span class="value">{{ formatDateTime(session.last_active_at) }}</span>
                </div>
                <div class="detail-item">
                  <el-icon><Calendar /></el-icon>
                  <span class="label">过期时间:</span>
                  <span class="value">{{ formatDateTime(session.expires_at) }}</span>
                </div>
                <div v-if="session.location" class="detail-item">
                  <el-icon><MapLocation /></el-icon>
                  <span class="label">位置:</span>
                  <span class="value">{{ session.location }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Monitor,
  SwitchButton,
  Refresh,
  Location,
  Clock,
  Timer,
  Calendar,
  MapLocation
} from '@element-plus/icons-vue'
import usersApi from '@/api/users.js'

// 响应式数据
const sessions = ref([])
const loading = ref(false)
const revokingAll = ref(false)
const revokingSessions = ref([])
const currentSessionId = ref(null)

// 获取会话列表
const fetchSessions = async () => {
  loading.value = true
  try {
    const response = await usersApi.getMySessions()
    if (response.success) {
      sessions.value = response.data || []
      // 标记当前会话（通过比较session_id和本地存储的token哈希）
      // 注意：这里需要从登录响应中获取session_id，或者通过其他方式标识当前会话
      // 暂时通过检查is_current字段（如果后端返回）
      const currentSession = sessions.value.find(s => s.is_current)
      if (currentSession) {
        currentSessionId.value = currentSession.session_id
      } else if (sessions.value.length > 0) {
        // 如果没有is_current字段，假设第一个是当前会话（临时方案）
        currentSessionId.value = sessions.value[0].session_id
      }
    } else {
      ElMessage.error(response.message || '获取会话列表失败')
    }
  } catch (error) {
    console.error('获取会话列表失败:', error)
    ElMessage.error('获取会话列表失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

// 刷新会话列表
const refreshSessions = () => {
  fetchSessions()
}

// 撤销指定会话
const revokeSession = async (sessionId) => {
  try {
    await ElMessageBox.confirm(
      '确定要登出此设备吗？该设备将需要重新登录。',
      '确认登出',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    revokingSessions.value.push(sessionId)
    try {
      const response = await usersApi.revokeSession(sessionId)
      if (response.success) {
        ElMessage.success('已成功登出该设备')
        // 刷新列表
        await fetchSessions()
      } else {
        ElMessage.error(response.message || '登出失败')
      }
    } catch (error) {
      console.error('登出会话失败:', error)
      ElMessage.error('登出失败，请稍后重试')
    } finally {
      revokingSessions.value = revokingSessions.value.filter(id => id !== sessionId)
    }
  } catch {
    // 用户取消
  }
}

// 撤销所有其他会话
const revokeAllOtherSessions = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要登出所有其他设备吗？其他设备将需要重新登录。',
      '确认登出所有其他设备',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    revokingAll.value = true
    try {
      // 获取当前会话ID（优先使用标记为is_current的会话）
      const currentSession = sessions.value.find(s => s.is_current)
      const sessionId = currentSession?.session_id || currentSessionId.value
      
      if (!sessionId) {
        ElMessage.warning('无法获取当前会话ID，请刷新页面后重试')
        revokingAll.value = false
        return
      }

      const response = await usersApi.revokeAllOtherSessions(sessionId)
      if (response.success) {
        ElMessage.success('已成功登出所有其他设备')
        // 刷新列表
        await fetchSessions()
      } else {
        ElMessage.error(response.message || '登出失败')
      }
    } catch (error) {
      console.error('登出所有其他会话失败:', error)
      ElMessage.error('登出失败，请稍后重试')
    } finally {
      revokingAll.value = false
    }
  } catch {
    // 用户取消
  }
}

// 格式化设备信息
const formatDeviceInfo = (deviceInfo) => {
  if (!deviceInfo) return '未知设备'
  
  // 尝试解析User-Agent
  if (deviceInfo.includes('Windows')) return 'Windows 设备'
  if (deviceInfo.includes('Mac')) return 'Mac 设备'
  if (deviceInfo.includes('Linux')) return 'Linux 设备'
  if (deviceInfo.includes('Android')) return 'Android 设备'
  if (deviceInfo.includes('iPhone') || deviceInfo.includes('iPad')) return 'iOS 设备'
  
  // 截取前50个字符
  return deviceInfo.length > 50 ? deviceInfo.substring(0, 50) + '...' : deviceInfo
}

// 格式化日期时间
const formatDateTime = (dateTime) => {
  if (!dateTime) return '未知'
  
  try {
    const date = new Date(dateTime)
    const now = new Date()
    const diff = now - date
    
    // 小于1分钟：刚刚
    if (diff < 60000) return '刚刚'
    
    // 小于1小时：X分钟前
    if (diff < 3600000) {
      const minutes = Math.floor(diff / 60000)
      return `${minutes} 分钟前`
    }
    
    // 小于24小时：X小时前
    if (diff < 86400000) {
      const hours = Math.floor(diff / 3600000)
      return `${hours} 小时前`
    }
    
    // 今天：今天 HH:mm
    if (date.toDateString() === now.toDateString()) {
      return `今天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
    }
    
    // 昨天：昨天 HH:mm
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === yesterday.toDateString()) {
      return `昨天 ${date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
    }
    
    // 其他：YYYY-MM-DD HH:mm
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch (error) {
    console.error('格式化日期时间失败:', error)
    return dateTime
  }
}

// 组件挂载时获取会话列表
onMounted(() => {
  fetchSessions()
})
</script>

<style scoped>
.sessions-page {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 100px);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.header-content {
  flex: 1;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.page-subtitle {
  margin: 8px 0 0 0;
  font-size: 14px;
  color: #909399;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.sessions-content {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.session-item {
  padding: 20px;
  background: #fafafa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  transition: all 0.3s;
}

.session-item:hover {
  background: #f0f2f5;
  border-color: #c0c4cc;
}

.session-item.current-session {
  background: #f0f9ff;
  border-color: #409eff;
  border-width: 2px;
}

.session-info {
  width: 100%;
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.session-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.device-icon {
  font-size: 20px;
  color: #409eff;
}

.device-name {
  flex: 1;
}

.current-tag {
  margin-left: 8px;
}

.session-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}

.detail-item .el-icon {
  color: #909399;
  font-size: 16px;
}

.detail-item .label {
  font-weight: 500;
  color: #909399;
}

.detail-item .value {
  color: #303133;
}

.loading-container {
  padding: 20px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .session-details {
    grid-template-columns: 1fr;
  }
}
</style>

