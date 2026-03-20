<template>
  <div class="product-quality-dashboard">
    <!-- 页头 -->
    <div class="page-header">
      <h1>⭐ 产品质量仪表盘</h1>
      <p class="subtitle">基于物化视图的产品健康度与质量分析 v4.9.0</p>
    </div>

    <!-- 筛选器 -->
    <el-card class="filter-card" shadow="hover">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="全部平台" clearable @change="loadData">
            <el-option label="全部" value=""></el-option>
            <el-option label="妙手ERP" value="miaoshou"></el-option>
            <el-option label="Shopee" value="shopee"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">刷新数据</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" v-loading="loading">
      <!-- 质量指标总览 -->
      <el-col :span="24">
        <el-card class="summary-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>产品质量指标总览</span>
              <el-tag type="info" size="small">数据源: 物化视图</el-tag>
            </div>
          </template>
          
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="stat-box excellent">
                <div class="stat-icon">🌟</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(qualityStats.excellent) }}</div>
                  <div class="stat-label">优质产品 (≥80分)</div>
                  <div class="stat-percent">{{ getPercent(qualityStats.excellent, qualityStats.total) }}</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box good">
                <div class="stat-icon">👍</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(qualityStats.good) }}</div>
                  <div class="stat-label">良好产品 (60-80分)</div>
                  <div class="stat-percent">{{ getPercent(qualityStats.good, qualityStats.total) }}</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box average">
                <div class="stat-icon">📊</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(qualityStats.average) }}</div>
                  <div class="stat-label">一般产品 (40-60分)</div>
                  <div class="stat-percent">{{ getPercent(qualityStats.average, qualityStats.total) }}</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box poor">
                <div class="stat-icon">⚠️</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(qualityStats.poor) }}</div>
                  <div class="stat-label">问题产品 (<40分)</div>
                  <div class="stat-percent">{{ getPercent(qualityStats.poor, qualityStats.total) }}</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <!-- 健康度分布图表 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>健康度分布</template>
          <div ref="healthChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- 转化率分析 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>转化率分布</template>
          <div ref="conversionChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- TopN优质产品 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>Top10 优质产品</span>
              <span class="query-time">健康度 ≥ 80分</span>
            </div>
          </template>
          
          <div class="product-list">
            <div v-for="(item, index) in excellentProducts" :key="item.platform_sku" class="product-item">
              <div class="product-rank">{{ index + 1 }}</div>
              <div class="product-info">
                <div class="product-name">{{ item.product_name || item.platform_sku }}</div>
                <div class="product-detail">
                  SKU: {{ item.platform_sku }} | 
                  评分: {{ (item.rating || 0).toFixed(1) }}⭐ | 
                  转化率: {{ ((item.conversion_rate || 0) * 100).toFixed(2) }}%
                </div>
              </div>
              <el-progress 
                :percentage="Math.round(item.product_health_score || 0)" 
                :color="getHealthColor(item.product_health_score)"
                style="width: 150px"
              />
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 问题产品预警 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>问题产品预警</span>
              <span class="query-time">健康度 < 40分</span>
            </div>
          </template>
          
          <div class="product-list">
            <div v-for="(item, index) in poorProducts" :key="item.platform_sku" class="product-item warning">
              <div class="product-rank danger">{{ index + 1 }}</div>
              <div class="product-info">
                <div class="product-name">{{ item.product_name || item.platform_sku }}</div>
                <div class="product-detail">
                  SKU: {{ item.platform_sku }} | 
                  库存: {{ item.stock || 0 }} | 
                  销量: {{ item.sales_volume || 0 }}
                </div>
              </div>
              <el-progress 
                :percentage="Math.round(item.product_health_score || 0)" 
                :color="getHealthColor(item.product_health_score)"
                style="width: 150px"
              />
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 店铺质量对比 -->
      <el-col :span="24">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>店铺产品质量对比</span>
              <span class="query-time">查询耗时: {{ queryTime }}ms</span>
            </div>
          </template>
          
          <el-table :data="shopData" stripe style="width: 100%">
            <el-table-column prop="shop_name" label="店铺" width="150" />
            <el-table-column label="总产品数" width="120" align="right">
              <template #default="{row}">{{ formatNumber(row.total_products) }}</template>
            </el-table-column>
            <el-table-column label="平均健康度" width="150">
              <template #default="{row}">
                <el-progress 
                  :percentage="Math.round(row.avg_health_score || 0)" 
                  :color="getHealthColor(row.avg_health_score)"
                />
              </template>
            </el-table-column>
            <el-table-column label="平均评分" width="120" align="right">
              <template #default="{row}">
                <span>{{ (row.avg_rating || 0).toFixed(2) }}⭐</span>
              </template>
            </el-table-column>
            <el-table-column label="平均转化率" width="120" align="right">
              <template #default="{row}">
                <span>{{ ((row.avg_conversion_rate || 0) * 100).toFixed(2) }}%</span>
              </template>
            </el-table-column>
            <el-table-column label="总销售额(CNY)" width="150" align="right">
              <template #default="{row}">
                <span>¥{{ formatNumber((row.total_sales_amount_rmb || 0).toFixed(0)) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="质量等级" width="120">
              <template #default="{row}">
                <el-tag :type="getQualityTagType(row.avg_health_score)">
                  {{ getQualityLabel(row.avg_health_score) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'
import echarts from '@/utils/echarts'

const loading = ref(false)
const shopData = ref([])
const excellentProducts = ref([])
const poorProducts = ref([])
const queryTime = ref(0)
const healthChart = ref(null)
const conversionChart = ref(null)

const filters = ref({
  platform: ''
})

const qualityStats = ref({
  total: 0,
  excellent: 0,
  good: 0,
  average: 0,
  poor: 0
})

const loadData = async () => {
  loading.value = true
  try {
    // 查询店铺汇总
    const shopRes = await api.queryShopSummary(filters.value)
    // 响应拦截器已提取data字段，直接使用
    if (shopRes) {
      shopData.value = shopRes
      queryTime.value = shopRes.query_time_ms?.toFixed(2) || '0.00'
    }
    
    // 查询优质产品
    const excellentRes = await api.queryTopProducts({
      platform: filters.value.platform,
      limit: 10,
      order_by: 'health_rank'
    })
    if (excellentRes.success) {
      excellentProducts.value = excellentRes.data
    }
    
    // 查询所有产品用于统计（使用库存管理API）
    const allProducts = await api._get('/products/products', {
      params: {
        platform: filters.value.platform || undefined,
        page: 1,
        page_size: 1000
      }
    })
    
    if (allProducts.success) {
      const products = allProducts.data
      qualityStats.value = {
        total: products.length,
        excellent: products.filter(p => (p.product_health_score || 0) >= 80).length,
        good: products.filter(p => (p.product_health_score || 0) >= 60 && (p.product_health_score || 0) < 80).length,
        average: products.filter(p => (p.product_health_score || 0) >= 40 && (p.product_health_score || 0) < 60).length,
        poor: products.filter(p => (p.product_health_score || 0) < 40).length
      }
      
      // 问题产品
      poorProducts.value = products
        .filter(p => (p.product_health_score || 0) < 40)
        .sort((a, b) => (a.product_health_score || 0) - (b.product_health_score || 0))
        .slice(0, 10)
      
      // 绘制图表
      await nextTick()
      renderHealthChart(products)
      renderConversionChart(products)
    }
    
    ElMessage.success('数据加载成功')
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const renderHealthChart = (products) => {
  if (!healthChart.value) return
  
  const chart = echarts.init(healthChart.value)
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    xAxis: {
      type: 'category',
      data: ['0-20', '20-40', '40-60', '60-80', '80-100']
    },
    yAxis: {
      type: 'value',
      name: '产品数量'
    },
    series: [{
      data: [
        products.filter(p => (p.product_health_score || 0) < 20).length,
        products.filter(p => (p.product_health_score || 0) >= 20 && (p.product_health_score || 0) < 40).length,
        products.filter(p => (p.product_health_score || 0) >= 40 && (p.product_health_score || 0) < 60).length,
        products.filter(p => (p.product_health_score || 0) >= 60 && (p.product_health_score || 0) < 80).length,
        products.filter(p => (p.product_health_score || 0) >= 80).length
      ],
      type: 'bar',
      itemStyle: {
        color: (params) => {
          const colors = ['#f56c6c', '#e6a23c', '#409eff', '#67c23a', '#13ce66']
          return colors[params.dataIndex]
        }
      }
    }]
  }
  chart.setOption(option)
}

const renderConversionChart = (products) => {
  if (!conversionChart.value) return
  
  const chart = echarts.init(conversionChart.value)
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    xAxis: {
      type: 'category',
      data: ['0-2%', '2-5%', '5-10%', '10-20%', '>20%']
    },
    yAxis: {
      type: 'value',
      name: '产品数量'
    },
    series: [{
      data: [
        products.filter(p => (p.conversion_rate || 0) < 0.02).length,
        products.filter(p => (p.conversion_rate || 0) >= 0.02 && (p.conversion_rate || 0) < 0.05).length,
        products.filter(p => (p.conversion_rate || 0) >= 0.05 && (p.conversion_rate || 0) < 0.1).length,
        products.filter(p => (p.conversion_rate || 0) >= 0.1 && (p.conversion_rate || 0) < 0.2).length,
        products.filter(p => (p.conversion_rate || 0) >= 0.2).length
      ],
      type: 'bar',
      itemStyle: {
        color: '#409eff'
      }
    }]
  }
  chart.setOption(option)
}

const getHealthColor = (score) => {
  if (score >= 80) return '#67c23a'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
}

const getQualityTagType = (score) => {
  if (score >= 80) return 'success'
  if (score >= 60) return ''
  if (score >= 40) return 'info'
  return 'danger'
}

const getQualityLabel = (score) => {
  if (score >= 80) return '优质'
  if (score >= 60) return '良好'
  if (score >= 40) return '一般'
  return '需改进'
}

const formatNumber = (num) => {
  return (num || 0).toLocaleString()
}

const getPercent = (part, total) => {
  if (!total) return '0%'
  return ((part / total) * 100).toFixed(1) + '%'
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.product-quality-dashboard {
  padding: 20px;
}

.page-header h1 {
  font-size: 24px;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #909399;
  margin: 0 0 20px 0;
}

.filter-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.query-time {
  font-size: 12px;
  color: #909399;
}

.stat-box {
  display: flex;
  align-items: center;
  padding: 20px;
  border-radius: 8px;
  color: white;
}

.stat-box.excellent {
  background: linear-gradient(135deg, #13ce66 0%, #35d98a 100%);
}

.stat-box.good {
  background: linear-gradient(135deg, #67c23a 0%, #85ce61 100%);
}

.stat-box.average {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
}

.stat-box.poor {
  background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%);
}

.stat-icon {
  font-size: 40px;
  margin-right: 15px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.stat-percent {
  font-size: 12px;
  margin-top: 5px;
  opacity: 0.8;
}

.chart-card {
  margin-top: 20px;
}

.product-list {
  max-height: 350px;
  overflow-y: auto;
}

.product-item {
  display: flex;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
}

.product-item:last-child {
  border-bottom: none;
}

.product-rank {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  margin-right: 15px;
  flex-shrink: 0;
}

.product-rank.danger {
  background: linear-gradient(135deg, #f56c6c 0%, #f78989 100%);
}

.product-info {
  flex: 1;
  margin-right: 15px;
}

.product-name {
  font-weight: 500;
  margin-bottom: 4px;
}

.product-detail {
  font-size: 12px;
  color: #909399;
}
</style>

