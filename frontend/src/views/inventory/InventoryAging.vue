<template>
  <div class="inventory-age-page">
    <h1 class="page-title">库存库龄</h1>

    <el-card class="filters-card">
      <el-form :inline="true" class="filters-form">
        <el-form-item label="平台">
          <el-input
            v-model="filters.platform"
            clearable
            placeholder="如 miaoshou"
          />
        </el-form-item>
        <el-form-item label="SKU">
          <el-input
            v-model="filters.platform_sku"
            clearable
            placeholder="输入 SKU 或 SKU Key"
          />
        </el-form-item>
        <el-form-item label="重置原因">
          <el-select v-model="filters.reset_reason" clearable placeholder="全部原因" style="width: 180px">
            <el-option label="首次有库存" value="first_positive" />
            <el-option label="归零后恢复" value="reappeared_after_zero" />
            <el-option label="库存增加重置" value="stock_increase" />
            <el-option label="延续上次库龄" value="continued" />
          </el-select>
        </el-form-item>
        <el-form-item label="库龄区间">
          <el-select v-model="filters.bucket" clearable placeholder="全部区间" style="width: 150px">
            <el-option label="0-30" value="0-30" />
            <el-option label="31-60" value="31-60" />
            <el-option label="61-90" value="61-90" />
            <el-option label="91-180" value="91-180" />
            <el-option label="180+" value="180+" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="filters.onlyHighAge">只看高库龄(>=61天)</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="filters.onlyRecentReset">只看最近重置</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="reload">查询</el-button>
        </el-form-item>
        <el-form-item>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" class="summary-row">
      <el-col :span="8">
        <el-card>
          <el-statistic title="有库存 SKU 数" :value="summary.total_sku_count" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="总库存数量" :value="summary.total_quantity" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic
            title="总库存金额"
            :value="summary.total_value"
            prefix="¥"
            :precision="2"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="7">
        <el-card>
          <template #header>库龄分布</template>
          <el-table :data="summary.buckets" size="small" stripe>
            <el-table-column prop="bucket" label="区间" width="100" />
            <el-table-column prop="sku_count" label="SKU 数" width="90" />
            <el-table-column prop="quantity" label="数量" width="90" />
            <el-table-column prop="inventory_value" label="金额" min-width="120">
              <template #default="{ row }">
                ¥{{ Number(row.inventory_value || 0).toFixed(2) }}
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :span="17">
        <el-card>
          <template #header>SKU 连续库龄明细</template>
          <el-table :data="filteredRows" v-loading="loading" stripe>
            <el-table-column prop="platform_code" label="平台" width="110" />
            <el-table-column label="SKU" min-width="190">
              <template #default="{ row }">
                <div class="sku-cell">
                  <div class="sku-primary">{{ row.platform_sku || row.sku_key }}</div>
                  <div v-if="row.product_sku && row.product_sku !== row.platform_sku" class="sku-secondary">
                    {{ row.product_sku }}
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="product_name" label="商品名称" min-width="240" show-overflow-tooltip />
            <el-table-column prop="current_qty" label="当前库存" width="100" />
            <el-table-column prop="age_days" label="库龄天数" width="100" />
            <el-table-column label="起算日期" width="120">
              <template #default="{ row }">
                {{ formatDate(row.age_anchor_date) }}
              </template>
            </el-table-column>
            <el-table-column label="重置原因" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="tagType(row.reset_reason)">
                  {{ resetReasonLabel(row.reset_reason) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="bucket" label="区间" width="90" />
            <el-table-column label="快照日期" width="120">
              <template #default="{ row }">
                {{ formatDate(row.snapshot_date) }}
              </template>
            </el-table-column>
            <el-table-column prop="inventory_value" label="库存金额" min-width="120">
              <template #default="{ row }">
                ¥{{ Number(row.inventory_value || 0).toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="110" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openHistory(row)">查看轨迹</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-drawer
      v-model="historyDrawer.visible"
      size="50%"
      :title="historyDrawer.title"
      destroy-on-close
    >
      <div class="history-drawer">
        <div class="history-summary-grid">
          <el-card shadow="never">
            <el-statistic title="当前库存" :value="historyDrawer.currentQty" />
          </el-card>
          <el-card shadow="never">
            <el-statistic title="当前库龄" :value="historyDrawer.currentAgeDays" suffix="天" />
          </el-card>
          <el-card shadow="never">
            <el-statistic title="轨迹点数" :value="historyDrawer.rows.length" />
          </el-card>
        </div>

        <div ref="historyChartEl" class="history-chart"></div>

        <el-table :data="historyDrawer.rows" v-loading="historyDrawer.loading" stripe>
          <el-table-column label="快照日期" width="120">
            <template #default="{ row }">{{ formatDate(row.snapshot_date) }}</template>
          </el-table-column>
          <el-table-column prop="current_qty" label="库存数量" width="100" />
          <el-table-column prop="qty_delta" label="数量变化" width="100" />
          <el-table-column prop="age_days" label="库龄天数" width="100" />
          <el-table-column label="起算日期" width="120">
            <template #default="{ row }">{{ formatDate(row.age_anchor_date) }}</template>
          </el-table-column>
          <el-table-column label="重置原因" width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="tagType(row.reset_reason)">
                {{ resetReasonLabel(row.reset_reason) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="bucket" label="区间" width="90" />
          <el-table-column prop="inventory_value" label="库存金额" min-width="120">
            <template #default="{ row }">
              ¥{{ Number(row.inventory_value || 0).toFixed(2) }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import echarts from '@/utils/echarts'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])
const historyChartEl = ref(null)
let historyChart = null
const summary = reactive({
  rows: [],
  buckets: [],
  total_sku_count: 0,
  total_quantity: 0,
  total_value: 0
})
const filters = reactive({
  platform: '',
  platform_sku: '',
  reset_reason: '',
  bucket: '',
  onlyHighAge: false,
  onlyRecentReset: false
})
const historyDrawer = reactive({
  visible: false,
  loading: false,
  title: 'SKU 轨迹',
  rows: [],
  currentQty: 0,
  currentAgeDays: 0,
  currentSku: '',
  currentPlatform: ''
})

const resetReasonLabel = (reason) => {
  switch (reason) {
    case 'first_positive':
      return '首次有库存'
    case 'reappeared_after_zero':
      return '归零后恢复'
    case 'stock_increase':
      return '库存增加重置'
    case 'continued':
      return '延续上次库龄'
    default:
      return reason || '未知'
  }
}

const tagType = (reason) => {
  switch (reason) {
    case 'stock_increase':
    case 'first_positive':
    case 'reappeared_after_zero':
      return 'success'
    case 'continued':
      return 'warning'
    default:
      return 'info'
  }
}

const formatDate = (value) => {
  if (!value) return '-'
  return String(value).slice(0, 10)
}

const filteredRows = computed(() => {
  return rows.value.filter((row) => {
    if (filters.reset_reason && row.reset_reason !== filters.reset_reason) return false
    if (filters.bucket && row.bucket !== filters.bucket) return false
    if (filters.onlyHighAge && Number(row.age_days || 0) < 61) return false
    if (filters.onlyRecentReset && !['stock_increase', 'first_positive', 'reappeared_after_zero'].includes(row.reset_reason)) return false
    return true
  })
})

const buildHistoryChart = async () => {
  if (!historyDrawer.visible || !historyChartEl.value || historyDrawer.rows.length === 0) return
  await nextTick()

  if (!historyChart) {
    historyChart = echarts.init(historyChartEl.value)
  }

  const labels = historyDrawer.rows.map((row) => formatDate(row.snapshot_date))
  const qtySeries = historyDrawer.rows.map((row) => Number(row.current_qty || 0))
  const ageSeries = historyDrawer.rows.map((row) => Number(row.age_days || 0))

  historyChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['库存数量', '库龄天数'] },
    grid: { left: 48, right: 32, top: 44, bottom: 32 },
    xAxis: {
      type: 'category',
      data: labels
    },
    yAxis: [
      {
        type: 'value',
        name: '库存数量'
      },
      {
        type: 'value',
        name: '库龄天数'
      }
    ],
    series: [
      {
        name: '库存数量',
        type: 'line',
        smooth: true,
        data: qtySeries,
        lineStyle: { width: 3, color: '#2563eb' },
        itemStyle: { color: '#2563eb' }
      },
      {
        name: '库龄天数',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: ageSeries,
        lineStyle: { width: 3, color: '#f97316' },
        itemStyle: { color: '#f97316' }
      }
    ]
  })
}

const openHistory = async (row) => {
  historyDrawer.visible = true
  historyDrawer.loading = true
  historyDrawer.title = `SKU 轨迹: ${row.platform_sku || row.sku_key}`
  historyDrawer.currentQty = Number(row.current_qty || 0)
  historyDrawer.currentAgeDays = Number(row.age_days || 0)
  historyDrawer.currentSku = row.platform_sku || row.sku_key
  historyDrawer.currentPlatform = row.platform_code
  historyDrawer.rows = []

  try {
    historyDrawer.rows = await inventoryDomainApi.getAgingHistory({
      platform: row.platform_code,
      platform_sku: row.platform_sku || row.sku_key
    })
    await buildHistoryChart()
  } catch (error) {
    ElMessage.error('加载 SKU 库龄轨迹失败')
  } finally {
    historyDrawer.loading = false
  }
}

const resetFilters = () => {
  filters.platform = ''
  filters.platform_sku = ''
  filters.reset_reason = ''
  filters.bucket = ''
  filters.onlyHighAge = false
  filters.onlyRecentReset = false
}

const reload = async () => {
  loading.value = true
  try {
    const params = {
      platform: filters.platform || undefined,
      platform_sku: filters.platform_sku || undefined
    }
    rows.value = await inventoryDomainApi.getAging(params)
    const response = await inventoryDomainApi.getAgingBuckets(params)
    Object.assign(summary, response)
  } catch (error) {
    ElMessage.error('加载库存库龄失败')
  } finally {
    loading.value = false
  }
}

onMounted(reload)

watch(
  () => historyDrawer.visible,
  async (visible) => {
    if (visible && historyDrawer.rows.length > 0) {
      await buildHistoryChart()
      return
    }
    if (!visible && historyChart) {
      historyChart.dispose()
      historyChart = null
    }
  }
)

onBeforeUnmount(() => {
  if (historyChart) {
    historyChart.dispose()
    historyChart = null
  }
})
</script>

<style scoped>
.inventory-age-page {
  padding: 20px;
}

.page-title {
  margin-bottom: 20px;
  font-size: 24px;
  font-weight: 700;
}

.filters-card,
.summary-row {
  margin-bottom: 20px;
}

.filters-form {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 0;
}

.sku-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sku-primary {
  font-weight: 600;
  color: #1f2937;
}

.sku-secondary {
  color: #6b7280;
  font-size: 12px;
}

.history-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.history-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.history-chart {
  width: 100%;
  height: 280px;
  border-radius: 12px;
  background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
}
</style>
