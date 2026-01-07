/**
 * 数据采集状态管理 - 混合架构版本
 * 
 * 集成统一后端API (http://localhost:8000/api/collection)
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useCollectionStore = defineStore('collection', () => {
  // 状态
  const loading = ref(false)
  const globalStatus = ref('idle') // idle, running, stopped, error
  
  const platforms = ref([
    {
      name: 'SHOPEE',
      icon: 'Shop',
      status: 'idle',
      progress: 0,
      lastRun: null,
      successRate: 95
    },
    {
      name: 'TIKTOK',
      icon: 'VideoCamera',
      status: 'idle',
      progress: 0,
      lastRun: null,
      successRate: 92
    },
    {
      name: 'AMAZON',
      icon: 'ShoppingBag',
      status: 'idle',
      progress: 0,
      lastRun: null,
      successRate: 88
    },
    {
      name: 'MIAOSHOU',
      icon: 'Store',
      status: 'idle',
      progress: 0,
      lastRun: null,
      successRate: 98
    }
  ])
  
  const historyRecords = ref([])
  const performanceMetrics = ref({
    totalTasks: 0,
    successfulTasks: 0,
    failedTasks: 0,
    averageDuration: 0
  })

  // 计算属性
  const overallSuccessRate = computed(() => {
    const total = performanceMetrics.value.totalTasks
    return total > 0 ? (performanceMetrics.value.successfulTasks / total * 100).toFixed(1) : 0
  })

  const runningPlatforms = computed(() => {
    return platforms.value.filter(p => p.status === 'running')
  })

  // 启动全平台采集
  const startAllCollection = async () => {
    try {
      loading.value = true
      globalStatus.value = 'running'
      
      // 模拟启动所有平台采集
      for (const platform of platforms.value) {
        platform.status = 'running'
        platform.progress = 0
      }
      
      // 模拟采集进度更新
      simulateCollectionProgress()
      
      return { success: true }
    } catch (error) {
      globalStatus.value = 'error'
      return { success: false, error: error.message }
    } finally {
      loading.value = false
    }
  }

  // 停止所有采集
  const stopAllCollection = async () => {
    try {
      loading.value = true
      globalStatus.value = 'stopped'
      
      // 停止所有平台采集
      for (const platform of platforms.value) {
        platform.status = 'idle'
        platform.progress = 0
      }
      
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    } finally {
      loading.value = false
    }
  }

  // 启动单个平台采集
  const startPlatformCollection = async (platformName) => {
    try {
      const platform = platforms.value.find(p => p.name === platformName)
      if (platform) {
        platform.status = 'running'
        platform.progress = 0
        platform.lastRun = new Date().toISOString()
        
        // 模拟采集进度
        simulatePlatformProgress(platform)
      }
      
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  // 停止单个平台采集
  const stopPlatformCollection = async (platformName) => {
    try {
      const platform = platforms.value.find(p => p.name === platformName)
      if (platform) {
        platform.status = 'idle'
        platform.progress = 0
      }
      
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  // 获取历史记录
  const fetchHistoryRecords = async () => {
    try {
      // 调用真实API
      const data = await api.getCollectionHistory(50)
      
      // 转换数据格式
      historyRecords.value = data.map(record => ({
        platform: record.platform,
        taskType: record.task_type || '数据采集',
        startTime: record.start_time || '',
        endTime: record.end_time || '',
        duration: record.duration || '',
        status: record.status,
        filesCount: record.files_count || 0,
        errorMessage: record.error_message || ''
      }))
      
      return { success: true, data: historyRecords.value }
    } catch (error) {
      console.error('获取采集历史失败:', error)
      // 失败时使用模拟数据
      historyRecords.value = []
      return { success: false, error: error.message }
    }
  }

  // 获取性能指标
  const fetchPerformanceMetrics = async () => {
    try {
      performanceMetrics.value = {
        totalTasks: 156,
        successfulTasks: 142,
        failedTasks: 14,
        averageDuration: 18.5
      }
      
      return { success: true, data: performanceMetrics.value }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  // 模拟采集进度
  const simulateCollectionProgress = () => {
    const interval = setInterval(() => {
      const runningPlatforms = platforms.value.filter(p => p.status === 'running')
      
      if (runningPlatforms.length === 0) {
        clearInterval(interval)
        globalStatus.value = 'idle'
        return
      }
      
      runningPlatforms.forEach(platform => {
        platform.progress += Math.random() * 10
        
        if (platform.progress >= 100) {
          platform.progress = 100
          platform.status = 'idle'
          platform.lastRun = new Date().toISOString()
        }
      })
    }, 2000)
  }

  // 模拟单个平台进度
  const simulatePlatformProgress = (platform) => {
    const interval = setInterval(() => {
      if (platform.status !== 'running') {
        clearInterval(interval)
        return
      }
      
      platform.progress += Math.random() * 15
      
      if (platform.progress >= 100) {
        platform.progress = 100
        platform.status = 'idle'
        platform.lastRun = new Date().toISOString()
        clearInterval(interval)
      }
    }, 1500)
  }

  // 初始化数据
  const initData = async () => {
    try {
      await Promise.all([
        fetchHistoryRecords(),
        fetchPerformanceMetrics()
      ])
      
      return { success: true }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  return {
    // 状态
    loading,
    globalStatus,
    platforms,
    historyRecords,
    performanceMetrics,
    
    // 计算属性
    overallSuccessRate,
    runningPlatforms,
    
    // 方法
    startAllCollection,
    stopAllCollection,
    startPlatformCollection,
    stopPlatformCollection,
    fetchHistoryRecords,
    fetchPerformanceMetrics,
    initData
  }
})
