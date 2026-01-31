<template>
  <div class="my-income erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">我的收入</h1>

    <template v-if="!income.linked">
      <el-alert type="warning" show-icon :closable="false">
        <template #title>您尚未关联员工档案</template>
        请联系管理员关联您的账号与员工档案后，即可查看收入明细。
      </el-alert>
    </template>

    <template v-else>
      <div class="action-bar" style="margin-bottom: 20px;">
        <el-date-picker
          v-model="selectedMonth"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择月份"
          size="small"
          style="width: 150px;"
          @change="loadIncome"
        />
      </div>

      <template v-if="income.loading">
        <el-skeleton :rows="5" animated />
      </template>

      <template v-else-if="!income.period && !income.loading">
        <el-empty description="暂无收入数据">
          <template #description>当前月份暂无收入数据，请稍后查看或联系人事部门。</template>
        </el-empty>
      </template>

      <template v-else>
        <el-row :gutter="20" style="margin-bottom: 20px;">
          <el-col :span="6">
            <el-card shadow="hover">
              <template #header>当月实发</template>
              <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                {{ formatMoney(income.total_income) }}
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover">
              <template #header>底薪</template>
              <div style="font-size: 18px;">{{ formatMoney(income.base_salary) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover">
              <template #header>提成</template>
              <div style="font-size: 18px;">{{ formatMoney(income.commission_amount) }}</div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover">
              <template #header>绩效得分</template>
              <div style="font-size: 18px;">{{ income.performance_score != null ? income.performance_score.toFixed(1) : '-' }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card v-if="income.breakdown && Object.keys(income.breakdown).length" shadow="hover">
          <template #header>收入明细</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item v-if="income.breakdown.payroll" label="工资单">底薪 {{ formatMoney(income.breakdown.payroll.base_salary) }}，提成 {{ formatMoney(income.breakdown.payroll.commission) }}</el-descriptions-item>
            <el-descriptions-item v-if="income.breakdown.salary_structure" label="薪资结构">底薪 {{ formatMoney(income.breakdown.salary_structure.base_salary) }}</el-descriptions-item>
            <el-descriptions-item v-if="income.breakdown.performance" label="绩效">得分 {{ income.breakdown.performance.score }}, 达成率 {{ (income.breakdown.performance.achievement_rate * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item v-if="income.breakdown.commission" label="提成">金额 {{ formatMoney(income.breakdown.commission.amount) }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card style="margin-top: 20px;" shadow="hover">
          <template #header>绩效依据</template>
          <p>绩效得分：{{ income.performance_score != null ? income.performance_score.toFixed(1) : '-' }}</p>
          <p>达成率：{{ income.achievement_rate != null ? (income.achievement_rate * 100).toFixed(1) + '%' : '-' }}</p>
          <el-link type="primary" href="/#/hr-performance-management">查看绩效公示</el-link>
        </el-card>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api from '@/api'

const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const income = ref({
  linked: true,
  period: null,
  base_salary: null,
  commission_amount: 0,
  commission_rate: null,
  performance_score: null,
  achievement_rate: null,
  total_income: null,
  breakdown: null,
  loading: false
})

function formatMoney(val) {
  if (val == null || val === undefined) return '-'
  return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

async function loadIncome() {
  income.value.loading = true
  try {
    const res = await api.getMyIncome(selectedMonth.value)
    income.value = { ...income.value, ...res, loading: false }
  } catch (e) {
    income.value.loading = false
    if (e?.response?.status === 404 || (e?.response?.data?.detail && String(e.response.data.detail).includes('关联'))) {
      income.value.linked = false
    }
  }
}

onMounted(() => {
  loadIncome()
})
</script>

<style scoped>
.my-income {
  padding: 20px;
}
</style>
