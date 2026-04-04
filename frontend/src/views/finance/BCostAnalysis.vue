<template>
  <div class="b-cost-analysis">
    <div class="page-header">
      <div>
        <h1 class="page-title">B类成本分析</h1>
        <p class="page-subtitle">按月查看平台与店铺维度的 B 类成本结构，并下钻订单明细。</p>
      </div>
    </div>

    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="月份">
          <el-date-picker
            v-model="filters.period_month"
            type="month"
            value-format="YYYY-MM"
            placeholder="选择月份"
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item label="平台">
          <el-select
            v-model="filters.platform"
            placeholder="全部平台"
            clearable
            style="width: 140px"
          >
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Lazada" value="lazada" />
          </el-select>
        </el-form-item>
        <el-form-item label="店铺">
          <el-input v-model="filters.shop_name" placeholder="请输入店铺名" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="16" class="kpi-row">
      <el-col v-for="item in kpiCards" :key="item.key" :xs="24" :sm="12" :md="8" :lg="4">
        <el-card class="kpi-card" shadow="hover">
          <div class="kpi-title">{{ item.title }}</div>
          <div class="kpi-value">{{ item.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="table-card">
      <template #header>
        <div class="card-header">
          <span>店铺月汇总</span>
        </div>
      </template>

      <el-alert
        v-if="shopMonthError"
        type="error"
        :closable="false"
        show-icon
        :title="shopMonthError"
        class="erp-mb-md"
      />

      <el-table
        :data="shopMonthRows"
        border
        stripe
        v-loading="shopMonthLoading"
      >
        <el-table-column prop="period_month" label="月份" width="120" />
        <el-table-column prop="platform" label="平台" width="120" />
        <el-table-column prop="shop_name" label="店铺" min-width="180" />
        <el-table-column prop="b_total_cost" label="B类总成本" min-width="130" align="right">
          <template #default="{ row }">{{ formatCurrency(row.b_total_cost) }}</template>
        </el-table-column>
        <el-table-column prop="gmv" label="GMV" min-width="130" align="right">
          <template #default="{ row }">{{ formatCurrency(row.gmv) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="handleViewOrderDetail(row)">查看订单明细</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无店铺月汇总数据" />
        </template>
      </el-table>
    </el-card>

    <el-drawer
      v-model="orderDetailDrawerVisible"
      title="订单明细"
      size="65%"
      destroy-on-close
    >
      <el-alert
        v-if="orderDetailError"
        type="error"
        :closable="false"
        show-icon
        :title="orderDetailError"
        class="erp-mb-md"
      />

      <el-table :data="orderDetailRows" border stripe v-loading="orderDetailLoading">
        <el-table-column prop="order_id" label="订单号" min-width="160" />
        <el-table-column prop="sku" label="SKU" min-width="120" />
        <el-table-column prop="purchase_amount" label="采购金额" min-width="120" align="right">
          <template #default="{ row }">{{ formatCurrency(row.purchase_amount) }}</template>
        </el-table-column>
        <el-table-column prop="warehouse_fee" label="仓库操作费" min-width="120" align="right">
          <template #default="{ row }">{{ formatCurrency(row.warehouse_fee) }}</template>
        </el-table-column>
        <el-table-column prop="platform_fee" label="平台费用" min-width="120" align="right">
          <template #default="{ row }">{{ formatCurrency(row.platform_fee) }}</template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无订单明细数据" />
        </template>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import dayjs from 'dayjs'
import dashboardApi from '@/api/dashboard'

const getCurrentMonth = () => dayjs().format('YYYY-MM')
const periodMonth = ref(getCurrentMonth())
const activeView = ref('shop-month')

const filters = reactive({
  period_month: periodMonth.value,
  platform: '',
  shop_name: '',
})

const overviewLoading = ref(false)
const shopMonthLoading = ref(false)
const orderDetailLoading = ref(false)

const overviewError = ref('')
const shopMonthError = ref('')
const orderDetailError = ref('')

const overview = ref({})
const shopMonthRows = ref([])
const orderDetailRows = ref([])
const selectedShopMonthRow = ref(null)
const orderDetailDrawerVisible = ref(false)

const toPayload = () => ({
  period_month: filters.period_month || periodMonth.value,
  platform: filters.platform || undefined,
  shop_name: filters.shop_name || undefined,
})

const unwrapObject = (response) => response?.data ?? response ?? {}
const unwrapList = (response) => {
  const payload = response?.data ?? response
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  if (Array.isArray(payload?.list)) return payload.list
  return []
}

const formatCurrency = (value) => {
  const num = Number(value ?? 0)
  if (Number.isNaN(num)) return '0.00'
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatPercent = (value) => {
  const num = Number(value ?? 0)
  if (Number.isNaN(num)) return '0.00%'
  return `${(num * 100).toFixed(2)}%`
}

const kpiCards = computed(() => {
  const data = overview.value || {}
  return [
    { key: 'b_total_cost', title: 'B类总成本', value: formatCurrency(data.b_total_cost) },
    { key: 'purchase_amount', title: '采购金额', value: formatCurrency(data.purchase_amount) },
    { key: 'warehouse_fee', title: '仓库操作费', value: formatCurrency(data.warehouse_fee) },
    { key: 'platform_fee_total', title: '平台费用合计', value: formatCurrency(data.platform_fee_total) },
    { key: 'gmv', title: 'GMV', value: formatCurrency(data.gmv) },
    { key: 'b_cost_ratio', title: 'B类成本占GMV比', value: formatPercent(data.b_cost_ratio) },
  ]
})

const loadOverview = async () => {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    const response = await dashboardApi.queryBCostAnalysisOverview(toPayload())
    overview.value = unwrapObject(response)
  } catch (error) {
    overview.value = {}
    overviewError.value = error?.message || '概览加载失败'
  } finally {
    overviewLoading.value = false
  }
}

const loadShopMonth = async () => {
  shopMonthLoading.value = true
  shopMonthError.value = ''
  try {
    const response = await dashboardApi.queryBCostAnalysisShopMonth(toPayload())
    shopMonthRows.value = unwrapList(response)
  } catch (error) {
    shopMonthRows.value = []
    shopMonthError.value = error?.message || '店铺月汇总加载失败'
  } finally {
    shopMonthLoading.value = false
  }
}

const loadOrderDetail = async (row) => {
  orderDetailLoading.value = true
  orderDetailError.value = ''
  try {
    const response = await dashboardApi.queryBCostAnalysisOrderDetail({
      period_month: row?.period_month || filters.period_month,
      platform: row?.platform || filters.platform || undefined,
      shop_name: row?.shop_name || undefined,
      shop_id: row?.shop_id || undefined,
    })
    orderDetailRows.value = unwrapList(response)
  } catch (error) {
    orderDetailRows.value = []
    orderDetailError.value = error?.message || '订单明细加载失败'
  } finally {
    orderDetailLoading.value = false
  }
}

const handleSearch = async () => {
  await Promise.all([loadOverview(), loadShopMonth()])
}

const handleViewOrderDetail = async (row) => {
  selectedShopMonthRow.value = row
  orderDetailDrawerVisible.value = true
  await loadOrderDetail(row)
}

onMounted(async () => {
  if (activeView.value !== 'shop-month') {
    activeView.value = 'shop-month'
  }
  await Promise.all([loadOverview(), loadShopMonth()])
})
</script>

<style scoped>
.b-cost-analysis {
  padding: 20px;
}

.page-header {
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  color: #303133;
}

.page-subtitle {
  margin: 8px 0 0;
  color: #606266;
  font-size: 14px;
}

.filter-card {
  margin-bottom: 16px;
}

.kpi-row {
  margin-bottom: 16px;
}

.kpi-card {
  border-left: 3px solid #409eff;
}

.kpi-title {
  color: #909399;
  font-size: 13px;
  margin-bottom: 8px;
}

.kpi-value {
  color: #303133;
  font-size: 22px;
  font-weight: 600;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
