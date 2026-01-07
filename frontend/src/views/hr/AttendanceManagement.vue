<template>
  <UnderDevelopment
    title="考勤管理"
    subtitle="考勤管理模块"
    :icon="Clock"
    description="员工考勤记录和统计"
    :features="features"
    timeline="待规划"
    progress="设计阶段"
  />
</template>

<script setup>
import UnderDevelopment from '@/components/common/UnderDevelopment.vue'
import { Clock } from '@element-plus/icons-vue'

const features = [
  "考勤打卡记录",
  "请假申请",
  "加班记录",
  "考勤统计",
  "考勤异常处理"
]
</script>

<style scoped>
/* 考勤管理 页面样式 */
</style>
