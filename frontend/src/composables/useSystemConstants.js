/**
 * 系统常量Composable - v4.3.5
 * 统一从后端API获取平台/数据域/粒度等常量
 * 避免前端硬编码导致的双重维护
 */

import { ref, onMounted } from 'vue'
import api from '@/api'

// 全局缓存（所有组件共享）
const platformsCache = ref([])
const dataDomainsCache = ref([])
const granularitiesCache = ref([])
const loaded = ref(false)
const loading = ref(false)

export function useSystemConstants() {
  const loadConstants = async () => {
    if (loaded.value || loading.value) {
      return {
        platforms: platformsCache.value,
        data_domains: dataDomainsCache.value,
        granularities: granularitiesCache.value
      }
    }

    loading.value = true
    try {
      // ⭐ 修复：响应拦截器已提取data字段，response就是data内容
      const response = await api._get('/system/constants')
      if (response) {
        platformsCache.value = response.platforms || []
        dataDomainsCache.value = response.data_domains || []
        granularitiesCache.value = response.granularities || []
        loaded.value = true
      }
    } catch (error) {
      console.error('Failed to load system constants:', error)
      // 兜底：使用硬编码（仅作为最后的fallback）
      platformsCache.value = ['shopee', 'tiktok', 'miaoshou']
      dataDomainsCache.value = ['orders', 'products', 'services', 'traffic']
      granularitiesCache.value = ['daily', 'weekly', 'monthly', 'snapshot']
    } finally {
      loading.value = false
    }

    return {
      platforms: platformsCache.value,
      data_domains: dataDomainsCache.value,
      granularities: granularitiesCache.value
    }
  }

  return {
    platforms: platformsCache,
    data_domains: dataDomainsCache,
    granularities: granularitiesCache,
    loaded,
    loading,
    loadConstants
  }
}

// 便捷函数：自动在mounted时加载
export function useAutoLoadConstants() {
  const constants = useSystemConstants()
  
  onMounted(async () => {
    if (!constants.loaded.value) {
      await constants.loadConstants()
    }
  })
  
  return constants
}

