<template>
  <UnderDevelopment
    title="系统日志"
    subtitle="系统日志模块"
    :icon="Document"
    description="系统操作日志和审计追踪"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "操作日志查询",
  "登录日志",
  "错误日志",
  "审计日志",
  "日志导出"
]
</script>

<style scoped>
/* 系统日志 页面样式 */
</style>
