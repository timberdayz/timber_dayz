<template>
  <div class="top-products-page">
    <!-- 页头 -->
    <div class="page-header">
      <h1>[star] TopN产品排行榜</h1>
      <p class="subtitle">基于物化视图的高性能产品排名分析 v4.9.0</p>
    </div>

    <!-- 筛选器 -->
    <el-card class="filter-card" shadow="hover">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="全部平台" clearable @change="loadData">
            <el-option label="全部" value=""></el-option>
            <el-option label="妙手ERP" value="miaoshou"></el-option>
            <el-option label="Shopee" value="shopee"></el-option>
            <el-option label="Amazon" value="amazon"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="排序方式">
          <el-select v-model="filters.orderBy" @change="loadData">
            <el-option label="销量排名" value="sales_rank"></el-option>
            <el-option label="健康度排名" value="health_rank"></el-option>
            <el-option label="流量排名" value="traffic_rank"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="显示数量">
          <el-select v-model="filters.limit" @change="loadData">
            <el-option :label="50" :value="50"></el-option>
            <el-option :label="100" :value="100"></el-option>
            <el-option :label="200" :value="200"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 排行榜 -->
    <el-card class="table-card" shadow="hover" v-loading="loading">
      <div class="stats-bar">
        <span>共 {{ products.length }} 个产品</span>
        <span>查询耗时: {{ queryTime }}ms</span>
        <span>数据源: 物化视图（实时）</span>
      </div>

      <el-table :data="products" stripe style="width: 100%">
        <el-table-column type="index" label="排名" width="80" />
        
        <el-table-column prop="platform_sku" label="SKU" width="150" />
        
        <el-table-column prop="product_name" label="产品名称" min-width="200" show-overflow-tooltip />
        
        <el-table-column label="30天销量" width="120" align="right">
          <template #default="{row}">
            <span style="font-weight: bold">{{ row.sales_volume_30d || 0 }}</span>
          </template>
        </el-table-column>
        
        <el-table-column label="销售额(RMB)" width="140" align="right">
          <template #default="{row}">
            <span>¥{{ (row.sales_amount_rmb || 0).toFixed(2) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column label="浏览量" width="100" align="right">
          <template #default="{row}">
            {{ row.page_views || 0 }}
          </template>
        </el-table-column>
        
        <el-table-column label="转化率" width="100" align="right">
          <template #default="{row}">
            {{ (row.conversion_rate * 100).toFixed(2) }}%
          </template>
        </el-table-column>
        
        <el-table-column label="健康度" width="120">
          <template #default="{row}">
            <el-progress 
              :percentage="row.product_health_score || 0" 
              :color="getHealthColor(row.product_health_score)"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="标签" width="120">
          <template #default="{row}">
            <el-tag :type="getTagType(row.sales_tag)">{{ getTagLabel(row.sales_tag) }}</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="排名统计" width="200">
          <template #default="{row}">
            <div style="font-size: 12px">
              <div>销量: #{{ row.sales_rank }}</div>
              <div>健康: #{{ row.health_rank }}</div>
              <div>流量: #{{ row.traffic_rank }}</div>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const products = ref([])
const queryTime = ref(0)

const filters = ref({
  platform: '',
  orderBy: 'sales_rank',
  limit: 100
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await api.queryTopProducts(filters.value)
    // 响应拦截器已提取data字段，直接使用
    if (res) {
      products.value = res.data || res || []
      queryTime.value = res.query_time_ms?.toFixed(2) || '0.00'
      ElMessage.success(`加载成功: ${products.value.length}个产品`)
    }
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const getHealthColor = (score) => {
  if (score >= 80) return '#67c23a'
  if (score >= 60) return '#e6a23c'
  return '#f56c6c'
}

const getTagType = (tag) => {
  const map = {
    'hot_seller': 'danger',
    'good_seller': 'success',
    'normal': 'info',
    'slow_mover': 'warning'
  }
  return map[tag] || 'info'
}

const getTagLabel = (tag) => {
  const map = {
    'hot_seller': '热销',
    'good_seller': '畅销',
    'normal': '正常',
    'slow_mover': '滞销'
  }
  return map[tag] || tag
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.top-products-page {
  padding: 20px;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 24px;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #909399;
  margin: 0;
}

.filter-card {
  margin-bottom: 20px;
}

.stats-bar {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 14px;
  color: #606266;
}
</style>

