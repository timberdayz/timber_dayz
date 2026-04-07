<template>
  <div class="debug-page">
    <h1>调试信息</h1>
    
    <div class="debug-section">
      <h2>路由信息</h2>
      <pre>{{ JSON.stringify(router.getRoutes(), null, 2) }}</pre>
    </div>
    
    <div class="debug-section">
      <h2>用户信息</h2>
      <pre>{{ JSON.stringify(userStore.userInfo, null, 2) }}</pre>
    </div>
    
    <div class="debug-section">
      <h2>权限信息</h2>
      <pre>权限: {{ JSON.stringify(userStore.permissions, null, 2) }}</pre>
      <pre>角色: {{ JSON.stringify(userStore.roles, null, 2) }}</pre>
    </div>
    
    <div class="debug-section">
      <h2>过滤后的菜单路由</h2>
      <pre>{{ JSON.stringify(filteredRoutes, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const filteredRoutes = computed(() => {
  return router.getRoutes().filter(route => {
    // 基本过滤条件
    if (!route.meta?.title || route.path === '/' || route.path === '/:pathMatch(.*)*') {
      return false
    }
    
    // 权限检查 - 如果没有权限要求则显示
    if (route.meta.permission && !userStore.hasPermission(route.meta.permission)) {
      return false
    }
    
    // 角色检查 - 如果没有角色要求则显示
    if (route.meta.roles && route.meta.roles.length > 0 && !userStore.hasRole(route.meta.roles)) {
      return false
    }
    
    return true
  })
})
</script>

<style scoped>
.debug-page {
  padding: 20px;
}

.debug-section {
  margin-bottom: 30px;
  border: 1px solid #ddd;
  padding: 15px;
  border-radius: 8px;
}

.debug-section h2 {
  margin-top: 0;
  color: #333;
}

pre {
  background-color: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
}
</style>
