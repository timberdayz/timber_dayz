/**
 * 用户管理API
 * 
 * 统一API调用规范：
 * - 使用统一的api实例（从index.js导入）
 * - 统一方法命名：getXxx、createXxx、updateXxx、deleteXxx
 * - 统一参数传递：GET使用params，POST/PUT/DELETE使用data
 * - 统一错误处理：由响应拦截器自动处理
 */

import api from './index.js'

export default {
  /**
   * 创建用户
   * @param {Object} userData - 用户数据
   * @returns {Promise} 创建的用户信息
   */
  async createUser(userData) {
    return await api._post('/users/', userData)
  },

  /**
   * 获取用户列表
   * @param {number} page - 页码（默认1）
   * @param {number} pageSize - 每页条数（默认20）
   * @returns {Promise} 用户列表
   */
  async getUsers(page = 1, pageSize = 20) {
    return await api._get('/users/', { params: { page, page_size: pageSize } })
  },

  /**
   * 获取用户详情
   * @param {number} userId - 用户ID
   * @returns {Promise} 用户详情
   */
  async getUser(userId) {
    return await api._get(`/users/${userId}`)
  },

  /**
   * 更新用户信息
   * @param {number} userId - 用户ID
   * @param {Object} userData - 用户数据
   * @returns {Promise} 更新后的用户信息
   */
  async updateUser(userId, userData) {
    return await api._put(`/users/${userId}`, userData)
  },

  /**
   * 删除用户
   * @param {number} userId - 用户ID
   * @returns {Promise} 删除结果
   */
  async deleteUser(userId) {
    return await api._delete(`/users/${userId}`)
  },

  /**
   * 重置用户密码
   * @param {number} userId - 用户ID
   * @param {string} newPassword - 新密码
   * @returns {Promise} 重置结果
   */
  async resetUserPassword(userId, newPassword) {
    return await api._post(`/users/${userId}/reset-password`, { new_password: newPassword })
  },

  /**
   * 审批用户
   * @param {number} userId - 用户ID
   * @param {Object} approvalData - 审批数据
   * @param {Array<number>} approvalData.role_ids - 角色ID列表（可选）
   * @param {string} approvalData.notes - 审批备注（可选）
   * @returns {Promise} 审批结果
   */
  async approveUser(userId, approvalData = {}) {
    return await api._post(`/users/${userId}/approve`, approvalData)
  },

  /**
   * 拒绝用户
   * @param {number} userId - 用户ID
   * @param {Object} rejectionData - 拒绝数据
   * @param {string} rejectionData.reason - 拒绝原因
   * @returns {Promise} 拒绝结果
   */
  async rejectUser(userId, rejectionData) {
    return await api._post(`/users/${userId}/reject`, rejectionData)
  },

  /**
   * 获取待审批用户列表
   * @param {number} page - 页码（默认1）
   * @param {number} pageSize - 每页条数（默认20）
   * @returns {Promise} 待审批用户列表
   */
  async getPendingUsers(page = 1, pageSize = 20) {
    return await api._get('/users/pending', { params: { page, page_size: pageSize } })
  },

  /**
   * 获取当前用户的所有活跃会话
   * @returns {Promise} 会话列表
   */
  async getMySessions() {
    return await api._get('/users/me/sessions')
  },

  /**
   * 撤销指定会话（强制登出其他设备）
   * @param {string} sessionId - 会话ID
   * @returns {Promise} 撤销结果
   */
  async revokeSession(sessionId) {
    return await api._delete(`/users/me/sessions/${sessionId}`)
  },

  /**
   * 撤销除当前会话外的所有会话
   * @param {string} currentSessionId - 当前会话ID（从响应头 X-Session-ID 获取）
   * @returns {Promise} 撤销结果
   */
  async revokeAllOtherSessions(currentSessionId) {
    return await api._delete('/users/me/sessions', {
      headers: {
        'X-Session-ID': currentSessionId
      }
    })
  },

  /**
   * v4.19.0: 获取当前用户所有通知偏好
   * @returns {Promise} 通知偏好列表
   */
  async getNotificationPreferences() {
    return await api._get('/users/me/notification-preferences')
  },

  /**
   * v4.19.0: 批量更新通知偏好
   * @param {Array<Object>} preferences - 通知偏好列表
   * @param {string} preferences[].notification_type - 通知类型
   * @param {boolean} preferences[].enabled - 是否启用应用内通知
   * @param {boolean} preferences[].desktop_enabled - 是否启用桌面通知
   * @returns {Promise} 更新后的通知偏好列表
   */
  async updateNotificationPreferences(preferences) {
    return await api._put('/users/me/notification-preferences', {
      preferences: preferences
    })
  },

  /**
   * v4.19.0: 获取特定类型通知偏好
   * @param {string} notificationType - 通知类型
   * @returns {Promise} 通知偏好
   */
  async getNotificationPreference(notificationType) {
    return await api._get(`/users/me/notification-preferences/${notificationType}`)
  },

  /**
   * v4.19.0: 更新特定类型通知偏好
   * @param {string} notificationType - 通知类型
   * @param {Object} preference - 通知偏好
   * @param {boolean} preference.enabled - 是否启用应用内通知
   * @param {boolean} preference.desktop_enabled - 是否启用桌面通知
   * @returns {Promise} 更新后的通知偏好
   */
  async updateNotificationPreference(notificationType, preference) {
    return await api._put(`/users/me/notification-preferences/${notificationType}`, preference)
  }
}
