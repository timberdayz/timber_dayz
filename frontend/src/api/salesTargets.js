import api from './index.js'

export default {
  async getShops() {
    return await api._get('/targets/shops')
  },

  async getList(params = {}) {
    return await api._get('/config/sales-targets', { params })
  },

  async create(payload) {
    return await api._post('/config/sales-targets', payload)
  },

  async update(id, payload) {
    return await api._put(`/config/sales-targets/${id}`, payload)
  },

  async remove(id) {
    return await api._delete(`/config/sales-targets/${id}`)
  },

  async copyLastMonth(targetMonth) {
    return await api._post(`/config/sales-targets/copy-last-month?target_month=${encodeURIComponent(targetMonth)}`)
  },
}
