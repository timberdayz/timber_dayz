<template>
  <UnderDevelopment
    title="会计期间"
    subtitle="会计期间模块"
    :icon="Calendar"
    description="会计期间管理和关账"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Calendar } from '@element-plus/icons-vue'

const features = [
  "会计期间设置",
  "期间开账/关账",
  "期间数据锁定",
  "期初余额设置",
  "期间报表查看"
]
</script>

<style scoped>
/* 会计期间 页面样式 */
</style>
