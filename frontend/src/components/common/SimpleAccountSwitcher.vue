<template>
  <div class="simple-account-switcher">
    <el-dropdown @command="handleCommand" trigger="click">
      <div class="account-trigger">
        <el-avatar :size="32" :src="currentUser?.avatar || ''">
          <el-icon><User /></el-icon>
        </el-avatar>
        <span class="account-name">{{ displayName || currentUser?.username || currentUser?.name || '用户' }}</span>
        <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <!-- 角色切换 -->
          <el-dropdown-item disabled class="dropdown-label">
            <span style="font-weight: bold; color: #909399;">切换角色</span>
          </el-dropdown-item>
          
          <!-- 动态显示用户拥有的角色 -->
          <el-dropdown-item 
            v-for="role in (availableRoles || [])"
            :key="role.code"
            :command="`role:${role.code}`"
            :class="{ 'active-role': currentActiveRole === role.code }"
          >
            <el-icon><component :is="role.icon" /></el-icon>
            <span>{{ role.name }}</span>
            <el-icon v-if="currentActiveRole === role.code" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>
          
          <el-dropdown-item v-if="!availableRoles || availableRoles.length === 0" disabled>
            <span style="color: #909399;">暂无可用角色</span>
          </el-dropdown-item>
          
          <el-dropdown-item divided disabled class="dropdown-label">
            <span style="font-size: 12px; color: #909399;">功能菜单</span>
          </el-dropdown-item>
          
          <el-dropdown-item command="personal-settings">
            <el-icon><User /></el-icon>
            <span>个人设置</span>
          </el-dropdown-item>
          
          <el-dropdown-item command="system-settings" v-if="hasAdminRole">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </el-dropdown-item>
          
          <el-dropdown-item divided command="logout">
            <el-icon><SwitchButton /></el-icon>
            <span>退出登录</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, ArrowDown, Setting, SwitchButton, UserFilled, Briefcase, Money, Check } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
import authApi from '@/api/auth'

const router = useRouter()
const userStore = useUserStore()
const authStore = useAuthStore()

// 当前激活的角色（从localStorage读取，默认为用户的第一个角色）
const currentActiveRole = ref(localStorage.getItem('activeRole') || '')

// 角色配置（根据2026-01-08讨论的权限矩阵）
// 必须在 normalizeRoleCode 之前定义，避免初始化顺序错误
const ROLE_CONFIG = {
  admin: {
    name: '管理员',
    icon: 'UserFilled',
    // ✅ 管理员拥有所有权限
    permissions: [
      // 工作台
      'business-overview',
      
      // 数据采集与管理（仅管理员）
      'collection-config', 'collection-tasks', 'collection-history',
      'component-recorder', 'component-versions',
      'data-sync', 'data-quarantine', 'field-mapping',
      
      // 产品与库存
      'product-management', 'inventory-management', 'inventory-dashboard-v3',
      
      // 采购管理
      'purchase-orders', 'grn-management', 'vendor-management', 'invoice-management',
      
      // 销售与分析
      'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
      'target:read', 'config:sales-targets',  // ✅ 目标管理（仅管理员）
      
      // 财务管理
      'financial-management', 'expense-management', 'finance-reports', 
      'fx-management', 'fiscal-periods',
      
      // 店铺运营
      'store-management', 'store-analytics', 'account-management', 'account-alignment',
      
      // 报表中心
      'sales-reports', 'inventory-reports', 'finance-reports-detail', 
      'vendor-reports', 'custom-reports',
      
      // 人力资源
      'human-resources', 'employee-management', 'attendance-management', 'performance:read',
      
      // 审批中心
      'my-tasks', 'my-requests', 'approval-history', 'workflow-config',
      
      // 消息中心
      'system-notifications', 'alerts', 'message-settings',
      
      // 系统管理（仅管理员）
      'user-management', 'role-management', 'permission-management',
      'system-settings', 'system-logs', 'data-backup', 'system-maintenance', 'notification-config',
      
      // 个人设置
      'personal-settings',
      
      // 帮助中心
      'user-guide', 'video-tutorials', 'faq',
      
      // 兼容旧权限标识
      'data-governance', 'sales-dashboard', 'data-collection', 'procurement',
      'report-center', 'approval-center', 'message-center', 'help-center',
      'notifications', 'product-category', 'inventory-alert'
    ]
  },
  manager: {
    name: '主管',
    icon: 'Briefcase',
    // ✅ 主管：业务管理、审批、配置权限（不包括系统管理、数据采集、目标管理）
    permissions: [
      // 工作台
      'business-overview',
      
      // 销售与分析
      'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
      'sales-campaign-management',
      
      // 库存管理
      'inventory-dashboard-v3',
      
      // 店铺管理
      'store-management', 'store-analytics',
      
      // 账号管理（主管可访问）
      'account-management', 'account-alignment',
      
      // 采购管理
      'purchase-orders', 'grn-management', 'vendor-management',
      
      // 财务管理
      'financial-management', 'expense-management', 'finance-reports',
      
      // 报表中心
      'sales-reports', 'inventory-reports', 'vendor-reports',
      
      // 人力资源
      'human-resources', 'employee-management', 'attendance-management', 'performance:read',
      
      // 审批中心
      'my-tasks', 'my-requests', 'approval-history',
      
      // 消息中心
      'system-notifications', 'alerts', 'message-settings',
      
      // 个人设置
      'personal-settings',
      
      // 兼容旧权限标识
      'sales-dashboard', 'procurement', 'report-center', 'approval-center',
      'message-center', 'notifications'
    ]
  },
  operator: {
    name: '操作员',
    icon: 'User',
    // ✅ 操作员：基础业务操作权限（不包括账号管理、目标管理、财务管理、数据同步）
    permissions: [
      // 工作台
      'business-overview',
      
      // 销售与分析
      'sales-dashboard-v3', 'customer-management', 'order-management',
      'sales-campaign-management',
      
      // 库存管理
      'inventory-dashboard-v3',
      
      // 店铺管理
      'store-management',
      
      // 人力资源（查看）
      'human-resources', 'performance:read',
      
      // 消息中心
      'system-notifications', 'alerts', 'message-settings',
      
      // 个人设置
      'personal-settings',
      
      // 兼容旧权限标识
      'sales-dashboard', 'message-center', 'notifications'
    ]
  },
  finance: {
    name: '财务',
    icon: 'Money',
    // ✅ 财务：财务和销售数据查看权限（不包括库存管理、店铺管理、账号管理）
    permissions: [
      // 销售数据查看
      'sales-analysis', 'sales-dashboard-v3', 'order-management',
      
      // 财务管理
      'financial-management', 'expense-management', 'finance-reports', 'finance-reports-detail',
      'invoice-management', 'fiscal-periods',
      
      // 消息中心
      'system-notifications', 'alerts', 'message-settings',
      
      // 个人设置
      'personal-settings',
      
      // 兼容旧权限标识
      'sales-dashboard', 'report-center', 'message-center', 'notifications'
    ]
  }
}

// 兼容：角色可能来自后端 role_name（如中文）或 role_code（如 admin/operator）
const normalizeRoleCode = (roleCode) => {
  if (!roleCode) return ''
  const v = String(roleCode).trim()
  if (ROLE_CONFIG[v]) return v
  const map = {
    '管理员': 'admin',
    '主管': 'manager',
    '经理': 'manager',
    '操作员': 'operator',
    '运营': 'operator',
    '财务': 'finance'
  }
  if (map[v]) return map[v]
  // 常见变体处理
  const lower = v.toLowerCase()
  if (ROLE_CONFIG[lower]) return lower
  return v
}

// 统一 currentActiveRole（避免保存了不可识别的角色导致菜单权限为空）
if (currentActiveRole.value) {
  const normalized = normalizeRoleCode(currentActiveRole.value)
  if (normalized !== currentActiveRole.value) {
    currentActiveRole.value = normalized
    localStorage.setItem('activeRole', normalized)
  }
}

// 当前用户信息（优先使用authStore，降级到userStore）
const currentUser = computed(() => {
  try {
    if (authStore.user) {
      return {
        id: authStore.user.id,
        username: authStore.user.username,
        name: authStore.user.full_name || authStore.user.username,
        email: authStore.user.email,
        avatar: '',
        roles: authStore.user.roles || []
      }
    }
    if (userStore.userInfo) {
      return {
        id: userStore.userInfo.id || 1,
        username: userStore.userInfo.username || 'user',
        name: userStore.userInfo.name || userStore.userInfo.username || '用户',
        email: userStore.userInfo.email || '',
        avatar: userStore.userInfo.avatar || '',
        roles: userStore.userInfo.roles || []
      }
    }
    // 默认用户信息（确保组件始终显示）
    return {
      id: 1,
      username: 'user',
      name: '用户',
      email: '',
      avatar: '',
      roles: []
    }
  } catch (error) {
    console.error('获取用户信息失败:', error)
    // 返回默认值，确保组件可以渲染
    return {
      id: 1,
      username: 'user',
      name: '用户',
      email: '',
      avatar: '',
      roles: []
    }
  }
})

// 显示名称（优先显示当前激活角色的名称）
const displayName = computed(() => {
  if (currentActiveRole.value) {
    const roleConfig = ROLE_CONFIG[currentActiveRole.value]
    if (roleConfig) {
      return roleConfig.name
    }
  }
  return currentUser.value.name || currentUser.value.username || '用户'
})

// 用户拥有的角色（优先使用authStore，降级到userStore）
const userRoles = computed(() => {
  if (authStore.user && authStore.user.roles) {
    return authStore.user.roles.map(normalizeRoleCode).filter(Boolean)
  }
  return (userStore.roles || []).map(normalizeRoleCode).filter(Boolean)
})

// 可用的角色列表（只显示用户拥有的角色）
const availableRoles = computed(() => {
  const roles = userRoles.value || []
  return roles
    .map(roleCode => {
      const config = ROLE_CONFIG[roleCode]
      if (!config) return null
      return {
        code: roleCode,
        name: config.name,
        icon: config.icon
      }
    })
    .filter(Boolean)
})

// 检查是否有管理员角色
const hasAdminRole = computed(() => userRoles.value.includes('admin'))

// 初始化：从后端获取用户信息
onMounted(async () => {
  await loadUserInfo()
})

// 监听authStore.user变化，自动同步到userStore
watch(() => authStore.user, async (newUser) => {
  if (newUser && newUser.roles) {
    // 同步到userStore
    userStore.updateUserInfo({
      id: newUser.id,
      username: newUser.username,
      name: newUser.full_name || newUser.username,
      email: newUser.email,
      roles: newUser.roles
    })
    userStore.roles = newUser.roles.map(normalizeRoleCode).filter(Boolean)
    
    // 如果当前激活角色未设置，使用第一个角色
    if (!currentActiveRole.value && newUser.roles.length > 0) {
      const normalizedRoles = newUser.roles.map(normalizeRoleCode).filter(Boolean)
      const preferredRole = normalizedRoles.includes('admin') ? 'admin' : normalizedRoles[0]
      currentActiveRole.value = preferredRole
      localStorage.setItem('activeRole', currentActiveRole.value)
      applyRolePermissions(currentActiveRole.value)
    }
  }
}, { immediate: true })

// 加载用户信息
const loadUserInfo = async () => {
  try {
    // 优先使用authStore的用户信息
    if (authStore.user && authStore.user.roles) {
      const normalizedRoles = authStore.user.roles.map(normalizeRoleCode).filter(Boolean)
      userStore.roles = normalizedRoles
      if (!currentActiveRole.value && normalizedRoles.length > 0) {
        const preferredRole = normalizedRoles.includes('admin') ? 'admin' : normalizedRoles[0]
        currentActiveRole.value = preferredRole
        localStorage.setItem('activeRole', currentActiveRole.value)
        applyRolePermissions(currentActiveRole.value)
      } else if (currentActiveRole.value) {
        applyRolePermissions(currentActiveRole.value)
      }
      return
    }
    
    // 如果authStore没有用户信息，尝试从后端获取
    if (authStore.token) {
      const response = await authApi.getCurrentUser()
      if (response && response.roles) {
        // 更新authStore
        const normalizedRoles = response.roles.map(normalizeRoleCode).filter(Boolean)
        authStore.user = {
          id: response.id,
          username: response.username,
          full_name: response.full_name || response.username,
          email: response.email,
          roles: normalizedRoles
        }
        
        // 同步到userStore
        userStore.updateUserInfo({
          id: response.id,
          username: response.username,
          name: response.full_name || response.username,
          email: response.email,
          roles: response.roles
        })
        userStore.roles = normalizedRoles
        
        // 如果当前激活角色未设置，使用第一个角色
        if (!currentActiveRole.value && normalizedRoles.length > 0) {
          const preferredRole = normalizedRoles.includes('admin') ? 'admin' : normalizedRoles[0]
          currentActiveRole.value = preferredRole
          localStorage.setItem('activeRole', currentActiveRole.value)
          applyRolePermissions(currentActiveRole.value)
        }
      }
    } else if (userStore.roles && userStore.roles.length > 0) {
      // 如果userStore有角色信息，使用它
      if (!currentActiveRole.value) {
        const preferredRole = userStore.roles.includes('admin') ? 'admin' : userStore.roles[0]
        currentActiveRole.value = preferredRole
        localStorage.setItem('activeRole', currentActiveRole.value)
        applyRolePermissions(currentActiveRole.value)
      } else if (currentActiveRole.value) {
        applyRolePermissions(currentActiveRole.value)
      }
    }
  } catch (error) {
    console.error('获取用户信息失败:', error)
    // 如果获取失败，尝试使用本地存储的角色
    if (currentActiveRole.value) {
      applyRolePermissions(currentActiveRole.value)
    }
  }
}

// 应用角色权限
const applyRolePermissions = (roleCode) => {
  const roleConfig = ROLE_CONFIG[roleCode]
  if (!roleConfig) {
    console.warn(`角色配置不存在: ${roleCode}`)
    return
  }
  
  // 更新权限
  userStore.permissions = roleConfig.permissions
  
  // 保存到localStorage
  localStorage.setItem('permissions', JSON.stringify(roleConfig.permissions))
  
  // 更新用户显示名称（不修改数据库，只修改前端显示）
  userStore.updateUserInfo({
    activeRole: roleCode
  })
}

// 切换角色
const switchRole = (roleCode) => {
  const roleConfig = ROLE_CONFIG[roleCode]
  if (!roleConfig) {
    ElMessage.warning('角色配置不存在')
    return
  }
  
  // 检查用户是否拥有该角色
  if (!userRoles.value.includes(roleCode)) {
    ElMessage.warning('您没有该角色的权限')
    return
  }
  
  // 更新当前激活角色
  currentActiveRole.value = roleCode
  localStorage.setItem('activeRole', roleCode)
  
  // 应用权限
  applyRolePermissions(roleCode)
  
  ElMessage.success(`已切换到 ${roleConfig.name} 角色`)
  
  // 刷新页面（触发菜单重新渲染和路由守卫）
  router.go(0)
}

// 处理命令
const handleCommand = (command) => {
  // 处理角色切换
  if (command.startsWith('role:')) {
    const roleCode = command.split(':')[1]
    switchRole(roleCode)
    return
  }
  
  // 处理其他命令
  switch (command) {
    case 'personal-settings':
      router.push('/personal-settings')
      break
    case 'system-settings':
      router.push('/system-config')
      break
    case 'logout':
      logout()
      break
  }
}

const logout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '确认退出', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    // 同时清除两个store
    await authStore.logout()
    userStore.logout()
    localStorage.removeItem('activeRole')
    ElMessage.success('已退出登录')
    router.push('/login')
  }).catch(() => {
    // 用户取消
  })
}
</script>

<style scoped>
.simple-account-switcher {
  display: flex;
  align-items: center;
}

.account-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.1);
}

.account-trigger:hover {
  background: rgba(255, 255, 255, 0.2);
}

.account-name {
  color: white;
  font-size: 14px;
  font-weight: 500;
}

.dropdown-icon {
  color: white;
  font-size: 12px;
  transition: transform 0.3s ease;
}

/* 角色切换样式 */
.dropdown-label {
  padding: 8px 16px;
  font-size: 12px;
  color: #909399;
  cursor: default;
}

.active-role {
  background-color: #ecf5ff;
  color: #409eff;
}

:deep(.el-dropdown-menu__item) {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.el-dropdown-menu__item .el-icon) {
  font-size: 16px;
}
</style>
