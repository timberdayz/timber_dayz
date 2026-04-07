import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { scanFiles, getFileGroups, previewFile, getFieldMapping, ingestFile, getCatalogStatus, cleanupInvalidFiles } from '../api'

export const useDataStore = defineStore('data', () => {
  // 状态
  const fileGroups = ref(null)
  const selectedFile = ref(null)
  const filePreview = ref(null)
  const fieldMappings = ref({})
  const catalogStatus = ref(null)
  
  const loading = ref({
    scan: false,
    fileGroups: false,
    preview: false,
    mapping: false,
    ingest: false,
    catalog: false,
    cleanup: false
  })

  const error = ref(null)

  // 计算属性
  const platforms = computed(() => {
    return fileGroups.value?.platforms || []
  })

  const domains = computed(() => {
    return fileGroups.value?.domains || {}
  })

  const files = computed(() => {
    return fileGroups.value?.files || {}
  })

  const mappingSuggestions = computed(() => {
    return Object.keys(fieldMappings.value).length > 0 ? fieldMappings.value : null
  })

  // 操作
  const scanFilesAction = async (directories = ['temp/outputs']) => {
    loading.value.scan = true
    error.value = null
    try {
      const response = await scanFiles(directories)
      if (response.success) {
        ElMessage.success(response.message)
        await loadFileGroups()
      } else {
        throw new Error(response.message)
      }
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`扫描失败: ${err.message}`)
      throw err
    } finally {
      loading.value.scan = false
    }
  }

  const loadFileGroups = async () => {
    loading.value.fileGroups = true
    try {
      const response = await getFileGroups()
      fileGroups.value = response
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`加载文件分组失败: ${err.message}`)
      throw err
    } finally {
      loading.value.fileGroups = false
    }
  }

  const selectFile = async (filePath, platform, dataDomain) => {
    loading.value.preview = true
    error.value = null
    selectedFile.value = { filePath, platform, dataDomain }
    
    try {
      // 预览文件
      const previewResponse = await previewFile(filePath, platform, dataDomain)
      if (previewResponse.success) {
        filePreview.value = previewResponse
        
        // 自动获取字段映射
        if (previewResponse.columns && dataDomain) {
          await getFieldMappingAction(previewResponse.columns, dataDomain)
        }
      } else {
        throw new Error(previewResponse.error)
      }
    } catch (err) {
      error.value = err.message
      ElMessage.error(`预览文件失败: ${err.message}`)
      throw err
    } finally {
      loading.value.preview = false
    }
  }

  const getFieldMappingAction = async (columns, dataDomain) => {
    loading.value.mapping = true
    try {
      const response = await getFieldMapping(columns, dataDomain)
      fieldMappings.value = response.mappings
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`获取字段映射失败: ${err.message}`)
      throw err
    } finally {
      loading.value.mapping = false
    }
  }

  const performIngestion = async (filePath, platform, dataDomain, mappings) => {
    loading.value.ingest = true
    try {
      const response = await ingestFile(filePath, platform, dataDomain, mappings)
      if (response.success) {
        ElMessage.success(response.message)
        // 刷新Catalog状态
        await loadCatalogStatus()
      } else {
        throw new Error(response.message)
      }
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`数据入库失败: ${err.message}`)
      throw err
    } finally {
      loading.value.ingest = false
    }
  }

  const loadCatalogStatus = async () => {
    loading.value.catalog = true
    try {
      const response = await getCatalogStatus()
      catalogStatus.value = response
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`加载Catalog状态失败: ${err.message}`)
      throw err
    } finally {
      loading.value.catalog = false
    }
  }

  const refreshCatalogStatus = async () => {
    await loadCatalogStatus()
  }

  const performCleanup = async () => {
    loading.value.cleanup = true
    try {
      const response = await cleanupInvalidFiles()
      ElMessage.success(response.message)
      // 清理后刷新数据
      await loadFileGroups()
      await loadCatalogStatus()
      return response
    } catch (err) {
      error.value = err.message
      ElMessage.error(`清理失败: ${err.message}`)
      throw err
    } finally {
      loading.value.cleanup = false
    }
  }

  const loadInitialData = async () => {
    try {
      await Promise.all([
        loadFileGroups(),
        loadCatalogStatus()
      ])
    } catch (err) {
      console.error('加载初始数据失败:', err)
    }
  }

  return {
    // 状态
    fileGroups,
    selectedFile,
    filePreview,
    fieldMappings,
    catalogStatus,
    loading,
    error,
    
    // 计算属性
    platforms,
    domains,
    files,
    mappingSuggestions,
    
    // 操作
    scanFilesAction,
    loadFileGroups,
    selectFile,
    getFieldMappingAction,
    performIngestion,
    loadCatalogStatus,
    refreshCatalogStatus,
    performCleanup,
    loadInitialData
  }
})
