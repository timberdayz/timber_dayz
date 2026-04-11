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
  }
}
