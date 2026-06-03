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
          <el-dropdown-item disabled class="dropdown-label">
            <span style="font-weight: bold; color: #909399;">当前角色</span>
          </el-dropdown-item>

          <el-dropdown-item
            v-for="role in availableRoles"
            :key="role.code"
            :command="`role:${role.code}`"
            :class="{ 'active-role': currentActiveRole === role.code }"
          >
            <el-icon><component :is="role.icon" /></el-icon>
            <span>{{ role.name }}</span>
            <el-icon v-if="currentActiveRole === role.code" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>

          <el-dropdown-item v-if="availableRoles.length === 0" disabled>
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
import { User, ArrowDown, Setting, SwitchButton, Check } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
import { ROLE_CONFIG, normalizeRoleCode } from '@/config/rolePermissions'
import {
  hasAuthRecoveryFailed,
  hasPersistedAuthSession,
  readPersistedAuthState,
} from '@/utils/authSession'

const router = useRouter()
const userStore = useUserStore()
const authStore = useAuthStore()
const currentActiveRole = ref(localStorage.getItem('activeRole') || '')

if (currentActiveRole.value) {
  const normalized = normalizeRoleCode(currentActiveRole.value)
  if (normalized !== currentActiveRole.value) {
    currentActiveRole.value = normalized
    localStorage.setItem('activeRole', normalized)
  }
}

const currentUser = computed(() => {
  if (authStore.user) {
    return {
      id: authStore.user.id,
      username: authStore.user.username,
      name: authStore.user.full_name || authStore.user.username,
      email: authStore.user.email,
      avatar: '',
      roles: authStore.user.roles || [],
    }
  }
  if (userStore.userInfo) {
    return {
      id: userStore.userInfo.id || 1,
      username: userStore.userInfo.username || 'user',
      name: userStore.userInfo.name || userStore.userInfo.username || '用户',
      email: userStore.userInfo.email || '',
      avatar: userStore.userInfo.avatar || '',
      roles: userStore.userInfo.roles || [],
    }
  }
  return {
    id: 1,
    username: 'user',
    name: '用户',
    email: '',
    avatar: '',
    roles: [],
  }
})

const userRoles = computed(() => {
  if (authStore.user?.roles) {
    return authStore.user.roles.map(normalizeRoleCode).filter(Boolean)
  }
  return (userStore.roles || []).map(normalizeRoleCode).filter(Boolean)
})

const displayName = computed(() => {
  if (currentActiveRole.value) {
    const roleConfig = ROLE_CONFIG[currentActiveRole.value]
    if (roleConfig) return roleConfig.name
  }
  return currentUser.value.name || currentUser.value.username || '用户'
})

const availableRoles = computed(() =>
  (userRoles.value || [])
    .map((roleCode) => {
      const config = ROLE_CONFIG[roleCode]
      if (!config) return null
      return {
        code: roleCode,
        name: config.name,
        icon: config.icon,
      }
    })
    .filter(Boolean)
)

const hasAdminRole = computed(() => userRoles.value.includes('admin'))

const ensureActiveRole = (roles = []) => {
  if (!roles.length) return
  if (currentActiveRole.value && roles.includes(currentActiveRole.value)) return
  const preferredRole = roles.includes('admin') ? 'admin' : roles[0]
  currentActiveRole.value = preferredRole
  localStorage.setItem('activeRole', preferredRole)
  userStore.updateUserInfo({ activeRole: preferredRole })
}

onMounted(() => {
  if (hasAuthRecoveryFailed(localStorage)) {
    return
  }

  const persistedState = readPersistedAuthState(localStorage)
  if (!hasPersistedAuthSession(persistedState)) {
    return
  }

  if (userRoles.value.length > 0) {
    ensureActiveRole(userRoles.value)
  }
})

watch(
  () => authStore.user,
  (newUser) => {
    if (!newUser?.roles) return
    const normalizedRoles = newUser.roles.map(normalizeRoleCode).filter(Boolean)
    userStore.updateUserInfo({
      id: newUser.id,
      username: newUser.username,
      name: newUser.full_name || newUser.username,
      email: newUser.email,
      roles: normalizedRoles,
      permissions: newUser.permissions || [],
      is_admin: newUser.is_admin || false,
    })
    userStore.roles = normalizedRoles
    if (Array.isArray(newUser.permissions)) {
      userStore.permissions = newUser.permissions
      localStorage.setItem('permissions', JSON.stringify(newUser.permissions))
    }
    ensureActiveRole(normalizedRoles)
  },
  { immediate: true }
)

const switchRole = (roleCode) => {
  if (!userRoles.value.includes(roleCode)) {
    ElMessage.warning('您没有该角色')
    return
  }
  currentActiveRole.value = roleCode
  localStorage.setItem('activeRole', roleCode)
  userStore.updateUserInfo({ activeRole: roleCode })
  const roleName = ROLE_CONFIG[roleCode]?.name || roleCode
  ElMessage.success(`已切换显示角色: ${roleName}`)
}

const handleCommand = (command) => {
  if (command.startsWith('role:')) {
    switchRole(command.split(':')[1])
    return
  }

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
    type: 'warning',
  })
    .then(async () => {
      try {
        await authStore.logout()
      } catch (_) {
        // Ignore logout API failures and continue local cleanup.
      }
      userStore.logout()
      localStorage.removeItem('activeRole')
      router.push('/login')
    })
    .catch(() => {})
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
