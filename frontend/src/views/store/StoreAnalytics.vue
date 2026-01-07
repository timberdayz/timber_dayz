<template>
  <div class="store-analytics erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">店铺分析</h1>
    
    <!-- 操作栏 -->
    <div class="action-bar" style="margin-bottom: 20px;">
      <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
      <div style="flex: 1;"></div>
      <el-select v-model="filters.platform" placeholder="选择平台" clearable size="small" style="width: 150px;" @change="handleFilterChange">
        <el-option label="全部平台" value="" />
        <el-option label="Shopee" value="Shopee" />
        <el-option label="Lazada" value="Lazada" />
      </el-select>
      <el-select v-model="filters.shopId" placeholder="选择店铺" clearable size="small" style="width: 200px; margin-left: 10px;" @change="handleFilterChange">
        <el-option
          v-for="shop in availableShops"
          :key="shop.id"
          :label="shop.name"
          :value="shop.id"
        />
      </el-select>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        size="small"
        style="width: 250px; margin-left: 10px;"
        @change="handleDateRangeChange"
      />
      <el-radio-group v-model="filters.granularity" size="small" style="margin-left: 10px;" @change="handleFilterChange">
        <el-radio-button label="daily">日</el-radio-button>
        <el-radio-button label="weekly">周</el-radio-button>
        <el-radio-button label="monthly">月</el-radio-button>
      </el-radio-group>
    </div>
    
    <!-- 店铺健康度评分卡片 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺健康度评分</span>
              <el-button size="small" :icon="Refresh" @click="loadHealthScore">刷新</el-button>
            </div>
          </template>
          
          <el-table :data="healthScore.data" stripe v-loading="healthScore.loading" class="erp-table">
            <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="health_score" label="健康度总分" width="120" align="center" sortable>
              <template #default="{ row }">
                <el-progress
                  :percentage="row.health_score"
                  :color="getHealthColor(row.health_score)"
                  :stroke-width="20"
                  :format="(percentage) => `${percentage}分`"
                />
              </template>
            </el-table-column>
            <el-table-column prop="gmv_score" label="GMV得分" width="100" align="right" sortable />
            <el-table-column prop="conversion_score" label="转化得分" width="100" align="right" sortable />
            <el-table-column prop="inventory_score" label="库存得分" width="100" align="right" sortable />
            <el-table-column prop="service_score" label="服务得分" width="100" align="right" sortable />
            <el-table-column prop="gmv" label="GMV" width="150" align="right" sortable>
              <template #default="{ row }">
                ¥{{ row.gmv.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="conversion_rate" label="转化率" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.conversion_rate.toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column prop="inventory_turnover" label="库存周转" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.inventory_turnover.toFixed(1) }}次
              </template>
            </el-table-column>
            <el-table-column prop="customer_satisfaction" label="客户满意度" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.customer_satisfaction.toFixed(1) }}⭐
              </template>
            </el-table-column>
            <el-table-column prop="risk_level" label="风险等级" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="getRiskTagType(row.risk_level)" size="small">
                  {{ getRiskLabel(row.risk_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleViewDetail(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- GMV趋势和转化率分析 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺GMV趋势</span>
              <el-button size="small" :icon="Refresh" @click="loadGMVTrend">刷新</el-button>
            </div>
          </template>
          <div ref="gmvChart" style="height: 300px;" v-loading="gmvTrend.loading"></div>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺转化率分析</span>
              <el-button size="small" :icon="Refresh" @click="loadConversionAnalysis">刷新</el-button>
            </div>
          </template>
          <div ref="conversionChart" style="height: 300px;" v-loading="conversionAnalysis.loading"></div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 店铺流量分析 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺流量分析</span>
              <el-button size="small" :icon="Refresh" @click="loadTrafficAnalysis">刷新</el-button>
            </div>
          </template>
          <div ref="trafficChart" style="height: 400px; min-height: 400px;" v-loading="trafficAnalysis.loading">
            <div v-if="!trafficAnalysis.loading && (!trafficAnalysis.data || trafficAnalysis.data.length === 0)" 
                 style="display: flex; align-items: center; justify-content: center; height: 100%; color: #909399; font-size: 14px;">
              <span>暂无流量数据，请选择店铺或调整日期范围</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 店铺对比分析 -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺对比分析</span>
              <div>
                <el-select
                  v-model="selectedShops"
                  multiple
                  placeholder="选择对比店铺"
                  size="small"
                  style="width: 300px; margin-right: 10px;"
                  @change="loadComparison"
                >
                  <el-option
                    v-for="shop in availableShops"
                    :key="shop.id"
                    :label="shop.name"
                    :value="shop.id"
                  />
                </el-select>
                <el-button size="small" :icon="Refresh" @click="loadComparison">刷新</el-button>
              </div>
            </div>
          </template>
          
          <el-table :data="comparison.data" stripe v-loading="comparison.loading" class="erp-table">
            <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="gmv" label="GMV" width="150" align="right" sortable>
              <template #default="{ row }">
                ¥{{ row.gmv.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="order_count" label="订单数" width="120" align="right" sortable />
            <el-table-column prop="avg_order_value" label="客单价" width="120" align="right" sortable>
              <template #default="{ row }">
                ¥{{ row.avg_order_value.toFixed(2) }}
              </template>
            </el-table-column>
            <el-table-column prop="conversion_rate" label="转化率" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.conversion_rate.toFixed(2) }}%
              </template>
            </el-table-column>
            <el-table-column prop="page_views" label="浏览量" width="120" align="right" sortable />
            <el-table-column prop="unique_visitors" label="访客数" width="120" align="right" sortable />
            <el-table-column prop="customer_satisfaction" label="客户满意度" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.customer_satisfaction.toFixed(1) }}⭐
              </template>
            </el-table-column>
            <el-table-column prop="inventory_turnover" label="库存周转" width="120" align="right" sortable>
              <template #default="{ row }">
                {{ row.inventory_turnover.toFixed(1) }}次
              </template>
            </el-table-column>
            <el-table-column prop="health_score" label="健康度" width="120" align="center" sortable>
              <template #default="{ row }">
                <el-progress
                  :percentage="row.health_score"
                  :color="getHealthColor(row.health_score)"
                  :stroke-width="10"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 店铺预警提醒 -->
    <el-row :gutter="20">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>店铺预警提醒</span>
              <div>
                <el-select v-model="alertFilter" placeholder="预警级别" clearable size="small" style="width: 120px; margin-right: 10px;" @change="loadAlerts">
                  <el-option label="全部" value="" />
                  <el-option label="严重" value="critical" />
                  <el-option label="警告" value="warning" />
                  <el-option label="提示" value="info" />
                </el-select>
                <el-button size="small" :icon="Refresh" @click="loadAlerts">刷新</el-button>
              </div>
            </div>
          </template>
          
          <el-table :data="alerts.data" stripe v-loading="alerts.loading" class="erp-table">
            <el-table-column prop="shop_name" label="店铺名称" width="200" show-overflow-tooltip />
            <el-table-column prop="alert_level" label="预警级别" width="120" align="center">
              <template #default="{ row }">
                <el-tag :type="getAlertTagType(row.alert_level)" size="small">
                  {{ getAlertLabel(row.alert_level) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="预警标题" width="200" show-overflow-tooltip />
            <el-table-column prop="message" label="预警内容" min-width="300" show-overflow-tooltip />
            <el-table-column prop="metric_value" label="当前值" width="120" align="right">
              <template #default="{ row }">
                {{ row.metric_value }}
              </template>
            </el-table-column>
            <el-table-column prop="threshold" label="阈值" width="120" align="right">
              <template #default="{ row }">
                {{ row.threshold }}
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="180" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 店铺详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      title="店铺详情"
      width="900px"
    >
      <div v-if="storeDetail.data" v-loading="storeDetail.loading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="店铺名称" :span="2">{{ storeDetail.data.shop_name }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ storeDetail.data.platform }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ storeDetail.data.region }}</el-descriptions-item>
          <el-descriptions-item label="健康度总分">
            <el-progress
              :percentage="storeDetail.data.health_score"
              :color="getHealthColor(storeDetail.data.health_score)"
              :stroke-width="20"
            />
          </el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="getRiskTagType(storeDetail.data.risk_level)" size="small">
              {{ getRiskLabel(storeDetail.data.risk_level) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="GMV">¥{{ storeDetail.data.gmv.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="订单数">{{ storeDetail.data.order_count }}</el-descriptions-item>
          <el-descriptions-item label="客单价">¥{{ storeDetail.data.avg_order_value.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="转化率">{{ storeDetail.data.conversion_rate.toFixed(2) }}%</el-descriptions-item>
          <el-descriptions-item label="浏览量">{{ storeDetail.data.page_views }}</el-descriptions-item>
          <el-descriptions-item label="访客数">{{ storeDetail.data.unique_visitors }}</el-descriptions-item>
          <el-descriptions-item label="客户满意度">{{ storeDetail.data.customer_satisfaction.toFixed(1) }}⭐</el-descriptions-item>
          <el-descriptions-item label="库存周转">{{ storeDetail.data.inventory_turnover.toFixed(1) }}次</el-descriptions-item>
        </el-descriptions>
        
        <!-- 评分明细 -->
        <el-card style="margin-top: 20px;" v-if="storeDetail.data.score_breakdown">
          <template #header>
            <span>评分明细</span>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="GMV得分">{{ storeDetail.data.score_breakdown.gmv_score }}</el-descriptions-item>
            <el-descriptions-item label="转化得分">{{ storeDetail.data.score_breakdown.conversion_score }}</el-descriptions-item>
            <el-descriptions-item label="库存得分">{{ storeDetail.data.score_breakdown.inventory_score }}</el-descriptions-item>
            <el-descriptions-item label="服务得分">{{ storeDetail.data.score_breakdown.service_score }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'
import * as echarts from 'echarts'
import { handleApiError } from '@/utils/errorHandler'
import { formatNumber, formatCurrency, formatPercent, formatInteger } from '@/utils/dataFormatter'

// Mock数据开关已移除，所有API直接使用真实后端API

// 筛选器
const filters = reactive({
  shopId: null,
  platform: '',
  granularity: 'daily'
})

const dateRange = ref([])
const selectedShops = ref([])
const alertFilter = ref('')

// Mock店铺列表
const availableShops = ref([
  { id: 'shopee_sg_001', name: 'Shopee新加坡旗舰店' },
  { id: 'lazada_sg_001', name: 'Lazada新加坡店' },
  { id: 'shopee_my_001', name: 'Shopee马来旗舰店' },
  { id: 'lazada_my_001', name: 'Lazada马来店' },
  { id: 'shopee_th_001', name: 'Shopee泰国旗舰店' }
])

// 数据状态
const healthScore = reactive({
  data: [],
  loading: false
})

const gmvTrend = reactive({
  data: [],
  loading: false
})

const conversionAnalysis = reactive({
  data: [],
  loading: false
})

const trafficAnalysis = reactive({
  data: [],
  loading: false
})

const comparison = reactive({
  data: [],
  loading: false
})

const alerts = reactive({
  data: [],
  loading: false
})

const storeDetail = reactive({
  data: null,
  loading: false
})

const detailVisible = ref(false)

// 图表引用
const gmvChart = ref(null)
const conversionChart = ref(null)
let gmvChartInstance = null
let conversionChartInstance = null

// 加载店铺健康度评分
const loadHealthScore = async () => {
  healthScore.loading = true
  try {
    const response = await api.getStoreHealthScores({
      shop_id: filters.shopId || undefined,
      platform_code: filters.platform || undefined
    })
    
    // 响应拦截器已处理success字段，分页响应直接返回data数组
    if (response && Array.isArray(response)) {
      healthScore.data = response
    } else if (response && response.data) {
      healthScore.data = response.data
    } else {
      healthScore.data = []
    }
  } catch (error) {
    console.error('加载健康度评分失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    healthScore.loading = false
  }
}

// 加载GMV趋势
const loadGMVTrend = async () => {
  gmvTrend.loading = true
  try {
    const params = {
      shop_id: filters.shopId || undefined,
      platform_code: filters.platform || undefined,
      granularity: filters.granularity
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0].toISOString().split('T')[0]
      params.end_date = dateRange.value[1].toISOString().split('T')[0]
    }
    
    const response = await api.getStoreGMVTrend(params)
    gmvTrend.data = response || []
    await nextTick()
    renderGMVChart()
  } catch (error) {
    console.error('加载GMV趋势失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    gmvTrend.loading = false
  }
}

// 加载转化率分析
const loadConversionAnalysis = async () => {
  conversionAnalysis.loading = true
  try {
    const params = {
      shop_id: filters.shopId || undefined,
      platform_code: filters.platform || undefined,
      granularity: filters.granularity
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0].toISOString().split('T')[0]
      params.end_date = dateRange.value[1].toISOString().split('T')[0]
    }
    
    const response = await api.getStoreConversionAnalysis(params)
    conversionAnalysis.data = response || []
    await nextTick()
    renderConversionChart()
  } catch (error) {
    console.error('加载转化率分析失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    conversionAnalysis.loading = false
  }
}

// 加载店铺对比分析
const loadComparison = async () => {
  comparison.loading = true
  try {
    if (selectedShops.value.length === 0) {
      comparison.data = []
      comparison.loading = false
      return
    }
    
    // 构建shop_ids参数（格式：platform_code:shop_id）
    const shopIds = selectedShops.value.map(shopId => {
      // 假设shopId格式为platform_shopId，需要解析
      // TODO: 根据实际店铺数据结构调整
      return shopId
    }).join(',')
    
    const response = await api.getStoreComparison({ shop_ids: shopIds })
    comparison.data = response || []
  } catch (error) {
    console.error('加载对比分析失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    comparison.loading = false
  }
}

// 加载预警提醒
const loadAlerts = async () => {
  alerts.loading = true
  try {
    const params = {
      shop_id: filters.shopId || undefined,
      platform_code: filters.platform || undefined,
      alert_level: alertFilter.value || undefined
    }
    
    const response = await api.getStoreAlerts(params)
    alerts.data = response || []
  } catch (error) {
    console.error('加载预警提醒失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    alerts.loading = false
  }
}

// 查看详情
const handleViewDetail = async (row) => {
  detailVisible.value = true
  storeDetail.loading = true
  try {
    // 从健康度评分数据中获取详情（暂时使用现有数据）
    // TODO: 未来可以从API获取完整详情
    storeDetail.data = {
      shop_name: row.shop_name,
      platform: row.platform_code || row.platform,
      region: '新加坡', // TODO: 从dim_shops获取
      health_score: row.health_score,
      gmv: row.gmv,
      order_count: Math.floor(row.gmv / 50), // 临时计算
      avg_order_value: 50.00,
      conversion_rate: row.conversion_rate,
      page_views: 0, // TODO: 从fact_product_metrics获取
      unique_visitors: 0, // TODO: 从fact_product_metrics获取
      customer_satisfaction: row.customer_satisfaction,
      inventory_turnover: row.inventory_turnover,
      risk_level: row.risk_level,
      score_breakdown: {
        gmv_score: row.gmv_score,
        conversion_score: row.conversion_score,
        inventory_score: row.inventory_score,
        service_score: row.service_score
      }
    }
  } catch (error) {
    console.error('加载店铺详情失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    storeDetail.loading = false
  }
}

// 渲染GMV趋势图表
const renderGMVChart = () => {
  if (!gmvChart.value || !gmvTrend.data.length) return
  
  if (gmvChartInstance) {
    gmvChartInstance.dispose()
  }
  
  gmvChartInstance = echarts.init(gmvChart.value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      }
    },
    legend: {
      data: ['GMV', '订单数']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: gmvTrend.data.map(item => item.date)
    },
    yAxis: [
      {
        type: 'value',
        name: 'GMV(CNY)',
        position: 'left'
      },
      {
        type: 'value',
        name: '订单数',
        position: 'right'
      }
    ],
    series: [
      {
        name: 'GMV',
        type: 'line',
        smooth: true,
        data: gmvTrend.data.map(item => item.gmv_cny.toFixed(2)),
        itemStyle: { color: '#409EFF' }
      },
      {
        name: '订单数',
        type: 'bar',
        yAxisIndex: 1,
        data: gmvTrend.data.map(item => item.order_count),
        itemStyle: { color: '#67C23A' }
      }
    ]
  }
  
  gmvChartInstance.setOption(option)
}

// 渲染转化率分析图表
const renderConversionChart = () => {
  if (!conversionChart.value || !conversionAnalysis.data.length) return
  
  if (conversionChartInstance) {
    conversionChartInstance.dispose()
  }
  
  conversionChartInstance = echarts.init(conversionChart.value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      }
    },
    legend: {
      data: ['转化率', '加购率']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: conversionAnalysis.data.map(item => item.date)
    },
    yAxis: {
      type: 'value',
      name: '百分比(%)',
      max: 100
    },
    series: [
      {
        name: '转化率',
        type: 'line',
        smooth: true,
        data: conversionAnalysis.data.map(item => item.conversion_rate),
        itemStyle: { color: '#E6A23C' }
      },
      {
        name: '加购率',
        type: 'line',
        smooth: true,
        data: conversionAnalysis.data.map(item => item.add_to_cart_rate),
        itemStyle: { color: '#F56C6C' }
      }
    ]
  }
  
  conversionChartInstance.setOption(option)
}

// 渲染流量分析图表
const renderTrafficChart = () => {
  if (!trafficChart.value) {
    console.warn('流量图表容器未准备好')
    return
  }
  
  if (!trafficAnalysis.data || trafficAnalysis.data.length === 0) {
    console.warn('流量分析数据为空，无法渲染图表')
    // 清空图表容器，显示空状态
    if (trafficChartInstance) {
      trafficChartInstance.dispose()
      trafficChartInstance = null
    }
    return
  }
  
  if (trafficChartInstance) {
    trafficChartInstance.dispose()
    trafficChartInstance = null
  }
  
  // 确保容器存在且有尺寸
  if (!trafficChart.value || trafficChart.value.offsetWidth === 0) {
    console.warn('流量图表容器尺寸为0，延迟渲染')
    setTimeout(() => renderTrafficChart(), 200)
    return
  }
  
  trafficChartInstance = echarts.init(trafficChart.value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross'
      }
    },
    legend: {
      data: ['浏览量(PV)', '访客数(UV)', '转化率', '加购率']
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: trafficAnalysis.data.map(item => item.date)
    },
    yAxis: [
      {
        type: 'value',
        name: '数量',
        position: 'left',
        axisLabel: {
          formatter: '{value}'
        }
      },
      {
        type: 'value',
        name: '百分比(%)',
        position: 'right',
        max: 100,
        axisLabel: {
          formatter: '{value}%'
        }
      }
    ],
    series: [
      {
        name: '浏览量(PV)',
        type: 'bar',
        yAxisIndex: 0,
        data: trafficAnalysis.data.map(item => item.page_views),
        itemStyle: { color: '#409EFF' }
      },
      {
        name: '访客数(UV)',
        type: 'bar',
        yAxisIndex: 0,
        data: trafficAnalysis.data.map(item => item.unique_visitors),
        itemStyle: { color: '#67C23A' }
      },
      {
        name: '转化率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: trafficAnalysis.data.map(item => parseFloat(item.conversion_rate || 0)),
        itemStyle: { color: '#E6A23C' }
      },
      {
        name: '加购率',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: trafficAnalysis.data.map(item => parseFloat(item.add_to_cart_rate || 0)),
        itemStyle: { color: '#F56C6C' }
      }
    ]
  }
  
  trafficChartInstance.setOption(option)
}

// 加载店铺流量分析
const loadTrafficAnalysis = async () => {
  trafficAnalysis.loading = true
  try {
    const params = {
      shop_id: filters.shopId || undefined,
      platform_code: filters.platform || undefined,
      granularity: filters.granularity
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0].toISOString().split('T')[0]
      params.end_date = dateRange.value[1].toISOString().split('T')[0]
    }
    
    const response = await api.getStoreTrafficAnalysis(params)
    trafficAnalysis.data = response || []
    console.log('流量分析数据加载成功:', trafficAnalysis.data.length, '条记录')
    if (trafficAnalysis.data.length > 0) {
      // 等待DOM更新后再渲染图表
      await nextTick()
      // 额外延迟确保图表容器已完全渲染
      setTimeout(() => {
        renderTrafficChart()
      }, 100)
    } else {
      ElMessage.warning('暂无流量数据，请选择店铺或调整日期范围')
    }
  } catch (error) {
    console.error('加载流量分析失败:', error)
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    trafficAnalysis.loading = false
  }
}

// 筛选器变化
const handleFilterChange = () => {
  loadHealthScore()
  loadGMVTrend()
  loadConversionAnalysis()
  loadTrafficAnalysis()
  loadAlerts()
}

// 日期范围变化
const handleDateRangeChange = () => {
  loadGMVTrend()
}

// 刷新所有数据
const refreshAll = () => {
  loadHealthScore()
  loadGMVTrend()
  loadConversionAnalysis()
  loadTrafficAnalysis()
  loadComparison()
  loadAlerts()
}

// 辅助函数
const getHealthColor = (score) => {
  if (score >= 90) return '#67C23A'
  if (score >= 80) return '#E6A23C'
  if (score >= 70) return '#F56C6C'
  return '#909399'
}

const getRiskLabel = (level) => {
  const map = {
    low: '低风险',
    medium: '中风险',
    high: '高风险'
  }
  return map[level] || level
}

const getRiskTagType = (level) => {
  const map = {
    low: 'success',
    medium: 'warning',
    high: 'danger'
  }
  return map[level] || ''
}

const getAlertLabel = (level) => {
  const map = {
    critical: '严重',
    warning: '警告',
    info: '提示'
  }
  return map[level] || level
}

const getAlertTagType = (level) => {
  const map = {
    critical: 'danger',
    warning: 'warning',
    info: 'info'
  }
  return map[level] || ''
}

onMounted(() => {
  refreshAll()
  // 窗口大小变化时重新渲染图表
  window.addEventListener('resize', () => {
    if (gmvChartInstance) gmvChartInstance.resize()
    if (conversionChartInstance) conversionChartInstance.resize()
    if (trafficChartInstance) trafficChartInstance.resize()
  })
  
})
</script>

<style scoped>
.store-analytics {
  padding: 20px;
}

.action-bar {
  display: flex;
  align-items: center;
}

/* 企业级表格样式 */
.erp-table :deep(.el-table__fixed-left) {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table__fixed-right) {
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
