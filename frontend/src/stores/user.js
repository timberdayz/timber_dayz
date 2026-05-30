import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

import authApi from '@/api/auth'
import { hasAnyRole, hasPermissionForRoles } from '@/utils/authRoles'
import {
  clearPersistedAuthState,
  hasPersistedAuthSession,
  readPersistedAuthState,
  writePersistedAuthState,
} from '@/utils/authSession'

export const useUserStore = defineStore('user', () => {
  const token = ref('')
  const userInfo = ref(null)
  const permissions = ref([])
  const roles = ref([])
  const isLoggedIn = computed(() => !!userInfo.value)

  const logout = () => {
    token.value = ''
    userInfo.value = null
    permissions.value = []
    roles.value = []
    clearPersistedAuthState(localStorage)
  }

  const updateUserInfo = (newUserInfo) => {
    userInfo.value = { ...(userInfo.value || {}), ...newUserInfo }
    localStorage.setItem('userInfo', JSON.stringify(userInfo.value))

    if (newUserInfo && Array.isArray(newUserInfo.roles)) {
      roles.value = newUserInfo.roles
      localStorage.setItem('roles', JSON.stringify(roles.value))
    }
  }

  const hasPermission = (permission) => hasPermissionForRoles(roles.value, permission)

  const hasRole = (requiredRoles) => hasAnyRole(roles.value, requiredRoles)

  const hydrateFromStorage = () => {
    const state = readPersistedAuthState(localStorage)
    if (!state.userInfo) {
      return false
    }

    if (state.userInfo) {
      userInfo.value = state.userInfo
    }
    if (Array.isArray(state.roles)) {
      roles.value = state.roles
    }
    if (Array.isArray(state.permissions)) {
      permissions.value = state.permissions
    }
    return true
  }

  const initUserInfo = async () => {
    const state = readPersistedAuthState(localStorage)

    if (!hasPersistedAuthSession(state)) {
      logout()
      return
    }

    hydrateFromStorage()

    try {
      const response = await authApi.getCurrentUser()
      const payload = response.data || response
      if (payload && payload.id) {
        userInfo.value = {
          id: payload.id,
          username: payload.username,
          name: payload.full_name || payload.username,
          email: payload.email,
          avatar: '',
          roles: payload.roles || [],
        }
        roles.value = payload.roles || []
        writePersistedAuthState(localStorage, {
          user_info: {
            id: payload.id,
            username: payload.username,
            email: payload.email,
            full_name: payload.full_name,
            roles: payload.roles || [],
          },
        })
        return
      }
    } catch (error) {
      console.error('获取用户信息失败:', error)
      if (error.response && error.response.status === 401) {
        logout()
      }
    }
  }

  return {
    token,
    userInfo,
    permissions,
    roles,
    isLoggedIn,
    logout,
    updateUserInfo,
    hasPermission,
    hasRole,
    hydrateFromStorage,
    initUserInfo,
  }
})
