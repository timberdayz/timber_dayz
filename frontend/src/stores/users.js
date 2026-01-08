/**
 * 用户管理状态
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import usersApi from '@/api/users'
import { ElMessage } from 'element-plus'

export const useUsersStore = defineStore('users', () => {
  // 状态
  const users = ref([])
  const currentUser = ref(null)
  const isLoading = ref(false)
  const total = ref(0)

  // 获取用户列表
  const fetchUsers = async (page = 1, pageSize = 20) => {
    try {
      isLoading.value = true
      const response = await usersApi.getUsers(page, pageSize)
      // 处理响应格式：可能是数组（直接返回）或对象（包含data和pagination字段）
      const usersList = Array.isArray(response) ? response : (response.data || [])
      users.value = usersList
      // 支持分页响应格式：response.pagination.total 或 response.total
      total.value = response.pagination?.total || response.total || usersList.length
      return usersList
    } catch (error) {
      ElMessage.error('获取用户列表失败: ' + (error.response?.data?.detail || error.message))
      throw error
    } finally {
      isLoading.value = false
    }
  }

  // 获取用户详情
  const fetchUser = async (userId) => {
    try {
      const response = await usersApi.getUser(userId)
      currentUser.value = response.data
      return response.data
    } catch (error) {
      ElMessage.error('获取用户详情失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 创建用户
  const createUser = async (userData) => {
    try {
      const response = await usersApi.createUser(userData)
      ElMessage.success('用户创建成功')
      return response.data
    } catch (error) {
      ElMessage.error('创建用户失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 更新用户
  const updateUser = async (userId, userData) => {
    try {
      const response = await usersApi.updateUser(userId, userData)
      ElMessage.success('用户更新成功')
      return response.data
    } catch (error) {
      ElMessage.error('更新用户失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 删除用户
  const deleteUser = async (userId) => {
    try {
      await usersApi.deleteUser(userId)
      ElMessage.success('用户删除成功')
      // 从列表中移除
      const index = users.value.findIndex(user => user.id === userId)
      if (index > -1) {
        users.value.splice(index, 1)
      }
    } catch (error) {
      ElMessage.error('删除用户失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 重置用户密码
  const resetUserPassword = async (userId, newPassword) => {
    try {
      await usersApi.resetUserPassword(userId, newPassword)
      ElMessage.success('密码重置成功')
    } catch (error) {
      ElMessage.error('密码重置失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  return {
    // 状态
    users,
    currentUser,
    isLoading,
    total,
    
    // 方法
    fetchUsers,
    fetchUser,
    createUser,
    updateUser,
    deleteUser,
    resetUserPassword
  }
})
