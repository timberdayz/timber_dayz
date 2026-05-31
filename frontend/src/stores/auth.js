import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

import authApi from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { normalizeRoleCode } from '@/config/rolePermissions'
import { hasAnyRole } from '@/utils/authRoles'
import {
  clearPersistedAuthState,
  resetAuthRecoveryState,
  hasAnyPersistedAuthArtifact,
  readPersistedAuthState,
  writePersistedAuthState,
} from '@/utils/authSession'

export const useAuthStore = defineStore('auth', () => {
  const token = ref('')
  const refreshToken = ref('')
  const user = ref(null)
  const isLoggedIn = computed(() => !!user.value)
  const isLoading = ref(false)

  const clearLocalSession = () => {
    token.value = ''
    refreshToken.value = ''
    user.value = null
    clearPersistedAuthState(localStorage)
    resetAuthRecoveryState(localStorage)

    try {
      const userStore = useUserStore()
      userStore.logout()
    } catch (error) {
      console.warn('[Auth] 清理 userStore 会话失败:', error)
    }
  }

  const login = async (credentials) => {
    try {
      isLoading.value = true
      const response = await authApi.login(credentials)
      const userInfo = response.user_info || response.data?.user_info

      if (!userInfo) {
        throw new Error('登录响应格式错误：缺少用户会话信息')
      }

      user.value = userInfo
      writePersistedAuthState(localStorage, { user_info: userInfo })
      resetAuthRecoveryState(localStorage)

      const userStore = useUserStore()
      userStore.hydrateFromStorage()

      if (userInfo.roles) {
        const normalizedRoles = userInfo.roles.map(normalizeRoleCode).filter(Boolean)
        const preferredRole = normalizedRoles.includes('admin') ? 'admin' : (normalizedRoles[0] || '')
        if (preferredRole) {
          localStorage.setItem('activeRole', preferredRole)
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

  const logout = async () => {
    const persistedState = readPersistedAuthState(localStorage)
    const shouldRevokeSession = hasAnyPersistedAuthArtifact(persistedState) || !!user.value

    try {
      if (shouldRevokeSession) {
        await authApi.logout()
      }
    } catch (_) {
      // ignore backend logout failure
    } finally {
      clearLocalSession()
    }

    ElMessage.success('已登出')
  }

  const refreshAccessToken = async () => {
    try {
      await authApi.refreshToken()
      resetAuthRecoveryState(localStorage)
      return true
    } catch (error) {
      console.error('[Auth] 刷新认证失败:', error)
      clearLocalSession()
      return false
    }
  }

  const fetchCurrentUser = async () => {
    try {
      const response = await authApi.getCurrentUser()
      user.value = response.data || response
      writePersistedAuthState(localStorage, { user_info: user.value })
      return user.value
    } catch (error) {
      console.error('获取用户信息失败:', error)
      return null
    }
  }

  const updateUserInfo = async (userData) => {
    try {
      const response = await authApi.updateCurrentUser(userData)
      user.value = response.data
      writePersistedAuthState(localStorage, { user_info: user.value })
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
    if (!permission) return true
    if (hasAnyRole(user.value?.roles, ['admin'])) return true
    return Boolean(user.value?.permissions?.includes(permission))
  }

  const hasRole = (roles) => {
    return hasAnyRole(user.value?.roles, roles)
  }

  const initAuth = () => {
    const state = readPersistedAuthState(localStorage)
    if (!state.authUser) {
      return
    }

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
    clearLocalSession,
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
