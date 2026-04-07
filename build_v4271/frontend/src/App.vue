<template>
  <el-config-provider :locale="zhCn" size="default">
    <div id="app">
    <!-- 公开路由（登录、注册）不显示系统布局，直接渲染路由视图 -->
    <router-view v-if="isPublicRoute" />
    
    <!-- 受保护路由显示完整系统布局（侧边栏 + 顶部栏 + 主内容） -->
    <div v-else-if="showProtectedLayout" class="app-layout">
      <!-- 侧边栏：使用分组菜单（企业级ERP标准） -->
      <GroupedSidebar />
      
      <!-- 主内容区 -->
      <div class="main-container">
        <!-- 顶部导航栏：使用 Header 组件（包含通知图标） -->
        <Header />
        
        <!-- 主内容 -->
        <div class="main-content">
          <router-view />
        </div>
      </div>
      <!-- ICP 备案号：底部左侧悬挂，满足合规要求 -->
      <IcpFooter />
    </div>
    <div v-else class="auth-pending-shell"></div>
    </div>
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { useUserStore } from '@/stores/user'
import { useAuthStore } from '@/stores/auth'
// import Sidebar from '@/components/common/Sidebar.vue'  // 旧版本（保留备份）
import GroupedSidebar from '@/components/common/GroupedSidebar.vue'  // ✅ 新版分组菜单
import Header from '@/components/common/Header.vue'  // ⭐ v4.19.0: 使用 Header 组件（包含通知图标）
import IcpFooter from '@/components/common/IcpFooter.vue'  // ICP 备案号页脚

const route = useRoute()
const userStore = useUserStore()
const authStore = useAuthStore()

// ⭐ v4.19.0: 判断是否为公开路由（登录、注册页面不显示系统布局）
const isPublicRoute = computed(() => {
  // 检查路由 meta 中的 public 标记
  if (route.meta?.public === true) {
    return true
  }
  // 检查路由路径（兜底方案）
  const publicPaths = ['/login', '/register']
  return publicPaths.includes(route.path)
})

const showProtectedLayout = computed(() => !isPublicRoute.value && authStore.isLoggedIn)

onMounted(() => {
  // ⭐ v4.19.5 修复：确保认证状态已恢复（main.js 中已调用，这里作为兜底）
  if (!authStore.isLoggedIn) {
    authStore.initAuth()
  }
  
  // 初始化用户信息（用于权限检查）
  if (authStore.isLoggedIn) {
    userStore.initUserInfo()
  }
  console.log('🚀 西虹ERP系统前端已启动')
})
</script>

<style>
* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: #2c3e50;
  background-color: #f8f9fa;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.auth-pending-shell {
  min-height: 100vh;
}

/* 应用布局 */
.app-layout {
  display: flex;
  min-height: 100vh;
}

/* 侧边栏样式 */
.sidebar {
  width: 250px;
  background-color: #2c3e50;
  color: white;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.menu {
  flex: 1;
  padding: 20px 0;
}

.menu-item {
  padding: 15px 20px;
  cursor: pointer;
  transition: background-color 0.3s;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.menu-item:hover {
  background-color: #34495e;
}

.menu-item.active {
  background-color: #3498db;
}

/* 主容器 */
.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 头部样式（由 Header 组件内部处理） */

/* 主内容区域 */
.main-content {
  flex: 1;
  background-color: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: #e9ecef;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb {
  background: #7f8c8d;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #34495e;
}
</style>
