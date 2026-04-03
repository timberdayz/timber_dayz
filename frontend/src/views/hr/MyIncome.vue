<template>
  <div class="my-income erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">我的收入</h1>
    <p style="color: #909399; margin-bottom: 20px;">
      当前页面仅展示工资单口径收入。绩效和提成会先沉淀到工资单，再在这里统一查看。
    </p>

    <template v-if="!income.linked">
      <el-alert type="warning" show-icon :closable="false">
        <template #title>您尚未关联员工档案</template>
        请联系管理员关联当前账号与员工档案后，再查看工资单收入。
      </el-alert>
    </template>

    <template v-else>
      <el-alert
        v-if="loadError"
        type="error"
        show-icon
        :closable="true"
        style="margin-bottom: 16px;"
        @close="loadError = false"
      >
        查询失败，请稍后重试。
      </el-alert>

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

      <template v-else-if="hasNoIncomeData">
        <el-empty>
          <template #description>
            <p style="margin: 0 0 8px 0;">当月工资单尚未生成</p>
            <p style="color: #909399; margin: 0; font-size: 13px;">
              请等待管理员完成当月绩效重算与工资单确认，或前往人力管理查看工资单记录。
            </p>
          </template>
        </el-empty>
      </template>

      <template v-else>
        <el-row :gutter="20" style="margin-bottom: 20px;">
          <el-col :span="8">
            <el-card shadow="hover">
              <template #header>当月实发</template>
              <div style="font-size: 24px; font-weight: bold; color: #409eff;">
                {{ formatMoney(income.total_income) }}
              </div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="hover">
              <template #header>固定工资</template>
              <div style="font-size: 18px;">{{ formatMoney(income.base_salary) }}</div>
            </el-card>
          </el-col>
          <el-col :span="8">
            <el-card shadow="hover">
              <template #header>提成</template>
              <div style="font-size: 18px;">{{ formatMoney(income.commission_amount) }}</div>
            </el-card>
          </el-col>
        </el-row>

        <el-card v-if="income.breakdown?.payroll" shadow="hover">
          <template #header>工资单摘要</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="固定工资">
              {{ formatMoney(income.breakdown.payroll.base_salary) }}
            </el-descriptions-item>
            <el-descriptions-item label="提成">
              {{ formatMoney(income.breakdown.payroll.commission) }}
            </el-descriptions-item>
            <el-descriptions-item label="实发工资">
              {{ formatMoney(income.breakdown.payroll.net_salary) }}
            </el-descriptions-item>
            <el-descriptions-item label="工资月份">
              {{ income.period || selectedMonth }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/api'

const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const loadError = ref(false)
const income = ref({
  linked: true,
  period: null,
  base_salary: null,
  commission_amount: null,
  total_income: null,
  breakdown: null,
  loading: false
})

const hasNoIncomeData = computed(() => {
  const current = income.value
  if (!current.linked || current.loading) return false
  const noTotal = current.total_income == null
  const noBreakdown = !current.breakdown || Object.keys(current.breakdown).length === 0
  return noTotal && noBreakdown
})

function formatMoney(val) {
  if (val == null || val === undefined) return '-'
  return '楼' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

async function loadIncome() {
  income.value.loading = true
  loadError.value = false
  try {
    const res = await api.getMyIncome(selectedMonth.value)
    const data = res?.data ?? res ?? {}
    income.value = {
      ...income.value,
      ...data,
      period: data.period ?? selectedMonth.value,
      loading: false
    }
  } catch (e) {
    income.value.loading = false
    loadError.value = true
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
