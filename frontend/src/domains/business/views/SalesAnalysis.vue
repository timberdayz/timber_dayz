<template>
  <div class="sales-analysis">
    <div class="page-header">
      <h1>销售分析</h1>
      <p>销售数据分析页面</p>
    </div>
    
    <div class="content">
      <el-card>
        <template #header>
          <span>销售数据概览</span>
        </template>
        <p>销售分析功能正在开发中...</p>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

// 简单的响应式数据
const data = ref('销售分析数据')
</script>

<style scoped>
.sales-analysis {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  color: #409EFF;
  margin-bottom: 10px;
}

.content {
  margin-top: 20px;
}
</style>