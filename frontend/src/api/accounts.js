/**
 * 账号管理 API 服务。
 *
 * 运行时数据源为数据库中的 `core.platform_accounts`。
 * 历史导入入口已移除。
 */

import api from './index'

export default {
  async listAccounts(params = {}) {
    return await api.get('/accounts/', { params })
  },

  async getAccount(accountId) {
    return await api.get(`/accounts/${accountId}`)
  },

  async createAccount(data) {
    return await api.post('/accounts/', data)
  },

  async updateAccount(accountId, data) {
    return await api.put(`/accounts/${accountId}`, data)
  },

  async deleteAccount(accountId) {
    return await api.delete(`/accounts/${accountId}`)
  },

  async batchCreate(batchData) {
    return await api.post('/accounts/batch', batchData)
  },

  async getStats() {
    return await api.get('/accounts/stats/summary')
  },

  async getUnmatchedShopAliases() {
    return await api.get('/accounts/unmatched-shop-aliases')
  }
}
