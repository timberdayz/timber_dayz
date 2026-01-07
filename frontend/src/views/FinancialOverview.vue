<template>
  <div class="financial-overview">
    <!-- 页头 -->
    <div class="page-header">
      <h1>💰 财务总览</h1>
      <p class="subtitle">基于物化视图的实时财务监控 v4.9.1</p>
    </div>

    <!-- 数据准备提示 -->
    <el-alert
      title="数据准备中"
      type="info"
      description="财务物化视图需要先采集并入库财务数据（PO、GRN、Invoice等）"
      :closable="false"
      style="margin-bottom: 20px"
    />

    <!-- 筛选器 -->
    <el-card class="filter-card" shadow="hover">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="全部平台" clearable>
            <el-option label="全部" value=""></el-option>
            <el-option label="妙手ERP" value="miaoshou"></el-option>
            <el-option label="Shopee" value="shopee"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" v-loading="loading">
      <!-- 财务指标概览 -->
      <el-col :span="24">
        <el-card class="summary-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>财务指标概览</span>
              <el-tag type="info" size="small">数据源: mv_financial_overview</el-tag>
            </div>
          </template>
          
          <el-row :gutter="20">
            <el-col :span="6">
              <div class="stat-box revenue">
                <div class="stat-icon">💵</div>
                <div class="stat-content">
                  <div class="stat-value">¥{{ formatNumber(stats.revenue) }}</div>
                  <div class="stat-label">总营业收入</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box cost">
                <div class="stat-icon">💸</div>
                <div class="stat-content">
                  <div class="stat-value">¥{{ formatNumber(stats.cost) }}</div>
                  <div class="stat-label">总成本</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box profit">
                <div class="stat-icon">💰</div>
                <div class="stat-content">
                  <div class="stat-value">¥{{ formatNumber(stats.profit) }}</div>
                  <div class="stat-label">毛利润</div>
                </div>
              </div>
            </el-col>
            
            <el-col :span="6">
              <div class="stat-box margin">
                <div class="stat-icon">📊</div>
                <div class="stat-content">
                  <div class="stat-value">{{ stats.margin.toFixed(2) }}%</div>
                  <div class="stat-label">毛利率</div>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <!-- P&L趋势 -->
      <el-col :span="24">
        <el-card class="chart-card" shadow="hover">
          <template #header>P&L趋势分析</template>
          <div ref="plChart" style="width: 100%; height: 350px;"></div>
        </el-card>
      </el-col>

      <!-- 费用结构 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>费用结构分布</template>
          <div ref="expenseChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- 毛利率趋势 -->
      <el-col :span="12">
        <el-card class="chart-card" shadow="hover">
          <template #header>毛利率趋势</template>
          <div ref="marginChart" style="width: 100%; height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 数据为空提示 -->
    <el-empty 
      v-if="!loading && trendData.length === 0" 
      description="暂无财务数据，请先采集并入库财务数据（采购订单、入库单、发票等）"
    >
      <el-button type="primary" @click="goToCollection">前往数据采集</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const router = useRouter()
const loading = ref(false)
const trendData = ref([])
const dateRange = ref([])
const queryTime = ref(0)
const plChart = ref(null)
const expenseChart = ref(null)
const marginChart = ref(null)

const filters = ref({
  platform: ''
})

const stats = ref({
  revenue: 0,
  cost: 0,
  profit: 0,
  margin: 0
})

const loadData = async () => {
  loading.value = true
  try {
    // TODO: 调用财务总览API（待后端实现）
    // const res = await api.queryFinancialOverview(filters.value)
    
    // 暂时使用模拟数据
    ElMessage.warning('财务物化视图暂无数据，请先采集财务数据')
    
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const formatNumber = (num) => {
  return (num || 0).toLocaleString()
}

const goToCollection = () => {
  router.push('/collection-config')
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.financial-overview {
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

.stat-box.revenue {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.stat-box.cost {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.stat-box.profit {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
}

.stat-box.margin {
  background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
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

.chart-card {
  margin-top: 20px;
}
</style>

