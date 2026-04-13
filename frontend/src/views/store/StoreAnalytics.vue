<template>
  <div class="store-analysis erp-page-container erp-page--dashboard">
    <PageHeader
      title="店铺分析"
      subtitle="按店铺查看流量、访问和转化表现，Shopee 支持日视图小时级下钻，TikTok 当前保留日级能力。"
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
        <el-select v-model="filters.platform" placeholder="选择平台" class="control-w-140" @change="handlePlatformChange">
          <el-option label="Shopee" value="shopee" />
          <el-option label="TikTok" value="tiktok" />
        </el-select>
        <el-input
          v-model="filters.shopId"
          placeholder="输入店铺ID"
          class="control-w-220"
          clearable
          @keyup.enter="reloadAll"
        />
        <el-select v-model="filters.granularity" placeholder="选择视图" class="control-w-140">
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

    <div class="kpi-grid" v-loading="loadingSummary">
      <el-card v-for="item in summaryCards" :key="item.key" class="kpi-card" shadow="hover">
        <div class="kpi-label">{{ item.label }}</div>
        <div class="kpi-value">{{ item.value }}</div>
      </el-card>
    </div>

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
        <el-table-column prop="conversion_rate" label="转化率" width="140" align="right">
          <template #default="{ row }">
            {{ formatPercent(row.conversion_rate) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import dashboardApi from '@/api/dashboard'
import { formatInteger, formatPercent } from '@/utils/dataFormatter'
import { handleApiError } from '@/utils/errorHandler'

const today = new Date().toISOString().slice(0, 10)

const filters = reactive({
  platform: 'shopee',
  shopId: '',
  granularity: 'daily',
  date: today
})

const loading = ref(false)
const loadingSummary = ref(false)
const loadingTrend = ref(false)

const capability = ref(null)
const summary = ref({
  visitor_count: null,
  page_views: null,
  conversion_rate: null,
  page_views_per_visitor: null
})
const trend = ref({
  requested_granularity: 'daily',
  effective_granularity: 'daily',
  items: []
})

const canQuery = computed(() => Boolean(filters.platform && filters.shopId && filters.date))

const showDailyFallbackHint = computed(() => {
  return (
    capability.value &&
    filters.granularity === 'daily' &&
    capability.value.supports_hourly_daily === false
  )
})

const granularityOptions = computed(() => {
  const options = [
    { value: 'daily', label: '日视图' },
    { value: 'weekly', label: '周视图' },
    { value: 'monthly', label: '月视图' },
    { value: 'quarterly', label: '季度视图' },
    { value: 'yearly', label: '年度视图' }
  ]
  return options
})

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
  { key: 'visitor_count', label: '访客数', value: formatInteger(summary.value.visitor_count) },
  { key: 'page_views', label: '浏览量', value: formatInteger(summary.value.page_views) },
  { key: 'conversion_rate', label: '转化率', value: formatPercent(summary.value.conversion_rate) },
  {
    key: 'page_views_per_visitor',
    label: '人均浏览页数',
    value: summary.value.page_views_per_visitor == null ? '-' : Number(summary.value.page_views_per_visitor).toFixed(2)
  }
])

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

async function loadSummary() {
  if (!canQuery.value) {
    summary.value = {
      visitor_count: null,
      page_views: null,
      conversion_rate: null,
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
      conversion_rate: null,
      page_views_per_visitor: null
    }
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingSummary.value = false
  }
}

async function loadTrend() {
  if (!canQuery.value) {
    trend.value = {
      requested_granularity: filters.granularity,
      effective_granularity: capability.value?.supported_daily_mode || 'daily',
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
  } catch (error) {
    trend.value = {
      requested_granularity: filters.granularity,
      effective_granularity: capability.value?.supported_daily_mode || 'daily',
      items: []
    }
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingTrend.value = false
  }
}

async function reloadAll() {
  if (!canQuery.value) {
    ElMessage.warning('请先选择平台、输入店铺ID并选择日期')
    return
  }
  loading.value = true
  await loadCapabilities()
  await Promise.all([loadSummary(), loadTrend()])
  loading.value = false
}

function handlePlatformChange() {
  capability.value = null
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
</script>

<style scoped>
.store-analysis {
  background-color: #f5f7fa;
  min-height: calc(100vh - var(--header-height));
}

.filter-card,
.trend-card {
  border: none;
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
