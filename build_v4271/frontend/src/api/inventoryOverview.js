import api from './index.js'

export default {
  async getSummary(params = {}) {
    return await api._get('/inventory-overview/summary', { params })
  },

  async getProducts(params = {}) {
    return await api._get('/inventory-overview/products', { params })
  },

  async getProductDetail(sku, params = {}) {
    return await api._get(`/inventory-overview/products/${sku}`, { params })
  },

  async getPlatformBreakdown(params = {}) {
    return await api._get('/inventory-overview/platform-breakdown', { params })
  },

  async getAlerts(params = {}) {
    return await api._get('/inventory-overview/alerts', { params })
  },

  async getReconciliationSnapshot(params = {}) {
    return await api._get('/inventory-overview/reconciliation-snapshot', { params })
  }
}
