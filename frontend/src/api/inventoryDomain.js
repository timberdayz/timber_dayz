import api from './index.js'

export default {
  async getBalances(params = {}) {
    return await api._get('/inventory/balances', { params })
  },

  async getOpeningBalances(params = {}) {
    return await api._get('/inventory/opening-balances', { params })
  },

  async createOpeningBalance(data, params = {}) {
    return await api._post('/inventory/opening-balances', data, { params })
  },

  async getBalanceDetail(platform, shopId, sku) {
    return await api._get(`/inventory/balances/${platform}/${shopId}/${sku}`)
  },

  async getLedger(params = {}) {
    return await api._get('/inventory/ledger', { params })
  },

  async getGrns(params = {}) {
    return await api._get('/inventory/grns', { params })
  },

  async postGrn(grnId, params = {}) {
    return await api._post(`/inventory/grns/${grnId}/post`, null, { params })
  },

  async getAdjustments(params = {}) {
    return await api._get('/inventory/adjustments', { params })
  },

  async createAdjustment(data, params = {}) {
    return await api._post('/inventory/adjustments', data, { params })
  },

  async postAdjustment(adjustmentId, params = {}) {
    return await api._post(`/inventory/adjustments/${adjustmentId}/post`, null, { params })
  },

  async getAlerts(params = {}) {
    return await api._get('/inventory/alerts', { params })
  },

  async getReconciliation(params = {}) {
    return await api._get('/inventory/reconciliation', { params })
  },

  async getAging(params = {}) {
    return await api._get('/inventory/aging', { params })
  },

  async getAgingBuckets(params = {}) {
    return await api._get('/inventory/aging/buckets', { params })
  },

  async getAgingHistory(params = {}) {
    return await api._get('/inventory/aging/history', { params })
  },

  /**
   * SKU 级滞销清单（真库龄口径）
   * 库龄取 mart.inventory_age_current.age_days，与商品中心定价同源。
   */
  async getClearanceRanking(params = {}) {
    return await api._get('/inventory/clearance-ranking', { params })
  }
}
