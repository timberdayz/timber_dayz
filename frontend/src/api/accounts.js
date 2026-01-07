/**
 * 账号管理API服务 (v4.7.0)
 * 
 * 提供平台账号管理的API调用封装
 */

import api from './index'

export default {
  /**
   * 获取账号列表
   * @param {Object} params - 查询参数
   * @param {string} params.platform - 平台筛选
   * @param {boolean} params.enabled - 启用状态
   * @param {string} params.shop_type - 店铺类型
   * @param {string} params.search - 搜索关键词
   * @returns {Promise<Array>} 账号列表
   */
  async listAccounts(params = {}) {
    // v4.18.0修复：账号管理使用 /api/accounts，采集模块使用 /api/collection/accounts
    const response = await api.get('/accounts', { params })
    return response  // ✅ 修复：直接返回response（已经是数组）
  },

  /**
   * 获取账号详情
   * @param {string} accountId - 账号ID
   * @returns {Promise<Object>} 账号详情
   */
  async getAccount(accountId) {
    const response = await api.get(`/accounts/${accountId}`)
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 创建账号
   * @param {Object} data - 账号数据
   * @returns {Promise<Object>} 创建的账号
   */
  async createAccount(data) {
    const response = await api.post('/accounts/', data)
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 更新账号
   * @param {string} accountId - 账号ID
   * @param {Object} data - 更新数据
   * @returns {Promise<Object>} 更新后的账号
   */
  async updateAccount(accountId, data) {
    const response = await api.put(`/accounts/${accountId}`, data)
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 删除账号
   * @param {string} accountId - 账号ID
   * @returns {Promise<Object>} 删除结果
   */
  async deleteAccount(accountId) {
    const response = await api.delete(`/accounts/${accountId}`)
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 批量创建账号（多店铺）
   * @param {Object} batchData - 批量数据
   * @param {string} batchData.parent_account - 主账号
   * @param {string} batchData.platform - 平台
   * @param {string} batchData.username - 用户名
   * @param {string} batchData.password - 密码
   * @param {Array} batchData.shops - 店铺列表
   * @returns {Promise<Array>} 创建的账号列表
   */
  async batchCreate(batchData) {
    const response = await api.post('/accounts/batch', batchData)
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 从local_accounts.py导入
   * @returns {Promise<Object>} 导入结果
   */
  async importFromLocal() {
    const response = await api.post('/accounts/import-from-local')
    return response  // ✅ 修复：直接返回response
  },

  /**
   * 获取账号统计
   * @returns {Promise<Object>} 统计数据
   */
  async getStats() {
    const response = await api.get('/accounts/stats/summary')
    return response  // ✅ 修复：直接返回response
  }
}

