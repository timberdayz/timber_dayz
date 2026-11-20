<template>
  <el-card class="section-card">
    <template #header>
      <div class="card-header">
        <span>本月结果</span>
        <el-tag v-if="adjustmentCount > 0" type="warning">含 {{ adjustmentCount }} 笔人工调整</el-tag>
      </div>
    </template>

    <el-row :gutter="16" class="overview-grid">
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">净利润</div>
          <div class="overview-value" :class="valueClass(netProfitAmount)">{{ formatAmount(netProfitAmount) }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">绩效工资</div>
          <div class="overview-value" :class="valueClass(performanceAmount)">{{ formatAmount(performanceAmount) }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">提成</div>
          <div class="overview-value" :class="valueClass(commissionAmount)">{{ formatAmount(commissionAmount) }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">员工侧分配</div>
          <div class="overview-value" :class="valueClass(employeeAllocationAmount)">{{ formatAmount(employeeAllocationAmount) }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">人工调整</div>
          <div class="overview-value" :class="valueClass(manualAdjustmentAmount)">{{ formatAmount(manualAdjustmentAmount) }}</div>
          <div class="overview-hint">正数扣减留存，负数追加留存</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4">
        <div class="overview-item">
          <div class="overview-label">公司留存</div>
          <div class="overview-value retained" :class="valueClass(companyRetainedAmount)">{{ formatAmount(companyRetainedAmount) }}</div>
        </div>
      </el-col>
    </el-row>

    <div class="overview-footer">
      <div class="footer-item">
        <span class="footer-label">分配占比</span>
        <span class="footer-value">{{ formatRatio(allocationRatio) }}</span>
      </div>
      <div class="footer-item">
        <span class="footer-label">超额分配标记</span>
        <el-tag v-if="overAllocationFlag" type="danger" effect="dark">超额分配</el-tag>
        <el-tag v-else type="info" effect="plain">未标记超额</el-tag>
      </div>
    </div>

    <el-alert
      v-if="overAllocationFlag"
      type="warning"
      :closable="false"
      show-icon
      title="本月分配已超过利润。"
      class="section-alert"
    />
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { formatDashboardAmount, formatDashboardRatio } from '@/stores/financeDashboard'

const props = defineProps({
  dashboard: { type: Object, required: true }
})

// ⚠️ 以下数值全部来自后端，前端只渲染、不重算、不推断。
const netProfitAmount = computed(() => props.dashboard?.net_profit_amount ?? null)
const performanceAmount = computed(() => props.dashboard?.performance_salary_amount ?? null)
const commissionAmount = computed(() => props.dashboard?.commission_amount ?? null)
const employeeAllocationAmount = computed(() => props.dashboard?.employee_allocation_amount ?? null)
const manualAdjustmentAmount = computed(() => props.dashboard?.manual_adjustment_amount ?? null)
const companyRetainedAmount = computed(() => props.dashboard?.company_retained_amount ?? null)
const allocationRatio = computed(() => props.dashboard?.allocation_ratio ?? null)
const overAllocationFlag = computed(() => props.dashboard?.over_allocation_flag === true)
const adjustmentCount = computed(() => Number(props.dashboard?.manual_adjustment_count ?? 0))

const formatAmount = (value) => formatDashboardAmount(value)
const formatRatio = (value) => formatDashboardRatio(value)

/** 负数显红：绝不截断为 0、绝不显示绝对值。 */
const valueClass = (value) => (Number(value) < 0 ? 'negative' : '')
</script>

<style scoped>
.section-card { margin-bottom: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-weight: 600; }
.overview-grid { margin-bottom: 8px; }
.overview-item { height: 100%; padding: 18px; border-radius: 10px; background: #fafbfc; border: 1px solid #ebeef5; }
.overview-label { margin-bottom: 8px; color: #606266; font-size: 13px; }
.overview-value { font-size: 24px; font-weight: 700; color: #303133; word-break: break-all; }
.overview-value.retained { color: #237804; }
.overview-value.negative { color: #f56c6c; }
.overview-hint { margin-top: 6px; color: #909399; font-size: 12px; }
.overview-footer { display: flex; flex-wrap: wrap; gap: 32px; padding: 14px 18px; border: 1px solid #ebeef5; border-radius: 10px; background: #fff; }
.footer-item { display: flex; align-items: center; gap: 10px; }
.footer-label { color: #606266; font-size: 13px; }
.footer-value { font-size: 18px; font-weight: 700; color: #303133; }
.section-alert { margin-top: 16px; }
</style>
