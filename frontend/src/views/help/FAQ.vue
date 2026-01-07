<template>
  <UnderDevelopment
    title="常见问题"
    subtitle="常见问题模块"
    :icon="QuestionFilled"
    description="常见问题解答"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const features = [
  "问题分类",
  "问题搜索",
  "解决方案",
  "反馈建议",
  "联系支持"
]
</script>

<style scoped>
/* 常见问题 页面样式 */
</style>
