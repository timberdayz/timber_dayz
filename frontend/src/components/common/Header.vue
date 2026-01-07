<template>
  <el-header class="header">
    <div class="header-content">
      <div class="header-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-actions">
        <el-button 
          type="primary" 
          @click="refreshData"
          :loading="loading"
          :icon="Refresh"
        >
          刷新数据
        </el-button>
        
        <!-- v4.19.0: 通知图标 -->
        <NotificationBell />
        
        <SimpleAccountSwitcher />
      </div>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useDashboardStore } from '@/stores/dashboard'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import SimpleAccountSwitcher from './SimpleAccountSwitcher.vue'
import NotificationBell from './NotificationBell.vue'  // v4.19.0: 通知图标组件

const route = useRoute()
const dashboardStore = useDashboardStore()

const loading = computed(() => dashboardStore.loading)

const pageTitle = computed(() => {
  const titles = {
    '/business-overview': '📊 业务概览',
    '/sales-analysis': '📈 销售分析',
    '/inventory-management': '📦 库存管理',
    '/human-resources': '👥 人力管理',
    '/financial-management': '💰 财务管理',
    '/store-management': '🏪 店铺管理',
    '/system-settings': '⚙️ 系统设置',
    '/account-management': '👤 账号管理',
    '/personal-settings': '👤 个人设置',
  }
  return titles[route.path] || '西虹ERP系统'
})

const refreshData = async () => {
  try {
    await dashboardStore.refreshAllData()
    ElMessage.success('数据刷新成功')
  } catch (error) {
    ElMessage.error('数据刷新失败')
  }
}

// 移除了handleCommand函数，现在由AccountSwitcher组件处理
</script>

<style scoped>
.header {
  background: var(--gradient-header);
  color: white;
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-xl);
  box-shadow: var(--shadow-base);
  height: var(--header-height);
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-title h2 {
  margin: 0;
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-2xl);
}

.header-actions {
  display: flex;
  gap: var(--spacing-base);
  align-items: center;
}

.user-dropdown {
  color: white;
  padding: var(--spacing-sm) var(--spacing-base);
  border-radius: var(--border-radius-base);
  transition: background-color var(--transition-fast);
}

.user-dropdown:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.user-dropdown .el-icon {
  margin-right: var(--spacing-xs);
}

.user-dropdown .el-icon--right {
  margin-left: var(--spacing-xs);
  margin-right: 0;
}
</style>
