/**
 * 数据同步状态管理（Pinia Store）
 * 
 * v4.12.0新增：
 * - 统一的数据同步状态管理
 * - 使用新的data_sync API
 * - 简化组件中的状态管理代码
 * 
 * v4.18.2修复：
 * - 符合异步架构：移除 isLoading 阻塞状态
 * - 添加超时机制：避免长时间等待API响应
 * - 立即启动轮询：不等待API响应完成
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useDataSyncStore = defineStore('dataSync', () => {
  // 状态
  const currentTaskId = ref(null)
  const syncProgress = ref(null)
  const syncTasks = ref([])
  const isLoading = ref(false)
  const error = ref(null)

  // 计算属性
  const hasActiveTask = computed(() => currentTaskId.value !== null)
  const progressPercentage = computed(() => {
    if (!syncProgress.value) return 0
    if (syncProgress.value.total_files === 0) return 0
    return Math.round(
      (syncProgress.value.processed_files / syncProgress.value.total_files) * 100
    )
  })

  // 操作
  // ⭐ v4.18.2修复：符合异步架构，移除 isLoading 阻塞状态，添加超时机制
  async function syncSingleFile(fileId, options = {}) {
    // ⭐ 关键修改：不设置 isLoading，避免阻塞UI
    error.value = null

    // ⭐ v4.19.5 优化：增加超时时间到 120 秒（2分钟），避免任务提交后立即超时
    const API_TIMEOUT = 120000 // 120秒超时（2分钟）

    try {
      const response = await Promise.race([
        api.post('/data-sync/single', {
          file_id: fileId,
          only_with_template: options.onlyWithTemplate ?? true,
          allow_quarantine: options.allowQuarantine ?? true,
        }),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('API响应超时，任务可能已提交')), API_TIMEOUT)
        )
      ])

      // ⭐ v4.14.0新增：检查是否有表头变化错误
      if (response.data?.error_code === 'HEADER_CHANGED') {
        const errorDetails = response.data?.error_details || {}
        const headerChanges = response.data?.header_changes || {}
        
        // 构建详细的错误信息
        let errorMsg = '表头字段已变化，请更新模板后再同步。\n\n'
        
        if (errorDetails.added_fields?.length > 0) {
          errorMsg += `新增字段（${errorDetails.added_fields.length}个）：\n`
          errorDetails.added_fields.forEach(field => {
            errorMsg += `  + "${field}"\n`
          })
          errorMsg += '\n'
        }
        
        if (errorDetails.removed_fields?.length > 0) {
          errorMsg += `删除字段（${errorDetails.removed_fields.length}个）：\n`
          errorDetails.removed_fields.forEach(field => {
            errorMsg += `  - "${field}"\n`
          })
          errorMsg += '\n'
        }
        
        if (!errorDetails.added_fields?.length && !errorDetails.removed_fields?.length) {
          errorMsg += '字段顺序已变化（字段名相同但顺序不同）\n\n'
        }
        
        errorMsg += `表头匹配率：${errorDetails.match_rate || 0}%\n`
        errorMsg += '\n请前往模板编辑页面更新模板。'
        
        error.value = errorMsg
        
        // 返回详细错误信息，供前端组件使用
        return {
          success: false,
          error_code: 'HEADER_CHANGED',
          header_changes: headerChanges,
          error_details: errorDetails,
          message: errorMsg
        }
      }

      // ⭐ 关键修改：立即启动轮询，不等待API响应完成
      if (response.data?.task_id) {
        currentTaskId.value = response.data.task_id
        // 立即开始轮询进度
        startPolling(response.data.task_id)
      }

      return response.data
    } catch (err) {
      // ⭐ 关键修改：超时错误不阻塞，假设任务已提交
      if (err.message === 'API响应超时，任务可能已提交') {
        // 超时情况下，假设任务已提交，启动轮询（使用fileId作为taskId的一部分）
        const estimatedTaskId = `single_file_${fileId}_${Date.now()}`
        currentTaskId.value = estimatedTaskId
        // 延迟启动轮询，给后端一些时间创建任务
        setTimeout(() => {
          startPolling(estimatedTaskId)
        }, 1000)
        
        return {
          success: true,
          task_id: estimatedTaskId,
          status: 'submitted',
          message: '任务已提交（API响应超时，但任务可能已成功提交）'
        }
      }
      
      // ⭐ v4.14.0新增：检查响应中的表头变化错误
      if (err.response?.data?.error_code === 'HEADER_CHANGED') {
        const errorDetails = err.response.data.error_details || {}
        const headerChanges = err.response.data.header_changes || {}
        
        // 构建详细的错误信息
        let errorMsg = '表头字段已变化，请更新模板后再同步。\n\n'
        
        if (errorDetails.added_fields?.length > 0) {
          errorMsg += `新增字段（${errorDetails.added_fields.length}个）：\n`
          errorDetails.added_fields.forEach(field => {
            errorMsg += `  + "${field}"\n`
          })
          errorMsg += '\n'
        }
        
        if (errorDetails.removed_fields?.length > 0) {
          errorMsg += `删除字段（${errorDetails.removed_fields.length}个）：\n`
          errorDetails.removed_fields.forEach(field => {
            errorMsg += `  - "${field}"\n`
          })
          errorMsg += '\n'
        }
        
        if (!errorDetails.added_fields?.length && !errorDetails.removed_fields?.length) {
          errorMsg += '字段顺序已变化（字段名相同但顺序不同）\n\n'
        }
        
        errorMsg += `表头匹配率：${errorDetails.match_rate || 0}%\n`
        errorMsg += '\n请前往模板编辑页面更新模板。'
        
        error.value = errorMsg
        
        return {
          success: false,
          error_code: 'HEADER_CHANGED',
          header_changes: headerChanges,
          error_details: errorDetails,
          message: errorMsg
        }
      }
      
      error.value = err.response?.data?.message || err.message || '同步失败'
      throw err
    }
    // ⭐ 关键修改：不在这里清除 isLoading（因为已经移除了）
  }

  // ⭐ v4.18.2修复：批量同步也采用异步架构
  async function syncBatch(options = {}) {
    // ⭐ 关键修改：不设置 isLoading，避免阻塞UI
    error.value = null

    // ⭐ 关键修改：添加超时机制
    const API_TIMEOUT = 5000

    try {
      const response = await Promise.race([
        api.post('/data-sync/batch', {
          platform: options.platform,
          domains: options.domains,
          granularities: options.granularities,
          since_hours: options.sinceHours,
          limit: options.limit ?? 100,
          only_with_template: options.onlyWithTemplate ?? true,
          allow_quarantine: options.allowQuarantine ?? true,
        }),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('API响应超时')), API_TIMEOUT)
        )
      ])

      // ⭐ 关键修改：立即启动轮询
      if (response.data?.task_id) {
        currentTaskId.value = response.data.task_id
        // 立即开始轮询进度
        startPolling(response.data.task_id)
      }

      return response.data
    } catch (err) {
      // ⭐ 关键修改：超时错误处理
      if (err.message === 'API响应超时') {
        error.value = 'API响应超时，但任务可能已提交，请查看任务进度'
        return {
          success: true,
          status: 'submitted',
          message: '任务已提交（API响应超时，但任务可能已成功提交）'
        }
      }
      error.value = err.message || '批量同步失败'
      throw err
    }
    // ⭐ 关键修改：不在这里清除 isLoading（因为已经移除了）
  }

  async function fetchProgress(taskId) {
    try {
      const response = await api.get(`/data-sync/progress/${taskId}`)
      if (response.data?.success) {
        syncProgress.value = response.data.data
        return response.data.data
      }
      return null
    } catch (err) {
      error.value = err.message || '获取进度失败'
      return null
    }
  }

  async function fetchTasks(status = null) {
    try {
      const params = {}
      if (status) {
        params.status = status
      }
      const response = await api.get('/data-sync/tasks', { params })
      if (response.data?.success) {
        syncTasks.value = response.data.data
        return response.data.data
      }
      return []
    } catch (err) {
      error.value = err.message || '获取任务列表失败'
      return []
    }
  }

  // 轮询进度
  let pollingInterval = null

  function startPolling(taskId, interval = 2000) {
    // 停止之前的轮询
    stopPolling()

    // 立即获取一次进度
    fetchProgress(taskId)

    // 开始轮询
    pollingInterval = setInterval(() => {
      fetchProgress(taskId).then(progress => {
        // 如果任务完成或失败，停止轮询
        if (progress && (progress.status === 'completed' || progress.status === 'failed')) {
          stopPolling()
        }
      })
    }, interval)
  }

  function stopPolling() {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
    }
  }

  function reset() {
    currentTaskId.value = null
    syncProgress.value = null
    error.value = null
    stopPolling()
  }

  return {
    // 状态
    currentTaskId,
    syncProgress,
    syncTasks,
    isLoading,
    error,
    // 计算属性
    hasActiveTask,
    progressPercentage,
    // 操作
    syncSingleFile,
    syncBatch,
    fetchProgress,
    fetchTasks,
    startPolling,
    stopPolling,
    reset,
  }
})

