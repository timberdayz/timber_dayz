<template>
  <UnderDevelopment
    title="采购订单"
    subtitle="采购订单模块"
    :icon="Document"
    description="PO（Purchase Order）管理，支持创建、审批、跟踪采购订单。当前版本仍处于桥接阶段，补货确认任务尚未接入自动员工任务流。"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  '创建采购订单',
  '采购订单列表查看',
  '订单状态跟踪（待审批、已审批、已收货）',
  '订单明细查看',
  '订单修改和取消',
  '补货确认任务桥接说明（当前仅支持任务中心设计占位，不宣称自动化已上线）'
]
</script>

<style scoped>
/* PurchaseOrders placeholder page */
</style>
