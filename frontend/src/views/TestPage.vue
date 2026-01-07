<template>
  <div class="test-page">
    <h1>测试页面</h1>
    <p>如果你能看到这个页面，说明Vue应用基本正常</p>
    <el-button type="primary" @click="testClick">测试按钮</el-button>
    <p>点击次数: {{ clickCount }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const clickCount = ref(0)

const testClick = () => {
  clickCount.value++
  ElMessage.success(`按钮被点击了 ${clickCount.value} 次`)
}
</script>

<style scoped>
.test-page {
  padding: 20px;
  text-align: center;
}

h1 {
  color: #2c3e50;
  margin-bottom: 20px;
}

p {
  color: #7f8c8d;
  margin-bottom: 20px;
}
</style>
