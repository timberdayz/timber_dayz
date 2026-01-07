<template>
  <UnderDevelopment
    title="财务报表"
    subtitle="财务报表模块"
    :icon="Document"
    description="P&L损益表、现金流量表等财务报表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "损益表（P&L）",
  "现金流量表",
  "资产负债表",
  "店铺级财务报表",
  "SKU级利润分析"
]
</script>

<style scoped>
/* 财务报表 页面样式 */
</style>
