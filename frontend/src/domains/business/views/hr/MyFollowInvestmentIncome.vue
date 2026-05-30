<template>
  <div class="my-follow-investment-income erp-page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">我的跟投收益</h1>
        <p class="page-subtitle">
          这里仅展示已经生成的个人跟投结算结果，不包含试算、审批或回退操作。
        </p>
      </div>
    </div>

    <div class="action-bar">
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

    <el-alert
      type="info"
      show-icon
      :closable="false"
      class="page-alert"
      title="预计收益仅供参考，最终以财务审批后的结算结果为准。"
    />

    <el-skeleton v-if="loading" :rows="5" animated />

    <template v-else>
      <el-row :gutter="20" class="summary-row">
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover">
            <template #header>预计收益</template>
            <div class="summary-value primary">{{ formatMoney(summary.estimated_income) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover">
            <template #header>已批准收益</template>
            <div class="summary-value success">{{ formatMoney(summary.approved_income) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover">
            <template #header>已确认收益</template>
            <div class="summary-value warning">{{ formatMoney(summary.paid_income) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :sm="12" :lg="6">
          <el-card shadow="hover">
            <template #header>本金快照</template>
            <div class="summary-value">{{ formatMoney(summary.current_contribution_amount) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="explanation-card">
        <template #header>收益说明</template>
        <div
          v-for="item in explanationItems"
          :key="item.key"
          class="explanation-item"
        >
          <div class="explanation-title">{{ item.title }}</div>
          <div class="explanation-body">{{ item.body }}</div>
        </div>
      </el-card>

      <el-empty v-if="!items.length" description="当前月份暂无跟投结算记录" />

      <el-table v-else :data="items" stripe>
        <el-table-column prop="period_month" label="月份" width="120" />
        <el-table-column prop="investor_name" label="投资人" width="140" />
        <el-table-column prop="platform_code" label="平台" width="120" />
        <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
        <el-table-column prop="profit_basis_amount" label="结算基准利润" width="160" align="right">
          <template #default="{ row }">{{ formatMoney(row.profit_basis_amount) }}</template>
        </el-table-column>
        <el-table-column prop="share_ratio" label="分配占比" width="120" align="right">
          <template #default="{ row }">{{ formatPercent(row.share_ratio) }}</template>
        </el-table-column>
        <el-table-column prop="estimated_income" label="预计收益" width="140" align="right">
          <template #default="{ row }">{{ formatMoney(row.estimated_income) }}</template>
        </el-table-column>
        <el-table-column prop="approved_income" label="已批准收益" width="140" align="right">
          <template #default="{ row }">{{ formatMoney(row.approved_income) }}</template>
        </el-table-column>
        <el-table-column prop="paid_income" label="已确认收益" width="140" align="right">
          <template #default="{ row }">{{ formatMoney(row.paid_income) }}</template>
        </el-table-column>
        <el-table-column prop="approved_at" label="审批时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.approved_at) }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" size="small">{{ formatStatus(row.status) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import financeApi from '@/api/finance'

const selectedMonth = ref(new Date().toISOString().slice(0, 7))
const loading = ref(false)
const summary = ref({
  estimated_income: 0,
  approved_income: 0,
  paid_income: 0,
  current_contribution_amount: 0
})
const items = ref([])
const explanationItems = [
  {
    key: 'estimated',
    title: '预计收益',
    body: '预计收益来自当前月份的跟投试算结果，只表示试算口径，不代表最终结算。'
  },
  {
    key: 'approved',
    title: '已批准收益',
    body: '已批准收益表示该月该店铺的跟投结算已经完成审批，月结中心会按这个值计入实际跟投收益。'
  },
  {
    key: 'paid',
    title: '已确认收益',
    body: '已确认收益表示后续支付或确认口径，当前如果为 0，说明已经审批但还没有进入确认环节。'
  },
  {
    key: 'snapshot',
    title: '本金快照',
    body: '本金快照展示该月参与分配时使用的本金记录，不代表你当前账户里的实时本金余额。'
  }
]

function formatMoney(val) {
  if (val == null || val === undefined) return '-'
  return `¥${Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatPercent(val) {
  if (val == null || val === undefined) return '-'
  return `${(Number(val) * 100).toFixed(2)}%`
}

function formatDateTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function formatStatus(status) {
  if (status === 'approved') return '已批准'
  if (status === 'calculated') return '已试算'
  if (status === 'reopened') return '已回退'
  if (status === 'draft') return '草稿'
  return status || '-'
}

function getStatusType(status) {
  if (status === 'approved') return 'success'
  if (status === 'calculated') return 'warning'
  if (status === 'reopened') return 'info'
  return 'info'
}

async function loadIncome() {
  loading.value = true
  try {
    const res = await financeApi.getMyFollowInvestmentIncome({ period_month: selectedMonth.value })
    const data = res?.data ?? res ?? {}
    summary.value = {
      estimated_income: Number(data.summary?.estimated_income || 0),
      approved_income: Number(data.summary?.approved_income || 0),
      paid_income: Number(data.summary?.paid_income || 0),
      current_contribution_amount: Number(data.summary?.current_contribution_amount || 0)
    }
    items.value = data.items || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadIncome()
})
</script>

<style scoped>
.my-follow-investment-income {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
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

.action-bar {
  margin-bottom: 16px;
}

.page-alert {
  margin-bottom: 20px;
}

.summary-row {
  margin-bottom: 20px;
}

.explanation-card {
  margin-bottom: 20px;
}

.explanation-item + .explanation-item {
  margin-top: 12px;
}

.explanation-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.explanation-body {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}

.summary-value {
  font-size: 22px;
  font-weight: 700;
}

.summary-value.primary {
  color: #409eff;
}

.summary-value.success {
  color: #67c23a;
}

.summary-value.warning {
  color: #e6a23c;
}
</style>
