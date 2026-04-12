import api from './index.js'

export default {
  // Program payload supports learning_url, exam_url, materials_url, external_course_id, and external_exam_id.
  async getOverview() {
    const response = await api._get('/training/overview')
    return response?.data ?? response ?? {}
  },

  async getPrograms() {
    const response = await api._get('/training/programs')
    return response?.data ?? response ?? {}
  },

  async createProgram(payload) {
    const response = await api._post('/training/programs', payload)
    return response?.data ?? response ?? {}
  },

  async bindFeishu(programId, payload) {
    const response = await api._put(`/training/programs/${programId}/feishu-binding`, payload)
    return response?.data ?? response ?? {}
  },

  async getAssignments() {
    const response = await api._get('/training/assignments')
    return response?.data ?? response ?? {}
  },

  async getAssignmentDetail(assignmentId) {
    const response = await api._get(`/training/assignments/${assignmentId}`)
    return response?.data ?? response ?? {}
  },

  async createAssignment(payload) {
    const response = await api._post('/training/assignments', payload)
    return response?.data ?? response ?? {}
  },

  async getResults() {
    const response = await api._get('/training/results')
    return response?.data ?? response ?? {}
  },

  async updateResult(assignmentId, payload) {
    const response = await api._put(`/training/results/${assignmentId}`, payload)
    return response?.data ?? response ?? {}
  },

  async getMyOverview() {
    const response = await api._get('/training/my-overview')
    return response?.data ?? response ?? {}
  },

  async getFeishuConfig() {
    const response = await api._get('/training/integrations/feishu/config')
    return response?.data ?? response ?? {}
  },

  async saveFeishuConfig(payload) {
    const response = await api._put('/training/integrations/feishu/config', payload)
    return response?.data ?? response ?? {}
  },

  async syncFeishuResults(payload) {
    const response = await api._post('/training/integrations/feishu/sync-results', payload)
    return response?.data ?? response ?? {}
  }
}
