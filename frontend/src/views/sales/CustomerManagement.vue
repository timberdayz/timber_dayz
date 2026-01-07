<template>
  <UnderDevelopment
    title="客户管理"
    subtitle="客户管理模块"
    :icon="UserFilled"
    description="CRM客户关系管理，客户档案和分析"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { UserFilled } from '@element-plus/icons-vue'

const features = [
  "客户档案管理",
  "客户分类和标签",
  "客户价值分析（RFM模型）",
  "客户生命周期管理",
  "客户联系记录"
]
</script>

<style scoped>
/* 客户管理 页面样式 */
</style>
