<template>
  <div class="store-analysis erp-page-container erp-page--dashboard">
    <PageHeader
      title="店铺分析"
      subtitle="按店铺查看流量、访问、转化与经营概览。Shopee 支持日视图小时级下钻，TikTok 当前保留日级能力。"
      family="dashboard"
    >
      <template #actions>
        <el-button type="primary" :loading="loading" @click="reloadAll">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </template>
    </PageHeader>

    <el-card class="filter-card" shadow="never">
      <div class="filter-row">
        <el-select
          v-model="filters.platform"
          placeholder="选择平台"
          class="control-w-140"
          @change="handlePlatformChange"
        >
          <el-option label="Shopee" value="shopee" />
          <el-option label="TikTok" value="tiktok" />
        </el-select>

        <el-select
          v-model="filters.shopId"
          placeholder="选择店铺"
          class="control-w-220"
          clearable
          filterable
        >
          <el-option
            v-for="shop in availableShops"
            :key="shop.shop_id"
            :label="shop.shop_id"
            :value="shop.shop_id"
          />
        </el-select>

        <el-select
          v-model="filters.granularity"
          placeholder="选择视图"
          class="control-w-140"
        >
          <el-option
            v-for="option in granularityOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>

        <el-date-picker
          v-model="filters.date"
          :type="pickerType"
          :format="pickerFormat"
          :value-format="pickerValueFormat"
          placeholder="选择日期"
          class="control-w-160"
        />

        <el-button :disabled="!canQuery" @click="reloadAll">查询</el-button>
      </div>

      <div class="capability-row">
        <el-tag v-if="capability" type="info" size="small">
          日视图能力：{{ capability.supported_daily_mode === 'hourly' ? '小时级' : '日级' }}
        </el-tag>
        <el-tag v-if="capability" type="success" size="small">
          长周期能力：{{ capability.supported_long_range_mode }}
        </el-tag>
        <span v-if="showDailyFallbackHint" class="capability-hint">
          当前平台暂无小时级流量数据，日视图按天展示。
        </span>
      </div>
    </el-card>

    <div class="kpi-grid" v-loading="loadingOverview || loadingSummary">
      <el-card
        v-for="item in summaryCards"
        :key="item.key"
        class="kpi-card"
        shadow="hover"
      >
        <div class="kpi-label">{{ item.label }}</div>
        <div class="kpi-value">{{ item.value }}</div>
      </el-card>
    </div>

    <el-row :gutter="20" class="summary-row">
      <el-col :xs="24" :lg="16">
        <el-card class="trend-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>流量趋势</span>
              <el-tag v-if="trend.effective_granularity" type="warning" size="small">
                实际粒度：{{ trend.effective_granularity }}
              </el-tag>
            </div>
          </template>

          <el-empty
            v-if="!loadingTrend && trend.items.length === 0"
            description="当前筛选条件下暂无流量数据"
          />

          <div
            v-else
            ref="trendChartRef"
            class="trend-chart"
            v-loading="loadingTrend"
          ></div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="insight-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>分析摘要</span>
            </div>
          </template>

          <div class="insight-list">
            <div class="insight-item">
              <div class="insight-label">店铺</div>
              <div class="insight-value">{{ filters.shopId || '-' }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">GMV</div>
              <div class="insight-value">{{ formatInteger(overview.gmv) }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">订单数</div>
              <div class="insight-value">{{ formatInteger(overview.order_count) }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">达成率</div>
              <div class="insight-value">{{ formatPercent(overview.achievement_rate) }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">经营结果</div>
              <div class="insight-value">{{ overview.operating_result_text || '-' }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">请求粒度</div>
              <div class="insight-value">{{ trend.requested_granularity || filters.granularity }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">实际粒度</div>
              <div class="insight-value">{{ trend.effective_granularity || '-' }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">时间范围</div>
              <div class="insight-value">{{ trendRangeText }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">数据点数</div>
              <div class="insight-value">{{ trend.items.length }}</div>
            </div>
            <div class="insight-item">
              <div class="insight-label">平台说明</div>
              <div class="insight-value insight-note">{{ platformHint }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="detail-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>明细数据</span>
          <el-tag v-if="trend.effective_granularity" type="warning" size="small">
            实际粒度：{{ trend.effective_granularity }}
          </el-tag>
        </div>
      </template>

      <el-empty
        v-if="!loadingTrend && trend.items.length === 0"
        description="当前筛选条件下暂无流量数据"
      />

      <el-table
        v-else
        :data="trend.items"
        stripe
        size="small"
        v-loading="loadingTrend"
      >
        <el-table-column prop="period_key" label="时间" min-width="180" />
        <el-table-column prop="visitor_count" label="访客数" width="140" align="right">
          <template #default="{ row }">
            {{ formatInteger(row.visitor_count) }}
          </template>
        </el-table-column>
        <el-table-column prop="page_views" label="浏览量" width="140" align="right">
          <template #default="{ row }">
            {{ formatInteger(row.page_views) }}
          </template>
        </el-table-column>
        <el-table-column prop="page_views_per_visitor" label="浏览进店比" width="140" align="right">
          <template #default="{ row }">
            {{ row.page_views_per_visitor == null ? '-' : Number(row.page_views_per_visitor).toFixed(2) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="detail-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>对比分析</span>
          <div class="comparison-labels">
            <el-tag v-if="comparison.current_period_label" type="info" size="small">
              当前：{{ comparison.current_period_label }}
            </el-tag>
            <el-tag v-if="comparison.previous_period_label" type="info" size="small">
              上期：{{ comparison.previous_period_label }}
            </el-tag>
          </div>
        </div>
      </template>

      <el-table
        :data="comparisonMetrics"
        stripe
        size="small"
      >
        <el-table-column prop="label" label="指标" min-width="140" />
        <el-table-column prop="current" label="当前周期" width="160" align="right">
          <template #default="{ row }">
            {{ row.key === 'page_views_per_visitor' ? (row.current == null ? '-' : Number(row.current).toFixed(2)) : formatInteger(row.current) }}
          </template>
        </el-table-column>
        <el-table-column prop="previous" label="上一周期" width="160" align="right">
          <template #default="{ row }">
            {{ row.key === 'page_views_per_visitor' ? (row.previous == null ? '-' : Number(row.previous).toFixed(2)) : formatInteger(row.previous) }}
          </template>
        </el-table-column>
        <el-table-column prop="change_pct" label="变化率" width="140" align="right">
          <template #default="{ row }">
            {{ formatPercent(row.change_pct) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="detail-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>商品贡献</span>
        </div>
      </template>

      <el-empty
        v-if="topProducts.length === 0"
        description="当前筛选条件下暂无商品贡献数据"
      />

      <el-table
        v-else
        :data="topProducts"
        stripe
        size="small"
      >
        <el-table-column prop="product_name" label="商品" min-width="220" show-overflow-tooltip />
        <el-table-column prop="sales_amount" label="销售额" width="140" align="right">
          <template #default="{ row }">
            {{ formatInteger(row.sales_amount) }}
          </template>
        </el-table-column>
        <el-table-column prop="order_count" label="订单数" width="120" align="right">
          <template #default="{ row }">
            {{ formatInteger(row.order_count) }}
          </template>
        </el-table-column>
        <el-table-column prop="sales_volume" label="销量" width="120" align="right">
          <template #default="{ row }">
            {{ formatInteger(row.sales_volume) }}
          </template>
        </el-table-column>
        <el-table-column prop="conversion_rate" label="转化率" width="120" align="right">
          <template #default="{ row }">
            {{ formatPercent(row.conversion_rate) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import dashboardApi from '@/api/dashboard'
import { formatInteger, formatPercent } from '@/utils/dataFormatter'
import { handleApiError } from '@/utils/errorHandler'
import echarts from '@/utils/echarts'

const today = new Date().toISOString().slice(0, 10)

const filters = reactive({
  platform: 'shopee',
  shopId: '',
  granularity: 'daily',
  date: today
})

const loading = ref(false)
const loadingOverview = ref(false)
const loadingSummary = ref(false)
const loadingTrend = ref(false)

const availableShops = ref([])
const trendChartRef = ref(null)
const capability = ref(null)
const overview = ref({
  gmv: null,
  order_count: null,
  avg_order_value: null,
  achievement_rate: null,
  profit: null,
  monthly_target: null,
  monthly_achievement_rate: null,
  time_gap: null,
  operating_result: null,
  operating_result_text: null
})
const summary = ref({
  visitor_count: null,
  page_views: null,
  page_views_per_visitor: null
})
const topProducts = ref([])
const comparison = ref({
  current_period_label: null,
  previous_period_label: null,
  metrics: {}
})
const trend = ref({
  requested_granularity: 'daily',
  effective_granularity: 'daily',
  period_start: null,
  period_end: null,
  items: []
})

const canQuery = computed(() => Boolean(filters.platform && filters.shopId && filters.date))

const showDailyFallbackHint = computed(() => {
  return capability.value && filters.granularity === 'daily' && capability.value.supports_hourly_daily === false
})

const granularityOptions = computed(() => [
  { value: 'daily', label: '日视图' },
  { value: 'weekly', label: '周视图' },
  { value: 'monthly', label: '月视图' },
  { value: 'quarterly', label: '季度视图' },
  { value: 'yearly', label: '年度视图' }
])

const pickerType = computed(() => {
  if (filters.granularity === 'weekly') return 'week'
  if (filters.granularity === 'monthly' || filters.granularity === 'quarterly') return 'month'
  if (filters.granularity === 'yearly') return 'year'
  return 'date'
})

const pickerFormat = computed(() => {
  if (filters.granularity === 'yearly') return 'YYYY'
  if (filters.granularity === 'monthly' || filters.granularity === 'quarterly') return 'YYYY-MM'
  return 'YYYY-MM-DD'
})

const pickerValueFormat = computed(() => {
  if (filters.granularity === 'yearly') return 'YYYY'
  if (filters.granularity === 'monthly' || filters.granularity === 'quarterly') return 'YYYY-MM'
  return 'YYYY-MM-DD'
})

const summaryCards = computed(() => [
  { key: 'gmv', label: 'GMV', value: formatInteger(overview.value.gmv) },
  { key: 'order_count', label: '订单数', value: formatInteger(overview.value.order_count) },
  { key: 'achievement_rate', label: '达成率', value: formatPercent(overview.value.achievement_rate) },
  { key: 'operating_result', label: '经营结果', value: overview.value.operating_result_text || '-' },
  { key: 'visitor_count', label: '访客数', value: formatInteger(summary.value.visitor_count) },
  { key: 'page_views', label: '浏览量', value: formatInteger(summary.value.page_views) },
  {
    key: 'page_views_per_visitor',
    label: '浏览进店比',
    value: summary.value.page_views_per_visitor == null ? '-' : Number(summary.value.page_views_per_visitor).toFixed(2)
  }
])

const trendRangeText = computed(() => {
  if (!trend.value.period_start || !trend.value.period_end) {
    return '-'
  }
  return `${trend.value.period_start} ~ ${trend.value.period_end}`
})

const platformHint = computed(() => {
  if (filters.platform === 'shopee') {
    return 'Shopee 日视图支持小时级趋势，可以查看单日小时变化。'
  }
  if (filters.platform === 'tiktok') {
    return 'TikTok 当前日视图按天展示，后续可接入小时级源数据。'
  }
  return '-'
})

const comparisonMetrics = computed(() => {
  const metrics = comparison.value.metrics || {}
  const labels = {
    gmv: 'GMV',
    order_count: '订单数',
    visitor_count: '访客数',
    page_views: '浏览量',
    page_views_per_visitor: '浏览进店比',
    profit: '利润'
  }
  return Object.entries(labels).map(([key, label]) => ({
    key,
    label,
    current: metrics[key]?.current ?? null,
    previous: metrics[key]?.previous ?? null,
    change_pct: metrics[key]?.change_pct ?? null
  }))
})

let trendChartInstance = null

async function loadShops() {
  if (!filters.platform) {
    availableShops.value = []
    return
  }
  try {
    availableShops.value = await dashboardApi.queryStoreAnalysisShops({
      platform: filters.platform
    })
    if (!filters.shopId && availableShops.value.length > 0) {
      filters.shopId = availableShops.value[0].shop_id
    }
  } catch (error) {
    availableShops.value = []
    handleApiError(error, { showMessage: true, logError: true })
  }
}

async function loadCapabilities() {
  if (!filters.platform || !filters.shopId) {
    capability.value = null
    return
  }
  try {
    capability.value = await dashboardApi.queryStoreAnalysisCapabilities({
      platform: filters.platform,
      shop_id: filters.shopId
    })
  } catch (error) {
    capability.value = null
    handleApiError(error, { showMessage: true, logError: true })
  }
}

async function loadOverview() {
  if (!canQuery.value) {
    overview.value = {
      gmv: null,
      order_count: null,
      avg_order_value: null,
      achievement_rate: null,
      profit: null,
      monthly_target: null,
      monthly_achievement_rate: null,
      time_gap: null,
      operating_result: null,
      operating_result_text: null
    }
    return
  }
  loadingOverview.value = true
  try {
    overview.value = await dashboardApi.queryStoreAnalysisOverview({
      platform: filters.platform,
      shop_id: filters.shopId,
      granularity: filters.granularity,
      date: filters.date
    })
  } catch (error) {
    overview.value = {
      gmv: null,
      order_count: null,
      avg_order_value: null,
      achievement_rate: null,
      profit: null,
      monthly_target: null,
      monthly_achievement_rate: null,
      time_gap: null,
      operating_result: null,
      operating_result_text: null
    }
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingOverview.value = false
  }
}

async function loadSummary() {
  if (!canQuery.value) {
    summary.value = {
      visitor_count: null,
      page_views: null,
      page_views_per_visitor: null
    }
    return
  }
  loadingSummary.value = true
  try {
    summary.value = await dashboardApi.queryStoreAnalysisTrafficSummary({
      platform: filters.platform,
      shop_id: filters.shopId,
      granularity: filters.granularity,
      date: filters.date
    })
  } catch (error) {
    summary.value = {
      visitor_count: null,
      page_views: null,
      page_views_per_visitor: null
    }
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingSummary.value = false
  }
}

async function loadComparison() {
  if (!canQuery.value) {
    comparison.value = {
      current_period_label: null,
      previous_period_label: null,
      metrics: {}
    }
    return
  }
  try {
    comparison.value = await dashboardApi.queryStoreAnalysisComparison({
      platform: filters.platform,
      shop_id: filters.shopId,
      granularity: filters.granularity,
      date: filters.date
    })
  } catch (error) {
    comparison.value = {
      current_period_label: null,
      previous_period_label: null,
      metrics: {}
    }
    handleApiError(error, { showMessage: true, logError: true })
  }
}

async function loadTopProducts() {
  if (!canQuery.value) {
    topProducts.value = []
    return
  }
  try {
    topProducts.value = await dashboardApi.queryStoreAnalysisTopProducts({
      platform: filters.platform,
      shop_id: filters.shopId,
      granularity: filters.granularity,
      date: filters.date,
      limit: 10
    })
  } catch (error) {
    topProducts.value = []
    handleApiError(error, { showMessage: true, logError: true })
  }
}

async function loadTrend() {
  if (!canQuery.value) {
    trend.value = {
      requested_granularity: filters.granularity,
      effective_granularity: capability.value?.supported_daily_mode || 'daily',
      period_start: null,
      period_end: null,
      items: []
    }
    return
  }
  loadingTrend.value = true
  try {
    trend.value = await dashboardApi.queryStoreAnalysisTrafficTrend({
      platform: filters.platform,
      shop_id: filters.shopId,
      granularity: filters.granularity,
      date: filters.date
    })
    await nextTick()
    renderTrendChart()
  } catch (error) {
    trend.value = {
      requested_granularity: filters.granularity,
      effective_granularity: capability.value?.supported_daily_mode || 'daily',
      period_start: null,
      period_end: null,
      items: []
    }
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingTrend.value = false
  }
}

async function reloadAll() {
  if (!canQuery.value) {
    ElMessage.warning('请先选择平台、店铺并选择日期')
    return
  }
  loading.value = true
  await loadCapabilities()
  await Promise.all([loadOverview(), loadSummary(), loadTrend(), loadComparison(), loadTopProducts()])
  loading.value = false
}

function handlePlatformChange() {
  capability.value = null
  filters.shopId = ''
  availableShops.value = []
  loadShops()
}

function renderTrendChart() {
  if (!trendChartRef.value) {
    return
  }
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
  if (!trend.value.items || trend.value.items.length === 0) {
    return
  }

  trendChartInstance = echarts.init(trendChartRef.value)
  trendChartInstance.setOption({
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: ['访客数', '浏览量', '浏览进店比']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: trend.value.items.map((item) => item.period_key)
    },
    yAxis: [
      {
        type: 'value',
        name: '数量'
      },
      {
        type: 'value',
        name: '转化率(%)',
        min: 0
      }
    ],
    series: [
      {
        name: '访客数',
        type: 'bar',
        data: trend.value.items.map((item) => item.visitor_count ?? 0),
        itemStyle: { color: '#409EFF' }
      },
      {
        name: '浏览量',
        type: 'bar',
        data: trend.value.items.map((item) => item.page_views ?? 0),
        itemStyle: { color: '#67C23A' }
      },
      {
        name: '浏览进店比',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: trend.value.items.map((item) => item.page_views_per_visitor ?? 0),
        itemStyle: { color: '#E6A23C' }
      }
    ]
  })
}

const resizeHandler = () => {
  if (trendChartInstance) {
    trendChartInstance.resize()
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('resize', resizeHandler)
}

watch(
  () => filters.granularity,
  () => {
    if (filters.granularity === 'yearly') {
      filters.date = new Date().toISOString().slice(0, 4)
    } else if (filters.granularity === 'monthly' || filters.granularity === 'quarterly') {
      filters.date = new Date().toISOString().slice(0, 7)
    } else {
      filters.date = today
    }
  },
  { immediate: true }
)

watch(
  () => [filters.platform, filters.shopId],
  async ([platform, shopId]) => {
    if (platform && shopId) {
      await loadCapabilities()
    }
  }
)

watch(
  () => filters.platform,
  async (platform) => {
    if (platform) {
      await loadShops()
    }
  },
  { immediate: true }
)

watch(
  () => trend.value.items,
  async () => {
    await nextTick()
    renderTrendChart()
  }
)

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', resizeHandler)
  }
  if (trendChartInstance) {
    trendChartInstance.dispose()
    trendChartInstance = null
  }
})
</script>

<style scoped>
.store-analysis {
  background-color: #f5f7fa;
  min-height: calc(100vh - var(--header-height));
}

.filter-card,
.trend-card,
.detail-card {
  border: none;
  margin-bottom: 20px;
}

.summary-row {
  margin-bottom: 20px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.capability-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.capability-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.control-w-140 {
  width: 140px;
}

.control-w-160 {
  width: 160px;
}

.control-w-220 {
  width: 220px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.kpi-card {
  border: none;
}

.kpi-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 6px;
}

.kpi-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.trend-chart {
  min-height: 360px;
}

.insight-card {
  border: none;
  height: 100%;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.insight-item {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
}

.insight-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.insight-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.insight-note {
  font-weight: 500;
  line-height: 1.5;
}

@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
