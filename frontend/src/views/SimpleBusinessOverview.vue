<template>
  <div class="simple-business-overview">
    <div class="page-header">
      <h1>业务概览</h1>
      <p>实时监控核心业务指标，洞察业务发展趋势</p>
    </div>

    <div class="kpi-cards">
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="6" v-for="kpi in kpiData" :key="kpi.key">
          <el-card class="kpi-card" shadow="hover">
            <div class="kpi-content">
              <div class="kpi-icon">{{ kpi.icon }}</div>
              <div class="kpi-info">
                <div class="kpi-value">{{ kpi.value }}</div>
                <div class="kpi-label">{{ kpi.label }}</div>
                <div class="kpi-change" :class="kpi.changeType">
                  {{ kpi.change }}
                </div>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <div class="charts-section">
      <el-row :gutter="20">
        <el-col :xs="24" :lg="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>销售趋势分析</span>
              </div>
            </template>
            <div class="chart-container">
              <div class="chart-placeholder">
                📈 销售趋势图表
                <br>
                <small>图表功能开发中...</small>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="12">
          <el-card class="chart-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <span>平台销售分布</span>
              </div>
            </template>
            <div class="chart-container">
              <div class="chart-placeholder">
                🥧 平台分布图表
                <br>
                <small>图表功能开发中...</small>
              </div>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <div class="recent-orders">
      <el-card class="orders-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>最近订单</span>
            <el-button type="primary" size="small">查看全部</el-button>
          </div>
        </template>
        <el-table :data="recentOrders" style="width: 100%">
          <el-table-column prop="orderId" label="订单号" width="120"></el-table-column>
          <el-table-column prop="customer" label="客户" width="100"></el-table-column>
          <el-table-column prop="amount" label="金额" width="100"></el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="scope">
              <el-tag :type="getStatusType(scope.row.status)">
                {{ scope.row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="date" label="日期"></el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

// KPI数据
const kpiData = ref([
  {
    key: 'sales',
    icon: '💰',
    value: '¥2,345,678',
    label: '总销售额',
    change: '+12.5%',
    changeType: 'positive'
  },
  {
    key: 'orders',
    icon: '📦',
    value: '15,678',
    label: '订单数量',
    change: '+8.3%',
    changeType: 'positive'
  },
  {
    key: 'customers',
    icon: '👥',
    value: '8,945',
    label: '客户数量',
    change: '+5.2%',
    changeType: 'positive'
  },
  {
    key: 'conversion',
    icon: '📊',
    value: '3.45%',
    label: '转化率',
    change: '-2.1%',
    changeType: 'negative'
  }
])

// 最近订单数据
const recentOrders = ref([
  {
    orderId: 'ORD001',
    customer: '张三',
    amount: '¥1,299',
    status: '已完成',
    date: '2024-01-16'
  },
  {
    orderId: 'ORD002',
    customer: '李四',
    amount: '¥899',
    status: '处理中',
    date: '2024-01-16'
  },
  {
    orderId: 'ORD003',
    customer: '王五',
    amount: '¥2,199',
    status: '已发货',
    date: '2024-01-15'
  },
  {
    orderId: 'ORD004',
    customer: '赵六',
    amount: '¥599',
    status: '已完成',
    date: '2024-01-15'
  }
])

// 获取状态类型
const getStatusType = (status) => {
  const statusMap = {
    '已完成': 'success',
    '处理中': 'warning',
    '已发货': 'info',
    '已取消': 'danger'
  }
  return statusMap[status] || 'info'
}
</script>

<style scoped>
.simple-business-overview {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}

.page-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 30px;
  border-radius: 12px;
  margin-bottom: 20px;
  text-align: center;
}

.page-header h1 {
  margin: 0 0 10px 0;
  font-size: 28px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  opacity: 0.9;
  font-size: 16px;
}

.kpi-cards {
  margin-bottom: 20px;
}

.kpi-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.kpi-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.kpi-content {
  display: flex;
  align-items: center;
  gap: 15px;
}

.kpi-icon {
  font-size: 32px;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  border-radius: 12px;
  color: white;
}

.kpi-info {
  flex: 1;
}

.kpi-value {
  font-size: 24px;
  font-weight: 700;
  color: #2c3e50;
  margin-bottom: 4px;
}

.kpi-label {
  font-size: 14px;
  color: #7f8c8d;
  margin-bottom: 4px;
}

.kpi-change {
  font-size: 12px;
  font-weight: 600;
}

.kpi-change.positive {
  color: #27ae60;
}

.kpi-change.negative {
  color: #e74c3c;
}

.charts-section {
  margin-bottom: 20px;
}

.chart-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: #2c3e50;
}

.chart-container {
  height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chart-placeholder {
  text-align: center;
  color: #7f8c8d;
  font-size: 18px;
}

.recent-orders {
  margin-bottom: 20px;
}

.orders-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .simple-business-overview {
    padding: 10px;
  }
  
  .page-header {
    padding: 20px;
  }
  
  .page-header h1 {
    font-size: 24px;
  }
  
  .kpi-content {
    flex-direction: column;
    text-align: center;
  }
  
  .kpi-icon {
    width: 50px;
    height: 50px;
    font-size: 24px;
  }
  
  .kpi-value {
    font-size: 20px;
  }
}
</style>
