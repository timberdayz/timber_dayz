<template>
  <UnderDevelopment
    title="我的待办"
    subtitle="我的待办模块"
    :icon="List"
    description="待我审批的任务列表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { List } from '@element-plus/icons-vue'

const features = [
  "待办任务列表",
  "任务详情查看",
  "审批/拒绝操作",
  "审批意见填写",
  "任务提醒"
]
</script>

<style scoped>
/* 我的待办 页面样式 */
</style>
