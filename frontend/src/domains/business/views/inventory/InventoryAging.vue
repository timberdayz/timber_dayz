<template>
  <div class="inventory-age-page">
    <h1 class="page-title">库存库龄</h1>

    <el-tabs v-model="activeTab" class="inventory-age-tabs" @tab-change="handleTabChange">
      <!-- ==================== 页签一：库龄明细 ==================== -->
      <el-tab-pane label="库龄明细" name="aging">
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
                <el-option label="首次有货" value="first_positive" />
                <el-option label="卖空重现" value="reappeared_after_zero" />
                <el-option label="补货归零" value="stock_increase" />
                <el-option label="持续累加" value="continued" />
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
      </el-tab-pane>

      <!-- ==================== 页签二：滞销清单 ==================== -->
      <el-tab-pane label="滞销清单" name="clearance">
        <el-card class="filters-card">
          <el-form :inline="true" class="filters-form">
            <el-form-item label="距上次进货天数下限">
              <el-input-number
                v-model="clearanceFilters.min_restock_days"
                :min="0"
                :max="3650"
                :step="30"
                controls-position="right"
                style="width: 130px"
              />
            </el-form-item>
            <el-form-item label="距上次进货天数上限">
              <el-input-number
                v-model="clearanceFilters.max_restock_days"
                :min="0"
                :max="3650"
                :step="30"
                controls-position="right"
                placeholder="不限"
                style="width: 130px"
              />
            </el-form-item>
            <el-form-item label="平台">
              <el-input
                v-model="clearanceFilters.platform_code"
                clearable
                placeholder="如 miaoshou"
                style="width: 140px"
              />
            </el-form-item>
            <el-form-item label="关键词">
              <el-input
                v-model="clearanceFilters.keyword"
                clearable
                placeholder="SKU 或商品名"
                style="width: 180px"
              />
            </el-form-item>
            <el-form-item label="排序">
              <el-select v-model="clearanceFilters.sort_by" style="width: 150px">
                <el-option label="距上次进货天数" value="days_since_restock" />
                <el-option label="库存金额" value="inventory_value" />
                <el-option label="在库数量" value="current_qty" />
              </el-select>
            </el-form-item>
            <el-form-item label="方向">
              <el-select v-model="clearanceFilters.sort_order" style="width: 100px">
                <el-option label="降序" value="desc" />
                <el-option label="升序" value="asc" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="queryClearance">查询</el-button>
            </el-form-item>
            <el-form-item>
              <el-button @click="resetClearanceFilters">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-row :gutter="20" class="summary-row">
          <el-col :span="6">
            <el-card>
              <el-statistic title="滞销 SKU 数" :value="clearanceSummary.sku_count" />
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card>
              <el-statistic
                title="压资金额"
                :value="clearanceSummary.total_inventory_value"
                prefix="¥"
                :precision="2"
              />
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card>
              <el-statistic title="在库数量" :value="clearanceSummary.total_quantity" />
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card>
              <el-statistic title="重度积压数" :value="clearanceDeepTierCount" />
            </el-card>
          </el-col>
        </el-row>

        <el-alert
          v-if="clearanceSummary.missing_reference_price_count > 0"
          type="warning"
          show-icon
          :closable="false"
          class="clearance-gap-alert"
          :title="`${clearanceSummary.missing_reference_price_count} 个 SKU 缺参考售价，无法计算清货回款`"
        />

        <el-row :gutter="20" class="distribution-row">
          <el-col :span="24">
            <el-card>
              <template #header>滞销档位分布（门槛来自档位表）</template>
              <div v-for="item in clearanceTierDistribution" :key="item.key" class="distribution-row-item">
                <span class="distribution-label distribution-label-wide">{{ item.label }}</span>
                <div class="distribution-track">
                  <div
                    class="distribution-fill"
                    :style="{ width: item.percent + '%', backgroundColor: '#2563eb' }"
                  />
                </div>
                <span class="distribution-value">
                  {{ item.count }} SKU · ¥{{ item.value.toFixed(2) }}
                </span>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card class="clearance-detail-card">
          <template #header>SKU 级滞销明细</template>
          <el-table :data="clearanceRows" v-loading="clearanceLoading" stripe>
            <el-table-column prop="days_since_restock" label="距上次进货天数" width="120" align="right" />
            <el-table-column prop="platform_code" label="平台" width="100" />
            <el-table-column prop="product_sku" label="SKU" width="150" show-overflow-tooltip />
            <el-table-column prop="product_name" label="商品名" min-width="220" show-overflow-tooltip />
            <el-table-column prop="current_qty" label="可用库存" width="100" align="right" />
            <el-table-column label="库存金额" width="120" align="right">
              <template #default="{ row }">
                {{ formatMoney(row.inventory_value) }}
              </template>
            </el-table-column>
            <el-table-column prop="checklist_dos_sales90" label="可售天数（参考）" width="130" align="right">
              <template #default="{ row }">
                <el-tooltip
                  content="按最近一次采集到的近90天销量估算；分母只在那一行被写入时才刷新，不是实时动销速度，仅供参考"
                  placement="top"
                >
                  <span>{{ row.checklist_dos_sales90 ?? '-' }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="档位" width="110">
              <template #default="{ row }">
                <el-tag v-if="!row.pricing_matched_erp" size="small" type="info">未匹配主数据</el-tag>
                <span v-else>{{ row.pricing_tier_label || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="当前可优惠" width="110" align="right">
              <template #default="{ row }">
                {{ formatPercent(row.current_discount_rate) }}
              </template>
            </el-table-column>
            <el-table-column label="最低售价" width="120" align="right">
              <template #default="{ row }">
                <div class="sku-cell">
                  <div class="sku-primary">{{ formatMoney(row.min_selling_price) }}</div>
                  <div class="sku-secondary">{{ minSellingPriceSourceLabel(row.min_selling_price_source) }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="清货回款" width="130" align="right">
              <template #default="{ row }">
                <span
                  v-if="row.clearance_recovery_amount === null || row.clearance_recovery_amount === undefined"
                  class="missing-price-hint"
                >缺参考售价</span>
                <span v-else>{{ formatMoney(row.clearance_recovery_amount) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="clearance-pagination">
            <el-pagination
              v-model:current-page="clearanceCurrentPage"
              v-model:page-size="clearancePageSize"
              :total="clearanceTotal"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @size-change="handleClearanceSizeChange"
              @current-change="handleClearancePageChange"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

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

const activeTab = ref('aging')

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

// ------------------------------------------------------------------
// 滞销清单（SKU 级，主判据 = 距上次进货天数）
// ------------------------------------------------------------------
const clearanceLoading = ref(false)
const clearanceLoaded = ref(false)
const clearanceRows = ref([])
const clearanceTotal = ref(0)
const clearanceCurrentPage = ref(1)
const clearancePageSize = ref(50)
const clearanceSummary = reactive({
  sku_count: 0,
  total_quantity: 0,
  total_inventory_value: 0,
  // 分档统计：门槛 / 档位名 / SKU 数 / 压资金额（门槛与档位名由后端按档位表给出）
  restock_tiers: [],
  missing_reference_price_count: 0
})
const clearanceFilters = reactive({
  // 默认 60：与后端接口默认值一致，也就是档位表第一个滞销门槛。
  // 低于这个门槛的 SKU 属于「日常档」，本就不该出现在滞销清单里。
  min_restock_days: 60,
  max_restock_days: null,
  platform_code: '',
  keyword: '',
  sort_by: 'days_since_restock',
  sort_order: 'desc'
})
const clearancePage = reactive({
  limit: 50,
  offset: 0
})

const resetReasonLabel = (reason) => {
  switch (reason) {
    case 'first_positive':
      return '首次有货'
    case 'reappeared_after_zero':
      return '卖空重现'
    case 'stock_increase':
      return '补货归零'
    case 'zero_stock':
      return '库存归零'
    case 'continued':
      return '持续累加'
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

const formatMoney = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `¥${num.toFixed(2)}`
}

const formatPercent = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return `${Number((num * 100).toFixed(2))}%`
}

const minSellingPriceSourceLabel = (source) => {
  switch (source) {
    case 'manual_override':
      return '人工覆盖'
    case 'cost_floor':
      return '成本底线'
    case 'discount_guard':
      return '折扣护栏'
    case 'unavailable':
      return '无法计算'
    default:
      return ''
  }
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

// 分档统计：门槛与档位名都由后端按档位表给出，前端不硬编码任何门槛数字
const clearanceTierList = computed(() => {
  const tiers = Array.isArray(clearanceSummary.restock_tiers) ? clearanceSummary.restock_tiers : []
  return tiers.map((tier) => ({
    label: `${tier.tier_label || '-'}（≥${tier.min_restock_days}天）`,
    minRestockDays: Number(tier.min_restock_days || 0),
    count: Number(tier.sku_count || 0),
    value: Number(tier.inventory_value || 0)
  }))
})

const clearanceTierDistribution = computed(() => {
  const items = clearanceTierList.value
  const max = Math.max(...items.map((item) => item.count), 1)
  return items.map((item) => ({
    ...item,
    key: item.label,
    percent: Math.round((item.count / max) * 100)
  }))
})

// 最深一档 = 重度积压（档位表门槛最高的那一档）
const clearanceDeepTierCount = computed(() => {
  const items = clearanceTierList.value
  if (items.length === 0) return 0
  const deepest = items.reduce((acc, item) => (item.minRestockDays > acc.minRestockDays ? item : acc))
  return Number(deepest.count || 0)
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

const reloadClearance = async () => {
  clearanceLoading.value = true
  try {
    const response = await inventoryDomainApi.getClearanceRanking({
      min_restock_days: clearanceFilters.min_restock_days,
      max_restock_days: clearanceFilters.max_restock_days ?? undefined,
      platform_code: clearanceFilters.platform_code || undefined,
      keyword: clearanceFilters.keyword || undefined,
      sort_by: clearanceFilters.sort_by,
      sort_order: clearanceFilters.sort_order,
      limit: clearancePage.limit,
      offset: clearancePage.offset
    })
    clearanceRows.value = response.items || []
    Object.assign(clearanceSummary, response.summary || {})
    clearanceTotal.value = Number(response.total || 0)
    clearanceLoaded.value = true
  } catch (error) {
    ElMessage.error('加载滞销清单失败')
  } finally {
    clearanceLoading.value = false
  }
}

const queryClearance = async () => {
  clearancePage.offset = 0
  clearanceCurrentPage.value = 1
  await reloadClearance()
}

const resetClearanceFilters = async () => {
  Object.assign(clearanceFilters, {
    min_restock_days: 60,
    max_restock_days: null,
    platform_code: '',
    keyword: '',
    sort_by: 'days_since_restock',
    sort_order: 'desc'
  })
  clearancePage.offset = 0
  clearanceCurrentPage.value = 1
  await reloadClearance()
}

const handleClearancePageChange = async (page) => {
  clearanceCurrentPage.value = page
  clearancePage.offset = (page - 1) * clearancePageSize.value
  await reloadClearance()
}

const handleClearanceSizeChange = async (size) => {
  clearancePageSize.value = size
  clearancePage.limit = size
  clearancePage.offset = (clearanceCurrentPage.value - 1) * size
  await reloadClearance()
}

// 首次切到滞销清单页签时才拉数据，避免每次进页面都多打一枪查询
const handleTabChange = async (name) => {
  if (name === 'clearance' && !clearanceLoaded.value) {
    await reloadClearance()
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

.inventory-age-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.filters-card,
.summary-row,
.distribution-row {
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

.clearance-gap-alert {
  margin-bottom: 20px;
}

.distribution-row-item {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.distribution-label {
  width: 64px;
  flex-shrink: 0;
  font-size: 13px;
  color: #374151;
}

.distribution-label-wide {
  width: 200px;
}

.distribution-track {
  flex: 1;
  height: 10px;
  border-radius: 999px;
  background: #f1f5f9;
  overflow: hidden;
}

.distribution-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.25s ease;
}

.distribution-value {
  width: 72px;
  flex-shrink: 0;
  text-align: right;
  font-size: 13px;
  color: #6b7280;
}

.clearance-detail-card {
  margin-bottom: 20px;
}

.missing-price-hint {
  color: #d97706;
  font-size: 12px;
}

.clearance-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
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
