<template>
  <UnderDevelopment
    title="汇率管理"
    subtitle="汇率管理模块"
    :icon="Money"
    description="全球180+货币汇率管理（CNY本位币）"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Money } from '@element-plus/icons-vue'

const features = [
  "汇率查询和维护",
  "历史汇率查看",
  "汇率预警设置",
  "汇率API配置",
  "货币符号标准化"
]
</script>

<style scoped>
/* 汇率管理 页面样式 */
</style>
