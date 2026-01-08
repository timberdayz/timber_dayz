/**
 * 认证状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import authApi from '@/api/auth'
import { ElMessage } from 'element-plus'

export const useAuthStore = defineStore('auth', () => {
  // 状态
  const token = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(null)
  const isLoggedIn = computed(() => !!token.value && !!user.value)
  const isLoading = ref(false)

  // 登录
  const login = async (credentials) => {
    try {
      isLoading.value = true
      const response = await authApi.login(credentials)
      
      // ⭐ v6.0.0修复：登录接口返回的是直接对象 {access_token, refresh_token, user_info}
      // 响应拦截器如果没有 success 字段，会直接返回 data（即整个响应对象）
      // 所以 response 可能是 {access_token, refresh_token, user_info} 或 {data: {...}}
      // 需要兼容两种格式
      const accessToken = response.access_token || response.data?.access_token
      const refreshTokenValue = response.refresh_token || response.data?.refresh_token
      const userInfo = response.user_info || response.data?.user_info
      
      if (!accessToken || !refreshTokenValue) {
        throw new Error('登录响应格式错误：缺少 token')
      }
      
      // 保存令牌
      token.value = accessToken
      refreshToken.value = refreshTokenValue
      user.value = userInfo
      
      // 保存到本地存储
      localStorage.setItem('access_token', token.value)
      localStorage.setItem('refresh_token', refreshToken.value)
      localStorage.setItem('user_info', JSON.stringify(user.value))
      
      // ✅ 2026-01-08: 同步用户信息到userStore（用于权限管理）
      if (userInfo && userInfo.roles) {
        const { useUserStore } = await import('@/stores/user')
        const userStore = useUserStore()
        userStore.updateUserInfo({
          id: userInfo.id,
          username: userInfo.username,
          name: userInfo.full_name || userInfo.username,
          email: userInfo.email,
          roles: userInfo.roles
        })
        userStore.roles = userInfo.roles
        userStore.token = accessToken
        
        // 设置默认激活角色
        if (userInfo.roles.length > 0) {
          localStorage.setItem('activeRole', userInfo.roles[0])
        }
      }
      
      ElMessage.success('登录成功')
      return { success: true, data: response }
    } catch (error) {
      ElMessage.error('登录失败: ' + (error.response?.data?.detail || error.message))
      return { success: false, error: error.message }
    } finally {
      isLoading.value = false
    }
  }

  // 登出
  const logout = async () => {
    try {
      if (token.value) {
        await authApi.logout()
      }
    } catch (error) {
      console.error('登出请求失败:', error)
    } finally {
      // 清除本地状态
      token.value = ''
      refreshToken.value = ''
      user.value = null
      
      // 清除本地存储
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user_info')
      
      ElMessage.success('已登出')
    }
  }

  // 刷新令牌
  const refreshAccessToken = async () => {
    try {
      // ⭐ v6.0.0修复：检查 refreshToken 是否存在
      // 注意：如果使用 Cookie 认证，localStorage 中的 refreshToken 可能为空
      // 但后端会从 Cookie 读取，所以这里仍然可以尝试刷新
      if (!refreshToken.value) {
        // ⭐ v6.0.0修复：如果 localStorage 中没有 refreshToken，尝试从 Cookie 刷新
        // 注意：httpOnly Cookie 无法通过 JavaScript 读取，但后端会从 Cookie 读取
        // 所以即使 localStorage 中没有，也可以尝试刷新（后端会从 Cookie 读取）
        console.warn('[Auth] localStorage 中没有 refreshToken，尝试从 Cookie 刷新')
      }
      
      // ⭐ v6.0.0修复：响应拦截器已提取 data 字段，response 就是 RefreshTokenResponse 对象
      // 刷新 token 接口使用 JSONResponse 直接返回，没有包装在 {success: true, data: {...}} 中
      // 所以响应拦截器会直接返回对象（兼容旧格式逻辑）
      const response = await authApi.refreshToken(refreshToken.value || '')
      
      // ⭐ v6.0.0修复：处理响应格式
      // 响应拦截器可能返回：
      // 1. 直接对象：{access_token: "...", refresh_token: "...", ...}
      // 2. 包装在 data 中：{data: {access_token: "...", ...}}（如果使用了 success_response）
      const accessToken = response?.access_token || response?.data?.access_token
      
      if (!accessToken) {
        console.error('[Auth] 刷新 token 响应格式错误:', response)
        throw new Error('Invalid refresh token response: missing access_token')
      }
      
      token.value = accessToken
      // ⭐ v6.0.0修复：同步更新 localStorage（确保双重机制一致）
      localStorage.setItem('access_token', token.value)
      
      // ⭐ v6.0.0修复：如果响应中包含 refresh_token，也同步更新
      // 注意：后端现在会返回新的 refresh_token（Refresh Token 轮换）
      const newRefreshToken = response?.refresh_token || response?.data?.refresh_token
      if (newRefreshToken) {
        refreshToken.value = newRefreshToken
        localStorage.setItem('refresh_token', refreshToken.value)
      }
      
      return true
    } catch (error) {
      console.error('[Auth] 刷新令牌失败:', error)
      // ⭐ v6.0.0修复：提供更详细的错误信息
      if (error.message?.includes('No refresh token')) {
        console.warn('[Auth] refreshToken 为空，可能需要重新登录')
      }
      await logout()
      return false
    }
  }

  // 获取当前用户信息
  const fetchCurrentUser = async () => {
    try {
      const response = await authApi.getCurrentUser()
      user.value = response.data
      localStorage.setItem('user_info', JSON.stringify(user.value))
      return response.data
    } catch (error) {
      console.error('获取用户信息失败:', error)
      return null
    }
  }

  // 更新用户信息
  const updateUserInfo = async (userData) => {
    try {
      const response = await authApi.updateCurrentUser(userData)
      user.value = response.data
      localStorage.setItem('user_info', JSON.stringify(user.value))
      ElMessage.success('用户信息更新成功')
      return response.data
    } catch (error) {
      ElMessage.error('更新失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 修改密码
  const changePassword = async (passwordData) => {
    try {
      await authApi.changePassword(passwordData)
      ElMessage.success('密码修改成功')
      return true
    } catch (error) {
      ElMessage.error('密码修改失败: ' + (error.response?.data?.detail || error.message))
      throw error
    }
  }

  // 检查权限
  const hasPermission = (permission) => {
    if (!user.value || !user.value.roles) return false
    // 管理员拥有所有权限
    if (user.value.roles.includes('admin')) return true
    // 这里可以根据实际权限系统进行扩展
    return true // 简化版本，所有用户都有权限
  }

  // 检查角色
  const hasRole = (roles) => {
    if (!user.value || !user.value.roles) return false
    if (Array.isArray(roles)) {
      return roles.some(role => user.value.roles.includes(role))
    }
    return user.value.roles.includes(roles)
  }

  // 初始化认证状态
  const initAuth = () => {
    const savedToken = localStorage.getItem('access_token')
    const savedUser = localStorage.getItem('user_info')
    
    if (savedToken && savedUser) {
      token.value = savedToken
      try {
        user.value = JSON.parse(savedUser)
      } catch (error) {
        console.error('解析用户信息失败:', error)
        logout()
      }
    }
  }

  return {
    // 状态
    token,
    refreshToken,
    user,
    isLoggedIn,
    isLoading,
    
    // 方法
    login,
    logout,
    refreshAccessToken,
    fetchCurrentUser,
    updateUserInfo,
    changePassword,
    hasPermission,
    hasRole,
    initAuth
  }
})
