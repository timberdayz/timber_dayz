<template>
  <div class="inventory-dashboard">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">库存管理看板</h1>
    
    <!-- 库存概览 -->
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总库存" :value="stats.total_stock" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card low-stock-card">
          <el-statistic 
            title="低库存预警" 
            :value="stats.low_stock_count"
            :value-style="{ color: '#f56c6c' }"
          />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card out-stock-card">
          <el-statistic 
            title="缺货数量" 
            :value="stats.out_of_stock_count"
            :value-style="{ color: '#ff0000' }"
          />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="库存价值" :value="stats.total_value" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 平台库存分布 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>平台库存分布</span>
          </template>
          <el-table :data="stats.platform_breakdown" stripe>
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="product_count" label="产品数" width="100" />
            <el-table-column prop="total_stock" label="总库存" width="120" />
            <el-table-column label="库存占比" width="120">
              <template #default="{ row }">
                {{ ((row.total_stock / stats.total_stock) * 100).toFixed(1) }}%
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>库存健康度</span>
          </template>
          <div style="padding: 20px;">
            <el-progress 
              :percentage="healthScore" 
              :color="healthColor"
              :stroke-width="20"
            >
              <span style="font-size: 16px; font-weight: bold;">{{ healthScore }}分</span>
            </el-progress>
            <div style="margin-top: 20px; text-align: center;">
              <el-tag :type="healthType" size="large">{{ healthText }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 低库存预警列表 -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>低库存预警列表</span>
          <el-button size="small" @click="loadLowStockProducts">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      
      <el-table :data="lowStockProducts" v-loading="loading" stripe>
        <!-- 产品图片 -->
        <el-table-column label="产品图片" width="100">
          <template #default="{ row }">
            <el-image 
              :src="row.thumbnail_url || '/placeholder.png'"
              fit="cover"
              style="width: 60px; height: 60px; border-radius: 4px; cursor: pointer;"
              @click="quickView(row)"
            >
              <template #error>
                <div style="width: 60px; height: 60px; display: flex; align-items: center; justify-content: center; background: #f5f5f5; border-radius: 4px;">
                  <el-icon :size="24" color="#ccc"><Picture /></el-icon>
                </div>
              </template>
            </el-image>
          </template>
        </el-table-column>
        
        <!-- 产品信息 -->
        <el-table-column prop="product_name" label="产品名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="platform_sku" label="SKU" width="150" />
        <el-table-column prop="platform_code" label="平台" width="100" />
        
        <!-- 库存状态 -->
        <el-table-column prop="stock" label="当前库存" width="100" sortable>
          <template #default="{ row }">
            <el-tag :type="row.stock === 0 ? 'danger' : row.stock < 5 ? 'danger' : 'warning'">
              {{ row.stock }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="price" label="单价" width="100">
          <template #default="{ row }">
            ¥{{ row.price.toFixed(2) }}
          </template>
        </el-table-column>
        
        <!-- 操作 -->
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="quickView(row)">查看</el-button>
            <el-button size="small" type="primary">补货</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 产品详情对话框 -->
    <el-dialog v-model="detailVisible" title="产品详情" width="900px">
      <el-row :gutter="20" v-if="currentProduct.platform_sku">
        <el-col :span="10">
          <!-- 图片轮播 -->
          <el-carousel height="400px" v-if="currentProduct.images && currentProduct.images.length > 0">
            <el-carousel-item v-for="img in currentProduct.images" :key="img.id">
              <el-image :src="img.image_url" fit="contain" style="height: 100%; width: 100%;" />
            </el-carousel-item>
          </el-carousel>
          
          <div v-else style="height: 400px; display: flex; align-items: center; justify-content: center; background: #f5f5f5; border-radius: 8px;">
            <div style="text-align: center;">
              <el-icon :size="80" color="#ccc"><Picture /></el-icon>
              <p style="margin-top: 10px; color: #999;">暂无产品图片</p>
            </div>
          </div>
        </el-col>
        
        <el-col :span="14">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="SKU">{{ currentProduct.platform_sku }}</el-descriptions-item>
            <el-descriptions-item label="平台">{{ currentProduct.platform_code }}</el-descriptions-item>
            <el-descriptions-item label="产品名称" :span="2">{{ currentProduct.product_name }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ currentProduct.category }}</el-descriptions-item>
            <el-descriptions-item label="品牌">{{ currentProduct.brand }}</el-descriptions-item>
            <el-descriptions-item label="单价">{{ currentProduct.price }} {{ currentProduct.currency }}</el-descriptions-item>
            <el-descriptions-item label="库存">
              <el-tag :type="currentProduct.stock < 10 ? 'danger' : 'success'">
                {{ currentProduct.stock }}
              </el-description-item>
            <el-descriptions-item label="销量">{{ currentProduct.sales_volume }}</el-descriptions-item>
            <el-descriptions-item label="销售额">¥{{ currentProduct.sales_amount.toFixed(2) }}</el-descriptions-item>
            <el-descriptions-item label="浏览量">{{ currentProduct.page_views }}</el-descriptions-item>
            <el-descriptions-item label="转化率">{{ (currentProduct.conversion_rate * 100).toFixed(2) }}%</el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Refresh, Picture } from '@element-plus/icons-vue'

const loading = ref(false)
const lowStockProducts = ref([])
const detailVisible = ref(false)
const currentProduct = ref({})

const stats = reactive({
  total_stock: 0,
  total_value: 0,
  low_stock_count: 0,
  out_of_stock_count: 0,
  platform_breakdown: []
})

// 库存健康度评分
const healthScore = computed(() => {
  if (stats.total_products === 0) return 0
  
  const lowStockRatio = stats.low_stock_count / stats.total_products
  const outStockRatio = stats.out_of_stock_count / stats.total_products
  
  // 100分制：低库存-30分，缺货-50分
  const score = 100 - (lowStockRatio * 30) - (outStockRatio * 50)
  return Math.max(0, Math.min(100, score)).toFixed(0)
})

const healthColor = computed(() => {
  const score = healthScore.value
  if (score >= 90) return '#67c23a'
  if (score >= 70) return '#e6a23c'
  return '#f56c6c'
})

const healthType = computed(() => {
  const score = healthScore.value
  if (score >= 90) return 'success'
  if (score >= 70) return 'warning'
  return 'danger'
})

const healthText = computed(() => {
  const score = healthScore.value
  if (score >= 90) return '健康'
  if (score >= 70) return '一般'
  return '需关注'
})

onMounted(() => {
  loadStats()
  loadLowStockProducts()
})

const loadStats = async () => {
  try {
    const response = await api.get('/products/stats/platform-summary')
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      Object.assign(stats, response)
    }
  } catch (error) {
    ElMessage.error('加载统计数据失败')
  }
}

const loadLowStockProducts = async () => {
  loading.value = true
  
  try {
    const response = await api.get('/products/products', {
      params: {
        low_stock: true,
        page: 1,
        page_size: 50
      }
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      lowStockProducts.value = response.data || response || []
    }
  } catch (error) {
    ElMessage.error('加载低库存列表失败')
  } finally {
    loading.value = false
  }
}

const quickView = async (product) => {
  try {
    const response = await api.get(`/products/products/${product.platform_sku}`, {
      params: {
        platform: product.platform_code,
        shop_id: product.shop_id
      }
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      currentProduct.value = response
      detailVisible.value = true
    }
  } catch (error) {
    ElMessage.error('获取产品详情失败')
  }
}
</script>

<style scoped>
.inventory-dashboard {
  padding: 20px;
}

.stat-card {
  text-align: center;
}

.low-stock-card {
  border-left: 4px solid #f56c6c;
}

.out-stock-card {
  border-left: 4px solid #ff0000;
}
</style>

