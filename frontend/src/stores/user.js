import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

import authApi from '@/api/auth'
import { clearPersistedAuthState, readPersistedAuthState } from '@/utils/authSession'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('access_token') || localStorage.getItem('token') || '')
  const userInfo = ref(null)
  const permissions = ref([])
  const roles = ref([])
  const isLoggedIn = computed(() => !!token.value)

  const login = async (credentials) => {
    try {
      const mockResponse = {
        token: 'mock-token-' + Date.now(),
        user: {
          id: 1,
          username: credentials.username,
          name: '管理员',
          email: 'admin@example.com',
          avatar: '',
          role: 'admin',
        },
        permissions: [],
        roles: ['admin'],
      }

      token.value = mockResponse.token
      userInfo.value = mockResponse.user
      permissions.value = mockResponse.permissions
      roles.value = mockResponse.roles

      localStorage.setItem('token', token.value)
      localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
      localStorage.setItem('roles', JSON.stringify(roles.value))

      return { success: true, data: mockResponse }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

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

  const hasPermission = (permission) => permissions.value.includes(permission)

  const hasRole = (requiredRoles) => requiredRoles.some((role) => roles.value.includes(role))

  const hydrateFromStorage = () => {
    const state = readPersistedAuthState(localStorage)
    if (!state.accessToken) {
      return false
    }

    token.value = state.accessToken
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

    if (state.accessToken) {
      hydrateFromStorage()
      try {
        const response = await authApi.getCurrentUser()
        if (response && response.id) {
          userInfo.value = {
            id: response.id,
            username: response.username,
            name: response.full_name || response.username,
            email: response.email,
            avatar: '',
            roles: response.roles || [],
          }
          roles.value = response.roles || []
          localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
          localStorage.setItem('roles', JSON.stringify(roles.value))
          return
        }
      } catch (error) {
        console.error('获取用户信息失败:', error)
        if (error.response && error.response.status === 401) {
          logout()
          return
        }
      }
    }

    if (state.userInfo) {
      hydrateFromStorage()
      return
    }

    userInfo.value = {
      id: 1,
      username: 'admin',
      name: '管理员',
      email: 'admin@xihong-erp.com',
      avatar: '',
      role: 'admin',
    }
    roles.value = ['admin']
  }

  return {
    token,
    userInfo,
    permissions,
    roles,
    isLoggedIn,
    login,
    logout,
    updateUserInfo,
    hasPermission,
    hasRole,
    hydrateFromStorage,
    initUserInfo,
  }
})
