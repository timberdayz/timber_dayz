<template>
  <div class="income-audit erp-page-container erp-page--admin">
    <div class="page-header">
      <div>
        <h1 class="page-title">员工月度收入审计</h1>
        <p class="page-subtitle">按员工和月份查看从店铺归属、绩效、提成到工资单的完整链路。</p>
      </div>
    </div>

    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <el-select v-model="filters.employeeCode" filterable placeholder="选择员工" style="width: 260px;">
          <el-option
            v-for="item in employeeOptions"
            :key="item.employee_code"
            :label="`${item.name || item.employee_code} (${item.employee_code})`"
            :value="item.employee_code"
          />
        </el-select>
        <el-date-picker
          v-model="filters.yearMonth"
          type="month"
          value-format="YYYY-MM"
          placeholder="选择月份"
          style="width: 160px;"
        />
        <el-button type="primary" :loading="loading" @click="loadAudit">查询</el-button>
      </div>
    </el-card>

    <el-alert
      v-if="audit?.my_income_projection?.is_stale_against_latest_calc"
      type="warning"
      :closable="false"
      title="当前工资单已落后于最新重算结果"
      style="margin-bottom: 16px;"
    />

    <el-card v-if="audit" shadow="never" class="section-card">
      <template #header>审计总览</template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="员工">{{ audit.employee?.name }} ({{ audit.employee?.employee_code }})</el-descriptions-item>
        <el-descriptions-item label="月份">{{ audit.year_month }}</el-descriptions-item>
        <el-descriptions-item label="月结状态">{{ audit.settlement_status || 'draft/none' }}</el-descriptions-item>
        <el-descriptions-item label="工资单状态">{{ audit.payroll_record?.status || '无工资单' }}</el-descriptions-item>
        <el-descriptions-item label="我的收入实发">{{ formatMoney(audit.my_income_projection?.net_salary) }}</el-descriptions-item>
        <el-descriptions-item label="最新重算时间">{{ audit.my_income_projection?.latest_calculated_at || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="audit" shadow="never" class="section-card">
      <template #header>店铺归属与店铺绩效</template>
      <el-table :data="audit.shop_assignments || []" border stripe>
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" min-width="160" />
        <el-table-column prop="commission_ratio" label="提成比例" width="100" align="right" />
        <el-table-column prop="allocatable_profit_rate" label="可分配利润率" width="120" align="right" />
        <el-table-column prop="profit_basis_amount" label="利润基数" width="120" align="right">
          <template #default="{ row }">{{ formatMoney(row.profit_basis_amount) }}</template>
        </el-table-column>
        <el-table-column prop="shop_performance_score" label="店铺绩效分" width="110" align="right" />
        <el-table-column prop="shop_performance_coefficient" label="店铺绩效系数" width="120" align="right" />
        <el-table-column prop="shop_performance_status" label="绩效状态" width="100" />
        <el-table-column label="待补维度" min-width="180">
          <template #default="{ row }">{{ (row.shop_performance_pending_dimensions || []).join(' / ') || '—' }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="audit" shadow="never" class="section-card">
      <template #header>个人绩效输入与结果</template>
      <el-table :data="audit.performance_inputs || []" border stripe>
        <el-table-column prop="metric_name" label="指标" min-width="160" />
        <el-table-column prop="metric_direction" label="方向" width="100" />
        <el-table-column prop="target_value" label="目标值" width="100" align="right" />
        <el-table-column prop="achieved_value" label="实际值" width="100" align="right" />
        <el-table-column prop="max_score" label="满分" width="90" align="right" />
        <el-table-column prop="source" label="来源" width="120" />
      </el-table>
      <el-descriptions :column="2" border style="margin-top: 16px;">
        <el-descriptions-item label="个人绩效分">{{ audit.employee_performance?.performance_score ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="实际销售额">{{ audit.employee_performance?.actual_sales ?? '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="audit" shadow="never" class="section-card">
      <template #header>提成结果与工资单</template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="提成金额">{{ formatMoney(audit.employee_commission?.commission_amount) }}</el-descriptions-item>
        <el-descriptions-item label="提成率">{{ audit.employee_commission?.commission_rate ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="绩效工资">{{ formatMoney(audit.payroll_record?.performance_salary) }}</el-descriptions-item>
        <el-descriptions-item label="工资单提成">{{ formatMoney(audit.payroll_record?.commission) }}</el-descriptions-item>
        <el-descriptions-item label="工资单实发">{{ formatMoney(audit.payroll_record?.net_salary) }}</el-descriptions-item>
        <el-descriptions-item label="工资单总成本">{{ formatMoney(audit.payroll_record?.total_cost) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const loading = ref(false)
const audit = ref(null)
const employeeOptions = ref([])
const filters = reactive({
  employeeCode: '',
  yearMonth: new Date().toISOString().slice(0, 7)
})

function formatMoney(value) {
  if (value == null || value === '') return '—'
  return `¥${Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

async function loadEmployees() {
  const response = await api.getHrEmployees({ page: 1, page_size: 500 })
  const data = Array.isArray(response) ? response : (response?.items || response?.data?.items || response?.data || [])
  employeeOptions.value = Array.isArray(data) ? data.filter((item) => !item.status || item.status === 'active') : []
}

async function loadAudit() {
  if (!filters.employeeCode || !filters.yearMonth) {
    ElMessage.warning('请选择员工和月份')
    return
  }
  loading.value = true
  try {
    const response = await api.getHrIncomeAudit(filters.employeeCode, filters.yearMonth)
    audit.value = response?.data || response
  } catch (error) {
    audit.value = null
    ElMessage.error(error?.response?.data?.detail || error?.message || '加载审计视图失败')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadEmployees()
})
</script>

<style scoped>
.income-audit {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
}

.page-subtitle {
  margin: 8px 0 0;
  color: #909399;
}

.filter-card,
.section-card {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
</style>
