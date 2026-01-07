/**
 * 角色管理API
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
   * 创建角色
   * @param {Object} roleData - 角色数据
   * @returns {Promise} 创建的角色信息
   */
  async createRole(roleData) {
    return await api._post('/roles/', roleData)
  },

  /**
   * 获取角色列表
   * @returns {Promise} 角色列表
   */
  async getRoles() {
    return await api._get('/roles/')
  },

  /**
   * 获取角色详情
   * @param {number} roleId - 角色ID
   * @returns {Promise} 角色详情
   */
  async getRole(roleId) {
    return await api._get(`/roles/${roleId}`)
  },

  /**
   * 更新角色信息
   * @param {number} roleId - 角色ID
   * @param {Object} roleData - 角色数据
   * @returns {Promise} 更新后的角色信息
   */
  async updateRole(roleId, roleData) {
    return await api._put(`/roles/${roleId}`, roleData)
  },

  /**
   * 删除角色
   * @param {number} roleId - 角色ID
   * @returns {Promise} 删除结果
   */
  async deleteRole(roleId) {
    return await api._delete(`/roles/${roleId}`)
  },

  /**
   * 获取可用权限列表
   * @returns {Promise} 权限列表
   */
  async getAvailablePermissions() {
    return await api._get('/roles/permissions/available')
  }
}
