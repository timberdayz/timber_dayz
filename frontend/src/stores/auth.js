import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

import authApi from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { normalizeRoleCode, applyRolePermissions } from '@/config/rolePermissions'
import { hasAnyRole, hasPermissionForRoles } from '@/utils/authRoles'
import {
  clearPersistedAuthState,
  hasAnyPersistedAuthArtifact,
  readPersistedAuthState,
  writePersistedAuthState,
} from '@/utils/authSession'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(null)
  const isLoggedIn = computed(() => !!token.value && !!user.value)
  const isLoading = ref(false)

  const login = async (credentials) => {
    try {
      isLoading.value = true
      const response = await authApi.login(credentials)

      const accessToken = response.access_token || response.data?.access_token
      const refreshTokenValue = response.refresh_token || response.data?.refresh_token
      const userInfo = response.user_info || response.data?.user_info

      if (!accessToken || !refreshTokenValue || !userInfo) {
        throw new Error('登录响应格式错误：缺少用户会话信息')
      }

      token.value = accessToken
      refreshToken.value = refreshTokenValue
      user.value = userInfo

      writePersistedAuthState(localStorage, {
        access_token: accessToken,
        refresh_token: refreshTokenValue,
        user_info: userInfo,
      })

      const userStore = useUserStore()
      userStore.hydrateFromStorage()

      if (userInfo.roles) {
        const normalizedRoles = userInfo.roles.map(normalizeRoleCode).filter(Boolean)
        const preferredRole = normalizedRoles.includes('admin') ? 'admin' : (normalizedRoles[0] || 'operator')
        localStorage.setItem('activeRole', preferredRole)
        applyRolePermissions(userStore, preferredRole)
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

  const logout = async () => {
    const persistedState = readPersistedAuthState(localStorage)
    const shouldRevokeSession =
      hasAnyPersistedAuthArtifact(persistedState) || !!token.value || !!user.value

    try {
      if (shouldRevokeSession) {
        await authApi.logout()
      }
    } catch (_) {
      // ignore backend logout failure
    } finally {
      token.value = ''
      refreshToken.value = ''
      user.value = null
      clearPersistedAuthState(localStorage)
    }

    ElMessage.success('已登出')
  }

  const refreshAccessToken = async () => {
    try {
      if (!refreshToken.value) {
        console.warn('[Auth] localStorage 中没有 refreshToken，尝试从 Cookie 刷新')
      }

      const response = await authApi.refreshToken(refreshToken.value || '')
      const accessToken = response?.access_token || response?.data?.access_token

      if (!accessToken) {
        throw new Error('Invalid refresh token response: missing access_token')
      }

      token.value = accessToken
      localStorage.setItem('access_token', token.value)

      const newRefreshToken = response?.refresh_token || response?.data?.refresh_token
      if (newRefreshToken) {
        refreshToken.value = newRefreshToken
        localStorage.setItem('refresh_token', refreshToken.value)
      }

      return true
    } catch (error) {
      console.error('[Auth] 刷新令牌失败:', error)
      await logout()
      return false
    }
  }

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

  const hasPermission = (permission) => {
    return hasPermissionForRoles(user.value?.roles, permission)
  }

  const hasRole = (roles) => {
    return hasAnyRole(user.value?.roles, roles)
  }

  const initAuth = () => {
    const state = readPersistedAuthState(localStorage)
    if (!state.accessToken || !state.authUser) {
      return
    }

    token.value = state.accessToken
    refreshToken.value = state.refreshToken
    user.value = state.authUser

    const userStore = useUserStore()
    userStore.hydrateFromStorage()
  }

  return {
    token,
    refreshToken,
    user,
    isLoggedIn,
    isLoading,
    login,
    logout,
    refreshAccessToken,
    fetchCurrentUser,
    updateUserInfo,
    changePassword,
    hasPermission,
    hasRole,
    initAuth,
  }
})
