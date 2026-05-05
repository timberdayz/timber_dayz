<template>
  <div class="order-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">订单管理</h1>
    
    <!-- ========== 订单统计看板 ========== -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总订单数" :value="stats.total_orders" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总金额" :value="stats.total_amount" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="待处理订单" :value="stats.pending_orders" :value-style="{ color: '#f56c6c' }" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="已完成订单" :value="stats.completed_orders" :value-style="{ color: '#67c23a' }" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- ========== 筛选器 ========== -->
    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-select v-model="filters.platform_code" placeholder="选择平台" clearable style="width: 150px;">
            <el-option label="全部" value="" />
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
            <el-option label="妙手" value="miaoshou" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="店铺">
          <el-input v-model="filters.shop_id" placeholder="店铺ID" clearable style="width: 150px;" />
        </el-form-item>
        
        <el-form-item label="订单日期">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 240px;"
          />
        </el-form-item>
        
        <el-form-item label="订单状态">
          <el-select v-model="filters.order_status" placeholder="订单状态" clearable style="width: 120px;">
            <el-option label="全部" value="" />
            <el-option label="待支付" value="pending" />
            <el-option label="已支付" value="paid" />
            <el-option label="已发货" value="shipped" />
            <el-option label="已完成" value="completed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="loadOrders" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- ========== 订单列表 ========== -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>订单列表（共{{ pagination.total }}条）</span>
          <div>
            <el-button size="small" @click="loadOrders">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-button size="small" type="primary" @click="exportOrders">
              <el-icon><Download /></el-icon>
              导出
            </el-button>
          </div>
        </div>
      </template>
      
      <el-table :data="orders" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="order_id" label="订单ID" width="180" />
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" width="120" />
        <el-table-column prop="order_date" label="订单日期" width="120" />
        <el-table-column prop="order_time_utc" label="订单时间" width="160" />
        <el-table-column prop="total_amount_rmb" label="订单金额" width="120" align="right">
          <template #default="{ row }">
            ¥{{ formatNumber(row.total_amount_rmb) }}
          </template>
        </el-table-column>
        <el-table-column prop="item_count" label="商品数" width="100" align="center" />
        <el-table-column prop="total_quantity" label="总数量" width="100" align="center" />
        <el-table-column prop="order_status" label="订单状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.order_status)">{{ getStatusText(row.order_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="payment_status" label="支付状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getPaymentStatusType(row.payment_status)">{{ getPaymentStatusText(row.payment_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="buyer_name" label="买家" width="120" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewOrderDetail(row)">详情</el-button>
            <el-button size="small" type="primary" @click="viewSalesDetail(row)">销售明细</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadOrders"
        @current-change="loadOrders"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Download } from '@element-plus/icons-vue'
import api from '@/api'

// 状态
const loading = ref(false)
const orders = ref([])
const dateRange = ref([])

// 筛选器
const filters = reactive({
  platform_code: '',
  shop_id: '',
  order_status: '',
  payment_status: '',
  is_cancelled: null
})

// 统计信息
const stats = reactive({
  total_orders: 0,
  total_amount: 0,
  pending_orders: 0,
  completed_orders: 0
})

// 分页
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

// 加载订单列表（使用主视图API）
const loadOrders = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size
    }
    
    if (filters.platform_code) {
      params.platform_code = filters.platform_code
    }
    if (filters.shop_id) {
      params.shop_id = filters.shop_id
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    if (filters.order_status) {
      params.order_status = filters.order_status
    }
    if (filters.payment_status) {
      params.payment_status = filters.payment_status
    }
    if (filters.is_cancelled !== null) {
      params.is_cancelled = filters.is_cancelled
    }
    
    const response = await api.getOrderSummary(params)
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      orders.value = response.data || response || []
      pagination.total = response.total || 0
      
      // 更新统计信息
      updateStats(orders.value)
    } else {
      ElMessage.error(response.message || '加载订单列表失败')
    }
  } catch (error) {
    console.error('加载订单列表失败:', error)
    ElMessage.error('加载订单列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 更新统计信息
const updateStats = (orderList) => {
  stats.total_orders = pagination.total
  stats.total_amount = orderList.reduce((sum, order) => sum + (parseFloat(order.total_amount_rmb) || 0), 0)
  stats.pending_orders = orderList.filter(order => order.order_status === 'pending').length
  stats.completed_orders = orderList.filter(order => order.order_status === 'completed').length
}

// 格式化数字
const formatNumber = (value) => {
  if (!value) return '0.00'
  return parseFloat(value).toFixed(2)
}

// 获取状态类型
const getStatusType = (status) => {
  const statusMap = {
    'pending': 'warning',
    'paid': 'info',
    'shipped': 'primary',
    'completed': 'success',
    'cancelled': 'danger'
  }
  return statusMap[status] || 'info'
}

// 获取状态文本
const getStatusText = (status) => {
  const statusMap = {
    'pending': '待支付',
    'paid': '已支付',
    'shipped': '已发货',
    'completed': '已完成',
    'cancelled': '已取消'
  }
  return statusMap[status] || status
}

// 获取支付状态类型
const getPaymentStatusType = (status) => {
  const statusMap = {
    'pending': 'warning',
    'paid': 'success',
    'refunded': 'danger'
  }
  return statusMap[status] || 'info'
}

// 获取支付状态文本
const getPaymentStatusText = (status) => {
  const statusMap = {
    'pending': '待支付',
    'paid': '已支付',
    'refunded': '已退款'
  }
  return statusMap[status] || status
}

// 查看订单详情
const viewOrderDetail = (order) => {
  ElMessage.info(`查看订单详情: ${order.order_id}`)
  // TODO: 实现订单详情弹窗或跳转
}

// 查看销售明细
const viewSalesDetail = (order) => {
  // 跳转到销售明细页面，筛选该订单的数据
  // TODO: 实现路由跳转
  ElMessage.info(`查看销售明细: ${order.order_id}`)
}

// 导出订单
const exportOrders = () => {
  ElMessage.info('导出功能开发中')
  // TODO: 实现导出功能
}

// 初始化
onMounted(() => {
  loadOrders()
})
</script>

<style scoped>
.order-management {
  padding: 20px;
}

.stat-card {
  text-align: center;
}

.filter-card {
  margin-bottom: 20px;
}
</style>
