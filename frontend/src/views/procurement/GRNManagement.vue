<template>
  <UnderDevelopment
    title="入库单管理"
    subtitle="入库单管理模块"
    :icon="Box"
    description="GRN（Goods Receipt Note）管理，记录采购商品入库"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Box } from '@element-plus/icons-vue'

const features = [
  "创建入库单",
  "关联采购订单",
  "入库数量核对",
  "质量检验记录",
  "自动过账到库存"
]
</script>

<style scoped>
/* 入库单管理 页面样式 */
</style>
