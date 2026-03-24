<template>
  <el-header class="header">
    <div class="header-content">
      <div class="header-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-actions">
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
import SimpleAccountSwitcher from './SimpleAccountSwitcher.vue'
import NotificationBell from './NotificationBell.vue'  // v4.19.0: 通知图标组件

const route = useRoute()

const pageTitle = computed(() => {
  return route.meta?.title || '西虹ERP系统'
})
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
