<template>
  <UnderDevelopment
    title="API文档"
    subtitle="API文档模块"
    :icon="Document"
    description="后端API接口文档"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "API列表",
  "接口详情",
  "参数说明",
  "示例代码",
  "在线调试"
]
</script>

<style scoped>
/* API文档 页面样式 */
</style>
