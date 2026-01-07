<template>
  <div class="sales-trend-chart">
    <!-- 页头 -->
    <div class="page-header">
      <h1>📈 销售趋势分析</h1>
      <p class="subtitle">基于物化视图的时间序列分析 v4.9.1</p>
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

        <el-form-item label="SKU">
          <el-input v-model="filters.platform_sku" placeholder="输入SKU" clearable style="width: 200px" />
        </el-form-item>

        <el-form-item label="天数">
          <el-select v-model="filters.days" @change="loadData">
            <el-option label="最近7天" :value="7"></el-option>
            <el-option label="最近30天" :value="30"></el-option>
            <el-option label="最近90天" :value="90"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 趋势图表 -->
    <el-row :gutter="20" v-loading="loading">
      <!-- 销量趋势 -->
      <el-col :span="24">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>销量趋势分析</span>
              <span class="query-time">查询耗时: {{ queryTime }}ms | 数据源: 物化视图</span>
            </div>
          </template>
          <div ref="salesChart" style="width: 100%; height: 400px;"></div>
        </el-card>
      </el-col>

      <!-- 环比增长 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>环比增长率</template>
          <div ref="growthChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- 累计销量 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>累计销量</template>
          <div ref="cumulativeChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- 数据表格 -->
      <el-col :span="24">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>趋势数据详情</span>
              <el-button type="primary" size="small" @click="exportData">导出Excel</el-button>
            </div>
          </template>
          
          <el-table :data="trendData" stripe max-height="400">
            <el-table-column prop="metric_date" label="日期" width="120" />
            <el-table-column prop="sales_volume" label="销量" width="100" align="right" />
            <el-table-column prop="sales_7d_avg" label="7日均线" width="100" align="right">
              <template #default="{row}">{{ (row.sales_7d_avg || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="sales_30d_avg" label="30日均线" width="100" align="right">
              <template #default="{row}">{{ (row.sales_30d_avg || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="growth_rate_pct" label="环比增长" width="120" align="right">
              <template #default="{row}">
                <span :style="{color: row.growth_rate_pct >= 0 ? '#67c23a' : '#f56c6c'}">
                  {{ (row.growth_rate_pct || 0).toFixed(2) }}%
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="cumulative_sales" label="累计销量" width="120" align="right" />
            <el-table-column prop="sales_amount_rmb" label="销售额(CNY)" width="140" align="right">
              <template #default="{row}">¥{{ (row.sales_amount_rmb || 0).toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 数据为空提示 -->
    <el-empty v-if="!loading && trendData.length === 0" description="暂无趋势数据，请先采集并入库产品数据" />
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const loading = ref(false)
const trendData = ref([])
const queryTime = ref(0)
const salesChart = ref(null)
const growthChart = ref(null)
const cumulativeChart = ref(null)

const filters = ref({
  platform: '',
  platform_sku: '',
  days: 30
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.querySalesTrend(filters.value)
    // 响应拦截器已提取data字段，直接使用
    if (res) {
      trendData.value = res.data || res || []
      queryTime.value = res.query_time_ms?.toFixed(2) || '0.00'
      
      if (trendData.value.length > 0) {
        await nextTick()
        renderCharts()
        ElMessage.success(`加载成功: ${trendData.value.length}条数据`)
      } else {
        ElMessage.warning('暂无数据，请先采集并入库产品数据')
      }
    }
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const renderCharts = () => {
  if (!trendData.value.length) return
  
  const dates = trendData.value.map(d => d.metric_date)
  const sales = trendData.value.map(d => d.sales_volume || 0)
  const avg7d = trendData.value.map(d => d.sales_7d_avg || 0)
  const avg30d = trendData.value.map(d => d.sales_30d_avg || 0)
  const growth = trendData.value.map(d => d.growth_rate_pct || 0)
  const cumulative = trendData.value.map(d => d.cumulative_sales || 0)
  
  // 销量趋势图
  if (salesChart.value) {
    const chart = echarts.init(salesChart.value)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['实际销量', '7日均线', '30日均线'] },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'value', name: '销量' },
      series: [
        { name: '实际销量', type: 'bar', data: sales, itemStyle: { color: '#409eff' } },
        { name: '7日均线', type: 'line', data: avg7d, smooth: true, itemStyle: { color: '#67c23a' } },
        { name: '30日均线', type: 'line', data: avg30d, smooth: true, itemStyle: { color: '#e6a23c' } }
      ]
    })
  }
  
  // 环比增长图
  if (growthChart.value) {
    const chart = echarts.init(growthChart.value)
    chart.setOption({
      tooltip: { trigger: 'axis', formatter: '{b}<br/>{a}: {c}%' },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'value', name: '增长率(%)' },
      series: [{
        name: '环比增长',
        type: 'bar',
        data: growth,
        itemStyle: {
          color: (params) => params.value >= 0 ? '#67c23a' : '#f56c6c'
        }
      }]
    })
  }
  
  // 累计销量图
  if (cumulativeChart.value) {
    const chart = echarts.init(cumulativeChart.value)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'value', name: '累计销量' },
      series: [{
        name: '累计销量',
        type: 'line',
        data: cumulative,
        smooth: true,
        areaStyle: { color: 'rgba(64, 158, 255, 0.2)' },
        itemStyle: { color: '#409eff' }
      }]
    })
  }
}

const exportData = () => {
  ElMessage.info('导出功能开发中...')
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.sales-trend-chart {
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

.chart-card {
  margin-top: 20px;
}
</style>

