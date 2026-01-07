<template>
  <UnderDevelopment
    title="发票管理"
    subtitle="发票管理模块"
    :icon="Document"
    description="发票上传、三单匹配（PO-GRN-Invoice）"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Document } from '@element-plus/icons-vue'

const features = [
  "发票上传和识别",
  "三单匹配（PO-GRN-Invoice）",
  "发票状态跟踪",
  "发票附件管理",
  "发票报表导出"
]
</script>

<style scoped>
/* 发票管理 页面样式 */
</style>
