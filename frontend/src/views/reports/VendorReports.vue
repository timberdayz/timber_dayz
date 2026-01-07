<template>
  <UnderDevelopment
    title="供应商报表"
    subtitle="供应商报表模块"
    :icon="Document"
    description="供应商表现分析报表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "供应商采购额",
  "交付准时率",
  "质量合格率",
  "供应商对比",
  "供应商评级"
]
</script>

<style scoped>
/* 供应商报表 页面样式 */
</style>
