<template>
  <div class="test-page">
    <h1>测试页面</h1>
    <p>如果你能看到这个页面，说明路由系统工作正常！</p>
    
    <div class="test-info">
      <h2>当前路由信息</h2>
      <p><strong>路径:</strong> {{ $route.path }}</p>
      <p><strong>名称:</strong> {{ $route.name }}</p>
      <p><strong>标题:</strong> {{ $route.meta?.title }}</p>
    </div>
    
    <div class="test-actions">
      <el-button type="primary" @click="goToBusinessOverview">
        前往业务概览
      </el-button>
      <el-button type="success" @click="goToDebug">
        前往调试页面
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goToBusinessOverview = () => {
  router.push('/business-overview')
}

const goToDebug = () => {
  router.push('/debug')
}
</script>

<style scoped>
.test-page {
  padding: 40px;
  text-align: center;
}

.test-info {
  margin: 30px 0;
  padding: 20px;
  background-color: #f5f5f5;
  border-radius: 8px;
  text-align: left;
  max-width: 500px;
  margin-left: auto;
  margin-right: auto;
}

.test-actions {
  margin-top: 30px;
}

.test-actions .el-button {
  margin: 0 10px;
}
</style>
