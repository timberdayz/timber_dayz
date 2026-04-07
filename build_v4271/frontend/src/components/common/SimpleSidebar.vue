<template>
  <el-aside class="simple-sidebar" width="250px">
    <div class="sidebar-header">
      <h2>西虹ERP系统</h2>
      <p>智能跨境电商管理平台</p>
    </div>
    
    <el-menu
      :default-active="activeMenu"
      class="sidebar-menu"
      background-color="#2c3e50"
      text-color="#ecf0f1"
      active-text-color="#3498db"
      router
    >
      <el-menu-item index="/business-overview">
        <span class="menu-icon">📊</span>
        <span>业务概览</span>
      </el-menu-item>
      
      <el-menu-item index="/sales-analysis">
        <span class="menu-icon">📈</span>
        <span>销售分析</span>
      </el-menu-item>
      
      <el-menu-item index="/inventory-management">
        <span class="menu-icon">📦</span>
        <span>库存管理</span>
      </el-menu-item>

      <el-menu-item index="/inventory-overview">
        <span class="menu-icon">📊</span>
        <span>库存总览</span>
      </el-menu-item>
      
      <el-menu-item index="/human-resources">
        <span class="menu-icon">👥</span>
        <span>人力管理</span>
      </el-menu-item>
      
      <el-menu-item index="/financial-management">
        <span class="menu-icon">💰</span>
        <span>财务管理</span>
      </el-menu-item>
      
      <el-menu-item index="/store-management">
        <span class="menu-icon">🏪</span>
        <span>店铺管理</span>
      </el-menu-item>
      
      <el-menu-item index="/system-settings">
        <span class="menu-icon">⚙️</span>
        <span>系统设置</span>
      </el-menu-item>
      
      <el-menu-item index="/account-management">
        <span class="menu-icon">👤</span>
        <span>账号管理</span>
      </el-menu-item>
      
      <el-menu-item index="/personal-settings">
        <span class="menu-icon">🔧</span>
        <span>个人设置</span>
      </el-menu-item>
      
      <el-menu-item index="/test">
        <span class="menu-icon">🧪</span>
        <span>测试页面</span>
      </el-menu-item>
    </el-menu>
    
    <div class="sidebar-footer">
      <div class="version-info">
        <span>版本: v4.0.0</span>
        <span>状态: 在线</span>
      </div>
    </div>
  </el-aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const activeMenu = computed(() => route.path)
</script>

<style scoped>
.simple-sidebar {
  background-color: #2c3e50;
  height: 100vh;
  overflow-y: auto;
  border-right: 1px solid #34495e;
}

.sidebar-header {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #34495e;
  background: linear-gradient(135deg, #34495e 0%, #2c3e50 100%);
}

.sidebar-header h2 {
  margin: 0 0 8px 0;
  color: #ecf0f1;
  font-size: 18px;
  font-weight: 600;
}

.sidebar-header p {
  margin: 0;
  color: #bdc3c7;
  font-size: 12px;
}

.sidebar-menu {
  border: none;
  height: calc(100vh - 120px);
}

.sidebar-menu .el-menu-item {
  height: 50px;
  line-height: 50px;
  padding: 0 20px;
  border-bottom: 1px solid #34495e;
  transition: all 0.3s ease;
}

.sidebar-menu .el-menu-item:hover {
  background-color: #34495e !important;
  color: #3498db !important;
}

.sidebar-menu .el-menu-item.is-active {
  background-color: #3498db !important;
  color: #ffffff !important;
  border-right: 3px solid #2980b9;
}

.menu-icon {
  margin-right: 12px;
  font-size: 16px;
  width: 20px;
  display: inline-block;
  text-align: center;
}

.sidebar-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 15px 20px;
  background-color: #34495e;
  border-top: 1px solid #2c3e50;
}

.version-info {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #bdc3c7;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .simple-sidebar {
    width: 0 !important;
    overflow: hidden;
  }
}

/* 滚动条样式 */
.simple-sidebar::-webkit-scrollbar {
  width: 4px;
}

.simple-sidebar::-webkit-scrollbar-track {
  background: #2c3e50;
}

.simple-sidebar::-webkit-scrollbar-thumb {
  background: #34495e;
  border-radius: 2px;
}

.simple-sidebar::-webkit-scrollbar-thumb:hover {
  background: #3498db;
}
</style>
