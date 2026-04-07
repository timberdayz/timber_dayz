<template>
  <div id="app">
    <el-container>
      <!-- 侧边栏 -->
      <el-aside width="250px" class="sidebar">
        <div class="logo">
          <h3>🎯 Vue字段映射</h3>
        </div>
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          router
          background-color="#2c3e50"
          text-color="#ecf0f1"
          active-text-color="#3498db"
        >
          <el-menu-item index="/">
            <el-icon><Connection /></el-icon>
            <span>字段映射审核</span>
          </el-menu-item>
          <el-menu-item index="/dashboard">
            <el-icon><DataBoard /></el-icon>
            <span>数据看板</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 主内容区 -->
      <el-container>
        <el-header class="header">
          <div class="header-content">
            <h2>{{ pageTitle }}</h2>
            <div class="header-actions">
              <el-button type="primary" @click="refreshData">
                <el-icon><Refresh /></el-icon>
                刷新数据
              </el-button>
            </div>
          </div>
        </el-header>

        <el-main class="main-content">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useDataStore } from './stores/data'

const route = useRoute()
const dataStore = useDataStore()

const activeMenu = computed(() => route.path)

const pageTitle = computed(() => {
  const titles = {
    '/': 'Vue字段映射审核系统',
    '/dashboard': '数据看板'
  }
  return titles[route.path] || 'Vue字段映射审核系统'
})

const refreshData = () => {
  dataStore.refreshCatalogStatus()
}

onMounted(() => {
  dataStore.loadInitialData()
})
</script>

<style scoped>
.sidebar {
  background-color: #2c3e50;
  min-height: 100vh;
}

.logo {
  padding: 20px;
  text-align: center;
  color: #ecf0f1;
  border-bottom: 1px solid #34495e;
}

.sidebar-menu {
  border: none;
}

.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-content h2 {
  margin: 0;
  font-weight: 600;
}

.main-content {
  background-color: #f5f5f5;
  min-height: calc(100vh - 60px);
}

#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', '微软雅黑', Arial, sans-serif;
}
</style>
