/**
 * 通知 WebSocket 客户端（v4.19.0）
 *
 * 功能：
 * - 管理与后端 `/api/notifications/ws` 的 WebSocket 连接
 * - 自动重连（指数退避，最多 10 次，最大 30 秒间隔）
 * - WebSocket 不可用或多次失败时自动降级到未读数量轮询
 * - 对消息做基本格式校验，防止恶意数据导致前端崩溃
 * - 向外暴露响应式的 `unreadCount`，以及新通知回调订阅接口
 */

import { ref } from 'vue'
import notificationsApi from '@/api/notifications'
import { useAuthStore } from '@/stores/auth'

// 连接状态：'disconnected' | 'connecting' | 'connected' | 'error'
const connectionStatus = ref('disconnected')
const unreadCount = ref(0)

// 最近推送的通知（仅用于前端实时展示，不作为权威数据源）
const recentNotifications = ref([]) // NotificationMessage[]

let ws = null
let reconnectAttempts = 0
const MAX_RECONNECT_ATTEMPTS = 10
const MAX_RECONNECT_DELAY = 30000 // 30s

let fallbackPollingTimer = null
const FALLBACK_POLLING_INTERVAL = 30000 // 30s

// 订阅者：在收到新通知时回调
const listeners = new Set()

const isWebSocketSupported = typeof window !== 'undefined' && 'WebSocket' in window

function getWebSocketUrl() {
  if (typeof window === 'undefined') return null

  const loc = window.location
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = loc.host

  // 优先从 authStore 获取 token，其次从 localStorage 回退
  let token = ''
  try {
    const authStore = useAuthStore()
    token = authStore.token || ''
  } catch (e) {
    // 可能在 Pinia 尚未初始化时调用，退回到 localStorage
    token = localStorage.getItem('access_token') || ''
  }

  if (!token) {
    return null
  }

  const encodedToken = encodeURIComponent(token)
  return `${protocol}//${host}/api/notifications/ws?token=${encodedToken}`
}

function stopFallbackPolling() {
  if (fallbackPollingTimer) {
    clearInterval(fallbackPollingTimer)
    fallbackPollingTimer = null
  }
}

async function fallbackFetchUnreadCountOnce() {
  try {
    const response = await notificationsApi.getUnreadCount()
    if (response && typeof response.unread_count === 'number') {
      unreadCount.value = response.unread_count
    }
  } catch (error) {
    console.error('[NotificationWS] Fallback fetch unread count failed:', error)
  }
}

function startFallbackPolling() {
  stopFallbackPolling()
  // 立即拉一次
  void fallbackFetchUnreadCountOnce()
  fallbackPollingTimer = setInterval(() => {
    void fallbackFetchUnreadCountOnce()
  }, FALLBACK_POLLING_INTERVAL)
}

function handleNewNotification(notificationData) {
  // 基本格式验证，防止异常数据导致前端错误
  if (
    !notificationData ||
    typeof notificationData !== 'object' ||
    typeof notificationData.notification_id !== 'number' ||
    typeof notificationData.title !== 'string'
  ) {
    console.warn('[NotificationWS] Invalid notification data received:', notificationData)
    return
  }

  // 未读数量 +1（真实数量以后端为准，这里只做前端即时体验）
  unreadCount.value = (unreadCount.value || 0) + 1

  // 维护最近通知列表（最多保留 20 条）
  recentNotifications.value = [
    { ...notificationData, is_read: false },
    ...recentNotifications.value
  ].slice(0, 20)

  // 通知订阅者
  listeners.forEach((fn) => {
    try {
      fn(notificationData)
    } catch (e) {
      console.error('[NotificationWS] Listener error:', e)
    }
  })
}

function scheduleReconnect() {
  if (!isWebSocketSupported) {
    connectionStatus.value = 'error'
    startFallbackPolling()
    return
  }

  if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    console.warn('[NotificationWS] Max reconnect attempts reached, fallback to polling')
    connectionStatus.value = 'error'
    startFallbackPolling()
    return
  }

  reconnectAttempts += 1
  const delay = Math.min(1000 * 2 ** (reconnectAttempts - 1), MAX_RECONNECT_DELAY)
  console.info(`[NotificationWS] Schedule reconnect in ${delay}ms (attempt ${reconnectAttempts})`)
  setTimeout(() => {
    connect()
  }, delay)
}

function connect() {
  if (!isWebSocketSupported) {
    console.warn('[NotificationWS] WebSocket not supported, using polling fallback')
    connectionStatus.value = 'error'
    startFallbackPolling()
    return
  }

  if (ws && (connectionStatus.value === 'connecting' || connectionStatus.value === 'connected')) {
    return
  }

  const url = getWebSocketUrl()
  if (!url) {
    // 未登录或没有 token，使用轮询（如果有必要）
    console.info('[NotificationWS] No token, skip WebSocket connection')
    connectionStatus.value = 'disconnected'
    stopFallbackPolling()
    return
  }

  try {
    connectionStatus.value = 'connecting'
    ws = new WebSocket(url)

    ws.onopen = () => {
      console.info('[NotificationWS] WebSocket connected')
      connectionStatus.value = 'connected'
      reconnectAttempts = 0
      stopFallbackPolling()
      // 连接成功后，同步一次未读数量，确保前后端一致
      void fallbackFetchUnreadCountOnce()
    }

    ws.onmessage = (event) => {
      try {
        const text = event.data
        if (text === 'ping' || text === 'pong') {
          // 心跳消息，忽略
          return
        }

        let msg
        try {
          msg = JSON.parse(text)
        } catch (e) {
          console.warn('[NotificationWS] Non-JSON message received, ignored:', text)
          return
        }

        if (!msg || typeof msg !== 'object') {
          return
        }

        // 连接确认消息
        if (msg.type === 'connected') {
          return
        }

        if (msg.type === 'notification' && msg.data) {
          handleNewNotification(msg.data)
        }
      } catch (e) {
        console.error('[NotificationWS] onmessage error:', e)
      }
    }

    ws.onerror = (event) => {
      console.error('[NotificationWS] WebSocket error:', event)
      connectionStatus.value = 'error'
    }

    ws.onclose = (event) => {
      console.warn('[NotificationWS] WebSocket closed:', event.code, event.reason)
      ws = null

      // 根据 close code 判断是否需要重连
      // 4005: token 过期 / 无效，4006/4007/4008: 限制/安全问题，直接降级为轮询
      if ([4005, 4006, 4007, 4008].includes(event.code)) {
        connectionStatus.value = 'error'
        startFallbackPolling()
        return
      }

      // 正常关闭（如页面卸载）不再重连
      if (event.code === 1000) {
        connectionStatus.value = 'disconnected'
        return
      }

      // 其他错误尝试重连
      connectionStatus.value = 'error'
      scheduleReconnect()
    }
  } catch (e) {
    console.error('[NotificationWS] Failed to create WebSocket:', e)
    connectionStatus.value = 'error'
    scheduleReconnect()
  }
}

function disconnect() {
  if (ws) {
    try {
      ws.close(1000, 'Client disconnect')
    } catch (e) {
      console.error('[NotificationWS] Error when closing WebSocket:', e)
    }
    ws = null
  }
  connectionStatus.value = 'disconnected'
  stopFallbackPolling()
}

function subscribe(callback) {
  if (typeof callback !== 'function') return () => {}
  listeners.add(callback)
  return () => {
    listeners.delete(callback)
  }
}

/**
 * 对外暴露的使用接口
 */
export function useNotificationWebSocket() {
  return {
    // 状态
    connectionStatus,
    unreadCount,
    recentNotifications,

    // 控制
    connect,
    disconnect,

    // 订阅新通知
    subscribe,

    // 显式触发一次未读数量拉取（例如组件初始化时）
    fetchUnreadCountOnce: fallbackFetchUnreadCountOnce
  }
}


