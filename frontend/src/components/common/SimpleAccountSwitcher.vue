<template>
  <div class="simple-account-switcher">
    <el-dropdown @command="handleCommand" trigger="click">
      <div class="account-trigger">
        <el-avatar :size="32" :src="currentUser.avatar">
          <el-icon><User /></el-icon>
        </el-avatar>
        <span class="account-name">{{ currentUser.name }}</span>
        <el-icon class="dropdown-icon"><ArrowDown /></el-icon>
      </div>
      <template #dropdown>
        <el-dropdown-menu>
          <!-- 角色切换 -->
          <el-dropdown-item disabled class="dropdown-label">
            <span style="font-weight: bold; color: #909399;">切换角色（测试）</span>
          </el-dropdown-item>
          
          <el-dropdown-item 
            command="role:admin"
            :class="{ 'active-role': currentUser.role === 'admin' }"
          >
            <el-icon><UserFilled /></el-icon>
            <span>👑 管理员</span>
            <el-icon v-if="currentUser.role === 'admin'" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>
          
          <el-dropdown-item 
            command="role:manager"
            :class="{ 'active-role': currentUser.role === 'manager' }"
          >
            <el-icon><Briefcase /></el-icon>
            <span>👔 主管</span>
            <el-icon v-if="currentUser.role === 'manager'" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>
          
          <el-dropdown-item 
            command="role:operator"
            :class="{ 'active-role': currentUser.role === 'operator' }"
          >
            <el-icon><User /></el-icon>
            <span>👨‍💼 操作员</span>
            <el-icon v-if="currentUser.role === 'operator'" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>
          
          <el-dropdown-item 
            command="role:finance"
            :class="{ 'active-role': currentUser.role === 'finance' }"
          >
            <el-icon><Money /></el-icon>
            <span>📊 财务</span>
            <el-icon v-if="currentUser.role === 'finance'" style="margin-left: auto; color: #67C23A;"><Check /></el-icon>
          </el-dropdown-item>
          
          <el-dropdown-item divided disabled class="dropdown-label">
            <span style="font-size: 12px; color: #909399;">功能菜单</span>
          </el-dropdown-item>
          
          <el-dropdown-item command="personal-settings">
            <el-icon><User /></el-icon>
            <span>个人设置</span>
          </el-dropdown-item>
          
          <el-dropdown-item command="system-settings">
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
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, ArrowDown, Setting, SwitchButton, UserFilled, Briefcase, Money, Check } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

// 角色配置
const ROLES = {
  admin: { name: '管理员', icon: '👑', permissions: ['field-mapping', 'data-governance', 'data-quarantine'] },  // ⚠️ v4.12.0移除：'data-browser'已移除，使用Metabase替代
  manager: { name: '主管', icon: '👔', permissions: [] },
  operator: { name: '操作员', icon: '👨‍💼', permissions: [] },
  finance: { name: '财务', icon: '📊', permissions: [] }
}

// 当前用户信息
const currentUser = computed(() => userStore.userInfo || {
  id: 1,
  name: '管理员',
  role: 'admin',
  avatar: '',
  email: 'admin@xihong-erp.com'
})

// 切换角色
const switchRole = (role) => {
  const roleConfig = ROLES[role]
  if (!roleConfig) return
  
  // 更新用户信息
  userStore.updateUserInfo({
    role: role,
    name: roleConfig.name
  })
  
  // 更新角色数组
  userStore.roles = [role]
  
  // 更新权限
  if (role === 'admin') {
    // ✅ 管理员拥有所有53个菜单项的权限（v4.6.1 - 2025-11-04）
    userStore.permissions = [
      // 工作台
      'business-overview',
      
      // 数据采集与管理（6项）
      'collection-config', 'collection-tasks', 'collection-history',
      'field-mapping', 'data-quarantine',  // ⚠️ v4.12.0移除：'data-browser'已移除，使用Metabase替代
      
      // 产品与库存（3项）
      'product-management', 'inventory-management', 'inventory-dashboard-v3',
      
      // 采购管理（4项）
      'purchase-orders', 'grn-management', 'vendor-management', 'invoice-management',
      
      // 销售与分析（4项）
      'sales-dashboard-v3', 'sales-analysis', 'customer-management', 'order-management',
      
      // 财务管理（5项）
      'financial-management', 'expense-management', 'finance-reports', 
      'fx-management', 'fiscal-periods',
      
      // 店铺运营（4项）
      'store-management', 'store-analytics', 'account-management', 'account-alignment',
      
      // 报表中心（5项）
      'sales-reports', 'inventory-reports', 'finance-reports-detail', 
      'vendor-reports', 'custom-reports',
      
      // 人力资源（3项）
      'human-resources', 'employee-management', 'attendance-management',
      
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
      
      // 兼容旧权限标识
      'data-governance', 'sales-dashboard', 'data-collection', 'procurement',
      'report-center', 'approval-center', 'message-center', 'help-center',
      'notifications', 'product-category', 'inventory-alert'
    ]
  } else if (role === 'manager') {
    userStore.permissions = [
      'business-overview',
      'product-management', 'product-category', 'inventory-management',
      'procurement', 'purchase-orders', 'grn-management', 'vendor-management',
      'sales-analysis', 'sales-dashboard', 'customer-management', 'order-management',
      'financial-management', 'expense-management', 'finance-reports',
      'store-management', 'store-analytics', 'account-management', 'account-alignment',
      'report-center', 'sales-reports', 'inventory-reports',
      'human-resources', 'employee-management',
      'approval-center', 'my-tasks', 'my-requests',
      'message-center', 'notifications',
      'personal-settings', 'help-center'
    ]
  } else if (role === 'operator') {
    userStore.permissions = [
      'business-overview',
      'product-management', 'inventory-management',
      'sales-analysis', 'sales-dashboard', 'order-management',
      'store-management',
      'message-center', 'notifications',
      'personal-settings', 'help-center'
    ]
  } else if (role === 'finance') {
    userStore.permissions = [
      'business-overview',
      'sales-analysis', 'sales-dashboard',
      'financial-management', 'expense-management', 'finance-reports', 'invoice-management',
      'report-center', 'finance-reports-detail',
      'message-center',
      'personal-settings', 'help-center'
    ]
  }
  
  // 保存到本地存储
  localStorage.setItem('roles', JSON.stringify([role]))
  
  ElMessage.success(`已切换到 ${roleConfig.icon} ${roleConfig.name} 角色`)
  
  // 刷新页面（触发菜单重新渲染和路由守卫）
  router.go(0)
}

// 方法
const handleCommand = (command) => {
  // 处理角色切换
  if (command.startsWith('role:')) {
    const role = command.split(':')[1]
    switchRole(role)
    return
  }
  
  // 处理其他命令
  switch (command) {
    case 'personal-settings':
      router.push('/personal-settings')
      break
    case 'system-settings':
      router.push('/system-settings')
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
  }).then(() => {
    userStore.logout()
    ElMessage.success('已退出登录')
    router.push('/business-overview')
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
