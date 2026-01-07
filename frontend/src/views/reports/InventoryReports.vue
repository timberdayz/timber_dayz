<template>
  <UnderDevelopment
    title="库存报表"
    subtitle="库存报表模块"
    :icon="Document"
    description="库存数据报表和分析"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "库存余额报表",
  "库存流水报表",
  "库龄分析报表",
  "呆滞库存报表",
  "库存周转率"
]
</script>

<style scoped>
/* 库存报表 页面样式 */
</style>
