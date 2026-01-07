<template>
  <UnderDevelopment
    title="视频教程"
    subtitle="视频教程模块"
    :icon="VideoPlay"
    description="视频教学和演示"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { VideoPlay } from '@element-plus/icons-vue'

const features = [
  "入门视频",
  "功能演示",
  "实战案例",
  "技巧分享",
  "在线学习"
]
</script>

<style scoped>
/* 视频教程 页面样式 */
</style>
