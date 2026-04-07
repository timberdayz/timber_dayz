<template>
  <el-header class="simple-header">
    <div class="header-content">
      <div class="header-title">
        <h2>{{ pageTitle }}</h2>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData">
          🔄 刷新数据
        </el-button>
        <SimpleAccountSwitcher />
      </div>
    </div>
  </el-header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import SimpleAccountSwitcher from './SimpleAccountSwitcher.vue'

const route = useRoute()

const pageTitle = computed(() => {
  const titles = {
    '/business-overview': '📊 业务概览',
    '/sales-analysis': '📈 销售分析',
    '/inventory-management': '📦 库存管理',
    '/inventory-overview': '📊 库存总览',
    '/inventory/ledger': '📜 库存流水',
    '/inventory/adjustments': '🧾 库存调整',
    '/inventory/grns': '📥 入库单管理',
    '/inventory/alerts': '🚨 库存预警',
    '/inventory/reconciliation': '🔎 库存对账',
    '/inventory/aging': '⏳ 库存库龄',
    '/inventory/opening-balances': '📘 期初余额',
    '/human-resources': '👥 人力管理',
    '/financial-management': '💰 财务管理',
    '/store-management': '🏪 店铺管理',
    '/system-settings': '⚙️ 系统设置',
    '/account-management': '👤 账号管理',
    '/personal-settings': '👤 个人设置',
    '/test': '🧪 测试页面'
  }
  return titles[route.path] || '西虹ERP系统'
})

const refreshData = () => {
  ElMessage.success('数据刷新成功')
}
</script>

<style scoped>
.simple-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  height: 60px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.header-title h2 {
  margin: 0;
  font-weight: 600;
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 15px;
  align-items: center;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .simple-header {
    padding: 0 15px;
  }
  
  .header-title h2 {
    font-size: 18px;
  }
  
  .header-actions {
    gap: 10px;
  }
}
</style>
