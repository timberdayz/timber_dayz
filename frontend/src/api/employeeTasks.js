import api from './index.js'

export default {
  async listTasks(scope = 'owner') {
    const response = await api._get('/employee-tasks', { params: { scope } })
    return response?.data ?? response ?? {}
  },

  async getTask(taskId) {
    const response = await api._get(`/employee-tasks/${taskId}`)
    return response?.data ?? response ?? {}
  },

  async startTask(taskId) {
    const response = await api._post(`/employee-tasks/${taskId}/start`)
    return response?.data ?? response ?? {}
  },

  async submitTask(taskId, payload) {
    const response = await api._post(`/employee-tasks/${taskId}/submit`, payload)
    return response?.data ?? response ?? {}
  },

  async appendComment(taskId, comment) {
    const response = await api._post(`/employee-tasks/${taskId}/comment`, { comment })
    return response?.data ?? response ?? {}
  },

  async appendSupplement(taskId, payload) {
    const response = await api._post(`/employee-tasks/${taskId}/supplement`, { payload })
    return response?.data ?? response ?? {}
  },

  async closeByInitiator(taskId, reason) {
    const response = await api._post(`/employee-tasks/${taskId}/close-by-initiator`, { reason })
    return response?.data ?? response ?? {}
  },

  async requestCancel(taskId, reason) {
    const response = await api._post(`/employee-tasks/${taskId}/request-cancel`, { reason })
    return response?.data ?? response ?? {}
  },

  async reassignTask(taskId, newOwnerUserId, reason) {
    const response = await api._post(`/employee-tasks/${taskId}/reassign`, { new_owner_user_id: newOwnerUserId, reason })
    return response?.data ?? response ?? {}
  },

  async takeOverTask(taskId, reason) {
    const response = await api._post(`/employee-tasks/${taskId}/takeover`, { reason })
    return response?.data ?? response ?? {}
  },

  async forceCloseTask(taskId, reason) {
    const response = await api._post(`/employee-tasks/${taskId}/force-close`, { reason })
    return response?.data ?? response ?? {}
  }
}
