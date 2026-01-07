<template>
  <UnderDevelopment
    title="费用管理"
    subtitle="费用管理模块"
    :icon="Wallet"
    description="运营费用管理和分摊"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Wallet } from '@element-plus/icons-vue'

const features = [
  "费用上传（Excel模板）",
  "费用分类管理",
  "费用分摊规则配置",
  "费用分摊执行",
  "费用明细查询"
]
</script>

<style scoped>
/* 费用管理 页面样式 */
</style>
