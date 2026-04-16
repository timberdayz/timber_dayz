<template>
  <div class="erp-page-container my-training-page">
    <PageHeader
      title="我的培训"
      subtitle="查看本人培训任务、学习状态、截止时间和下一步动作"
      family="admin"
    />

    <section class="my-training-banner">
      <div>
        <p class="banner-label">当前员工</p>
        <h2>{{ employeeName }}</h2>
      </div>
      <div class="banner-stats">
        <div>
          <span>待学习</span>
          <strong>{{ summary.pending_count }}</strong>
        </div>
        <div>
          <span>待考试</span>
          <strong>{{ summary.pending_exam_count }}</strong>
        </div>
        <div>
          <span>已通过</span>
          <strong>{{ summary.passed_count }}</strong>
        </div>
      </div>
    </section>

    <el-card shadow="hover">
      <el-table :data="items" empty-text="暂无个人培训任务">
        <el-table-column prop="program_name" label="培训项目" min-width="180" />
        <el-table-column prop="learning_status" label="学习状态" min-width="120" />
        <el-table-column prop="current_status" label="当前状态" min-width="120" />
        <el-table-column prop="due_date" label="截止日期" min-width="120" />
        <el-table-column prop="supervisor_name" label="直属主管" min-width="120" />
        <el-table-column prop="note" label="下一步说明" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" min-width="120">
          <template #default="{ row }">
            <el-button link type="primary" @click="router.push(`/training/assignments/${row.assignment_id}`)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import trainingApi from '@/api/training.js'

const router = useRouter()
const employeeName = ref('当前员工')
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

onMounted(async () => {
  const response = await trainingApi.getMyOverview()
  employeeName.value = response.employee_name || employeeName.value
  summary.value = response.summary || summary.value
  items.value = response.items || []
})
</script>

<style scoped>
.my-training-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  margin-bottom: 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, #17324d, #2b5f71);
  color: #fff;
}

.banner-label {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  opacity: 0.75;
}

.my-training-banner h2 {
  margin: 0;
  font-size: 28px;
}

.banner-stats {
  display: flex;
  gap: 20px;
}

.banner-stats span {
  display: block;
  font-size: 12px;
  opacity: 0.8;
}

.banner-stats strong {
  display: block;
  margin-top: 8px;
  font-size: 26px;
}
</style>
