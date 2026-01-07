<template>
  <UnderDevelopment
    title="财务报表详情"
    subtitle="财务报表详情模块"
    :icon="Document"
    description="详细财务分析报表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "P&L明细",
  "成本分析",
  "利润分析",
  "费用明细",
  "税务报表"
]
</script>

<style scoped>
/* 财务报表详情 页面样式 */
</style>
