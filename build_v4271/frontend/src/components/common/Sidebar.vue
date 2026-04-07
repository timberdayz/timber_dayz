<template>
  <el-aside width="250px" class="sidebar">
    <!-- Logo区域 -->
    <div class="sidebar-logo">
      <h3>🎯 西虹ERP系统</h3>
      <p>智能跨境电商管理平台</p>
    </div>
    
    <!-- 导航菜单 -->
    <el-menu
      :default-active="activeMenu"
      class="sidebar-menu"
      router
      background-color="#2c3e50"
      text-color="#ecf0f1"
      active-text-color="#3498db"
    >
      <el-menu-item 
        v-for="route in menuRoutes" 
        :key="route.path"
        :index="route.path"
        :disabled="!allowRoute(route)"
      >
        <el-icon v-if="route.meta.icon">
          <component :is="getIconComponent(route.meta.icon)" />
        </el-icon>
        <span>{{ route.meta.title }}</span>
      </el-menu-item>
    </el-menu>
    
    <!-- 底部信息 -->
    <div class="sidebar-footer">
      <div class="system-info">
        <div class="info-item">
          <span class="label">版本:</span>
          <span class="value">v4.6.1</span>
        </div>
        <div class="info-item">
          <span class="label">状态:</span>
          <span class="value status-online">在线</span>
        </div>
      </div>
    </div>
  </el-aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'
import {
  DataBoard,
  TrendCharts,
  Box,
  User,
  Money,
  Shop,
  Setting,
  UserFilled,
  Connection,
  Key,
  Lock,
  Search,
  Warning
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

const menuRoutes = computed(() => {
  let routes = router.getRoutes().filter(route => {
    return route.meta?.title && route.path !== '/' && route.path !== '/:pathMatch(.*)*'
  })

  // 开发模式固定将字段映射置顶，并且确保可见
  if (import.meta.env.DEV) {
    // 找到字段映射路由
    const fm = routes.find(r => r.path === '/field-mapping')
    if (fm) {
      // 先移除，再插入到首位
      routes = [fm, ...routes.filter(r => r.path !== '/field-mapping')]
    }
  }

  return routes
})

const hasPermission = (permission) => {
  if (!permission) return true
  return userStore.hasPermission(permission)
}

const hasRole = (roles) => {
  if (!roles || roles.length === 0) return true
  return userStore.hasRole(roles)
}

// 🔒 严格权限控制（开发和生产环境一致）
const allowRoute = (route) => {
  // ⭐ Phase 8.1修复: 检查是否为管理员（管理员拥有所有权限）
  const isAdmin = userStore.hasRole(['admin'])
  
  // ✅ 管理员跳过权限检查，符合RBAC标准
  if (isAdmin) {
    return true
  }
  
  // 非管理员：检查权限和角色
  const okPerm = hasPermission(route.meta?.permission)
  const okRole = hasRole(route.meta?.roles)
  return okPerm && okRole
}

const getIconComponent = (iconName) => {
  const iconMap = {
    'DataBoard': DataBoard,
    'TrendCharts': TrendCharts,
    'Box': Box,
    'User': User,
    'Money': Money,
    'Shop': Shop,
    'Setting': Setting,
    'UserFilled': UserFilled,
    'Connection': Connection,
    'Key': Key,
    'Lock': Lock,
    'Search': Search,
    'Warning': Warning
  }
  return iconMap[iconName] || Setting
}
</script>

<style scoped>
.sidebar {
  background-color: var(--primary-color);
  min-height: 100vh;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.sidebar-logo {
  padding: var(--spacing-xl);
  text-align: center;
  color: #ecf0f1;
  border-bottom: 1px solid var(--primary-light);
}

.sidebar-logo h3 {
  margin: 0 0 var(--spacing-xs) 0;
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
}

.sidebar-logo p {
  margin: 0;
  font-size: var(--font-size-xs);
  opacity: 0.8;
}

.sidebar-menu {
  border: none;
  flex: 1;
}

.sidebar-menu .el-menu-item {
  height: 56px;
  line-height: 56px;
  margin: 4px 8px;
  border-radius: var(--border-radius-base);
  transition: all var(--transition-base);
}

.sidebar-menu .el-menu-item:hover {
  background-color: rgba(52, 152, 219, 0.1);
}

.sidebar-menu .el-menu-item.is-active {
  background-color: rgba(52, 152, 219, 0.2);
  color: #3498db;
}

.sidebar-menu .el-menu-item .el-icon {
  margin-right: var(--spacing-base);
  font-size: var(--font-size-lg);
}

.sidebar-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--primary-light);
}

.system-info {
  color: #ecf0f1;
  font-size: var(--font-size-xs);
}

.info-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--spacing-xs);
}

.info-item .label {
  opacity: 0.8;
}

.info-item .value {
  font-weight: var(--font-weight-medium);
}

.status-online {
  color: #27ae60;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
