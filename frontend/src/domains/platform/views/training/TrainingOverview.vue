<template>
  <div class="training-page erp-page-container">
    <PageHeader
      title="培训总览"
      subtitle="统一查看培训项目、培训状态、通过率和风险名单"
      family="admin"
    />

    <section class="training-hero">
      <div class="hero-copy">
        <p class="hero-kicker">{{ moduleName }}</p>
        <h2>把培训从临时试点提升为正式业务模块</h2>
        <p class="hero-text">
          外部平台承载课程和考试，ERP 负责项目、分配、结果、逾期风险和统一入口。
        </p>
      </div>
      <div class="hero-status">
        <div class="status-chip">
          <span>总人数</span>
          <strong>{{ summary.total_count }}</strong>
        </div>
        <div class="status-chip">
          <span>已通过</span>
          <strong>{{ summary.passed_count }}</strong>
        </div>
        <div class="status-chip danger">
          <span>已逾期</span>
          <strong>{{ summary.overdue_count }}</strong>
        </div>
      </div>
    </section>

    <el-row :gutter="16" class="summary-row">
      <el-col :span="6" v-for="card in summaryCards" :key="card.label">
        <el-card shadow="hover" class="summary-card">
          <div class="summary-label">{{ card.label }}</div>
          <div class="summary-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span>近期培训分配</span>
          <el-tag type="info">正式模块入口</el-tag>
        </div>
      </template>
      <el-table :data="items" empty-text="暂无培训数据">
        <el-table-column prop="employee_name" label="员工姓名" min-width="120" />
        <el-table-column prop="department" label="部门" min-width="120" />
        <el-table-column prop="role_name" label="岗位" min-width="120" />
        <el-table-column prop="program_name" label="培训项目" min-width="180" />
        <el-table-column prop="learning_status" label="学习状态" min-width="120" />
        <el-table-column prop="current_status" label="当前状态" min-width="120" />
        <el-table-column prop="due_date" label="截止日期" min-width="120" />
        <el-table-column prop="note" label="备注" min-width="220" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const moduleName = ref('培训管理')
const items = ref([])
const summary = ref({
  total_count: 0,
  pending_count: 0,
  studying_count: 0,
  pending_exam_count: 0,
  passed_count: 0,
  failed_count: 0,
  overdue_count: 0
})

const summaryCards = computed(() => [
  { label: '待学习', value: summary.value.pending_count },
  { label: '学习中', value: summary.value.studying_count },
  { label: '待考试', value: summary.value.pending_exam_count },
  { label: '未通过', value: summary.value.failed_count }
])

onMounted(async () => {
  const response = await trainingApi.getOverview()
  moduleName.value = response.module_name || moduleName.value
  summary.value = response.summary || summary.value
  items.value = response.items || []
})
</script>

<style scoped>
.training-hero {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
  padding: 24px;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(10, 72, 117, 0.95), rgba(20, 130, 120, 0.9));
  color: #fff;
  box-shadow: 0 12px 30px rgba(6, 45, 75, 0.16);
}

.hero-kicker {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.8;
}

.hero-copy h2 {
  margin: 0 0 12px;
  font-size: 28px;
  line-height: 1.2;
}

.hero-text {
  margin: 0;
  line-height: 1.7;
  color: rgba(255, 255, 255, 0.88);
}

.hero-status {
  display: grid;
  gap: 12px;
}

.status-chip {
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.12);
}

.status-chip span {
  display: block;
  font-size: 13px;
  opacity: 0.8;
}

.status-chip strong {
  display: block;
  margin-top: 8px;
  font-size: 26px;
}

.status-chip.danger {
  background: rgba(180, 32, 38, 0.22);
}

.summary-row {
  margin-bottom: 16px;
}

.summary-label {
  font-size: 13px;
  color: #909399;
}

.summary-value {
  margin-top: 10px;
  font-size: 28px;
  font-weight: 700;
  color: #243241;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
