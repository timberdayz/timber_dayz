<template>
  <UnderDevelopment
    title="供应商管理"
    subtitle="供应商管理模块"
    :icon="OfficeBuilding"
    description="供应商主数据管理，评估供应商表现"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { OfficeBuilding } from '@element-plus/icons-vue'

const features = [
  "供应商档案管理",
  "供应商分类和标签",
  "供应商表现评估",
  "采购历史统计",
  "联系人管理"
]
</script>

<style scoped>
/* 供应商管理 页面样式 */
</style>
