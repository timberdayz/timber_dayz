/**
 * 用户状态管理
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import authApi from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  // 状态
  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(null)
  const permissions = ref([])
  const roles = ref(['admin']) // 默认管理员角色
  const isLoggedIn = computed(() => !!token.value)

  // 登录
  const login = async (credentials) => {
    try{
      // 这里应该调用实际的登录API
      // const response = await api.post('/auth/login', credentials)
      
      // 模拟登录成功
      const mockResponse = {
        token: 'mock-token-' + Date.now(),
        user: {
          id: 1,
          username: credentials.username,
          name: '管理员',
          email: 'admin@example.com',
          avatar: '',
          role: 'admin'
        },
        permissions: [
          // 工作台
          'business-overview',
          
          // 数据采集与管理（8项，v4.6.0新增数据同步，v4.6.1删除字段映射审核，v4.7.0新增组件录制，v4.9.4新增版本管理）
          'collection-config', 'collection-tasks', 'collection-history',
          'component-recorder',  // ⭐ Phase 8.1新增：组件录制工具权限
          'component-versions',  // ⭐ Phase 9.4新增：组件版本管理权限
          'data-sync',  // ⭐ v4.6.0新增：数据同步权限
          'data-quarantine',  // ⚠️ v4.12.0移除：'data-browser'已移除，使用Metabase替代
          
          // 产品与库存（3项）
          'product-management', 'inventory-management', 'inventory-dashboard-v3',
          
          // 采购管理（4项）
          'purchase-orders', 'grn-management', 'vendor-management', 'invoice-management',
          
          // 销售与分析（6项）
          'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
          'campaign:read', 'target:read',  // A类数据配置权限
          
          // 财务管理（5项）
          'financial-management', 'expense-management', 'finance-reports', 
          'fx-management', 'fiscal-periods',
          
          // 店铺运营（4项）
          'store-management', 'store-analytics', 'account-management', 'account-alignment',
          
          // 报表中心（5项）
          'sales-reports', 'inventory-reports', 'finance-reports-detail', 
          'vendor-reports', 'custom-reports',
          
          // 人力资源（4项）
          'human-resources', 'employee-management', 'attendance-management',
          'performance:read',  // 绩效管理权限
          
          // 审批中心（4项）
          'my-tasks', 'my-requests', 'approval-history', 'workflow-config',
          
          // 消息中心（3项）
          'system-notifications', 'alerts', 'message-settings',
          
          // 系统管理（6项）
          'user-management', 'role-management', 'permission-management',
          'system-settings', 'system-logs', 'personal-settings',
          
          // 帮助中心（3项）
          'user-guide', 'video-tutorials', 'faq',
          
          // 开发工具（4项 - 开发环境）
          'debug', 'test', 'ultra-simple', 'api-docs',
          
          // 兼容旧权限标识和分组级别权限
          'data-governance', 'sales-dashboard', 'data-collection', 'procurement',
          'report-center', 'approval-center', 'message-center', 'help-center',
          'notifications', 'product-category', 'inventory-alert'
        ],
        roles: ['admin']
      }
      
      token.value = mockResponse.token
      userInfo.value = mockResponse.user
      permissions.value = mockResponse.permissions
      roles.value = mockResponse.roles
      
      // 保存到本地存储
      localStorage.setItem('token', token.value)
      localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
      localStorage.setItem('roles', JSON.stringify(roles.value))
      
      return { success: true, data: mockResponse }
    } catch (error) {
      return { success: false, error: error.message }
    }
  }

  // 登出
  const logout = () => {
    token.value = ''
    userInfo.value = null
    permissions.value = []
    roles.value = []
    
    // 清除本地存储
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
    localStorage.removeItem('roles')
  }

  // 更新用户信息
  const updateUserInfo = (newUserInfo) => {
    userInfo.value = { ...userInfo.value, ...newUserInfo }
    localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
  }

  // 检查权限
  const hasPermission = (permission) => {
    return permissions.value.includes(permission)
  }

  // 检查角色权限
  const hasRole = (requiredRoles) => {
    return requiredRoles.some(role => roles.value.includes(role))
  }

  // 初始化用户信息（从后端获取）
  const initUserInfo = async () => {
    const savedUserInfo = localStorage.getItem('userInfo')
    const savedRoles = localStorage.getItem('roles')
    const savedToken = localStorage.getItem('token')
    
    // 如果有token，尝试从后端获取最新用户信息
    if (savedToken) {
      try {
        const response = await authApi.getCurrentUser()
        if (response && response.id) {
          userInfo.value = {
            id: response.id,
            username: response.username,
            name: response.full_name || response.username,
            email: response.email,
            avatar: '',
            roles: response.roles || []
          }
          roles.value = response.roles || []
          
          // 保存到本地存储
          localStorage.setItem('userInfo', JSON.stringify(userInfo.value))
          localStorage.setItem('roles', JSON.stringify(roles.value))
          
          // 如果有激活的角色，应用其权限（由SimpleAccountSwitcher组件处理）
          const activeRole = localStorage.getItem('activeRole')
          if (activeRole && roles.value.includes(activeRole)) {
            // 权限由SimpleAccountSwitcher组件应用
            return
          }
          
          // 如果没有激活的角色，使用第一个角色
          if (roles.value.length > 0) {
            localStorage.setItem('activeRole', roles.value[0])
          }
          
          return
        }
      } catch (error) {
        console.error('获取用户信息失败:', error)
        // 如果获取失败，清除token，要求重新登录
        if (error.response && error.response.status === 401) {
          logout()
          return
        }
      }
    }
    
    // 如果没有token或获取失败，使用本地存储的信息
    if (savedUserInfo) {
      try {
        userInfo.value = JSON.parse(savedUserInfo)
        
        if (savedRoles) {
          roles.value = JSON.parse(savedRoles)
        }
      } catch (error) {
        console.error('解析用户信息失败:', error)
        logout()
      }
    } else {
      // 如果没有保存的用户信息，设置默认值
      userInfo.value = {
        id: 1,
        username: 'admin',
        name: '管理员',
        email: 'admin@xihong-erp.com',
        avatar: '',
        role: 'admin'
      }
      roles.value = ['admin']
    }
  }

  return {
    // 状态
    token,
    userInfo,
    permissions,
    roles,
    isLoggedIn,
    
    // 方法
    login,
    logout,
    updateUserInfo,
    hasPermission,
    hasRole,
    initUserInfo
  }
})
