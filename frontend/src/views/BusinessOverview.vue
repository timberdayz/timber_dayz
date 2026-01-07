<template>
  <div class="business-overview">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <p class="page-subtitle">实时监控核心业务指标，洞察业务发展趋势</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
          刷新数据
        </el-button>
      </div>
    </div>

    <!-- 核心KPI指标卡片（6个） -->
    <div class="kpi-cards" v-loading="loadingKPI">
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" :lg="4" v-for="kpi in kpiData" :key="kpi.key">
          <el-card class="kpi-card" shadow="hover">
            <div class="kpi-content">
              <div class="kpi-icon" :class="kpi.iconClass">
                <el-icon><component :is="kpi.icon" /></el-icon>
              </div>
              <div class="kpi-info">
                <div class="kpi-title">{{ kpi.title }}</div>
                <div class="kpi-value">{{ kpi.value }}</div>
                <div class="kpi-change" :class="kpi.changeType">
                  <el-icon><component :is="kpi.changeIcon" /></el-icon>
                  {{ kpi.change }}
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 经营指标表格（门店经营） -->
    <div class="operational-metrics-section">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
            <span>经营指标</span>
            <el-button size="small" @click="loadOperationalMetrics">
              <el-icon><Refresh /></el-icon>
              刷新
                  </el-button>
              </div>
            </template>
        <div class="operational-metrics-grid" v-loading="loadingOperational">
          <div class="metrics-row">
            <div class="metric-item">
              <div class="metric-label">月目标(w)</div>
              <div class="metric-value">{{ formatNumber(operationalMetrics.monthly_target) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">当月总达成(w)</div>
              <div class="metric-value">{{ formatNumber(operationalMetrics.monthly_total_achieved) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">今日销售额(w)</div>
              <div class="metric-value">{{ formatNumber(operationalMetrics.today_sales) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">月达成率</div>
              <div class="metric-value">
                <el-tag :type="getAchievementRateTagType(operationalMetrics.monthly_achievement_rate)" size="small">
                  {{ operationalMetrics.monthly_achievement_rate }}%
                </el-tag>
              </div>
            </div>
          </div>
          <div class="metrics-row">
            <div class="metric-item">
              <div class="metric-label">时间GAP</div>
              <div class="metric-value">
                <el-tag :type="getTimeGapTagType(operationalMetrics.time_gap)" size="small">
                  {{ operationalMetrics.time_gap > 0 ? '+' : '' }}{{ operationalMetrics.time_gap }}%
                </el-tag>
              </div>
            </div>
            <div class="metric-item">
              <div class="metric-label">预估毛利(w)</div>
              <div class="metric-value">{{ formatNumber(operationalMetrics.estimated_gross_profit) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">预估费用(w)</div>
              <div class="metric-value">{{ formatNumber(operationalMetrics.estimated_expenses) }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">经营结果</div>
              <div class="metric-value">
                <el-tag :type="operationalMetrics.operating_result >= 0 ? 'success' : 'danger'" size="small">
                  {{ operationalMetrics.operating_result_text }}
                </el-tag>
              </div>
            </div>
          </div>
            </div>
          </el-card>
    </div>

    <!-- 数据对比和店铺赛马区域 -->
    <div class="comparison-section">
      <el-row :gutter="20">
        <!-- 左侧：数据对比图表 -->
        <el-col :xs="24" :lg="14">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>数据对比分析</span>
                <div class="header-controls">
                  <el-radio-group v-model="comparisonGranularity" size="small" @change="handleGranularityChange">
                    <el-radio-button label="daily">日</el-radio-button>
                    <el-radio-button label="weekly">周</el-radio-button>
                    <el-radio-button label="monthly">月</el-radio-button>
                  </el-radio-group>
                  <el-date-picker
                    v-model="comparisonDate"
                    :type="datePickerType"
                    :format="datePickerFormat"
                    :placeholder="datePickerPlaceholder"
                    size="small"
                    style="margin-left: 12px; width: 150px"
                    @change="loadComparisonData"
                  />
                </div>
              </div>
            </template>
            <div class="chart-container">
              <!-- 目标达成率进度条 -->
              <div class="target-progress-section" v-loading="loadingComparison">
                <div class="target-progress-item">
                  <div class="target-label">{{ targetProgressLabel }}</div>
                  <el-progress 
                    :percentage="targetAchievementRate" 
                    :color="getTargetProgressColor(targetAchievementRate)"
                    :stroke-width="20"
                    :format="(percentage) => `${percentage.toFixed(1)}%`"
                  />
                  <div class="target-details">
                    <span>目标: {{ formatNumber(targetValue) }}{{ targetUnit }}</span>
                    <span>达成: {{ formatNumber(achievedValue) }}{{ targetUnit }}</span>
            </div>
              </div>
              </div>
              
              <!-- 数据对比表格 -->
              <div class="comparison-table-container">
                <el-table 
                  :data="comparisonTableData" 
                  stripe 
                  style="width: 100%" 
                  size="small"
                  border
                  :show-header="true"
                  empty-text="暂无数据"
                >
                  <el-table-column prop="metric" label="指标" width="120" align="left" fixed="left" />
                  <el-table-column :label="currentPeriodLabel" width="100" align="right">
                    <template #default="{ row }">
                      <span :class="row.todayClass">{{ row.today }}</span>
            </template>
                  </el-table-column>
                  <el-table-column :label="previousPeriodLabel" width="100" align="right">
                    <template #default="{ row }">
                      {{ row.yesterday }}
                    </template>
                  </el-table-column>
                  <el-table-column :label="averageLabel" width="100" align="right">
                    <template #default="{ row }">
                      {{ row.average }}
                    </template>
                  </el-table-column>
                  <el-table-column label="环比" width="100" align="center">
                    <template #default="{ row }">
                      <div class="change-indicator">
                        <el-icon v-if="row.changeType === 'increase'" class="increase-icon">
                          <ArrowUp />
                </el-icon>
                        <el-icon v-else-if="row.changeType === 'decrease'" class="decrease-icon">
                          <ArrowDown />
                        </el-icon>
                        <el-icon v-else class="neutral-icon">
                          <Minus />
                        </el-icon>
                        <span :class="row.changeClass">{{ row.change }}</span>
                </div>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：店铺赛马 -->
        <el-col :xs="24" :lg="10">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>店铺赛马</span>
                <div class="header-controls">
                  <el-radio-group v-model="racingGroupBy" size="small" @change="loadShopRacingData">
                    <el-radio-button label="shop">店铺</el-radio-button>
                    <el-radio-button label="platform">平台</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </template>
            <div class="racing-container">
              <el-table :data="shopRacingData" stripe style="width: 100%" size="small">
                <el-table-column prop="name" label="名称" width="120" />
                <el-table-column prop="target" label="目标" width="80">
                  <template #default="{ row }">
                    {{ formatCurrency(row.target) }}
                  </template>
                </el-table-column>
                <el-table-column prop="achieved" label="完成" width="80">
                  <template #default="{ row }">
                    {{ formatCurrency(row.achieved) }}
                  </template>
                </el-table-column>
                <el-table-column prop="achievement_rate" label="完成率" width="100">
                  <template #default="{ row }">
                    <el-progress
                      :percentage="Math.round(row.achievement_rate * 100)"
                      :color="getAchievementColor(row.achievement_rate)"
                      :stroke-width="8"
                    />
                  </template>
                </el-table-column>
                <el-table-column prop="rank" label="排名" width="60" align="center">
                  <template #default="{ row }">
                    <el-tag :type="row.rank <= 3 ? 'success' : 'info'" size="small">
                      {{ row.rank }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <!-- 流量排名模块 -->
    <div class="traffic-ranking-section">
      <el-card class="chart-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>流量排名</span>
            <div class="header-controls">
              <el-radio-group v-model="trafficRankingGranularity" size="small" @change="loadTrafficRanking">
                <el-radio-button label="daily">日</el-radio-button>
                <el-radio-button label="weekly">周</el-radio-button>
                <el-radio-button label="monthly">月</el-radio-button>
              </el-radio-group>
              <el-radio-group v-model="trafficRankingDimension" size="small" style="margin-left: 12px;" @change="loadTrafficRanking">
                <el-radio-button label="shop">店铺</el-radio-button>
                <el-radio-button label="account">账号</el-radio-button>
              </el-radio-group>
              <el-date-picker
                v-model="trafficRankingDate"
                :type="trafficRankingDatePickerType"
                :format="trafficRankingDatePickerFormat"
                :placeholder="trafficRankingDatePickerPlaceholder"
                size="small"
                style="margin-left: 12px; width: 150px"
                @change="loadTrafficRanking"
              />
              <el-button size="small" @click="loadTrafficRanking" style="margin-left: 12px;">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </div>
        </template>
        <el-table :data="trafficRankingData" stripe style="width: 100%" size="small" v-loading="loadingTrafficRanking" class="erp-table">
          <el-table-column prop="rank" label="排名" width="80" fixed="left" align="center">
            <template #default="{ row }">
              <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : 'primary'" size="small">
                {{ row.rank }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" width="200" fixed="left" show-overflow-tooltip />
          <el-table-column prop="platform_code" label="平台" width="120" v-if="trafficRankingDimension === 'shop'" />
          <el-table-column prop="unique_visitors" label="访客数(UV)" width="150" align="right" sortable>
            <template #default="{ row }">
              {{ formatNumber(row.unique_visitors) }}
            </template>
          </el-table-column>
          <el-table-column prop="page_views" label="浏览量(PV)" width="150" align="right" sortable>
            <template #default="{ row }">
              {{ formatNumber(row.page_views) }}
            </template>
          </el-table-column>
          <el-table-column prop="uv_change_rate" label="UV环比" width="120" align="right" sortable>
            <template #default="{ row }">
              <span :class="row.uv_change_rate >= 0 ? 'text-success' : 'text-danger'">
                {{ row.uv_change_rate >= 0 ? '+' : '' }}{{ row.uv_change_rate.toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="pv_change_rate" label="PV环比" width="120" align="right" sortable>
            <template #default="{ row }">
              <span :class="row.pv_change_rate >= 0 ? 'text-success' : 'text-danger'">
                {{ row.pv_change_rate >= 0 ? '+' : '' }}{{ row.pv_change_rate.toFixed(2) }}%
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="compare_unique_visitors" label="对比期UV" width="150" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.compare_unique_visitors) }}
            </template>
          </el-table-column>
          <el-table-column prop="compare_page_views" label="对比期PV" width="150" align="right">
            <template #default="{ row }">
              {{ formatNumber(row.compare_page_views) }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 库存滞销情况 -->
    <div class="inventory-section">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
            <span>库存滞销情况</span>
            <div class="header-controls">
              <el-button size="small" @click="loadInventoryBacklog">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
              </div>
            </template>
        
        <!-- 库存汇总 -->
        <div class="inventory-summary" v-loading="loadingInventory">
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">总库存价值</div>
                <div class="summary-value">{{ formatCurrency(inventorySummary.total_value) }}</div>
                </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">30天滞销</div>
                <div class="summary-value danger">{{ formatCurrency(inventorySummary.backlog_30d_value) }}</div>
                <div class="summary-ratio">{{ inventorySummary.backlog_30d_ratio }}%</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">60天滞销</div>
                <div class="summary-value warning">{{ formatCurrency(inventorySummary.backlog_60d_value) }}</div>
                <div class="summary-ratio">{{ inventorySummary.backlog_60d_ratio }}%</div>
                </div>
            </el-col>
            <el-col :span="6">
              <div class="summary-item">
                <div class="summary-label">90天滞销</div>
                <div class="summary-value danger">{{ formatCurrency(inventorySummary.backlog_90d_value) }}</div>
                <div class="summary-ratio">{{ inventorySummary.backlog_90d_ratio }}%</div>
              </div>
            </el-col>
          </el-row>
                </div>

        <!-- 滞销产品Top20 -->
        <div class="inventory-table">
          <el-table :data="inventoryBacklogProducts" stripe style="width: 100%" size="small">
            <el-table-column type="index" label="排名" width="60" align="center" />
            <el-table-column prop="product_name" label="产品名称" min-width="150" show-overflow-tooltip />
            <el-table-column prop="platform_sku" label="SKU" width="120" />
            <el-table-column prop="total_stock" label="库存数量" width="100" align="right" />
            <el-table-column prop="age_days" label="滞销天数" width="100" align="right">
              <template #default="{ row }">
                <el-tag :type="getAgeTagType(row.age_days)" size="small">
                  {{ row.age_days }}天
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="backlog_value" label="滞销价值" width="120" align="right">
              <template #default="{ row }">
                {{ formatCurrency(row.backlog_value) }}
              </template>
            </el-table-column>
            <el-table-column prop="backlog_category" label="分类" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="getCategoryTagType(row.backlog_category)" size="small">
                  {{ row.backlog_category }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
            </div>
          </el-card>
    </div>

    <!-- 滞销清理排名模块 -->
    <div class="clearance-ranking-section">
      <el-row :gutter="20">
        <!-- 月度排名 -->
        <el-col :span="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>滞销清理排名（月度）</span>
                <div class="header-controls">
                  <el-date-picker
                    v-model="clearanceMonth"
                    type="month"
                    format="YYYY-MM"
                    placeholder="选择月份"
                    size="small"
                    style="width: 150px"
                    @change="loadClearanceRanking('monthly')"
                  />
                  <el-button size="small" @click="loadClearanceRanking('monthly')">
                    <el-icon><Refresh /></el-icon>
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            <el-table :data="monthlyClearanceRanking" stripe style="width: 100%" size="small" v-loading="loadingClearanceRanking" class="erp-table">
              <el-table-column prop="rank" label="排名" width="80" fixed="left" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : 'primary'" size="small">
                    {{ row.rank }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
              <el-table-column prop="clearance_amount" label="清理金额" width="150" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.clearance_amount) }}
                </template>
              </el-table-column>
              <el-table-column prop="clearance_quantity" label="清理数量" width="120" align="right" sortable />
              <el-table-column prop="incentive_amount" label="激励金额" width="120" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.incentive_amount) }}
                </template>
              </el-table-column>
              <el-table-column prop="total_incentive" label="总计激励" width="120" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.total_incentive) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
        
        <!-- 周度排名 -->
        <el-col :span="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>滞销清理排名（周度）</span>
                <div class="header-controls">
                  <el-date-picker
                    v-model="clearanceWeek"
                    type="week"
                    format="YYYY-WW"
                    placeholder="选择周"
                    size="small"
                    style="width: 150px"
                    @change="loadClearanceRanking('weekly')"
                  />
                  <el-button size="small" @click="loadClearanceRanking('weekly')">
                    <el-icon><Refresh /></el-icon>
                    刷新
                  </el-button>
                </div>
              </div>
            </template>
            <el-table :data="weeklyClearanceRanking" stripe style="width: 100%" size="small" v-loading="loadingClearanceRanking" class="erp-table">
              <el-table-column prop="rank" label="排名" width="80" fixed="left" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : 'primary'" size="small">
                    {{ row.rank }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
              <el-table-column prop="clearance_amount" label="清理金额" width="150" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.clearance_amount) }}
                </template>
              </el-table-column>
              <el-table-column prop="clearance_quantity" label="清理数量" width="120" align="right" sortable />
              <el-table-column prop="incentive_amount" label="激励金额" width="120" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.incentive_amount) }}
                </template>
              </el-table-column>
              <el-table-column prop="total_incentive" label="总计激励" width="120" align="right" sortable>
                <template #default="{ row }">
                  {{ formatCurrency(row.total_incentive) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import api from '@/api'
import { formatCurrency, formatNumber as formatNumberUtil, formatPercent as formatPercentUtil, formatInteger as formatIntegerUtil } from '@/utils/dataFormatter'
import { showError as showApiError, handleApiError } from '@/utils/errorHandler'

// 响应式数据
const loading = ref(false)
const loadingKPI = ref(false)
const loadingComparison = ref(false)
const loadingInventory = ref(false)

// KPI数据
const kpiData = ref([
  {
    key: 'conversion_rate',
    title: '转化率',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'DataBoard',
    iconClass: 'kpi-conversion'
  },
  {
    key: 'traffic',
    title: '客流量',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'User',
    iconClass: 'kpi-traffic'
  },
  {
    key: 'average_order_value',
    title: '客单价',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'Money',
    iconClass: 'kpi-aov'
  },
  {
    key: 'attach_rate',
    title: '连带率',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'ShoppingCart',
    iconClass: 'kpi-attach'
  },
  {
    key: 'labor_efficiency',
    title: '人效',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'UserFilled',
    iconClass: 'kpi-labor'
  },
  {
    key: 'order_count',
    title: '销售单数',
    value: '--',
    change: '--',
    changeType: 'neutral',
    changeIcon: 'TrendCharts',
    icon: 'Document',
    iconClass: 'kpi-orders'
  }
])

// 数据对比
const comparisonChart = ref(null)
const comparisonGranularity = ref('daily')
const comparisonDate = ref(new Date())
const comparisonData = ref({
  metrics: {},
  today: {},
  yesterday: {},
  average: {}
})

// 对比表格数据
const comparisonTableData = ref([])


// 目标达成率相关数据
const targetValue = ref(0)
const achievedValue = ref(0)
const targetAchievementRate = ref(0)
const targetUnit = ref('(w)')

// 根据粒度计算列标题
const currentPeriodLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '本月'
  } else if (comparisonGranularity.value === 'weekly') {
    return '本周'
  } else {
    return '今日'
  }
})

const previousPeriodLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '上月'
  } else if (comparisonGranularity.value === 'weekly') {
    return '上周'
  } else {
    return '昨日'
  }
})

const averageLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '本月平均'
  } else if (comparisonGranularity.value === 'weekly') {
    return '本周平均'
  } else {
    return '本月平均'
  }
})

const targetProgressLabel = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '月度目标达成率'
  } else if (comparisonGranularity.value === 'weekly') {
    return '周度目标达成率'
  } else {
    return '日度目标达成率'
  }
})

// 获取目标进度条颜色
const getTargetProgressColor = (percentage) => {
  if (percentage >= 100) return '#67C23A'
  if (percentage >= 80) return '#E6A23C'
  return '#F56C6C'
}

// 根据粒度计算日期选择器类型和格式
const datePickerType = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return 'month'  // 月份选择器
  } else if (comparisonGranularity.value === 'weekly') {
    return 'week'  // 周选择器
  } else {
    return 'date'  // 日期选择器
  }
})

const datePickerFormat = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return 'YYYY-MM'
  } else if (comparisonGranularity.value === 'weekly') {
    return 'YYYY 第 ww 周'
  } else {
    return 'YYYY-MM-DD'
  }
})

const datePickerPlaceholder = computed(() => {
  if (comparisonGranularity.value === 'monthly') {
    return '选择月份'
  } else if (comparisonGranularity.value === 'weekly') {
    return '选择周'
  } else {
    return '选择日期'
  }
})

// 流量排名日期选择器类型和格式
const trafficRankingDatePickerType = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return 'month'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return 'week'
  } else {
    return 'date'
  }
})

const trafficRankingDatePickerFormat = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return 'YYYY-MM'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return 'YYYY-WW'
  } else {
    return 'YYYY-MM-DD'
  }
})

const trafficRankingDatePickerPlaceholder = computed(() => {
  if (trafficRankingGranularity.value === 'monthly') {
    return '选择月份'
  } else if (trafficRankingGranularity.value === 'weekly') {
    return '选择周'
  } else {
    return '选择日期'
  }
})

// 处理粒度变化
const handleGranularityChange = () => {
  // 根据新的粒度调整日期
  const today = new Date()
  if (comparisonGranularity.value === 'monthly') {
    // 设置为当前月份的第一天
    comparisonDate.value = new Date(today.getFullYear(), today.getMonth(), 1)
  } else if (comparisonGranularity.value === 'weekly') {
    // 设置为当前周的第一天（周一）
    const dayOfWeek = today.getDay()
    const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
    comparisonDate.value = new Date(today)
    comparisonDate.value.setDate(today.getDate() + diff)
  } else {
    // 设置为今天
    comparisonDate.value = today
  }
  loadComparisonData()
}

// 店铺赛马
const racingGroupBy = ref('shop')
const shopRacingData = ref([])

// 库存滞销
const inventorySummary = ref({
  total_value: 0,
  backlog_30d_value: 0,
  backlog_30d_ratio: 0,
  backlog_60d_value: 0,
  backlog_60d_ratio: 0,
  backlog_90d_value: 0,
  backlog_90d_ratio: 0,
  total_quantity: 0,
  backlog_30d_quantity: 0,
  backlog_60d_quantity: 0,
  backlog_90d_quantity: 0
})
const inventoryBacklogProducts = ref([])

// 流量排名数据
const trafficRankingGranularity = ref('monthly')
const trafficRankingDimension = ref('shop')
const trafficRankingDate = ref(new Date())
const trafficRankingData = ref([])
const loadingTrafficRanking = ref(false)

// 滞销清理排名数据
const loadingClearanceRanking = ref(false)
const monthlyClearanceRanking = ref([])
const weeklyClearanceRanking = ref([])
const clearanceMonth = ref(new Date())
const clearanceWeek = ref(new Date())

// 经营指标
const loadingOperational = ref(false)
const operationalMetrics = ref({
  monthly_target: 0,
  monthly_total_achieved: 0,
  today_sales: 0,
  monthly_achievement_rate: 0,
  time_gap: 0,
  estimated_gross_profit: 0,
  estimated_expenses: 0,
  operating_result: 0,
  operating_result_text: '--',
  monthly_order_count: 0,
  today_order_count: 0
})

// 图表实例
let comparisonChartInstance = null

// 使用统一的格式化函数（从dataFormatter导入）
const formatNumber = formatNumberUtil
const formatInteger = formatIntegerUtil
// formatPercent需要特殊处理：如果输入是0-1的小数，需要设置isDecimal=true
const formatPercent = (value, isDecimal = true) => {
  return formatPercentUtil(value, 2, '-', isDecimal)
}

// 获取变化类型
const getChangeType = (change) => {
  if (change === null || change === undefined) return 'neutral'
  const num = Number(change)
  if (num > 0) return 'increase'
  if (num < 0) return 'decrease'
  return 'neutral'
}

// 获取变化图标
const getChangeIcon = (change) => {
  const num = Number(change)
  if (num > 0) return 'ArrowUp'
  if (num < 0) return 'ArrowDown'
  return 'Minus'
}

// 获取完成率颜色
const getAchievementColor = (rate) => {
  if (rate >= 1.0) return '#67C23A'
  if (rate >= 0.8) return '#E6A23C'
  return '#F56C6C'
}

// 获取滞销天数标签类型
const getAgeTagType = (days) => {
  if (days >= 90) return 'danger'
  if (days >= 60) return 'warning'
  return 'info'
}

// 获取分类标签类型
const getCategoryTagType = (category) => {
  if (category === '90天+') return 'danger'
  if (category === '60-90天') return 'warning'
  if (category === '30-60天') return 'info'
  return 'primary'
}

// 获取达成率标签类型
const getAchievementRateTagType = (rate) => {
  if (rate >= 100) return 'success'
  if (rate >= 80) return 'warning'
  return 'danger'
}

// 获取时间GAP标签类型
const getTimeGapTagType = (gap) => {
  if (gap > 0) return 'success'
  if (gap < 0) return 'danger'
  return 'info'
}

// 加载KPI数据
const loadKPIData = async () => {
  loadingKPI.value = true
  try {
    const today = new Date()
    const lastMonth = new Date(today.getFullYear(), today.getMonth() - 1, today.getDate())
    
    const response = await api.getBusinessOverviewKPI({
      start_date: lastMonth.toISOString().split('T')[0],
      end_date: today.toISOString().split('T')[0]
    })
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      const data = response
      
      // 更新转化率
      kpiData.value[0].value = formatPercent(data.conversion_rate?.current)
      kpiData.value[0].change = data.conversion_rate?.change ? `${data.conversion_rate.change > 0 ? '+' : ''}${formatPercent(Math.abs(data.conversion_rate.change))}` : '--'
      kpiData.value[0].changeType = getChangeType(data.conversion_rate?.change)
      kpiData.value[0].changeIcon = getChangeIcon(data.conversion_rate?.change)
      
      // 更新客流量
      kpiData.value[1].value = data.traffic?.current ? Number(data.traffic.current).toLocaleString() : '--'
      kpiData.value[1].change = data.traffic?.change ? `${data.traffic.change > 0 ? '+' : ''}${(data.traffic.change * 100).toFixed(2)}%` : '--'
      kpiData.value[1].changeType = getChangeType(data.traffic?.change)
      kpiData.value[1].changeIcon = getChangeIcon(data.traffic?.change)
      
      // 更新客单价
      kpiData.value[2].value = formatCurrency(data.average_order_value?.current)
      kpiData.value[2].change = data.average_order_value?.change ? `${data.average_order_value.change > 0 ? '+' : ''}${formatPercent(Math.abs(data.average_order_value.change))}` : '--'
      kpiData.value[2].changeType = getChangeType(data.average_order_value?.change)
      kpiData.value[2].changeIcon = getChangeIcon(data.average_order_value?.change)
      
      // 更新连带率
      kpiData.value[3].value = data.attach_rate?.current ? Number(data.attach_rate.current).toFixed(2) : '--'
      kpiData.value[3].change = data.attach_rate?.change ? `${data.attach_rate.change > 0 ? '+' : ''}${(data.attach_rate.change * 100).toFixed(2)}%` : '--'
      kpiData.value[3].changeType = getChangeType(data.attach_rate?.change)
      kpiData.value[3].changeIcon = getChangeIcon(data.attach_rate?.change)
      
      // 更新人效（如果有数据）
      if (data.labor_efficiency?.current !== null && data.labor_efficiency?.current !== undefined) {
        kpiData.value[4].value = formatCurrency(data.labor_efficiency.current)
        kpiData.value[4].change = data.labor_efficiency.change ? `${data.labor_efficiency.change > 0 ? '+' : ''}${formatPercent(Math.abs(data.labor_efficiency.change))}` : '--'
        kpiData.value[4].changeType = getChangeType(data.labor_efficiency.change)
        kpiData.value[4].changeIcon = getChangeIcon(data.labor_efficiency.change)
      } else {
        kpiData.value[4].value = '暂无数据'
        kpiData.value[4].change = '--'
      }
      
      // 销售单数会在loadOperationalMetrics中更新
    }
  } catch (error) {
    console.error('加载KPI数据失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingKPI.value = false
  }
}

// 更新销售单数KPI（从经营指标数据更新）
const updateOrderCountKPI = () => {
  if (operationalMetrics.value.monthly_order_count > 0) {
    kpiData.value[5].value = formatInteger(operationalMetrics.value.monthly_order_count)
    // 可以计算变化率，这里简化处理
    kpiData.value[5].change = '--'
  }
}

// 加载数据对比
const loadComparisonData = async () => {
  loadingComparison.value = true
  try {
    // 根据粒度格式化日期
    let dateStr = ''
    if (comparisonGranularity.value === 'monthly') {
      // 月份格式：YYYY-MM
      const year = comparisonDate.value.getFullYear()
      const month = String(comparisonDate.value.getMonth() + 1).padStart(2, '0')
      dateStr = `${year}-${month}-01`  // 使用月份第一天
    } else if (comparisonGranularity.value === 'weekly') {
      // 周格式：使用周的第一天
      dateStr = comparisonDate.value.toISOString().split('T')[0]
    } else {
      // 日期格式：YYYY-MM-DD
      dateStr = comparisonDate.value.toISOString().split('T')[0]
    }
    
    const response = await api.getBusinessOverviewComparison({
      granularity: comparisonGranularity.value,
      date: dateStr
    })
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      comparisonData.value = response
      
      console.log('对比数据:', response)  // 调试信息
      
      // 更新目标达成率（使用销售额作为主要指标）
      // 注意：response已经是data字段（拦截器已处理）
      const metrics = response.metrics || {}
      const salesAmount = metrics.sales_amount || {}
      achievedValue.value = salesAmount.today || 0
      
      // 计算目标值（简化：基于平均值或历史数据）
      // 实际应该从配置表读取，这里使用简化逻辑
      const avgSales = salesAmount.average || 0
      if (comparisonGranularity.value === 'monthly') {
        targetValue.value = avgSales * 1.2  // 月度目标 = 平均值的120%
      } else if (comparisonGranularity.value === 'weekly') {
        targetValue.value = avgSales * 1.1  // 周度目标 = 平均值的110%
      } else {
        targetValue.value = avgSales * 1.05  // 日度目标 = 平均值的105%
      }
      
      targetAchievementRate.value = targetValue.value > 0 
        ? (achievedValue.value / targetValue.value * 100) 
        : 0
      
      updateComparisonTable()
    } else {
      console.error('API返回失败:', response)
      // 即使API失败，也保持表格结构（显示7个指标行，数据为--）
      updateComparisonTable()
    }
  } catch (error) {
    console.error('加载数据对比失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
    // 即使出错，也保持表格结构（显示7个指标行，数据为--）
    updateComparisonTable()
  } finally {
    loadingComparison.value = false
  }
}

// 更新对比表格
const updateComparisonTable = () => {
  const data = comparisonData.value || {}
  const tableData = []
  
  console.log('updateComparisonTable - comparisonData:', data)  // 调试信息
  
  // 即使数据为空，也显示所有指标行（前端设计优先）
  const metrics = (data && typeof data.metrics === 'object' && !Array.isArray(data.metrics)) 
    ? data.metrics 
    : {}
  
  console.log('metrics:', metrics)  // 调试信息
  
  // 销售额
  const salesAmount = metrics.sales_amount || {}
  tableData.push({
    metric: '销售额(w)',
    today: salesAmount.today !== undefined ? formatNumber(salesAmount.today) : '--',
    yesterday: salesAmount.yesterday !== undefined ? formatNumber(salesAmount.yesterday) : '--',
    average: salesAmount.average !== undefined ? formatNumber(salesAmount.average) : '--',
    change: salesAmount.change !== undefined ? `${salesAmount.change > 0 ? '+' : ''}${salesAmount.change.toFixed(2)}%` : '--',
    changeType: salesAmount.change_type || 'neutral',
    changeClass: salesAmount.change_type || 'neutral',
    todayClass: ''
  })
  
  // 销售数量
  const salesQty = metrics.sales_quantity || {}
  tableData.push({
    metric: '销售数量',
    today: salesQty.today !== undefined ? formatInteger(salesQty.today) : '--',
    yesterday: salesQty.yesterday !== undefined ? formatInteger(salesQty.yesterday) : '--',
    average: salesQty.average !== undefined ? formatInteger(salesQty.average) : '--',
    change: salesQty.change !== undefined ? `${salesQty.change > 0 ? '+' : ''}${salesQty.change.toFixed(2)}%` : '--',
    changeType: salesQty.change_type || 'neutral',
    changeClass: salesQty.change_type || 'neutral',
    todayClass: ''
  })
  
  // 客流量
  const traffic = metrics.traffic || {}
  tableData.push({
    metric: '客流量',
    today: traffic.today !== undefined ? formatInteger(traffic.today) : '--',
    yesterday: traffic.yesterday !== undefined ? formatInteger(traffic.yesterday) : '--',
    average: traffic.average !== undefined ? formatInteger(traffic.average) : '--',
    change: traffic.change !== undefined ? `${traffic.change > 0 ? '+' : ''}${traffic.change.toFixed(2)}%` : '--',
    changeType: traffic.change_type || 'neutral',
    changeClass: traffic.change_type || 'neutral',
    todayClass: ''
  })
  
  // 转化率
  const conversion = metrics.conversion_rate || {}
  const conversionToday = conversion.today
  const conversionAvg = conversion.average
  tableData.push({
    metric: '转化率',
    today: conversionToday !== undefined && conversionToday !== null ? `${conversionToday.toFixed(2)}%` : '--',
    yesterday: conversion.yesterday !== undefined && conversion.yesterday !== null ? `${conversion.yesterday.toFixed(2)}%` : '--',
    average: conversionAvg !== undefined && conversionAvg !== null ? `${conversionAvg.toFixed(2)}%` : '--',
    change: conversion.change !== undefined ? `${conversion.change > 0 ? '+' : ''}${conversion.change.toFixed(2)}%` : '--',
    changeType: conversion.change_type || 'neutral',
    changeClass: conversion.change_type || 'neutral',
    todayClass: conversionToday > conversionAvg ? 'highlight-positive' : ''
  })
  
  // 客单价
  const aov = metrics.avg_order_value || {}
  const aovToday = aov.today
  const aovAvg = aov.average
  tableData.push({
    metric: '客单价',
    today: aovToday !== undefined ? formatInteger(aovToday) : '--',
    yesterday: aov.yesterday !== undefined ? formatInteger(aov.yesterday) : '--',
    average: aovAvg !== undefined ? formatInteger(aovAvg) : '--',
    change: aov.change !== undefined ? `${aov.change > 0 ? '+' : ''}${aov.change.toFixed(2)}%` : '--',
    changeType: aov.change_type || 'neutral',
    changeClass: aov.change_type || 'neutral',
    todayClass: aovToday > aovAvg ? 'highlight-positive' : ''
  })
  
  // 连带率
  const attach = metrics.attach_rate || {}
  const attachToday = attach.today
  const attachAvg = attach.average
  tableData.push({
    metric: '连带率',
    today: attachToday !== undefined ? attachToday.toFixed(2) : '--',
    yesterday: attach.yesterday !== undefined ? attach.yesterday.toFixed(2) : '--',
    average: attachAvg !== undefined ? attachAvg.toFixed(2) : '--',
    change: attach.change !== undefined ? `${attach.change > 0 ? '+' : ''}${attach.change.toFixed(2)}%` : '--',
    changeType: attach.change_type || 'neutral',
    changeClass: attach.change_type || 'neutral',
    todayClass: attachToday > attachAvg ? 'highlight-positive' : ''
  })
  
  // 利润
  const profit = metrics.profit || {}
  tableData.push({
    metric: '利润(w)',
    today: profit.today !== undefined ? formatNumber(profit.today) : '--',
    yesterday: profit.yesterday !== undefined ? formatNumber(profit.yesterday) : '--',
    average: profit.average !== undefined ? formatNumber(profit.average) : '--',
    change: profit.change !== undefined ? `${profit.change > 0 ? '+' : ''}${profit.change.toFixed(2)}%` : '--',
    changeType: profit.change_type || 'neutral',
    changeClass: profit.change_type || 'neutral',
    todayClass: ''
  })
  
  console.log('表格数据:', tableData)  // 调试信息
  console.log('表格数据长度:', tableData.length)  // 调试信息
  comparisonTableData.value = tableData
  console.log('comparisonTableData.value 已设置:', comparisonTableData.value.length, '行')
}

// 更新对比图表（保留，但暂时不使用）
const updateComparisonChart = () => {
  // 暂时不使用图表，使用表格展示
  updateComparisonTable()
}

// 加载店铺赛马数据
const loadShopRacingData = async () => {
  try {
    const dateStr = comparisonDate.value.toISOString().split('T')[0]
    const response = await api.getBusinessOverviewShopRacing({
      granularity: comparisonGranularity.value,
      date: dateStr,
      group_by: racingGroupBy.value
    })
    
    // 响应拦截器已处理success字段，直接使用data
    if (response && response.groups) {
      // shop-racing API返回的是groups数组，需要展平
      shopRacingData.value = []
      response.groups.forEach(group => {
        if (group.shops && Array.isArray(group.shops)) {
          shopRacingData.value.push(...group.shops)
        }
      })
    } else if (response && Array.isArray(response)) {
      shopRacingData.value = response
    } else {
      shopRacingData.value = []
    }
  } catch (error) {
    console.error('加载店铺赛马数据失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  }
}

// 加载经营指标数据
const loadOperationalMetrics = async () => {
  loadingOperational.value = true
  try {
    const response = await api.getBusinessOverviewOperationalMetrics()
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      operationalMetrics.value = {
        monthly_target: response.monthly_target || 0,
        monthly_total_achieved: response.monthly_total_achieved || 0,
        today_sales: response.today_sales || 0,
        monthly_achievement_rate: response.monthly_achievement_rate || 0,
        time_gap: response.time_gap || 0,
        estimated_gross_profit: response.estimated_gross_profit || 0,
        estimated_expenses: response.estimated_expenses || 0,
        operating_result: response.operating_result || 0,
        operating_result_text: response.operating_result_text || '--',
        monthly_order_count: response.monthly_order_count || 0,
        today_order_count: response.today_order_count || 0
      }
      // 更新销售单数KPI卡片
      updateOrderCountKPI()
    }
  } catch (error) {
    console.error('加载经营指标数据失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingOperational.value = false
  }
}

// 加载流量排名
const loadTrafficRanking = async () => {
  loadingTrafficRanking.value = true
  try {
    // 根据粒度确定日期值
    let dateValue = trafficRankingDate.value
    if (trafficRankingGranularity.value === 'monthly') {
      // 月份选择器返回的是月份第一天
      dateValue = new Date(dateValue.getFullYear(), dateValue.getMonth(), 1)
    } else if (trafficRankingGranularity.value === 'weekly') {
      // 周选择器需要转换为周的第一天（周一）
      const dayOfWeek = dateValue.getDay()
      const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
      dateValue = new Date(dateValue)
      dateValue.setDate(dateValue.getDate() + diff)
    }
    
    const params = {
      granularity: trafficRankingGranularity.value,
      dimension: trafficRankingDimension.value,
      date: dateValue.toISOString().split('T')[0]  // 后端API使用date_value，但前端统一使用date
    }
    
    const response = await api.getBusinessOverviewTrafficRanking(params)
    
    // 响应拦截器已处理success字段，直接使用data
    trafficRankingData.value = response || []
  } catch (error) {
    console.error('加载流量排名失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingTrafficRanking.value = false
  }
}

// 加载库存滞销数据
const loadInventoryBacklog = async () => {
  loadingInventory.value = true
  try {
    const response = await api.getBusinessOverviewInventoryBacklog()
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      inventorySummary.value = response.summary || inventorySummary.value
      inventoryBacklogProducts.value = response.top_products || []
    }
  } catch (error) {
    console.error('加载库存滞销数据失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingInventory.value = false
  }
}

// 刷新所有数据
// 加载滞销清理排名
const loadClearanceRanking = async (granularity) => {
  loadingClearanceRanking.value = true
  try {
    const params = {}
    if (granularity === 'monthly' && clearanceMonth.value) {
      const month = clearanceMonth.value.getMonth() + 1
      const year = clearanceMonth.value.getFullYear()
      params.month = `${year}-${String(month).padStart(2, '0')}`
    }
    if (granularity === 'weekly' && clearanceWeek.value) {
      // 计算周数
      const week = getWeekNumber(clearanceWeek.value)
      const year = clearanceWeek.value.getFullYear()
      params.week = `${year}W${String(week).padStart(2, '0')}`
    }
    
    params.granularity = granularity
    
    // 响应拦截器已处理success字段，直接使用data
    const response = await api.getClearanceRanking(params)
    
    if (granularity === 'monthly') {
      monthlyClearanceRanking.value = response || []
    } else {
      weeklyClearanceRanking.value = response || []
    }
  } catch (error) {
    console.error('加载滞销清理排名失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loadingClearanceRanking.value = false
  }
}

// 获取周数辅助函数
const getWeekNumber = (date) => {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7)
}


const refreshData = async () => {
  loading.value = true
  try {
    await Promise.all([
      loadKPIData(),
      loadComparisonData(),
      loadShopRacingData(),
      loadTrafficRanking(),
      loadInventoryBacklog(),
      loadOperationalMetrics(),
      loadClearanceRanking('monthly'),
      loadClearanceRanking('weekly'),
    ])
    ElMessage.success('数据刷新成功')
  } catch (error) {
    ElMessage.error('数据刷新失败')
  } finally {
    loading.value = false
  }
}

// 生命周期
onMounted(() => {
  // 立即初始化表格结构（即使没有数据也要显示7个指标行）
  updateComparisonTable()
  // 然后加载真实数据
  refreshData()
  
})
</script>

<style scoped>
.business-overview {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: white;
}

.header-content .page-subtitle {
  font-size: 16px;
  opacity: 0.9;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.kpi-cards {
  margin-bottom: 24px;
}

.kpi-card {
  border: none;
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
}

.kpi-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kpi-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: white;
}

.kpi-icon.kpi-conversion {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
}

.kpi-icon.kpi-traffic {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.kpi-icon.kpi-aov {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.kpi-icon.kpi-attach {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.kpi-icon.kpi-labor {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.kpi-icon.kpi-orders {
  background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
}

.kpi-info {
  flex: 1;
}

.kpi-title {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.kpi-change {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.kpi-change.increase {
  color: #67C23A;
}

.kpi-change.decrease {
  color: #F56C6C;
}

.kpi-change.neutral {
  color: #909399;
}

.comparison-section {
  margin-bottom: 24px;
}

.chart-card {
  border: none;
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.chart-container {
  min-height: 400px;
}

.target-progress-section {
  margin-bottom: 20px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
}

.target-progress-item {
  width: 100%;
}

.target-label {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.target-details {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.comparison-table-container {
  padding: 10px 0;
}

.change-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.increase-icon {
  color: #67C23A;
}

.decrease-icon {
  color: #F56C6C;
}

.neutral-icon {
  color: #909399;
}

.change-indicator .increase {
  color: #67C23A;
}

.change-indicator .decrease {
  color: #F56C6C;
}

.change-indicator .neutral {
  color: #909399;
}

.highlight-positive {
  color: #67C23A;
  font-weight: 600;
}

.chart {
  width: 100%;
  height: 100%;
}

.racing-container {
  max-height: 400px;
  overflow-y: auto;
}

.operational-metrics-section {
  margin-bottom: 24px;
}

.operational-metrics-grid {
  padding: 10px 0;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.metrics-row:last-child {
  margin-bottom: 0;
}

.metric-item {
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  text-align: center;
}

.metric-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

@media (max-width: 1200px) {
  .metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics-row {
    grid-template-columns: 1fr;
  }
}

.inventory-summary {
  margin-bottom: 20px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
}

.summary-item {
  text-align: center;
}

.summary-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

.summary-value.danger {
  color: #F56C6C;
}

.summary-value.warning {
  color: #E6A23C;
}

.summary-ratio {
  font-size: 12px;
  color: #909399;
}

.inventory-table {
  margin-top: 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
    text-align: center;
  }
  
  .header-actions {
    width: 100%;
    justify-content: center;
  }
  
  .kpi-content {
    flex-direction: column;
    text-align: center;
  }
  
  .kpi-icon {
    width: 50px;
    height: 50px;
    font-size: 20px;
  }
  
  .header-controls {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
