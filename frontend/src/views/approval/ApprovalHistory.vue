<template>
  <UnderDevelopment
    title="审批历史"
    subtitle="审批历史模块"
    :icon="Clock"
    description="所有审批记录查询"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Clock } from '@element-plus/icons-vue'

const features = [
  "历史记录查询",
  "按状态筛选",
  "按类型筛选",
  "审批统计",
  "导出记录"
]
</script>

<style scoped>
/* 审批历史 页面样式 */
</style>
