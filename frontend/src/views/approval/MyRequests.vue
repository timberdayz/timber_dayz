<template>
  <UnderDevelopment
    title="我的申请"
    subtitle="我的申请模块"
    :icon="Document"
    description="我发起的审批申请"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "申请列表",
  "申请进度跟踪",
  "申请撤回",
  "申请详情",
  "审批历史"
]
</script>

<style scoped>
/* 我的申请 页面样式 */
</style>
