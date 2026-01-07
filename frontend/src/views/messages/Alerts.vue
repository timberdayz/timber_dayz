<template>
  <UnderDevelopment
    title="预警提醒"
    subtitle="预警提醒模块"
    :icon="Warning"
    description="业务异常预警和提醒"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Warning } from '@element-plus/icons-vue'

const features = [
  "库存预警",
  "订单异常",
  "财务异常",
  "采集失败",
  "系统异常"
]
</script>

<style scoped>
/* 预警提醒 页面样式 */
</style>
