<template>
  <UnderDevelopment
    title="采购订单"
    subtitle="采购订单模块"
    :icon="Document"
    description="PO（Purchase Order）管理，支持创建、审批、跟踪采购订单"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "创建采购订单",
  "采购订单列表查看",
  "订单状态跟踪（待审批/已审批/已收货）",
  "订单明细查看",
  "订单修改和取消"
]
</script>

<style scoped>
/* 采购订单 页面样式 */
</style>
