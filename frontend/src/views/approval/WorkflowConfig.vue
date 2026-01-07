<template>
  <UnderDevelopment
    title="流程配置"
    subtitle="流程配置模块"
    :icon="Setting"
    description="审批流程规则配置（仅管理员）"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Setting } from '@element-plus/icons-vue'

const features = [
  "流程设计器",
  "审批节点配置",
  "审批人设置",
  "审批条件配置",
  "流程测试"
]
</script>

<style scoped>
/* 流程配置 页面样式 */
</style>
