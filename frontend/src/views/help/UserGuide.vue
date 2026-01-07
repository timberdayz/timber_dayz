<template>
  <UnderDevelopment
    title="操作指南"
    subtitle="操作指南模块"
    :icon="Reading"
    description="系统操作手册和使用指南"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Reading } from '@element-plus/icons-vue'

const features = [
  "快速入门",
  "功能说明",
  "操作步骤",
  "最佳实践",
  "常见场景"
]
</script>

<style scoped>
/* 操作指南 页面样式 */
</style>
