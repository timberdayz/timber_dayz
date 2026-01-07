<template>
  <div class="dashboard-container">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>数据看板</h1>
      <p class="subtitle">实时销售数据分析 · 智能决策支持</p>
    </div>

    <!-- KPI卡片区域 -->
    <el-row :gutter="20" class="kpi-row">
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
              <i class="el-icon-money"></i>
            </div>
            <div class="kpi-info">
              <div class="kpi-label">总销售额（GMV）</div>
              <div class="kpi-value">¥{{ formatNumber(kpiData.total_gmv) }}</div>
              <div class="kpi-subtitle">最近30天</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%)">
              <i class="el-icon-shopping-cart-full"></i>
            </div>
            <div class="kpi-info">
              <div class="kpi-label">订单总数</div>
              <div class="kpi-value">{{ formatNumber(kpiData.total_orders) }}</div>
              <div class="kpi-subtitle">最近30天</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
              <i class="el-icon-wallet"></i>
            </div>
            <div class="kpi-info">
              <div class="kpi-label">客单价</div>
              <div class="kpi-value">¥{{ formatNumber(kpiData.avg_order_value) }}</div>
              <div class="kpi-subtitle">平均每单</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%)">
              <i class="el-icon-box"></i>
            </div>
            <div class="kpi-info">
              <div class="kpi-label">商品总数</div>
              <div class="kpi-value">{{ formatNumber(kpiData.total_products) }}</div>
              <div class="kpi-subtitle">在售商品</div>
            </div>
          </div>
        </el-card>
      </el-col>
      
      <el-col :span="6">
        <el-card class="kpi-card">
          <div class="kpi-content">
            <div class="kpi-icon" style="background: linear-gradient(135deg, #34e89e 0%, #0f3443 100%)">
              <i class="el-icon-data-analysis"></i>
            </div>
            <div class="kpi-info">
              <div class="kpi-label">转化率</div>
              <div class="kpi-value">{{ kpiData.conversion_rate !== null ? (kpiData.conversion_rate * 100).toFixed(2) + '%' : '-' }}</div>
              <div class="kpi-subtitle">订单数 / UV</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="20" class="chart-row">
      <!-- GMV趋势图 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>GMV趋势</span>
              <el-select v-model="gmvPeriod" size="small" style="width: 120px">
                <el-option label="最近7天" value="7"></el-option>
                <el-option label="最近30天" value="30"></el-option>
                <el-option label="最近90天" value="90"></el-option>
              </el-select>
            </div>
          </template>
          <div id="gmv-chart" style="height: 350px">
            <div v-if="!chartsReady" class="chart-placeholder">
              <p>📊 ECharts图表组件</p>
              <p class="hint">阶段2将集成ECharts实现专业数据可视化</p>
              <p class="hint">当前显示占位符，功能框架已就绪</p>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 平台销售占比 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>平台销售占比</span>
          </template>
          <div id="platform-chart" style="height: 350px">
            <div v-if="!chartsReady" class="chart-placeholder">
              <p>🥧 饼图展示</p>
              <p class="hint">各平台GMV占比分析</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <!-- TOP商品排行 -->
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>TOP商品排行</span>
          </template>
          <div id="products-chart" style="height: 350px">
            <div v-if="!chartsReady" class="chart-placeholder">
              <p>📊 条形图展示</p>
              <p class="hint">销售额TOP 10商品</p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据来源说明 -->
    <el-alert
      title="数据来源说明"
      type="info"
      :closable="false"
      style="margin-top: 20px"
    >
      <template #default>
        <p>数据来源: PostgreSQL fact_orders 和 fact_product_metrics 表</p>
        <p>更新频率: 实时（数据入库后立即可见）</p>
        <p>缓存策略: Redis缓存5分钟（阶段2实施后启用）</p>
        <p style="color: #E6A23C; margin-top: 10px">
          <strong>当前状态</strong>: 后端API框架已就绪，等待timeout问题解决后启用
        </p>
      </template>
    </el-alert>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import api from '@/api'

// 状态
const loading = ref(false)
const chartsReady = ref(false)  // ECharts是否已加载
const gmvPeriod = ref('30')

// KPI数据
const kpiData = ref({
  total_gmv: 0,
  total_orders: 0,
  avg_order_value: 0,
  total_products: 0,
  conversion_rate: null
})

// 方法
const formatNumber = (num) => {
  if (!num || num === 0) return '0'
  if (num >= 10000) {
    return (num / 10000).toFixed(2) + '万'
  }
  return num.toFixed(2)
}

const loadKPIData = async () => {
  try {
    loading.value = true
    // TODO: 迁移到 Metabase Question API: /dashboard/business-overview/kpi
    // const res = await api.get('/dashboard/business-overview/kpi', {
    //   params: {
    //     start_date: getStartDate(),
    //     end_date: getEndDate()
    //   }
    // })
    // kpiData.value = res?.data || {}
    
    // 临时：显示空数据
    kpiData.value = {
      total_gmv: 0,
      total_orders: 0,
      avg_order_value: 0,
      total_products: 0,
      conversion_rate: null
    }
  } catch (error) {
    console.error('加载KPI数据失败:', error)
    kpiData.value = {
      total_gmv: 0,
      total_orders: 0,
      avg_order_value: 0,
      total_products: 0,
      conversion_rate: null
    }
  } finally {
    loading.value = false
  }
}

const loadGMVTrend = async () => {
  try {
    // TODO: 迁移到 Metabase Question API: /dashboard/business-overview/comparison
    // const data = await api.get('/dashboard/business-overview/comparison', {
    //   params: {
    //     granularity: 'daily',
    //     date: getCurrentDate()
    //   }
    // })
    // ECharts集成后在这里渲染图表
    console.log('GMV趋势数据: TODO - 迁移到 Metabase Question API')
  } catch (error) {
    console.error('加载GMV趋势失败:', error)
  }
}

// 生命周期
onMounted(() => {
  loadKPIData()
  loadGMVTrend()
  
  // 检查ECharts是否已安装
  // import('echarts').then(() => {
  //   chartsReady.value = true
  // }).catch(() => {
  //   console.warn('ECharts未安装，使用占位符')
  // })
})

// 监听周期变化
watch(gmvPeriod, () => {
  loadGMVTrend()
})
</script>

<style scoped>
.dashboard-container {
  padding: 20px;
}

.page-header {
  margin-bottom: 30px;
}

.page-header h1 {
  font-size: 28px;
  color: #303133;
  margin: 0 0 10px 0;
}

.subtitle {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

/* KPI卡片 */
.kpi-row {
  margin-bottom: 20px;
}

.kpi-card {
  border-radius: 8px;
  transition: all 0.3s;
}

.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.kpi-content {
  display: flex;
  align-items: center;
}

.kpi-icon {
  width: 60px;
  height: 60px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  color: white;
  margin-right: 15px;
}

.kpi-info {
  flex: 1;
}

.kpi-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
  margin-bottom: 4px;
}

.kpi-subtitle {
  font-size: 12px;
  color: #C0C4CC;
}

/* 图表区域 */
.chart-row {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #909399;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  border-radius: 8px;
}

.chart-placeholder p {
  margin: 10px 0;
  font-size: 18px;
}

.chart-placeholder .hint {
  font-size: 14px;
  color: #C0C4CC;
}
</style>
