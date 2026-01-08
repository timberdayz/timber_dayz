<template>
  <el-aside width="250px" class="grouped-sidebar">
    <!-- Logo区域 -->
    <div class="sidebar-logo">
      <h3>🎯 西虹ERP系统</h3>
      <p>智能跨境电商管理平台</p>
    </div>
    
    <!-- 分组导航菜单 -->
    <el-scrollbar class="menu-scrollbar">
      <div class="menu-groups">
        <div 
          v-for="group in visibleGroups" 
          :key="group.id"
          class="menu-group"
        >
          <!-- 分组标题 -->
          <div 
            class="group-header"
            @click.stop="toggleGroup(group.id)"
            :class="{ 'is-expanded': expandedGroups[group.id] }"
          >
            <div class="group-title">
              <el-icon class="group-icon">
                <component :is="getIconComponent(group.icon)" />
              </el-icon>
              <span class="group-text">{{ group.title }}</span>
              <el-tag 
                v-if="group.badge === 'core'" 
                type="danger" 
                size="small"
                class="core-badge"
              >
                核心
              </el-tag>
            </div>
            <el-icon 
              class="expand-icon"
              :class="{ 'is-rotated': expandedGroups[group.id] }"
            >
              <ArrowRight />
            </el-icon>
          </div>
          
          <!-- 分组菜单项 -->
          <el-collapse-transition>
            <div v-show="expandedGroups[group.id]" class="group-items">
              <el-menu
                :default-active="activeMenu"
                class="group-menu"
                router
                background-color="transparent"
                text-color="#ecf0f1"
                active-text-color="#3498db"
              >
                <el-menu-item 
                  v-for="route in group.visibleRoutes" 
                  :key="route.path"
                  :index="route.path"
                  class="group-menu-item"
                >
                  <el-icon v-if="route.meta.icon" class="item-icon">
                    <component :is="getIconComponent(route.meta.icon)" />
                  </el-icon>
                  <span class="item-text">{{ getDisplayName(route) }}</span>
                </el-menu-item>
              </el-menu>
            </div>
          </el-collapse-transition>
        </div>
      </div>
    </el-scrollbar>
    
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
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { menuGroups, routeDisplayNames, deprecatedRoutes } from '@/config/menuGroups'
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
  Warning,
  ArrowRight,
  Tools,
  ShoppingCart,
  Document,
  Check,
  Bell,
  QuestionFilled
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// 展开/收起状态
const expandedGroups = ref({})

// 当前激活的菜单
const activeMenu = computed(() => route.path)

// 权限检查
const hasPermission = (permission) => {
  if (!permission) return true
  return userStore.hasPermission(permission)
}

const hasRole = (roles) => {
  if (!roles || roles.length === 0) return true
  return userStore.hasRole(roles)
}

const allowRoute = (routeItem) => {
  // ⭐ Phase 8.1修复: 检查是否为管理员（管理员拥有所有权限）
  const isAdmin = userStore.hasRole(['admin'])
  
  // ✅ 管理员跳过权限检查，符合RBAC标准
  if (isAdmin) {
    return true
  }
  
  // 非管理员：检查权限和角色
  const okPerm = hasPermission(routeItem.meta?.permission)
  const okRole = hasRole(routeItem.meta?.roles)
  return okPerm && okRole
}

// 获取显示名称
const getDisplayName = (routeItem) => {
  // 使用配置的显示名称覆盖
  if (routeDisplayNames[routeItem.path]) {
    return routeDisplayNames[routeItem.path]
  }
  return routeItem.meta?.title || routeItem.path
}

// 计算可见的分组
const visibleGroups = computed(() => {
  const allRoutes = router.getRoutes()
  
  return menuGroups
    .filter(group => {
      // 开发工具仅在开发环境显示
      if (group.devOnly && !import.meta.env.DEV) {
        return false
      }
      return true
    })
    .map(group => {
      // 获取该分组的路由
      const groupRoutes = group.items
        .map(path => allRoutes.find(r => r.path === path))
        .filter(r => {
          if (!r) return false
          // 过滤废弃路由
          if (deprecatedRoutes.includes(r.path)) return false
          // 权限检查
          return allowRoute(r)
        })
      
      return {
        ...group,
        visibleRoutes: groupRoutes
      }
    })
    .filter(group => {
      // 如果分组内没有可见路由，隐藏整个分组
      return group.visibleRoutes.length > 0
    })
    .sort((a, b) => a.order - b.order)
})

// 切换分组展开/收起
const toggleGroup = (groupId) => {
  const group = visibleGroups.value.find(g => g.id === groupId)
  if (!group || group.visibleRoutes.length === 0) {
    // 如果组不存在或没有可见路由，不执行任何操作
    return
  }
  
  // 如果组已展开，则收起
  if (expandedGroups.value[groupId]) {
    expandedGroups.value[groupId] = false
  } else {
    // 如果组未展开，则展开
    expandedGroups.value[groupId] = true
    
    // 如果组内只有一个可见路由，直接跳转到该路由
    if (group.visibleRoutes.length === 1) {
      const targetRoute = group.visibleRoutes[0]
      if (targetRoute && targetRoute.path) {
        router.push(targetRoute.path).catch(err => {
          // 忽略导航重复的错误
          if (err.name !== 'NavigationDuplicated') {
            console.error('导航失败:', err)
          }
        })
      }
    }
  }
  
  // 保存到localStorage
  localStorage.setItem('expandedGroups', JSON.stringify(expandedGroups.value))
}

// 初始化展开状态
const initExpandedState = () => {
  // 从localStorage恢复
  const saved = localStorage.getItem('expandedGroups')
  if (saved) {
    try {
      expandedGroups.value = JSON.parse(saved)
    } catch (e) {
      console.error('恢复展开状态失败:', e)
    }
  }
  
  // 设置默认展开状态
  visibleGroups.value.forEach(group => {
    if (expandedGroups.value[group.id] === undefined) {
      expandedGroups.value[group.id] = group.defaultExpanded
    }
  })
  
  // 确保当前页面所在的分组展开
  const currentGroup = visibleGroups.value.find(group => 
    group.visibleRoutes.some(r => r.path === route.path)
  )
  if (currentGroup) {
    expandedGroups.value[currentGroup.id] = true
  }
}

// 图标映射
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
    'Warning': Warning,
    'ArrowRight': ArrowRight,
    'Tools': Tools,
    'ShoppingCart': ShoppingCart,  // 采购管理
    'Document': Document,          // 报表中心
    'Check': Check,                // 审批中心
    'Bell': Bell,                  // 消息中心
    'QuestionFilled': QuestionFilled  // 帮助中心
  }
  return iconMap[iconName] || Setting
}

// 组件挂载时初始化
onMounted(() => {
  initExpandedState()
})
</script>

<style scoped>
.grouped-sidebar {
  background-color: #2c3e50;
  min-height: 100vh;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
}

.sidebar-logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid rgba(236, 240, 241, 0.1);
}

.sidebar-logo h3 {
  margin: 0;
  color: #ecf0f1;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 1px;
}

.sidebar-logo p {
  margin: 5px 0 0;
  color: #95a5a6;
  font-size: 12px;
}

.menu-scrollbar {
  flex: 1;
  overflow-y: auto;
}

.menu-groups {
  padding: 10px 0;
}

/* 分组样式 */
.menu-group {
  margin-bottom: 4px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  cursor: pointer;
  transition: all 0.3s ease;
  user-select: none;
}

.group-header:hover {
  background-color: rgba(52, 152, 219, 0.1);
}

.group-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.group-icon {
  font-size: 18px;
  color: #3498db;
}

.group-text {
  color: #ecf0f1;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.core-badge {
  margin-left: 8px;
  font-size: 10px;
  padding: 0 6px;
  height: 18px;
  line-height: 18px;
}

.expand-icon {
  font-size: 14px;
  color: #95a5a6;
  transition: transform 0.3s ease;
}

.expand-icon.is-rotated {
  transform: rotate(90deg);
}

/* 分组菜单项 */
.group-items {
  padding-left: 10px;
  background-color: rgba(0, 0, 0, 0.1);
}

.group-menu {
  border: none;
}

.group-menu-item {
  padding-left: 40px !important;
  height: 45px;
  line-height: 45px;
  position: relative;
}

.group-menu-item::before {
  content: '';
  position: absolute;
  left: 25px;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: #95a5a6;
}

.group-menu-item.is-active::before {
  background-color: #3498db;
}

.item-icon {
  font-size: 16px;
  margin-right: 8px;
}

.item-text {
  font-size: 14px;
}

/* 底部信息 */
.sidebar-footer {
  padding: 15px 20px;
  border-top: 1px solid rgba(236, 240, 241, 0.1);
  background-color: rgba(0, 0, 0, 0.1);
}

.system-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.info-item .label {
  color: #95a5a6;
}

.info-item .value {
  color: #ecf0f1;
  font-weight: 500;
}

.status-online {
  color: #2ecc71;
}

/* 滚动条样式 */
:deep(.el-scrollbar__wrap) {
  overflow-x: hidden;
}

:deep(.el-scrollbar__bar.is-vertical) {
  width: 6px;
}

:deep(.el-scrollbar__thumb) {
  background-color: rgba(144, 147, 153, 0.3);
}

:deep(.el-scrollbar__thumb:hover) {
  background-color: rgba(144, 147, 153, 0.5);
}
</style>

