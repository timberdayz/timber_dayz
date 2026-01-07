<template>
  <div class="sales-detail-by-product erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">销售明细（产品ID级别）</h1>
    
    <!-- ========== 统计看板 ========== -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总销售数量" :value="stats.total_quantity" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总销售额" :value="stats.total_sales_amount" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总成本" :value="stats.total_cost" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总毛利" :value="stats.total_profit" prefix="¥" :precision="2" :value-style="{ color: '#67c23a' }" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- ========== 筛选器 ========== -->
    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="产品ID（SN）">
          <el-input v-model="filters.product_id" placeholder="输入产品ID" clearable style="width: 150px;" />
        </el-form-item>
        
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
        
        <el-form-item label="平台SKU">
          <el-input v-model="filters.platform_sku" placeholder="平台SKU" clearable style="width: 150px;" />
        </el-form-item>
        
        <el-form-item label="订单ID">
          <el-input v-model="filters.order_id" placeholder="订单ID" clearable style="width: 180px;" />
        </el-form-item>
        
        <el-form-item label="销售日期">
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
        
        <el-form-item>
          <el-button type="primary" @click="loadSalesDetail" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- ========== 销售明细列表 ========== -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>销售明细列表（共{{ pagination.total }}条）</span>
          <div>
            <el-button size="small" @click="loadSalesDetail">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-button size="small" type="primary" @click="exportSalesDetail">
              <el-icon><Download /></el-icon>
              导出
            </el-button>
          </div>
        </div>
      </template>
      
      <el-table :data="salesDetail" v-loading="loading" stripe style="width: 100%" border>
        <el-table-column prop="product_id" label="产品ID（SN）" width="120" fixed="left" />
        <el-table-column prop="order_id" label="订单ID" width="180" />
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" width="120" />
        <el-table-column prop="platform_sku" label="平台SKU" width="150" />
        <el-table-column prop="product_name" label="产品名称" width="200" show-overflow-tooltip />
        <el-table-column prop="sale_date" label="销售日期" width="120" />
        <el-table-column prop="quantity" label="数量" width="80" align="right" />
        <el-table-column prop="unit_price_rmb" label="单价（¥）" width="120" align="right">
          <template #default="{ row }">
            ¥{{ formatNumber(row.unit_price_rmb) }}
          </template>
        </el-table-column>
        <el-table-column prop="subtotal_rmb" label="小计（¥）" width="120" align="right">
          <template #default="{ row }">
            ¥{{ formatNumber(row.subtotal_rmb) }}
          </template>
        </el-table-column>
        <el-table-column prop="cost_rmb" label="成本（¥）" width="120" align="right">
          <template #default="{ row }">
            ¥{{ formatNumber(row.cost_rmb) }}
          </template>
        </el-table-column>
        <el-table-column prop="profit_rmb" label="毛利（¥）" width="120" align="right">
          <template #default="{ row }">
            <span :style="{ color: parseFloat(row.profit_rmb) >= 0 ? '#67c23a' : '#f56c6c' }">
              ¥{{ formatNumber(row.profit_rmb) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="profit_margin" label="毛利率" width="100" align="right">
          <template #default="{ row }">
            {{ formatPercent(row.profit_margin) }}
          </template>
        </el-table-column>
        <el-table-column prop="buyer_name" label="买家" width="120" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewProductDetail(row)">详情</el-button>
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
        @size-change="loadSalesDetail"
        @current-change="loadSalesDetail"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Download } from '@element-plus/icons-vue'
import api from '@/api'

// 状态
const loading = ref(false)
const salesDetail = ref([])
const dateRange = ref([])

// 筛选器
const filters = reactive({
  product_id: null,
  platform_code: '',
  shop_id: '',
  platform_sku: '',
  order_id: ''
})

// 统计信息
const stats = reactive({
  total_quantity: 0,
  total_sales_amount: 0,
  total_cost: 0,
  total_profit: 0
})

// 分页
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

// 加载销售明细（使用mv_sales_detail_by_product物化视图）
const loadSalesDetail = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.page_size
    }
    
    if (filters.product_id) {
      params.product_id = parseInt(filters.product_id)
    }
    if (filters.platform_code) {
      params.platform_code = filters.platform_code
    }
    if (filters.shop_id) {
      params.shop_id = filters.shop_id
    }
    if (filters.platform_sku) {
      params.platform_sku = filters.platform_sku
    }
    if (filters.order_id) {
      params.order_id = filters.order_id
    }
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    
    const response = await api.getSalesDetailByProduct(params)
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      salesDetail.value = response.data || response || []
      pagination.total = response.total || 0
      
      // 更新统计信息
      updateStats(salesDetail.value)
    } else {
      ElMessage.error(response.message || '加载销售明细失败')
    }
  } catch (error) {
    console.error('加载销售明细失败:', error)
    ElMessage.error('加载销售明细失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 更新统计信息
const updateStats = (detailList) => {
  stats.total_quantity = detailList.reduce((sum, item) => sum + (parseInt(item.quantity) || 0), 0)
  stats.total_sales_amount = detailList.reduce((sum, item) => sum + (parseFloat(item.subtotal_rmb) || 0), 0)
  stats.total_cost = detailList.reduce((sum, item) => sum + (parseFloat(item.cost_rmb) || 0), 0)
  stats.total_profit = stats.total_sales_amount - stats.total_cost
}

// 格式化数字
const formatNumber = (value) => {
  if (!value) return '0.00'
  return parseFloat(value).toFixed(2)
}

// 格式化百分比
const formatPercent = (value) => {
  if (!value) return '0.00%'
  return (parseFloat(value) * 100).toFixed(2) + '%'
}

// 查看产品详情
const viewProductDetail = (row) => {
  ElMessage.info(`查看产品详情: Product ID ${row.product_id}`)
  // TODO: 实现产品详情弹窗或跳转
}

// 导出销售明细
const exportSalesDetail = () => {
  ElMessage.info('导出功能开发中')
  // TODO: 实现导出功能
}

// 初始化
onMounted(() => {
  loadSalesDetail()
})
</script>

<style scoped>
.sales-detail-by-product {
  padding: 20px;
}

.stat-card {
  text-align: center;
}

.filter-card {
  margin-bottom: 20px;
}
</style>

