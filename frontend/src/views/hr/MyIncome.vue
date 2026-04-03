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
          <template #header>
            <div class="payroll-card-header">
              <span>工资单明细</span>
              <el-tag
                v-if="payrollDetails.status"
                :type="getPayrollStatusType(payrollDetails.status)"
                size="small"
              >
                {{ formatPayrollStatus(payrollDetails.status) }}
              </el-tag>
            </div>
          </template>

          <div class="payroll-meta">
            <span>工资月份：{{ income.period || selectedMonth }}</span>
            <span v-if="payrollDetails.pay_date">发薪日期：{{ payrollDetails.pay_date }}</span>
          </div>

          <div
            v-for="section in payrollSections"
            :key="section.title"
            class="payroll-section"
          >
            <div class="payroll-section-title">{{ section.title }}</div>
            <el-descriptions :column="2" border>
              <el-descriptions-item
                v-for="item in section.items"
                :key="item.key"
                :label="item.label"
              >
                {{ formatMoney(item.value) }}
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <el-alert
            v-if="payrollDetails.remark"
            type="info"
            :closable="false"
            show-icon
            style="margin-top: 16px;"
          >
            <template #title>备注</template>
            {{ payrollDetails.remark }}
          </el-alert>
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

const payrollDetails = computed(() => income.value.breakdown?.payroll ?? null)

const payrollSections = computed(() => {
  const payroll = payrollDetails.value
  if (!payroll) return []

  return [
    {
      title: '应发项',
      items: [
        { key: 'base_salary', label: '基本工资', value: payroll.base_salary },
        { key: 'position_salary', label: '岗位工资', value: payroll.position_salary },
        { key: 'performance_salary', label: '绩效工资', value: payroll.performance_salary },
        { key: 'overtime_pay', label: '加班费', value: payroll.overtime_pay },
        { key: 'commission', label: '提成', value: payroll.commission },
        { key: 'allowances', label: '津贴', value: payroll.allowances },
        { key: 'bonus', label: '奖金', value: payroll.bonus },
        { key: 'gross_salary', label: '应发合计', value: payroll.gross_salary }
      ]
    },
    {
      title: '扣除项',
      items: [
        { key: 'social_insurance_personal', label: '个人社保', value: payroll.social_insurance_personal },
        { key: 'housing_fund_personal', label: '个人公积金', value: payroll.housing_fund_personal },
        { key: 'income_tax', label: '个税', value: payroll.income_tax },
        { key: 'other_deductions', label: '其他扣款', value: payroll.other_deductions },
        { key: 'total_deductions', label: '扣款合计', value: payroll.total_deductions },
        { key: 'net_salary', label: '实发工资', value: payroll.net_salary }
      ]
    },
    {
      title: '公司成本',
      items: [
        { key: 'social_insurance_company', label: '公司社保', value: payroll.social_insurance_company },
        { key: 'housing_fund_company', label: '公司公积金', value: payroll.housing_fund_company },
        { key: 'total_cost', label: '公司总成本', value: payroll.total_cost }
      ]
    }
  ]
})

function formatMoney(val) {
  if (val == null || val === undefined) return '-'
  return '¥' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

function formatPayrollStatus(status) {
  if (status === 'confirmed') return '已确认'
  if (status === 'paid') return '已发放'
  return '草稿'
}

function getPayrollStatusType(status) {
  if (status === 'confirmed') return 'success'
  if (status === 'paid') return 'warning'
  return 'info'
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

.payroll-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.payroll-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  color: #606266;
  font-size: 13px;
}

.payroll-section + .payroll-section {
  margin-top: 16px;
}

.payroll-section-title {
  margin-bottom: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
</style>
