<template>
  <div class="inventory-management erp-page-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">库存管理</h1>
    
    <!-- ========== 库存概览看板 ========== -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
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
    
    <!-- ========== 平台库存分布和健康度 ========== -->
    <el-row :gutter="20" style="margin-bottom: 20px;">
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
                {{ stats.total_stock > 0 ? ((row.total_stock / stats.total_stock) * 100).toFixed(1) : '0.0' }}%
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
    
    <!-- ========== 筛选器 ========== -->
    <el-card class="filter-card">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-select v-model="filters.platform" placeholder="选择平台" clearable style="width: 150px;">
            <el-option label="全部" value="" />
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
            <el-option label="Amazon" value="amazon" />
            <el-option label="妙手" value="miaoshou" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="搜索SKU/产品名称" clearable style="width: 200px;" />
        </el-form-item>
        
        <el-form-item label="低库存">
          <el-checkbox v-model="filters.low_stock">仅显示低库存产品</el-checkbox>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="loadProducts" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
    
    <!-- ========== 库存列表 ========== -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>库存列表（共{{ pagination.total }}个）</span>
          <el-button size="small" @click="loadProducts">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      
      <el-table :data="products" v-loading="loading" stripe>
        <!-- 产品图片 -->
        <el-table-column label="产品图片" width="100" align="center">
          <template #default="{ row }">
            <el-image 
              :src="getProductImageUrl(row)"
              fit="cover"
              style="width: 60px; height: 60px; border-radius: 4px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
              :preview-src-list="getPreviewImages(row)"
              preview-teleported
              lazy
              @click="viewProduct(row)"
            >
              <template #placeholder>
                <div class="image-loading">
                  <el-icon class="is-loading" :size="20" color="#409eff">
                    <Loading />
                  </el-icon>
                </div>
              </template>
              <template #error>
                <div class="image-placeholder">
                  <el-icon :size="24" color="#ccc"><Picture /></el-icon>
                  <span class="image-placeholder-text">暂无图片</span>
                </div>
              </template>
            </el-image>
          </template>
        </el-table-column>
        
        <!-- 产品信息 -->
        <el-table-column prop="platform_sku" label="SKU" width="150" />
        <el-table-column prop="product_name" label="产品名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120" />
        <el-table-column prop="price" label="价格" width="100">
          <template #default="{ row }">
            {{ row.price ? row.price.toFixed(2) : '0.00' }} {{ row.currency || 'CNY' }}
          </template>
        </el-table-column>
        
        <!-- 库存状态 -->
        <el-table-column prop="stock" label="库存" width="100">
          <template #default="{ row }">
            <el-tag :type="row.stock === 0 ? 'danger' : row.stock < 10 ? 'warning' : 'success'">
              {{ row.stock }}
            </el-tag>
          </template>
        </el-table-column>
        
        <!-- 库存价值 -->
        <el-table-column label="库存价值" width="120" align="right">
          <template #default="{ row }">
            ¥{{ ((row.stock || 0) * (row.price || 0)).toFixed(2) }}
          </template>
        </el-table-column>
        
        <!-- 销售指标 -->
        <el-table-column prop="sales_volume" label="销量" width="100" align="right" />
        <el-table-column prop="page_views" label="浏览量" width="100" align="right" />
        
        <!-- 固定列: 操作（始终可见） -->
        <el-table-column label="操作" width="180" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="viewProduct(row)">详情</el-button>
            <el-button size="small" type="primary">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <!-- 分页 -->
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadProducts"
        @size-change="loadProducts"
        style="margin-top: 20px; justify-content: center;"
      />
    </el-card>
    
    <!-- ========== 产品详情对话框 ========== -->
    <el-dialog v-model="detailVisible" title="库存详情" width="900px">
      <el-row :gutter="20" v-if="currentProduct.platform_sku">
        <el-col :span="10">
          <!-- 图片轮播 -->
          <el-carousel height="400px" v-if="currentProduct.images && currentProduct.images.length > 0">
            <el-carousel-item v-for="img in currentProduct.images" :key="img.id">
              <el-image :src="img.image_url" fit="contain" style="height: 100%; width: 100%;" />
            </el-carousel-item>
          </el-carousel>
          
          <!-- 无图片占位 -->
          <div v-else style="height: 400px; display: flex; align-items: center; justify-content: center; background: #f5f5f5; border-radius: 8px;">
            <div style="text-align: center;">
              <el-icon :size="80" color="#ccc"><Picture /></el-icon>
              <p style="margin-top: 10px; color: #999;">暂无产品图片</p>
            </div>
          </div>
        </el-col>
        
        <el-col :span="14">
          <!-- 产品信息 -->
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
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="库存价值">
              ¥{{ ((currentProduct.stock || 0) * (currentProduct.price || 0)).toFixed(2) }}
            </el-descriptions-item>
            <el-descriptions-item label="销量">{{ currentProduct.sales_volume || 0 }}</el-descriptions-item>
            <el-descriptions-item label="销售额">{{ currentProduct.sales_amount ? currentProduct.sales_amount.toFixed(2) : '0.00' }}</el-descriptions-item>
            <el-descriptions-item label="浏览量">{{ currentProduct.page_views || 0 }}</el-descriptions-item>
            <el-descriptions-item label="转化率">{{ currentProduct.conversion_rate ? (currentProduct.conversion_rate * 100).toFixed(2) : '0.00' }}%</el-descriptions-item>
            <el-descriptions-item label="数据日期">{{ currentProduct.metric_date }}</el-descriptions-item>
            <el-descriptions-item label="粒度">{{ currentProduct.granularity }}</el-descriptions-item>
          </el-descriptions>
          
          <!-- 图片管理 -->
          <div style="margin-top: 20px;" v-if="currentProduct.images && currentProduct.images.length > 0">
            <el-divider>产品图片 ({{ currentProduct.images.length }}张)</el-divider>
            <el-space wrap>
              <div v-for="img in currentProduct.images" :key="img.id" style="position: relative;">
                <el-image 
                  :src="img.thumbnail_url" 
                  style="width: 80px; height: 80px; border-radius: 4px;"
                  :preview-src-list="[img.image_url]"
                />
                <el-tag v-if="img.is_main" size="small" type="danger" style="position: absolute; top: 0; left: 0;">主图</el-tag>
              </div>
            </el-space>
          </div>
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Picture, Loading } from '@element-plus/icons-vue'
import { handleApiError } from '@/utils/errorHandler'
import { formatCurrency, formatNumber, formatPercent, formatInteger } from '@/utils/dataFormatter'

const loading = ref(false)
const products = ref([])
const detailVisible = ref(false)
const currentProduct = ref({})

const filters = reactive({
  platform: '',
  keyword: '',
  low_stock: false
})

const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0
})

// 库存统计数据
const stats = reactive({
  total_stock: 0,
  total_value: 0,
  low_stock_count: 0,
  out_of_stock_count: 0,
  total_products: 0,
  platform_breakdown: []
})

// 库存健康度评分
const healthScore = computed(() => {
  if (stats.total_products === 0) return 100
  
  const lowStockRatio = stats.low_stock_count / stats.total_products
  const outStockRatio = stats.out_of_stock_count / stats.total_products
  
  // 100分制：低库存-30分，缺货-50分
  const score = 100 - (lowStockRatio * 30) - (outStockRatio * 50)
  return Math.max(0, Math.min(100, Math.round(score)))
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
  loadProducts()
})

// 加载库存统计数据
const loadStats = async () => {
  try {
    const response = await api.get('/products/stats/platform-summary')
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      Object.assign(stats, response)
      // 如果没有total_products，从platform_breakdown计算
      if (!stats.total_products && stats.platform_breakdown) {
        stats.total_products = stats.platform_breakdown.reduce((sum, p) => sum + (p.product_count || 0), 0)
      }
    }
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  }
}

// 加载产品列表
const loadProducts = async () => {
  loading.value = true
  
  try {
    const response = await api.get('/products/products', {
      params: {
        platform: filters.platform || undefined,
        keyword: filters.keyword || undefined,
        low_stock: filters.low_stock || undefined,
        page: pagination.page,
        page_size: pagination.page_size
      }
    })
    
    // 响应拦截器已处理success字段，分页响应直接返回data对象
    if (response && response.data) {
      products.value = response.data
      pagination.total = response.total || 0
    } else if (response && Array.isArray(response)) {
      products.value = response
      pagination.total = response.length
    } else {
      products.value = []
      pagination.total = 0
    }
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  } finally {
    loading.value = false
  }
}

/**
 * 获取产品图片URL（智能降级）
 * 优先级: thumbnail_url → image_url → placeholder
 */
const getProductImageUrl = (product) => {
  // 优先使用缩略图
  if (product.thumbnail_url) {
    return product.thumbnail_url
  }
  
  // 其次使用主图URL（v4.6.3新增：直接使用image_url字段）
  if (product.image_url) {
    return product.image_url
  }
  
  // 最后使用占位图
  return '/placeholder.png'
}

/**
 * 获取图片预览列表
 * 支持多图预览
 */
const getPreviewImages = (product) => {
  // 如果有多图数组
  if (product.all_images && Array.isArray(product.all_images)) {
    return product.all_images
  }
  
  // 如果有单图URL
  if (product.image_url) {
    return [product.image_url]
  }
  
  // 无图片
  return []
}

const viewProduct = async (product) => {
  try {
    const response = await api.get(`/products/products/${product.platform_sku}`, {
      params: {
        platform: product.platform_code,
        shop_id: product.shop_id
      }
    })
    
    // 响应拦截器已处理success字段，直接使用data
    if (response) {
      currentProduct.value = response
      
      // 如果没有images数组，使用image_url创建
      if (!currentProduct.value.images && currentProduct.value.image_url) {
        currentProduct.value.images = [{
          id: 1,
          image_url: currentProduct.value.image_url,
          thumbnail_url: currentProduct.value.image_url,
          is_main: true
        }]
      }
      
      detailVisible.value = true
    }
  } catch (error) {
    handleApiError(error, { showMessage: true, logError: true })
  }
}
</script>

<style scoped>
.inventory-management {
  padding: 20px;
}

.filter-card {
  margin-bottom: 20px;
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

/* 图片加载状态 */
.image-loading {
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 4px;
}

/* 图片占位符 */
.image-placeholder {
  width: 60px;
  height: 60px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 4px;
  border: 1px dashed #dcdfe6;
  transition: all 0.3s;
}

.image-placeholder:hover {
  border-color: #409eff;
  background: #ecf5ff;
}

.image-placeholder-text {
  font-size: 10px;
  color: #909399;
  margin-top: 4px;
}

/* 图片hover效果 */
.el-table :deep(.el-image) {
  transition: transform 0.3s;
}

.el-table :deep(.el-image:hover) {
  transform: scale(1.05);
}
</style>
