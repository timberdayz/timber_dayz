<template>
  <div class="annual-summary">
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">年度数据总结</h1>
        <p class="page-subtitle">按月度/年度汇总核心 KPI 与成本产出，支撑年度审视与来年成本配置</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="loadData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <span class="filter-label">粒度</span>
      <el-radio-group v-model="granularity" size="small" @change="onGranularityChange">
        <el-radio-button label="monthly">月度</el-radio-button>
        <el-radio-button label="yearly">年度</el-radio-button>
      </el-radio-group>
      <template v-if="granularity === 'monthly'">
        <span class="filter-label">月份</span>
        <el-date-picker
          v-model="periodMonth"
          type="month"
          format="YYYY-MM"
          value-format="YYYY-MM"
          placeholder="选择月份"
          size="small"
          style="width: 140px"
          @change="loadData"
        />
      </template>
      <template v-else>
        <span class="filter-label">年份</span>
        <el-date-picker
          v-model="periodYear"
          type="year"
          format="YYYY"
          value-format="YYYY"
          placeholder="选择年份"
          size="small"
          style="width: 120px"
          @change="loadData"
        />
      </template>
    </div>

    <!-- 核心 KPI -->
    <div class="section-title">核心 KPI 指标</div>
    <div class="kpi-section" v-loading="loading">
      <el-row :gutter="20" class="kpi-cards-row">
        <el-col
          v-for="kpi in kpiData"
          :key="kpi.key"
          :xs="24"
          :sm="12"
          :md="8"
          :lg="3"
        >
          <el-card class="kpi-card" shadow="hover">
            <div class="kpi-content">
              <div class="kpi-info">
                <div class="kpi-title">{{ kpi.title }}</div>
                <div class="kpi-value">{{ kpi.value }}</div>
                <div class="kpi-change" :class="kpi.changeType">
                  {{ kpi.change }}
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 成本与产出 -->
    <div class="section-title">成本与产出</div>
    <div class="cost-section" v-loading="loading">
      <el-row :gutter="20" class="cost-cards-row">
        <el-col v-for="item in costData" :key="item.key" :xs="24" :sm="12" :md="8" :lg="4">
          <el-card class="cost-card" shadow="hover">
            <div class="cost-title">{{ item.title }}</div>
            <div class="cost-value">{{ item.value }}</div>
            <div class="cost-sub" v-if="item.sub">{{ item.sub }}</div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 月度/年度趋势（无数据时显示 0，与业务概览一致） -->
    <div class="section-title">月度/年度趋势</div>
    <div class="ext-section" v-loading="loadingExtension">
      <div ref="trendChartRef" class="chart-container" style="height: 280px;"></div>
    </div>

    <!-- 平台占比 (GMV)（无数据时显示 0） -->
    <div class="section-title">平台占比 (GMV)</div>
    <div class="ext-section" v-loading="loadingExtension">
      <div ref="platformShareChartRef" class="chart-container chart-pie" style="height: 280px;"></div>
    </div>

    <!-- 目标完成率（无数据时显示 0%） -->
    <div class="section-title">目标完成率</div>
    <div class="ext-section target-section">
      <div class="target-item">
        <span class="target-label">GMV 目标</span>
        <el-progress
          :percentage="Math.min(100, Math.round(targetCompletion.achievement_rate_gmv ?? 0))"
          :stroke-width="16"
          :format="() => `${(targetCompletion.achievement_rate_gmv ?? 0).toFixed(1)}%`"
        />
      </div>
      <div class="target-item">
        <span class="target-label">利润目标</span>
        <el-progress
          :percentage="Math.min(100, Math.round(targetCompletion.achievement_rate_profit ?? 0))"
          :stroke-width="16"
          :format="() => `${(targetCompletion.achievement_rate_profit ?? 0).toFixed(1)}%`"
        />
      </div>
    </div>

    <!-- 按店铺下钻（无数据时表格展示空状态，显示 0） -->
    <div class="section-title">按店铺下钻</div>
    <div class="ext-section" v-loading="loadingExtension">
      <el-table :data="byShopList" border stripe style="width: 100%" empty-text="0">
        <el-table-column label="店铺/平台" min-width="120">
          <template #default="{ row }">{{ row.shop_name || row.platform || (row.platform_code ? `${row.platform_code}-${row.shop_id || ''}` : row.shop_id) || '0' }}</template>
        </el-table-column>
        <el-table-column prop="gmv" label="GMV" min-width="100">
          <template #default="{ row }">{{ formatCurrency(row.gmv) }}</template>
        </el-table-column>
        <el-table-column prop="total_cost" label="总成本" min-width="100">
          <template #default="{ row }">{{ formatCurrency(row.total_cost) }}</template>
        </el-table-column>
        <el-table-column prop="cost_to_revenue_ratio" label="成本产出比" width="110">
          <template #default="{ row }">{{ ratioDisplay(row.cost_to_revenue_ratio) }}</template>
        </el-table-column>
        <el-table-column prop="gross_margin" label="毛利率" width="100">
          <template #default="{ row }">{{ ratioDisplay(row.gross_margin) }}</template>
        </el-table-column>
        <el-table-column prop="net_margin" label="净利率" width="100">
          <template #default="{ row }">{{ ratioDisplay(row.net_margin) }}</template>
        </el-table-column>
        <el-table-column prop="roi" label="ROI" width="100">
          <template #default="{ row }">{{ ratioDisplay(row.roi) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import dashboardApi from '@/api/dashboard'
import { handleApiError } from '@/utils/errorHandler'

const loading = ref(false)
const loadingExtension = ref(false)
const granularity = ref('monthly')
const trendChartRef = ref(null)
const platformShareChartRef = ref(null)
const trendData = ref([])
const platformShareData = ref([])
const targetCompletion = ref({
  target_gmv: 0,
  achieved_gmv: null,
  achievement_rate_gmv: null,
  target_orders: 0,
  target_profit: null,
  achieved_profit: null,
  achievement_rate_profit: null,
})
const byShopList = ref([])
const periodMonth = ref(
  (() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })()
)
const periodYear = ref(String(new Date().getFullYear()))

const period = computed(() => {
  const p = granularity.value === 'monthly' ? periodMonth.value : periodYear.value
  return p != null ? String(p) : ''
})

const kpiData = ref([
  { key: 'conversion_rate', title: '转化率', value: '0.00%', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'traffic', title: '客流量', value: '0', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'avg_order_value', title: '客单价', value: '0.00', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'gmv', title: 'GMV', value: '0.00', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'order_count', title: '订单数', value: '0', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'attach_rate', title: '连带率', value: '0.00', change: '较上月 0.00%', changeType: 'neutral' },
  { key: 'labor_efficiency', title: '人效', value: '0.00', change: '较上月 0.00%', changeType: 'neutral' },
])

const costData = ref([
  { key: 'total_cost', title: '总成本', value: '0.00', sub: '' },
  { key: 'gmv_out', title: 'GMV（产出）', value: '0.00', sub: '' },
  { key: 'cost_to_revenue_ratio', title: '成本产出比', value: '0.00%', sub: '总成本/GMV' },
  { key: 'roi', title: 'ROI', value: '0.00%', sub: '(GMV-总成本)/总成本' },
  { key: 'gross_margin', title: '毛利率', value: '0.00%', sub: '(GMV-COGS)/GMV' },
  { key: 'net_margin', title: '净利率', value: '0.00%', sub: '(GMV-总成本)/GMV' },
])

function formatChange(num) {
  if (num === null || num === undefined) return '0.00%'
  const n = Number(num)
  if (Number.isNaN(n)) return '0.00%'
  const prefix = n > 0 ? '+' : ''
  return `${prefix}${n.toFixed(2)}%`
}

function getChangeType(num) {
  if (num === null || num === undefined) return 'neutral'
  const n = Number(num)
  if (Number.isNaN(n)) return 'neutral'
  return n > 0 ? 'up' : n < 0 ? 'down' : 'neutral'
}

function formatInteger(n) {
  if (n === null || n === undefined) return '0'
  const num = Number(n)
  return Number.isNaN(num) ? '0' : num.toLocaleString()
}

function formatCurrency(n) {
  if (n === null || n === undefined) return '0.00'
  const num = Number(n)
  if (Number.isNaN(num)) return '0.00'
  if (num >= 1e8) return (num / 1e8).toFixed(2) + '亿'
  if (num >= 1e4) return (num / 1e4).toFixed(2) + '万'
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ratioDisplay(val) {
  if (val === null || val === undefined) return '0.00%'
  const num = Number(val)
  if (Number.isNaN(num)) return '0.00%'
  return (num * 100).toFixed(2) + '%'
}

function ratioDisplayStrict(val) {
  if (val === null || val === undefined) return '0.00%'
  const num = Number(val)
  if (Number.isNaN(num)) return '0.00%'
  return (num * 100).toFixed(2) + '%'
}

function onGranularityChange() {
  loadData()
}

async function loadData() {
  if (!period.value) return
  loading.value = true
  try {
    const res = await dashboardApi.queryAnnualSummaryKpi({
      granularity: granularity.value,
      period: period.value,
    })
    const data = res?.data || res
    if (!data) return

    const formatChangeVal = (v) => formatChange(v)
    const getType = (v) => getChangeType(v)

    const cmpLabel = granularity.value === 'monthly' ? '较上月 ' : '较去年 '
    kpiData.value[0].value = data.conversion_rate != null ? `${Number(data.conversion_rate).toFixed(2)}%` : '0.00%'
    kpiData.value[0].change = cmpLabel + formatChangeVal(data.conversion_rate_change)
    kpiData.value[0].changeType = getType(data.conversion_rate_change)

    const visitorCount = data.visitor_count ?? data.traffic?.current
    kpiData.value[1].value = visitorCount != null ? formatInteger(visitorCount) : '0'
    kpiData.value[1].change = cmpLabel + formatChangeVal(data.visitor_count_change)
    kpiData.value[1].changeType = getType(data.visitor_count_change)

    const aov = data.avg_order_value ?? data.average_order_value?.current
    kpiData.value[2].value = aov != null ? formatCurrency(aov) : '0.00'
    kpiData.value[2].change = cmpLabel + formatChangeVal(data.avg_order_value_change)
    kpiData.value[2].changeType = getType(data.avg_order_value_change)

    kpiData.value[3].value = data.gmv != null ? formatCurrency(data.gmv) : '0.00'
    kpiData.value[3].change = cmpLabel + formatChangeVal(data.gmv_change)
    kpiData.value[3].changeType = getType(data.gmv_change)

    kpiData.value[4].value = data.order_count != null ? formatInteger(data.order_count) : '0'
    kpiData.value[4].change = cmpLabel + formatChangeVal(data.order_count_change)
    kpiData.value[4].changeType = getType(data.order_count_change)

    const attachRate = data.attach_rate ?? data.attach_rate_obj?.current
    kpiData.value[5].value = attachRate != null ? Number(attachRate).toFixed(2) : '0.00'
    kpiData.value[5].change = cmpLabel + formatChangeVal(data.attach_rate_change ?? data.attach_rate_obj?.change)
    kpiData.value[5].changeType = getType(data.attach_rate_change ?? data.attach_rate_obj?.change)

    const laborEff = data.labor_efficiency ?? data.labor_efficiency_obj?.current
    kpiData.value[6].value = laborEff != null ? formatCurrency(laborEff) : '0.00'
    kpiData.value[6].change = cmpLabel + formatChangeVal(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)
    kpiData.value[6].changeType = getType(data.labor_efficiency_change ?? data.labor_efficiency_obj?.change)

    costData.value[0].value = data.total_cost != null ? formatCurrency(data.total_cost) : '0.00'
    costData.value[0].sub = ''
    costData.value[1].value = data.gmv != null ? formatCurrency(data.gmv) : '0.00'
    costData.value[1].sub = ''
    costData.value[2].value = data.cost_to_revenue_ratio != null ? ratioDisplayStrict(data.cost_to_revenue_ratio) : (data.gmv === 0 || data.gmv == null ? 'N/A' : '0.00%')
    costData.value[2].sub = '总成本/GMV'
    costData.value[3].value = data.roi != null ? ratioDisplayStrict(data.roi) : (data.total_cost === 0 || data.total_cost == null ? 'N/A' : '0.00%')
    costData.value[3].sub = '(GMV-总成本)/总成本'
    costData.value[4].value = data.gross_margin != null ? ratioDisplayStrict(data.gross_margin) : '0.00%'
    costData.value[4].sub = '(GMV-COGS)/GMV'
    costData.value[5].value = data.net_margin != null ? ratioDisplayStrict(data.net_margin) : '0.00%'
    costData.value[5].sub = '(GMV-总成本)/GMV'
    loadExtensionData()
  } catch (err) {
    handleApiError(err, { showMessage: true, logError: true })
  } finally {
    loading.value = false
  }
}

function unwrapList(res) {
  if (Array.isArray(res)) return res
  if (res && Array.isArray(res.data)) return res.data
  return []
}

function unwrapTarget(res) {
  const o = res?.data ?? res
  return o && typeof o === 'object' ? o : {}
}

async function loadExtensionData() {
  if (!period.value) return
  loadingExtension.value = true
  const params = { granularity: granularity.value, period: period.value }
  const [byShopResult, trendResult, shareResult, targetResult] = await Promise.allSettled([
    dashboardApi.queryAnnualSummaryByShop(params),
    dashboardApi.queryAnnualSummaryTrend(params),
    dashboardApi.queryAnnualSummaryPlatformShare(params),
    dashboardApi.queryAnnualSummaryTargetCompletion(params),
  ])
  byShopList.value = byShopResult.status === 'fulfilled' ? unwrapList(byShopResult.value) : []
  trendData.value = trendResult.status === 'fulfilled' ? unwrapList(trendResult.value) : []
  platformShareData.value = shareResult.status === 'fulfilled' ? unwrapList(shareResult.value) : []
  const tc = targetResult.status === 'fulfilled' ? unwrapTarget(targetResult.value) : {}
  targetCompletion.value = {
    target_gmv: tc.target_gmv ?? 0,
    achieved_gmv: tc.achieved_gmv ?? null,
    achievement_rate_gmv: tc.achievement_rate_gmv ?? null,
    target_orders: tc.target_orders ?? 0,
    target_profit: tc.target_profit ?? null,
    achieved_profit: tc.achieved_profit ?? null,
    achievement_rate_profit: tc.achievement_rate_profit ?? null,
  }
  if (trendResult.status === 'rejected') {
    handleApiError(trendResult.reason, { showMessage: false, logError: true })
  }
  if (shareResult.status === 'rejected') {
    handleApiError(shareResult.reason, { showMessage: false, logError: true })
  }
  try {
    await nextTick()
    renderTrendChart()
    renderPlatformShareChart()
  } finally {
    loadingExtension.value = false
  }
}

function renderTrendChart() {
  const el = trendChartRef.value
  if (!el) return
  let chart = echarts.getInstanceByDom(el)
  if (chart) chart.dispose()
  chart = echarts.init(el)
  const raw = trendData.value
  const months = raw.length ? raw.map((d) => d.month || d.period_month || d.label || '') : [period.value || '0']
  const gmvSeries = raw.length ? raw.map((d) => d.gmv ?? 0) : [0]
  const costSeries = raw.length ? raw.map((d) => d.total_cost ?? 0) : [0]
  const profitSeries = raw.length ? raw.map((d) => (d.profit ?? (d.gmv - (d.total_cost || 0)))) : [0]
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['GMV', '总成本', '利润'], bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
    xAxis: { type: 'category', data: months },
    yAxis: { type: 'value', name: '元' },
    series: [
      { name: 'GMV', type: 'line', data: gmvSeries, smooth: true },
      { name: '总成本', type: 'line', data: costSeries, smooth: true },
      { name: '利润', type: 'line', data: profitSeries, smooth: true },
    ],
  })
  setTimeout(() => chart.resize(), 50)
}

function renderPlatformShareChart() {
  const el = platformShareChartRef.value
  if (!el) return
  let chart = echarts.getInstanceByDom(el)
  if (chart) chart.dispose()
  chart = echarts.init(el)
  const raw = platformShareData.value
  const data = raw.length
    ? raw.map((d) => ({ name: d.platform || d.name || d.label || '0', value: Number(d.gmv ?? d.value ?? 0) }))
    : [{ name: '暂无数据', value: 1 }]
  chart.setOption({
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left' },
    series: [{ type: 'pie', radius: '60%', data, label: { formatter: '{b}: {d}%' } }],
  })
  setTimeout(() => chart.resize(), 50)
}

onMounted(() => {
  loadData()
})

watch([period, granularity], () => {
  loadExtensionData()
})
</script>

<style scoped>
.annual-summary {
  padding: 20px;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-size: 24px;
  margin: 0 0 8px 0;
}
.page-subtitle {
  color: #909399;
  margin: 0;
  font-size: 14px;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.filter-label {
  color: #606266;
  font-size: 14px;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 24px 0 12px 0;
  color: #303133;
}
.section-title:first-of-type {
  margin-top: 0;
}
.kpi-section,
.cost-section {
  margin-bottom: 16px;
}
.kpi-cards-row,
.cost-cards-row {
  margin-bottom: 0;
}
.kpi-card,
.cost-card {
  margin-bottom: 16px;
}
.kpi-content,
.kpi-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kpi-title,
.cost-title {
  font-size: 14px;
  color: #909399;
}
.kpi-value,
.cost-value {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.kpi-change {
  font-size: 12px;
}
.kpi-change.up {
  color: #67c23a;
}
.kpi-change.down {
  color: #f56c6c;
}
.kpi-change.neutral {
  color: #909399;
}
.cost-sub {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.ext-section {
  margin-bottom: 24px;
}
.chart-container {
  width: 100%;
  min-height: 200px;
}
.chart-pie {
  max-width: 400px;
}
.empty-tip {
  color: #909399;
  font-size: 14px;
  padding: 16px 0;
  text-align: center;
}
.target-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 480px;
}
.target-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.target-label {
  width: 90px;
  font-size: 14px;
  color: #606266;
}
</style>
