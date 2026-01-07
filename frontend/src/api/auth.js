/**
 * 认证相关API
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
   * 用户登录
   * @param {Object} credentials - 登录凭证
   * @param {string} credentials.username - 用户名
   * @param {string} credentials.password - 密码
   * @returns {Promise} 登录响应（包含token）
   */
  async login(credentials) {
    return await api._post('/auth/login', credentials)
  },

  /**
   * 刷新令牌
   * @param {string} refreshToken - 刷新令牌
   * @returns {Promise} 新的访问令牌
   */
  async refreshToken(refreshToken) {
    return await api._post('/auth/refresh', { refresh_token: refreshToken })
  },

  /**
   * 用户登出
   * @returns {Promise} 登出结果
   */
  async logout() {
    return await api._post('/auth/logout')
  },

  /**
   * 获取当前用户信息
   * @returns {Promise} 当前用户信息
   */
  async getCurrentUser() {
    return await api._get('/auth/me')
  },

  /**
   * 更新当前用户信息
   * @param {Object} userData - 用户数据
   * @returns {Promise} 更新后的用户信息
   */
  async updateCurrentUser(userData) {
    return await api._put('/auth/me', userData)
  },

  /**
   * 修改密码
   * @param {Object} passwordData - 密码数据
   * @param {string} passwordData.oldPassword - 旧密码
   * @param {string} passwordData.newPassword - 新密码
   * @returns {Promise} 修改结果
   */
  async changePassword(passwordData) {
    return await api._post('/auth/change-password', passwordData)
  },

  /**
   * 获取审计日志
   */
  async getAuditLogs(page = 1, pageSize = 20) {
    return await api.get(`/auth/audit-logs?page=${page}&page_size=${pageSize}`)
  },

  /**
   * 用户注册
   * @param {Object} userData - 注册数据
   * @param {string} userData.username - 用户名
   * @param {string} userData.email - 邮箱
   * @param {string} userData.password - 密码
   * @param {string} userData.full_name - 姓名（可选）
   * @param {string} userData.phone - 手机号（可选）
   * @param {string} userData.department - 部门（可选）
   * @returns {Promise} 注册响应
   */
  async register(userData) {
    return await api._post('/auth/register', userData)
  }
}
