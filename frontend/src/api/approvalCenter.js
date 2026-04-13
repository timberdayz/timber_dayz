import api from './index.js'

export default {
  async listRequests() {
    const response = await api._get('/approval-center/requests')
    return response?.data ?? response ?? {}
  },

  async listHistory() {
    const response = await api._get('/approval-center/history')
    return response?.data ?? response ?? {}
  },

  async listTemplates() {
    const response = await api._get('/approval-center/templates')
    return response?.data ?? response ?? {}
  },

  async getApproval(approvalId) {
    const response = await api._get(`/approval-center/${approvalId}`)
    return response?.data ?? response ?? {}
  },

  async approve(approvalId, comment = '') {
    const response = await api._post(`/approval-center/${approvalId}/approve`, { comment })
    return response?.data ?? response ?? {}
  },

  async reject(approvalId, comment = '') {
    const response = await api._post(`/approval-center/${approvalId}/reject`, { comment })
    return response?.data ?? response ?? {}
  },

  async withdraw(approvalId, comment = '') {
    const response = await api._post(`/approval-center/${approvalId}/withdraw`, { comment })
    return response?.data ?? response ?? {}
  }
}
