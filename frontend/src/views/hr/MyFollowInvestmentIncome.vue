<template>
  <div class="my-income erp-page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">我的跟投收益</h1>
        <p class="page-subtitle">查看统一利润分配基准下的个人跟投收益明细。</p>
      </div>
    </div>

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

    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>预计收益</template>
          <div style="font-size: 22px; font-weight: bold; color: #409eff;">
            {{ formatMoney(summary.estimated_income) }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>已批准收益</template>
          <div style="font-size: 22px; font-weight: bold; color: #67c23a;">
            {{ formatMoney(summary.approved_income) }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>已支付收益</template>
          <div style="font-size: 22px; font-weight: bold; color: #e6a23c;">
            {{ formatMoney(summary.paid_income) }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header>本金快照</template>
          <div style="font-size: 22px; font-weight: bold;">
            {{ formatMoney(summary.current_contribution_amount) }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
      title="预计收益仅供参考，以财务审核后的结算结果为准。"
    />

    <el-table :data="items" stripe v-loading="loading">
      <el-table-column prop="period_month" label="月份" width="120" />
      <el-table-column prop="platform_code" label="平台" width="120" />
      <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
      <el-table-column prop="profit_basis_amount" label="结算基准利润 (楼)" width="160" align="right">
        <template #default="{ row }">{{ formatMoney(row.profit_basis_amount) }}</template>
      </el-table-column>
      <el-table-column prop="share_ratio" label="我的占比" width="120" align="right">
        <template #default="{ row }">{{ formatPercent(row.share_ratio) }}</template>
      </el-table-column>
      <el-table-column prop="estimated_income" label="预计收益 (楼)" width="140" align="right">
        <template #default="{ row }">{{ formatMoney(row.estimated_income) }}</template>
      </el-table-column>
      <el-table-column prop="approved_income" label="已批准 (楼)" width="140" align="right">
        <template #default="{ row }">{{ formatMoney(row.approved_income) }}</template>
      </el-table-column>
      <el-table-column prop="paid_income" label="已支付 (楼)" width="140" align="right">
        <template #default="{ row }">{{ formatMoney(row.paid_income) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120" />
    </el-table>
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

function formatMoney(val) {
  if (val == null || val === undefined) return '-'
  return '楼' + Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

function formatPercent(val) {
  if (val == null || val === undefined) return '-'
  return `${(Number(val) * 100).toFixed(2)}%`
}

async function loadIncome() {
  loading.value = true
  try {
    const res = await financeApi.getMyFollowInvestmentIncome({ period_month: selectedMonth.value })
    const data = res?.data ?? res ?? {}
    summary.value = data.summary || summary.value
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
.my-income {
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
</style>
