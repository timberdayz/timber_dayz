<template>
  <div class="inventory-health-dashboard">
    <!-- 页头 -->
    <div class="page-header">
      <h1>📦 库存健康仪表盘</h1>
      <p class="subtitle">基于物化视图的实时库存健康度分析 v4.9.0</p>
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
      <!-- 库存状态总览 -->
      <el-col :span="24">
        <el-card class="summary-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>库存状态总览</span>
              <el-tag type="info" size="small">数据源: 物化视图</el-tag>
            </div>
          </template>
          
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="stat-box total">
                <div class="stat-icon">📊</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(totalStats.products) }}</div>
                  <div class="stat-label">总产品数</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box out-of-stock">
                <div class="stat-icon">🚫</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(totalStats.outOfStock) }}</div>
                  <div class="stat-label">缺货产品</div>
                  <div class="stat-percent">{{ getPercent(totalStats.outOfStock, totalStats.products) }}</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box low-stock">
                <div class="stat-icon">⚠️</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(totalStats.lowStock) }}</div>
                  <div class="stat-label">低库存预警</div>
                  <div class="stat-percent">{{ getPercent(totalStats.lowStock, totalStats.products) }}</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box healthy">
                <div class="stat-icon">✅</div>
                <div class="stat-content">
                  <div class="stat-value">{{ formatNumber(totalStats.healthy) }}</div>
                  <div class="stat-label">健康库存</div>
                  <div class="stat-percent">{{ getPercent(totalStats.healthy, totalStats.products) }}</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <!-- 店铺库存健康度 -->
      <el-col :span="24">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>店铺库存健康度对比</span>
              <span class="query-time">查询耗时: {{ queryTime }}ms</span>
            </div>
          </template>
          
          <el-table :data="shopData" stripe style="width: 100%">
            <el-table-column prop="shop_name" label="店铺" width="150" />
            <el-table-column label="总产品" width="100" align="right">
              <template #default="{row}">{{ formatNumber(row.total_products) }}</template>
            </el-table-column>
            <el-table-column label="缺货" width="100" align="right">
              <template #default="{row}">
                <el-tag type="danger" size="small">{{ formatNumber(row.out_of_stock_count) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="低库存" width="100" align="right">
              <template #default="{row}">
                <el-tag type="warning" size="small">{{ formatNumber(row.low_stock_count) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="中库存" width="100" align="right">
              <template #default="{row}">
                <el-tag type="info" size="small">{{ formatNumber(row.medium_stock_count) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="高库存" width="100" align="right">
              <template #default="{row}">
                <el-tag type="success" size="small">{{ formatNumber(row.high_stock_count) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="总库存量" width="120" align="right">
              <template #default="{row}">{{ formatNumber(row.total_stock) }}</template>
            </el-table-column>
            <el-table-column label="可用库存" width="120" align="right">
              <template #default="{row}">{{ formatNumber(row.total_available_stock) }}</template>
            </el-table-column>
            <el-table-column label="库存健康度" width="150">
              <template #default="{row}">
                <el-progress 
                  :percentage="getStockHealthScore(row)" 
                  :color="getHealthColor(getStockHealthScore(row))"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 库存结构饼图 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>库存结构分布</template>
          <div ref="pieChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- 库存预警列表 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>库存预警Top10</template>
          <div class="warning-list">
            <div v-for="item in warningList" :key="item.platform_sku" class="warning-item">
              <div class="warning-info">
                <div class="warning-name">{{ item.product_name || item.platform_sku }}</div>
                <div class="warning-detail">SKU: {{ item.platform_sku }} | 库存: {{ item.stock || 0 }}</div>
              </div>
              <el-tag :type="item.stock_status === 'out_of_stock' ? 'danger' : 'warning'" size="small">
                {{ item.stock_status === 'out_of_stock' ? '缺货' : '低库存' }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const loading = ref(false)
const shopData = ref([])
const warningList = ref([])
const queryTime = ref(0)
const pieChart = ref(null)

const filters = ref({
  platform: ''
})

const totalStats = ref({
  products: 0,
  outOfStock: 0,
  lowStock: 0,
  healthy: 0
})

const loadData = async () => {
  loading.value = true
  try {
    // 查询店铺汇总
    const res = await api.queryShopSummary(filters.value)
    // 响应拦截器已提取data字段，直接使用
    if (res) {
      shopData.value = res
      queryTime.value = res.query_time_ms?.toFixed(2) || '0.00'
      
      // 计算总统计
      totalStats.value = {
        products: shopData.value.reduce((sum, s) => sum + (s.total_products || 0), 0),
        outOfStock: shopData.value.reduce((sum, s) => sum + (s.out_of_stock_count || 0), 0),
        lowStock: shopData.value.reduce((sum, s) => sum + (s.low_stock_count || 0), 0),
        healthy: shopData.value.reduce((sum, s) => sum + (s.medium_stock_count || 0) + (s.high_stock_count || 0), 0)
      }
      
      // 绘制饼图
      await nextTick()
      renderPieChart()
    }
    
    // 查询预警列表
    const productsRes = await api.getProducts({
      platform: filters.value.platform,
      low_stock: true,
      page: 1,
      page_size: 10
    })
    // 响应拦截器已提取data字段，直接使用
    if (productsRes && productsRes.data) {
      warningList.value = productsRes.data
    }
    
    ElMessage.success('数据加载成功')
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const renderPieChart = () => {
  if (!pieChart.value) return
  
  const chart = echarts.init(pieChart.value)
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: 10,
      top: 'center'
    },
    series: [
      {
        name: '库存结构',
        type: 'pie',
        radius: ['40%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: false,
          position: 'center'
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 20,
            fontWeight: 'bold'
          }
        },
        labelLine: {
          show: false
        },
        data: [
          { value: totalStats.value.outOfStock, name: '缺货', itemStyle: { color: '#f56c6c' } },
          { value: totalStats.value.lowStock, name: '低库存', itemStyle: { color: '#e6a23c' } },
          { value: totalStats.value.healthy, name: '健康库存', itemStyle: { color: '#67c23a' } }
        ]
      }
    ]
  }
  chart.setOption(option)
}

const getStockHealthScore = (shop) => {
  const total = shop.total_products || 1
  const healthy = (shop.medium_stock_count || 0) + (shop.high_stock_count || 0)
  return Math.round((healthy / total) * 100)
}

const getHealthColor = (score) => {
  if (score >= 80) return '#67c23a'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
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
.inventory-health-dashboard {
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
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.stat-box.total {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-box.out-of-stock {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-box.low-stock {
  background: linear-gradient(135deg, #fad0c4 0%, #ffd1ff 100%);
  color: #333;
}

.stat-box.healthy {
  background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
  color: #333;
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

.warning-list {
  max-height: 300px;
  overflow-y: auto;
}

.warning-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
}

.warning-item:last-child {
  border-bottom: none;
}

.warning-info {
  flex: 1;
}

.warning-name {
  font-weight: 500;
  margin-bottom: 4px;
}

.warning-detail {
  font-size: 12px;
  color: #909399;
}
</style>

