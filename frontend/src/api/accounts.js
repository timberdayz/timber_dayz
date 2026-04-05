/**
 * 主账号 / 店铺账号 / 店铺别名 API 服务。
 */

import api from './index'

export default {
  async listMainAccounts(params = {}) {
    return await api.get('/main-accounts', { params })
  },

  async createMainAccount(data) {
    return await api.post('/main-accounts', data)
  },

  async updateMainAccount(mainAccountId, data) {
    return await api.put(`/main-accounts/${mainAccountId}`, data)
  },

  async deleteMainAccount(mainAccountId) {
    return await api.delete(`/main-accounts/${mainAccountId}`)
  },

  async listShopAccounts(params = {}) {
    return await api.get('/shop-accounts', { params })
  },

  async createShopAccount(data) {
    return await api.post('/shop-accounts', data)
  },

  async updateShopAccount(shopAccountId, data) {
    return await api.put(`/shop-accounts/${shopAccountId}`, data)
  },

  async deleteShopAccount(shopAccountId) {
    return await api.delete(`/shop-accounts/${shopAccountId}`)
  },

  async batchCreateShopAccounts(batchData) {
    return await api.post('/shop-accounts/batch', batchData)
  },

  async listShopAccountAliases(params = {}) {
    return await api.get('/shop-account-aliases', { params })
  },

  async claimShopAccountAlias(data) {
    return await api.post('/shop-account-aliases/claim', data)
  },

  async clearShopAccountPrimaryAlias(shopAccountId) {
    return await api.delete(`/shop-account-aliases/primary/${shopAccountId}`)
  },

  async listPlatformShopDiscoveries(params = {}) {
    return await api.get('/platform-shop-discoveries', { params })
  },

  async confirmPlatformShopDiscovery(discoveryId, data) {
    return await api.post(`/platform-shop-discoveries/${discoveryId}/confirm`, data)
  },

  async runCurrentShopDiscovery(mainAccountId, data = {}) {
    return await api.post(`/main-accounts/${mainAccountId}/shop-discovery/current`, data)
  },

  async createShopAccountFromDiscovery(discoveryId, data) {
    return await api.post(`/platform-shop-discoveries/${discoveryId}/create-shop-account`, data)
  },

  async getUnmatchedShopAliases() {
    return await api.get('/shop-account-aliases/unmatched')
  },

  async getStats() {
    const shopAccounts = await this.listShopAccounts()
    const platformBreakdown = {}
    for (const item of shopAccounts || []) {
      const key = item.platform || 'unknown'
      platformBreakdown[key] = (platformBreakdown[key] || 0) + 1
    }
    return {
      total: (shopAccounts || []).length,
      active: (shopAccounts || []).filter((item) => item.enabled).length,
      inactive: (shopAccounts || []).filter((item) => !item.enabled).length,
      platforms: Object.keys(platformBreakdown).length,
      platform_breakdown: platformBreakdown,
    }
  },

}
