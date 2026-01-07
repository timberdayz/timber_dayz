/**
 * 角色管理状态
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import rolesApi from '@/api/roles'
import { ElMessage } from 'element-plus'

export const useRolesStore = defineStore('roles', () => {
  // 状态
  const roles = ref([])
  const currentRole = ref(null)
  const permissions = ref([])
  const isLoading = ref(false)

  // 获取角色列表
  const fetchRoles = async () => {
    try {
      isLoading.value = true
      const response = await rolesApi.getRoles()
      roles.value = response.data
      return response.data
    } catch (error) {
      ElMessage.error('获取角色列表失败: ' + (error.response?.data?.detail || error.message))
      throw error
    } finally {
      isLoading.value = false
    }
  }

  // 获取角色详情
  const fetchRole = async (roleId) => {
    try {
      const response = await rolesApi.getRole(roleId)
      currentRole.value = response.data
      return response.data
    } catch (error) {
      ElMessage.error('获取角色详情失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 创建角色
  const createRole = async (roleData) => {
    try {
      const response = await rolesApi.createRole(roleData)
      ElMessage.success('角色创建成功')
      return response.data
    } catch (error) {
      ElMessage.error('创建角色失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 更新角色
  const updateRole = async (roleId, roleData) => {
    try {
      const response = await rolesApi.updateRole(roleId, roleData)
      ElMessage.success('角色更新成功')
      return response.data
    } catch (error) {
      ElMessage.error('更新角色失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 删除角色
  const deleteRole = async (roleId) => {
    try {
      await rolesApi.deleteRole(roleId)
      ElMessage.success('角色删除成功')
      // 从列表中移除
      const index = roles.value.findIndex(role => role.id === roleId)
      if (index > -1) {
        roles.value.splice(index, 1)
      }
    } catch (error) {
      ElMessage.error('删除角色失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 获取可用权限
  const fetchPermissions = async () => {
    try {
      const response = await rolesApi.getAvailablePermissions()
      permissions.value = response.data
      return response.data
    } catch (error) {
      ElMessage.error('获取权限列表失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  return {
    // 状态
    roles,
    currentRole,
    permissions,
    isLoading,
    
    // 方法
    fetchRoles,
    fetchRole,
    createRole,
    updateRole,
    deleteRole,
    fetchPermissions
  }
})
