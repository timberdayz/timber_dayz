<template>
  <UnderDevelopment
    title="销售报表"
    subtitle="销售报表模块"
    :icon="Document"
    description="销售数据多维度报表"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "店铺销售报表",
  "SKU销售报表",
  "时间维度报表",
  "平台对比报表",
  "自定义维度"
]
</script>

<style scoped>
/* 销售报表 页面样式 */
</style>
