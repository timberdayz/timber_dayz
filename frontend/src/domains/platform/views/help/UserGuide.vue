<template>
  <div class="user-guide-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">操作指南</h1>
        <p class="page-subtitle">集中查看关键业务手册、运行说明和排障入口。</p>
      </div>
    </div>

    <el-row :gutter="20">
      <el-col :span="24" :lg="16">
        <el-card id="hr-payroll" shadow="hover" class="guide-card">
          <template #header>
            <div class="guide-card-header">
              <div>
                <div class="guide-card-title">HR工资单运行手册</div>
                <div class="guide-card-subtitle">覆盖绩效重算、工资单流转、锁定冲突、审计定位和排障步骤。</div>
              </div>
              <el-tag type="success" size="small">hr-payroll</el-tag>
            </div>
          </template>

          <el-descriptions :column="1" border>
            <el-descriptions-item label="适用对象">HR、管理员、维护人员</el-descriptions-item>
            <el-descriptions-item label="关键入口">绩效管理、工资单管理、我的收入</el-descriptions-item>
            <el-descriptions-item label="仓库文档路径">
              <code>docs/guides/HR_PAYROLL_OPERATIONS_RUNBOOK.md</code>
            </el-descriptions-item>
          </el-descriptions>

          <div class="guide-section">
            <div class="guide-section-title">包含内容</div>
            <ul class="guide-list">
              <li>月度绩效重算如何触发工资单更新</li>
              <li>锁定冲突如何识别、退回草稿并重算</li>
              <li><code>draft / confirmed / paid</code> 的状态语义</li>
              <li>“我的收入”为空态时如何排障</li>
              <li>工资单已发放后如何定位审计日志</li>
            </ul>
          </div>
        </el-card>
      </el-col>

      <el-col :span="24" :lg="8">
        <el-card shadow="hover" class="guide-card">
          <template #header>
            <div class="guide-card-title">快速入口</div>
          </template>

          <div class="quick-links">
            <el-button type="primary" plain @click="focusTopic('hr-payroll')">
              打开工资单运行手册
            </el-button>
            <el-button plain @click="router.push('/human-resources?tab=salary')">
              前往工资单管理
            </el-button>
            <el-button plain @click="router.push('/my-income')">
              前往我的收入
            </el-button>
            <el-button plain @click="router.push('/hr-performance-management')">
              前往绩效管理
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { nextTick, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

async function focusTopic(topic) {
  await router.replace({ name: 'UserGuide', query: { topic } })
  await nextTick()
  document.getElementById(topic)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(async () => {
  const topic = typeof route.query.topic === 'string' ? route.query.topic : ''
  if (topic) {
    await nextTick()
    document.getElementById(topic)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
})
</script>

<style scoped>
.user-guide-page {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  color: #303133;
}

.page-subtitle {
  margin: 8px 0 0;
  color: #606266;
}

.guide-card {
  margin-bottom: 20px;
}

.guide-card-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.guide-card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.guide-card-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #909399;
}

.guide-section {
  margin-top: 16px;
}

.guide-section-title {
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.guide-list {
  margin: 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.8;
}

.quick-links {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
