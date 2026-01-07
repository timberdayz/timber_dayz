<template>
  <UnderDevelopment
    title="员工档案"
    subtitle="员工档案模块"
    :icon="UserFilled"
    description="员工基本信息管理"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { UserFilled } from '@element-plus/icons-vue'

const features = [
  "员工信息录入",
  "员工档案查看",
  "员工组织架构",
  "员工合同管理",
  "员工离职管理"
]
</script>

<style scoped>
/* 员工档案 页面样式 */
</style>
