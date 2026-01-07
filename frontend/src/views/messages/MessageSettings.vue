<template>
  <UnderDevelopment
    title="消息设置"
    subtitle="消息设置模块"
    :icon="Setting"
    description="消息通知偏好设置"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Setting } from '@element-plus/icons-vue'

const features = [
  "通知方式设置",
  "提醒频率设置",
  "预警阈值设置",
  "免打扰时段",
  "消息订阅管理"
]
</script>

<style scoped>
/* 消息设置 页面样式 */
</style>
