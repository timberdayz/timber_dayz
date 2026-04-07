import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useDataStore = defineStore('data', () => {
  // 状态
  const fileGroups = ref({})
  const selectedPlatform = ref('')
  const selectedDomain = ref('')
  const selectedDate = ref('')
  const selectedFile = ref('')
  const selectedFileId = ref(null) // 仅使用 file_id
  const selectedFilePath = ref('') // 添加文件路径状态
  const selectedGranularity = ref('') // hour/day/week/month for product_metrics
  const headerRow = ref(null)
  const filePreview = ref([])
  const fieldMappings = ref({})
  const catalogStatus = ref({})
  const loading = ref(false)
  const error = ref('')

  // 计算属性
  const platforms = computed(() => Object.keys(fileGroups.value))
  const domains = computed(() => {
    if (!selectedPlatform.value) return []
    return Object.keys(fileGroups.value[selectedPlatform.value] || {})
  })
  const files = computed(() => {
    if (!selectedPlatform.value || !selectedDomain.value) return []

    const platformData = fileGroups.value[selectedPlatform.value] || {}
    const domainData = platformData[selectedDomain.value] || []

    if (Array.isArray(domainData)) {
      // 现在每项多为 {id, file_name, granularity, ...}
      if (!selectedGranularity.value) return domainData
      const g = selectedGranularity.value
      return domainData.filter(item => {
        if (item && typeof item === 'object') {
          // 优先比较granularity字段
          if (item.granularity) return String(item.granularity).toLowerCase() === g
          // 回退用文件名关键字
          const name = String(item.file_name || '')
          const lower = name.toLowerCase()
          const tokens = { daily: ['daily','day'], weekly: ['weekly','week'], monthly: ['monthly','month'], snapshot: ['snapshot','snap'] }[g] || []
          return tokens.some(t => lower.includes(`_${t}_`) || lower.endsWith(`${t}.xlsx`) || lower.endsWith(`${t}.json`))
        }
        // 兼容字符串项
        const lower = String(item).toLowerCase()
        const tokens = { daily: ['daily','day'], weekly: ['weekly','week'], monthly: ['monthly','month'], snapshot: ['snapshot','snap'] }[g] || []
        return tokens.some(t => lower.includes(`_${t}_`) || lower.endsWith(`${t}.xlsx`) || lower.endsWith(`${t}.json`))
      })
    }

    if (typeof domainData === 'object' && domainData !== null) {
      if (!selectedGranularity.value) {
        const allFiles = []
        Object.values(domainData).forEach(fileList => {
          if (Array.isArray(fileList)) allFiles.push(...fileList)
        })
        return allFiles
      }
      const granularityKey = selectedGranularity.value
      const granularityFiles = domainData[granularityKey] || []
      return Array.isArray(granularityFiles) ? granularityFiles : []
    }

    return []
  })

  // 动作
  const scanFiles = async () => {
    loading.value = true
    error.value = ''
    try {
      // ⭐ 修复：响应拦截器已提取data字段，response就是data内容
      const response = await api.scanFiles()
      if (response) {
        await loadFileGroups()
        return { success: true, data: response }
      } else {
        error.value = '扫描文件失败'
        return { success: false, message: '扫描文件失败' }
      }
    } catch (err) {
      error.value = err.message
      return { success: false, message: err.message }
    } finally {
      loading.value = false
    }
  }

  const loadFileGroups = async () => {
    try {
      const response = await api.getFileGroups()
      // 修复：API返回的是 {platforms: [], domains: {}, files: {}}
      if (response && typeof response === 'object') {
        fileGroups.value = response.files || {}
        // 设置平台和域信息
        if (response.platforms) {
          // 可以在这里处理平台信息
        }
        if (response.domains) {
          // 可以在这里处理域信息
        }
      }
      return response
    } catch (err) {
      console.error('Failed to load file groups:', err)
      // 不设置error.value，避免显示错误信息
      return { platforms: [], domains: {}, files: {} }
    }
  }

  const previewFile = async ({ fileId, headerRow = 0 }) => {
    loading.value = true
    try {
      // ⭐ 修复：响应拦截器已提取data字段，response就是data内容
      const response = await api.previewFile({ fileId, headerRow })
      if (response) {
        // 预览返回 data / columns（response已经是data内容，包含data和columns字段）
        filePreview.value = response.data || []
        // 注意：previewColumns 是计算属性，不需要手动设置
        return { success: true, data: response }
      } else {
        error.value = '预览文件失败'
        return { success: false, error: '预览文件失败' }
      }
    } catch (err) {
      error.value = err.message
      return { success: false, error: err.message }
    } finally {
      loading.value = false
    }
  }

  const getFieldMappings = async ({ columns, dataDomain }) => {
    try {
      const response = await api.getFieldMappings({ columns, dataDomain })
      if (response.mappings) {
        fieldMappings.value = response.mappings
      }
      return response
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  const ingestFile = async ({ fileId, platform, domain, mappings, rows }) => {
    loading.value = true
    try {
      const response = await api.ingestFile({ fileId, platform, domain, mappings, rows })
      return response
    } catch (err) {
      error.value = err.message
      return { success: false, message: err.message }
    } finally {
      loading.value = false
    }
  }

  const validateRows = async ({ domain, rows }) => {
    return await api.validateRows({ domain, rows })
  }

  const refreshCatalogStatus = async () => {
    try {
      const status = await api.getCatalogStatus()
      catalogStatus.value = status
      return status
    } catch (err) {
      console.error('Failed to refresh catalog status:', err)
      // 不设置error.value，避免显示错误信息
      return { total: 0, by_status: [] }
    }
  }

  const cleanupInvalidFiles = async () => {
    try {
      const response = await api.cleanupInvalidFiles()
      await refreshCatalogStatus()
      return response
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  const loadInitialData = async () => {
    try {
      // 清除之前的错误状态
      error.value = ''
      await Promise.all([
        loadFileGroups(),
        refreshCatalogStatus()
      ])
    } catch (err) {
      console.error('Failed to load initial data:', err)
      // 不设置error.value，避免显示错误信息
    }
  }

  const getTaskProgress = async (taskId) => {
    try {
      const response = await api.getTaskProgress(taskId)
      return response
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  const listTasks = async (status = null) => {
    try {
      const response = await api.listTasks(status)
      return response
    } catch (err) {
      error.value = err.message
      throw err
    }
  }

  // 重置状态
  const resetState = () => {
    selectedPlatform.value = ''
    selectedDomain.value = ''
    selectedDate.value = ''
    selectedFile.value = ''
    selectedGranularity.value = ''
    filePreview.value = []
    fieldMappings.value = {}
    headerRow.value = null
    error.value = ''
  }

  return {
    // 状态
    fileGroups,
    selectedPlatform,
    selectedDomain,
    selectedFile,
    selectedFileId,
    selectedDate,
    selectedGranularity,
    headerRow,
    filePreview,
    fieldMappings,
    catalogStatus,
    loading,
    error,
    
    // 计算属性
    platforms,
    domains,
    files,
    
    // 动作
    scanFiles,
    loadFileGroups,
    previewFile,
    getFieldMappings,
    ingestFile,
    validateRows,
    refreshCatalogStatus,
    cleanupInvalidFiles,
    loadInitialData,
    getTaskProgress,
    listTasks,
    resetState
  }
})
