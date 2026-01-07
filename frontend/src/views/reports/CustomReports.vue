<template>
  <UnderDevelopment
    title="自定义报表"
    subtitle="自定义报表模块"
    :icon="Document"
    description="用户自定义维度报表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "报表设计器",
  "维度自定义",
  "指标自定义",
  "报表保存",
  "报表分享"
]
</script>

<style scoped>
/* 自定义报表 页面样式 */
</style>
