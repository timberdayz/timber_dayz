<template>
  <div class="dashboard-container">
    <!-- 状态概览 -->
    <el-row :gutter="20" class="status-overview">
      <el-col :span="6">
        <el-card class="status-card" shadow="hover">
          <div class="status-item">
            <div class="status-icon">
              <el-icon size="30" color="#67C23A"><Files /></el-icon>
            </div>
            <div class="status-info">
              <div class="status-value">{{ catalogStats.totalFiles || 0 }}</div>
              <div class="status-label">总文件数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card" shadow="hover">
          <div class="status-item">
            <div class="status-icon">
              <el-icon size="30" color="#409EFF"><DataBoard /></el-icon>
            </div>
            <div class="status-info">
              <div class="status-value">{{ catalogStats.processedFiles || 0 }}</div>
              <div class="status-label">已处理文件</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card" shadow="hover">
          <div class="status-item">
            <div class="status-icon">
              <el-icon size="30" color="#E6A23C"><Warning /></el-icon>
            </div>
            <div class="status-info">
              <div class="status-value">{{ catalogStats.pendingFiles || 0 }}</div>
              <div class="status-label">待处理文件</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="status-card" shadow="hover">
          <div class="status-item">
            <div class="status-icon">
              <el-icon size="30" color="#F56C6C"><CircleClose /></el-icon>
            </div>
            <div class="status-info">
              <div class="status-value">{{ catalogStats.failedFiles || 0 }}</div>
              <div class="status-label">失败文件</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="charts-section">
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <h4>📊 平台文件分布</h4>
          </template>
          <div ref="platformChart" class="chart-container"></div>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>
            <h4>📈 数据域分布</h4>
          </template>
          <div ref="domainChart" class="chart-container"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近文件列表 -->
    <el-card class="recent-files-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <h4>🕒 最近处理的文件</h4>
          <el-button 
            type="primary" 
            size="small"
            :loading="dataStore.loading.catalog"
            @click="refreshData"
          >
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      
      <el-table 
        :data="recentFiles" 
        style="width: 100%"
        v-loading="dataStore.loading.catalog"
      >
        <el-table-column prop="file_name" label="文件名" width="300" />
        <el-table-column prop="platform_code" label="平台" width="100">
          <template #default="{ row }">
            <el-tag :type="getPlatformType(row.platform_code)">
              {{ row.platform_code?.toUpperCase() || 'UNKNOWN' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="data_domain" label="数据域" width="120">
          <template #default="{ row }">
            <el-tag type="info">{{ row.data_domain || 'unknown' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ row.status || 'pending' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="first_seen_at" label="发现时间" width="180" />
        <el-table-column prop="last_processed_at" label="最后处理" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useDataStore } from '../stores/data'
import * as echarts from 'echarts'

const dataStore = useDataStore()

// 响应式数据
const platformChart = ref(null)
const domainChart = ref(null)

// 计算属性
const catalogStats = computed(() => {
  const status = dataStore.catalogStatus
  if (!status) return { totalFiles: 0, processedFiles: 0, pendingFiles: 0, failedFiles: 0 }
  
  return {
    totalFiles: status.total || 0,
    processedFiles: status.by_status?.find(s => s.status === 'processed')?.count || 0,
    pendingFiles: status.by_status?.find(s => s.status === 'pending')?.count || 0,
    failedFiles: status.by_status?.find(s => s.status === 'failed')?.count || 0
  }
})

const recentFiles = computed(() => {
  // 模拟最近文件数据
  return [
    {
      file_name: 'shopee_products_20250116.xlsx',
      platform_code: 'shopee',
      data_domain: 'products',
      status: 'processed',
      first_seen_at: '2025-01-16 10:30:00',
      last_processed_at: '2025-01-16 10:35:00'
    },
    {
      file_name: 'tiktok_orders_20250116.xlsx',
      platform_code: 'tiktok',
      data_domain: 'orders',
      status: 'pending',
      first_seen_at: '2025-01-16 11:00:00',
      last_processed_at: null
    },
    {
      file_name: 'miaoshou_traffic_20250116.xlsx',
      platform_code: 'miaoshou',
      data_domain: 'traffic',
      status: 'failed',
      first_seen_at: '2025-01-16 11:15:00',
      last_processed_at: '2025-01-16 11:20:00'
    }
  ]
})

// 方法
const refreshData = async () => {
  await dataStore.refreshCatalogStatus()
  await nextTick()
  updateCharts()
}

const updateCharts = () => {
  updatePlatformChart()
  updateDomainChart()
}

const updatePlatformChart = () => {
  if (!platformChart.value) return
  
  const chart = echarts.init(platformChart.value)
  const status = dataStore.catalogStatus
  
  const platformData = status?.by_platform || [
    { platform: 'shopee', count: 45 },
    { platform: 'tiktok', count: 32 },
    { platform: 'miaoshou', count: 28 },
    { platform: 'amazon', count: 15 }
  ]
  
  const option = {
    tooltip: {
      trigger: 'item'
    },
    series: [
      {
        name: '平台文件分布',
        type: 'pie',
        radius: '50%',
        data: platformData.map(item => ({
          value: item.count,
          name: item.platform.toUpperCase()
        })),
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        }
      }
    ]
  }
  
  chart.setOption(option)
}

const updateDomainChart = () => {
  if (!domainChart.value) return
  
  const chart = echarts.init(domainChart.value)
  const status = dataStore.catalogStatus
  
  const domainData = status?.by_domain || [
    { domain: 'products', count: 60 },
    { domain: 'orders', count: 35 },
    { domain: 'traffic', count: 20 },
    { domain: 'service', count: 5 }
  ]
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    xAxis: {
      type: 'category',
      data: domainData.map(item => item.domain)
    },
    yAxis: {
      type: 'value'
    },
    series: [
      {
        name: '文件数量',
        type: 'bar',
        data: domainData.map(item => item.count),
        itemStyle: {
          color: '#409EFF'
        }
      }
    ]
  }
  
  chart.setOption(option)
}

const getPlatformType = (platform) => {
  const types = {
    'shopee': 'success',
    'tiktok': 'warning',
    'miaoshou': 'info',
    'amazon': 'danger'
  }
  return types[platform] || 'info'
}

const getStatusType = (status) => {
  const types = {
    'processed': 'success',
    'pending': 'warning',
    'failed': 'danger'
  }
  return types[status] || 'info'
}

// 生命周期
onMounted(async () => {
  await dataStore.loadInitialData()
  await nextTick()
  updateCharts()
  
  // 监听窗口大小变化
  window.addEventListener('resize', () => {
    if (platformChart.value) echarts.init(platformChart.value).resize()
    if (domainChart.value) echarts.init(domainChart.value).resize()
  })
})
</script>

<style scoped>
.dashboard-container {
  padding: 20px;
}

.status-overview {
  margin-bottom: 20px;
}

.status-card {
  height: 100px;
}

.status-item {
  display: flex;
  align-items: center;
  height: 100%;
}

.status-icon {
  margin-right: 15px;
}

.status-info {
  flex: 1;
}

.status-value {
  font-size: 24px;
  font-weight: bold;
  color: #2c3e50;
  line-height: 1;
}

.status-label {
  font-size: 14px;
  color: #7f8c8d;
  margin-top: 5px;
}

.charts-section {
  margin-bottom: 20px;
}

.chart-card,
.recent-files-card {
  height: 400px;
}

.chart-container {
  height: 300px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h4 {
  margin: 0;
  color: #2c3e50;
}
</style>
