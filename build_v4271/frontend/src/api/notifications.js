/**
 * 通知管理API (v4.19.0)
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
   * 获取通知列表
   * @param {Object} params - 查询参数
   * @param {number} params.page - 页码（默认1）
   * @param {number} params.page_size - 每页数量（默认20）
   * @param {boolean} params.is_read - 过滤已读/未读（可选）
   * @param {string} params.notification_type - 过滤通知类型（可选）
   * @returns {Promise} 通知列表响应
   */
  async getNotifications(params = {}) {
    const queryParams = {
      page: params.page || 1,
      page_size: params.page_size || 20,
      ...params
    }
    // v4.19.0: 支持优先级过滤和排序
    if (params.priority) {
      queryParams.priority = params.priority
    }
    if (params.sort_by) {
      queryParams.sort_by = params.sort_by
    }
    return await api._get('/notifications', { params: queryParams })
  },

  /**
   * 获取未读通知数量
   * @returns {Promise<{unread_count: number}>} 未读数量
   */
  async getUnreadCount() {
    return await api._get('/notifications/unread-count')
  },

  /**
   * 获取单个通知详情
   * @param {number} notificationId - 通知ID
   * @returns {Promise} 通知详情
   */
  async getNotification(notificationId) {
    return await api._get(`/notifications/${notificationId}`)
  },

  /**
   * 标记单个通知为已读
   * @param {number} notificationId - 通知ID
   * @returns {Promise} 标记结果
   */
  async markAsRead(notificationId) {
    return await api._put(`/notifications/${notificationId}/read`)
  },

  /**
   * 标记通知为已读（批量或全部）
   * @param {Array<number>} notificationIds - 通知ID列表（为空则标记全部）
   * @returns {Promise} 标记结果
   */
  async markAllAsRead(notificationIds = []) {
    return await api._put('/notifications/read-all', { notification_ids: notificationIds })
  },

  /**
   * 删除单个通知
   * @param {number} notificationId - 通知ID
   * @returns {Promise} 删除结果
   */
  async deleteNotification(notificationId) {
    return await api._delete(`/notifications/${notificationId}`)
  },

  /**
   * 删除所有已读通知
   * @returns {Promise} 删除结果
   */
  async deleteAllReadNotifications() {
    return await api._delete('/notifications')
  },

  /**
   * v4.19.0: 执行通知快速操作
   * @param {number} notificationId - 通知ID
   * @param {string} actionType - 操作类型（approve_user, reject_user）
   * @param {string} reason - 操作原因（拒绝时需要）
   * @returns {Promise} 操作结果
   */
  async executeAction(notificationId, actionType, reason = null) {
    const data = { action_type: actionType }
    if (reason) {
      data.reason = reason
    }
    return await api._post(`/notifications/${notificationId}/action`, data)
  },

  /**
   * v4.19.0: 获取按类型分组的通知列表
   * @returns {Promise} 分组列表响应
   */
  async getNotificationsGrouped() {
    return await api._get('/notifications/grouped')
  }
}

