/**
 * Metabase API服务
 * 用于与后端Metabase代理API交互
 */

import api from '@/api'

const metabaseApi = {
  /**
   * 获取嵌入token
   * @param {Object} params - 参数
   * @param {number|string} params.dashboard_id - Dashboard ID
   * @param {Object} params.filters - 筛选器对象
   * @returns {Promise<string>} 嵌入token
   */
  async getEmbeddingToken(params) {
    try {
      const response = await api.post('/metabase/embedding-token', params)
      return response.data?.token || response.token
    } catch (error) {
      console.error('获取Metabase嵌入token失败:', error)
      throw error
    }
  },

  /**
   * 获取Dashboard嵌入URL
   * @param {Object} params - 参数
   * @param {number|string} params.dashboard_id - Dashboard ID
   * @param {Object} params.filters - 筛选器对象
   * @param {string} params.granularity - 时间粒度
   * @returns {Promise<string>} 嵌入URL
   */
  async getDashboardEmbedUrl(params) {
    try {
      const response = await api.get(`/metabase/dashboard/${params.dashboard_id}/embed-url`, {
        params: {
          filters: params.filters,
          granularity: params.granularity
        }
      })
      return response.data?.url || response.url
    } catch (error) {
      console.error('获取Metabase Dashboard嵌入URL失败:', error)
      throw error
    }
  },

  /**
   * 刷新物化视图
   * @returns {Promise<void>}
   */
  async refreshViews() {
    try {
      await api.post('/metabase/refresh-views')
    } catch (error) {
      console.error('刷新Metabase视图失败:', error)
      throw error
    }
  },

  /**
   * 检查Metabase健康状态
   * @returns {Promise<boolean>} 是否健康
   */
  async checkHealth() {
    try {
      const response = await api.get('/metabase/health')
      return response.data?.healthy || response.healthy || false
    } catch (error) {
      console.error('检查Metabase健康状态失败:', error)
      return false
    }
  }
}

export default metabaseApi

