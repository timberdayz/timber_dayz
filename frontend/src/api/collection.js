/**
 * 数据采集 API 服务
 * 
 * 提供数据采集相关的所有API调用封装
 * @module api/collection
 * @version 4.6.0
 */

import api from './index'

// ============================================================
// 配置管理 API
// ============================================================

/**
 * 获取采集配置列表
 * @param {Object} params - 查询参数
 * @param {string} [params.platform] - 平台筛选
 * @param {boolean} [params.is_active] - 是否激活
 * @returns {Promise<Array>} 配置列表
 */
export const getConfigs = async (params = {}) => {
  const response = await api.get('/collection/configs', { params })
  // 响应拦截器已经提取了data，直接返回response
  return response || []
}

/**
 * 获取配置详情
 * @param {number} id - 配置ID
 * @returns {Promise<Object>} 配置详情
 */
export const getConfig = async (id) => {
  const response = await api.get(`/collection/configs/${id}`)
  return response
}

/**
 * 创建采集配置
 * @param {Object} config - 配置数据
 * @param {string} config.name - 配置名称
 * @param {string} config.platform - 平台
 * @param {Array<string>} config.account_ids - 账号ID列表
 * @param {Array<string>} config.data_domains - 数据域列表
 * @param {string} [config.sub_domain] - 子域
 * @param {string} [config.granularity] - 粒度
 * @param {string} [config.date_range_type] - 日期范围类型
 * @param {boolean} [config.schedule_enabled] - 是否启用定时
 * @param {string} [config.schedule_cron] - Cron表达式
 * @returns {Promise<Object>} 创建的配置
 */
export const createConfig = async (config) => {
  const response = await api.post('/collection/configs', config)
  return response
}

/**
 * 更新采集配置
 * @param {number} id - 配置ID
 * @param {Object} config - 配置数据
 * @returns {Promise<Object>} 更新后的配置
 */
export const updateConfig = async (id, config) => {
  const response = await api.put(`/collection/configs/${id}`, config)
  return response
}

/**
 * 删除采集配置
 * @param {number} id - 配置ID
 * @returns {Promise<void>}
 */
export const deleteConfig = async (id) => {
  await api.delete(`/collection/configs/${id}`)
}

// ============================================================
// 账号 API
// ============================================================

/**
 * 获取账号列表（脱敏）
 * @param {Object} params - 查询参数
 * @param {string} [params.platform] - 平台筛选
 * @returns {Promise<Array>} 账号列表
 */
export const getAccounts = async (params = {}) => {
  const response = await api.get('/collection/accounts', { params })
  // 响应拦截器已经提取了data，直接返回response
  return response || []
}

/**
 * 按平台获取账号
 * @param {string} platform - 平台代码
 * @returns {Promise<Array>} 账号列表
 */
export const getAccountsByPlatform = async (platform) => {
  return getAccounts({ platform })
}

// ============================================================
// 任务 API
// ============================================================

/**
 * 创建采集任务
 * @param {Object} task - 任务数据
 * @param {string} task.platform - 平台
 * @param {string} task.account_id - 账号ID
 * @param {Array<string>} task.data_domains - 数据域列表
 * @param {string} [task.sub_domain] - 子域
 * @param {string} [task.granularity] - 粒度
 * @param {Object} [task.date_range] - 日期范围
 * @returns {Promise<Object>} 创建的任务
 */
export const createTask = async (task) => {
  const response = await api.post('/collection/tasks', task)
  return response
}

/**
 * 获取任务列表
 * @param {Object} params - 查询参数
 * @param {string} [params.status] - 状态筛选
 * @param {string} [params.platform] - 平台筛选
 * @param {string} [params.account_id] - 账号筛选
 * @returns {Promise<Array>} 任务列表
 */
export const getTasks = async (params = {}) => {
  const response = await api.get('/collection/tasks', { params })
  // 响应拦截器已经提取了data，直接返回response
  return response || []
}

/**
 * 获取任务详情
 * @param {string} taskId - 任务UUID
 * @returns {Promise<Object>} 任务详情
 */
export const getTask = async (taskId) => {
  const response = await api.get(`/collection/tasks/${taskId}`)
  return response
}

/**
 * 取消任务
 * @param {string} taskId - 任务UUID
 * @returns {Promise<void>}
 */
export const cancelTask = async (taskId) => {
  await api.delete(`/collection/tasks/${taskId}`)
}

/**
 * 重试任务
 * @param {string} taskId - 任务UUID
 * @returns {Promise<Object>} 新创建的任务
 */
export const retryTask = async (taskId) => {
  const response = await api.post(`/collection/tasks/${taskId}/retry`)
  return response
}

/**
 * 恢复暂停的任务
 * @param {string} taskId - 任务UUID
 * @param {string} [verificationCode] - 验证码（如果需要）
 * @returns {Promise<Object>} 恢复的任务
 */
export const resumeTask = async (taskId, verificationCode = null) => {
  const params = verificationCode ? { verification_code: verificationCode } : {}
  const response = await api.post(`/collection/tasks/${taskId}/resume`, null, { params })
  return response
}

/**
 * 获取任务日志
 * @param {string} taskId - 任务UUID
 * @returns {Promise<Array>} 日志列表
 */
export const getTaskLogs = async (taskId) => {
  const response = await api.get(`/collection/tasks/${taskId}/logs`)
  return response || []
}

// ============================================================
// 历史和统计 API
// ============================================================

/**
 * 获取采集历史
 * @param {Object} params - 查询参数
 * @param {string} [params.platform] - 平台筛选
 * @param {string} [params.status] - 状态筛选
 * @param {number} [params.limit] - 数量限制
 * @param {number} [params.offset] - 偏移量
 * @returns {Promise<Array>} 历史记录列表
 */
export const getHistory = async (params = {}) => {
  const response = await api.get('/collection/history', { params })
  return response || []
}

/**
 * 获取采集统计
 * @returns {Promise<Object>} 统计数据
 */
export const getStats = async () => {
  const response = await api.get('/collection/history/stats')
  return response
}

// ============================================================
// 调度管理 API
// ============================================================

/**
 * 更新配置的定时设置
 * @param {number} configId - 配置ID
 * @param {Object} schedule - 调度设置
 * @param {boolean} schedule.schedule_enabled - 是否启用
 * @param {string} [schedule.schedule_cron] - Cron表达式
 * @returns {Promise<Object>} 更新结果
 */
export const updateConfigSchedule = async (configId, schedule) => {
  const response = await api.post(`/collection/configs/${configId}/schedule`, schedule)
  return response
}

/**
 * 获取配置的定时状态
 * @param {number} configId - 配置ID
 * @returns {Promise<Object>} 调度状态
 */
export const getConfigSchedule = async (configId) => {
  const response = await api.get(`/collection/configs/${configId}/schedule`)
  return response
}

/**
 * 验证Cron表达式
 * @param {string} cronExpression - Cron表达式
 * @returns {Promise<Object>} 验证结果
 */
export const validateCronExpression = async (cronExpression) => {
  const response = await api.post('/collection/schedule/validate', { cron_expression: cronExpression })
  return response
}

/**
 * 获取Cron预设
 * @returns {Promise<Object>} 预设列表
 */
export const getCronPresets = async () => {
  const response = await api.get('/collection/schedule/presets')
  return response
}

/**
 * 获取所有定时任务
 * @returns {Promise<Object>} 任务列表
 */
export const getScheduledJobs = async () => {
  const response = await api.get('/collection/schedule/jobs')
  return response || []
}

// ============================================================
// 健康检查 API
// ============================================================

/**
 * 获取采集模块健康状态
 * @returns {Promise<Object>} 健康状态
 */
export const getHealth = async () => {
  const response = await api.get('/collection/health')
  return response
}

// ============================================================
// WebSocket 服务
// ============================================================

/**
 * 创建任务状态WebSocket连接
 * @param {string} taskId - 任务UUID
 * @param {string} [token] - JWT Token（如果需要认证）
 * @param {Object} callbacks - 回调函数
 * @param {Function} callbacks.onProgress - 进度更新回调
 * @param {Function} callbacks.onLog - 日志回调
 * @param {Function} callbacks.onComplete - 完成回调
 * @param {Function} callbacks.onVerification - 验证码请求回调
 * @param {Function} callbacks.onError - 错误回调
 * @returns {WebSocket} WebSocket实例
 */
export const createTaskWebSocket = (taskId, token, callbacks = {}) => {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = import.meta.env.VITE_API_BASE_URL?.replace(/^https?:\/\//, '') || window.location.host
  
  let wsUrl = `${wsProtocol}//${wsHost}/api/collection/ws/collection/${taskId}`
  if (token) {
    wsUrl += `?token=${encodeURIComponent(token)}`
  }
  
  const ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log(`[WS] Connected to task ${taskId}`)
  }
  
  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      
      switch (message.type) {
        case 'connected':
          console.log(`[WS] ${message.message}`)
          break
        case 'progress':
          callbacks.onProgress?.(message)
          break
        case 'log':
          callbacks.onLog?.(message)
          break
        case 'complete':
          callbacks.onComplete?.(message)
          break
        case 'verification_required':
          callbacks.onVerification?.(message)
          break
        default:
          console.log(`[WS] Unknown message type: ${message.type}`)
      }
    } catch (e) {
      console.error('[WS] Failed to parse message:', e)
    }
  }
  
  ws.onerror = (error) => {
    console.error(`[WS] Error:`, error)
    callbacks.onError?.(error)
  }
  
  ws.onclose = (event) => {
    console.log(`[WS] Closed: code=${event.code}, reason=${event.reason}`)
  }
  
  return ws
}

/**
 * 获取WebSocket连接统计
 * @returns {Promise<Object>} 统计数据
 */
export const getWebSocketStats = async () => {
  const response = await api.get('/collection/ws/collection/stats')
  return response
}

// ============================================================
// 导出默认对象
// ============================================================

export default {
  // 配置管理
  getConfigs,
  getConfig,
  createConfig,
  updateConfig,
  deleteConfig,
  
  // 账号管理
  getAccounts,
  getAccountsByPlatform,
  
  // 任务管理
  createTask,
  getTasks,
  getTask,
  cancelTask,
  retryTask,
  resumeTask,
  getTaskLogs,
  
  // 历史和统计
  getHistory,
  getStats,
  
  // 调度管理
  updateConfigSchedule,
  getConfigSchedule,
  validateCronExpression,
  getCronPresets,
  getScheduledJobs,
  
  // 健康检查
  getHealth,
  
  // WebSocket
  createTaskWebSocket,
  getWebSocketStats
}

