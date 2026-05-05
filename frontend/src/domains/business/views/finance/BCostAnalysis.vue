<template>
  <div class="b-cost-analysis">
    <div class="page-header">
      <div>
        <h1 class="page-title">B类成本分析</h1>
        <p class="page-subtitle">按月查看 B 类成本，并可下钻到订单明细。</p>
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
          <el-input
            v-model="filters.platform"
            placeholder="例如 shopee"
            clearable
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item label="店铺ID">
          <el-input
            v-model="filters.shop_id"
            placeholder="请输入 shop_id"
            clearable
            style="width: 180px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-alert
      v-if="overviewError"
      type="error"
      :closable="false"
      show-icon
      :title="overviewError"
      class="erp-mb-md"
    />

    <el-row v-else :gutter="16" class="kpi-row" v-loading="overviewLoading">
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

      <el-table :data="shopMonthRows" border stripe v-loading="shopMonthLoading">
        <el-table-column prop="period_month" label="月份" width="120" />
        <el-table-column prop="platform_code" label="平台" width="120" />
        <el-table-column prop="shop_id" label="店铺ID" min-width="140" />
        <el-table-column prop="currency_code" label="币种" width="100" />
        <el-table-column prop="total_cost_b" label="B类总成本" min-width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.total_cost_b) }}</template>
        </el-table-column>
        <el-table-column prop="gmv" label="GMV" min-width="140" align="right">
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
        <el-table-column label="SKU" min-width="160">
          <template #default="{ row }">{{ row.platform_sku || row.product_sku || '-' }}</template>
        </el-table-column>
        <el-table-column prop="currency_code" label="币种" width="100" />
        <el-table-column prop="purchase_amount" label="采购金额" min-width="120" align="right">
          <template #default="{ row }">{{ formatCurrency(row.purchase_amount) }}</template>
        </el-table-column>
        <el-table-column prop="warehouse_operation_fee" label="仓库操作费" min-width="120" align="right">
          <template #default="{ row }">{{ formatCurrency(row.warehouse_operation_fee) }}</template>
        </el-table-column>
        <el-table-column prop="platform_total_cost_itemized" label="平台费用(明细)" min-width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.platform_total_cost_itemized) }}</template>
        </el-table-column>
        <el-table-column prop="platform_total_cost_derived" label="平台费用(推导)" min-width="140" align="right">
          <template #default="{ row }">{{ formatCurrency(row.platform_total_cost_derived) }}</template>
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

const orderDetailPage = ref(1)
const orderDetailPageSize = ref(20)

const filters = reactive({
  period_month: periodMonth.value,
  platform: '',
  shop_id: '',
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

const toOverviewPayload = () => ({
  period_month: filters.period_month || periodMonth.value,
  platform: filters.platform || undefined,
  shop_id: filters.shop_id || undefined,
})

const toOrderDetailPayload = (row) => ({
  period_month: row?.period_month || filters.period_month,
  platform: row?.platform_code || filters.platform || undefined,
  shop_id: row?.shop_id || filters.shop_id || undefined,
  page: orderDetailPage.value,
  page_size: orderDetailPageSize.value,
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
  if (value === null || value === undefined || value === '') return '--'
  const num = Number(value)
  if (Number.isNaN(num)) return '--'
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const formatPercent = (value) => {
  if (value === null || value === undefined || value === '') return 'N/A'
  const num = Number(value)
  if (Number.isNaN(num)) return 'N/A'
  return `${(num * 100).toFixed(2)}%`
}

const kpiCards = computed(() => {
  const data = overview.value || {}
  const totalCostBValue = data.total_cost_b
  const gmvValue = data.gmv
  let bCostRatio = null
  if (
    totalCostBValue !== null &&
    totalCostBValue !== undefined &&
    gmvValue !== null &&
    gmvValue !== undefined
  ) {
    const totalCostB = Number(totalCostBValue)
    const gmv = Number(gmvValue)
    if (!Number.isNaN(totalCostB) && !Number.isNaN(gmv) && gmv !== 0) {
      bCostRatio = totalCostB / gmv
    }
  }
  return [
    { key: 'total_cost_b', title: 'B类总成本', value: formatCurrency(data.total_cost_b) },
    { key: 'purchase_amount', title: '采购金额', value: formatCurrency(data.purchase_amount) },
    { key: 'warehouse_operation_fee', title: '仓库操作费', value: formatCurrency(data.warehouse_operation_fee) },
    { key: 'platform_total_cost_itemized', title: '平台费用合计', value: formatCurrency(data.platform_total_cost_itemized) },
    { key: 'gmv', title: 'GMV', value: formatCurrency(data.gmv) },
    { key: 'b_cost_ratio', title: 'B类成本占GMV比', value: formatPercent(bCostRatio) },
  ]
})

const loadOverview = async () => {
  overviewLoading.value = true
  overviewError.value = ''
  try {
    const response = await dashboardApi.queryBCostAnalysisOverview(toOverviewPayload())
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
    const response = await dashboardApi.queryBCostAnalysisShopMonth(toOverviewPayload())
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
    const response = await dashboardApi.queryBCostAnalysisOrderDetail(toOrderDetailPayload(row))
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
