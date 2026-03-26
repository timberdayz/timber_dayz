import api from './index'

export default {
  async getHealth() {
    return await api.get('/cloud-sync/health')
  },

  async getTables(params = {}) {
    return await api.get('/cloud-sync/tables', { params })
  },

  async getTasks(params = {}) {
    return await api.get('/cloud-sync/tasks', { params })
  },

  async getTask(jobId) {
    return await api.get(`/cloud-sync/tasks/${jobId}`)
  },

  async getEvents(params = {}) {
    return await api.get('/cloud-sync/events', { params })
  },

  async triggerSync(payload) {
    return await api.post('/cloud-sync/tasks/trigger', payload)
  },

  async retryTask(jobId) {
    return await api.post(`/cloud-sync/tasks/${jobId}/retry`)
  },

  async cancelTask(jobId) {
    return await api.post(`/cloud-sync/tasks/${jobId}/cancel`)
  },

  async dryRunTable(tableName, payload = {}) {
    return await api.post(`/cloud-sync/tables/${tableName}/dry-run`, payload)
  },

  async repairCheckpoint(tableName, payload = {}) {
    return await api.post(`/cloud-sync/tables/${tableName}/repair-checkpoint`, payload)
  },

  async refreshProjection(tableName, payload = {}) {
    return await api.post(`/cloud-sync/tables/${tableName}/refresh-projection`, payload)
  },
}
