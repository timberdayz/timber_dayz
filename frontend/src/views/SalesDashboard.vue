<template>
  <div class="sales-dashboard erp-content-container">
    <h1 style="font-size: 24px; font-weight: bold; margin-bottom: 20px;">销售看板</h1>
    
    <!-- 概览卡片 -->
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总产品数" :value="stats.total_products" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="总库存" :value="stats.total_stock" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="库存价值" :value="stats.total_value" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <el-statistic title="低库存预警" :value="stats.low_stock_count" />
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 平台销售对比 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>平台产品分布</span>
          </template>
          <el-table :data="stats.platform_breakdown" stripe>
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="product_count" label="产品数" width="120" />
            <el-table-column prop="total_stock" label="总库存" width="120" />
          </el-table>
        </el-card>
      </el-col>
      
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>产品分类占比</span>
          </template>
          <div ref="categoryChart" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>
    
    <!-- 店铺级别销售数据表格 -->
    <el-card style="margin-top: 20px;" class="erp-table">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>店铺销售表现</span>
          <div style="display: flex; gap: 10px; align-items: center;">
            <el-select v-model="shopFilters.platform" placeholder="选择平台" clearable size="small" style="width: 150px;" @change="loadShopPerformance">
              <el-option label="全部平台" value="" />
              <el-option label="Shopee" value="Shopee" />
              <el-option label="Lazada" value="Lazada" />
            </el-select>
            <el-select v-model="shopFilters.shopRegion" placeholder="选择地区" clearable size="small" style="width: 150px;" @change="loadShopPerformance">
              <el-option label="全部地区" value="" />
              <el-option label="新加坡" value="新加坡" />
              <el-option label="马来西亚" value="马来西亚" />
              <el-option label="泰国" value="泰国" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadShopPerformance">刷新</el-button>
          </div>
        </div>
      </template>
      
      <el-table :data="shopPerformance.data" stripe v-loading="shopPerformance.loading" class="erp-table">
        <el-table-column prop="shop_region" label="店铺地区" width="120" fixed="left" />
        <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
        <el-table-column label="销售数量" width="150">
          <template #default="{ row }">
            <div>
              <span>目标: {{ row.sales_quantity_target }}</span><br/>
              <span>达成: {{ row.sales_quantity_achieved }}</span><br/>
              <el-tag :type="row.sales_quantity_rate >= 90 ? 'success' : row.sales_quantity_rate >= 80 ? 'warning' : 'danger'" size="small">
                达成率: {{ row.sales_quantity_rate.toFixed(1) }}%
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="销售额" width="180">
          <template #default="{ row }">
            <div>
              <span>目标: ¥{{ row.sales_amount_target.toFixed(2) }}</span><br/>
              <span>达成: ¥{{ row.sales_amount_achieved.toFixed(2) }}</span><br/>
              <el-tag :type="row.sales_amount_rate >= 90 ? 'success' : row.sales_amount_rate >= 80 ? 'warning' : 'danger'" size="small">
                达成率: {{ row.sales_amount_rate.toFixed(1) }}%
              </el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="profit" label="利润" width="120" sortable>
          <template #default="{ row }">
            ¥{{ row.profit.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="commission" label="提成" width="120" sortable>
          <template #default="{ row }">
            ¥{{ row.commission.toFixed(2) }}
          </template>
        </el-table-column>
      </el-table>
      
      <el-pagination
        v-model:current-page="shopPerformance.page"
        v-model:page-size="shopPerformance.pageSize"
        :total="shopPerformance.total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 20px; justify-content: flex-end;"
        @size-change="loadShopPerformance"
        @current-change="loadShopPerformance"
      />
    </el-card>
    
    <!-- 销售周度/月度PK模块 -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>销售周度/月度PK</span>
          <div style="display: flex; gap: 10px; align-items: center;">
            <el-radio-group v-model="pkGranularity" size="small" @change="loadPKRanking">
              <el-radio-button label="weekly">周度</el-radio-button>
              <el-radio-button label="monthly">月度</el-radio-button>
            </el-radio-group>
            <el-select v-model="pkGroupBy" placeholder="分组方式" size="small" style="width: 120px;" @change="loadPKRanking">
              <el-option label="按店铺" value="shop" />
              <el-option label="按地区" value="region" />
              <el-option label="按平台" value="platform" />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadPKRanking">刷新</el-button>
          </div>
        </div>
      </template>
      
      <el-table :data="pkRanking.data" stripe v-loading="pkRanking.loading" class="erp-table">
        <el-table-column prop="rank" label="排名" width="80" fixed="left">
          <template #default="{ row }">
            <el-tag :type="row.rank === 1 ? 'success' : row.rank === 2 ? 'warning' : row.rank === 3 ? 'info' : ''" size="small">
              {{ row.rank }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="shop_name" label="店铺名称" width="200" fixed="left" show-overflow-tooltip />
        <el-table-column prop="shop_region" label="地区" width="120" />
        <el-table-column prop="sales_amount" label="销售额" width="150" sortable>
          <template #default="{ row }">
            ¥{{ row.sales_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="achievement_rate" label="达成率" width="120" sortable>
          <template #default="{ row }">
            <el-tag :type="row.achievement_rate >= 90 ? 'success' : row.achievement_rate >= 80 ? 'warning' : 'danger'" size="small">
              {{ row.achievement_rate.toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="growth_rate" label="环比增长" width="120" sortable>
          <template #default="{ row }">
            <el-tag :type="row.growth_rate >= 0 ? 'success' : 'danger'" size="small">
              {{ row.growth_rate >= 0 ? '+' : '' }}{{ row.growth_rate.toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sales_quantity" label="销售数量" width="120" sortable />
      </el-table>
    </el-card>
    
    <!-- 产品销售排行 -->
    <el-card style="margin-top: 20px;">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span>产品销售排行 TOP20</span>
          <el-radio-group v-model="sortBy" size="small" @change="loadTopProducts">
            <el-radio-button label="sales_amount">按销售额</el-radio-button>
            <el-radio-button label="sales_volume">按销量</el-radio-button>
            <el-radio-button label="page_views">按浏览量</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      
      <el-table :data="topProducts" stripe>
        <!-- 产品图片 -->
        <el-table-column label="产品图片" width="100">
          <template #default="{ row }">
            <el-image 
              :src="row.thumbnail_url || '/placeholder.png'"
              fit="cover"
              style="width: 60px; height: 60px; border-radius: 4px; cursor: pointer;"
              :preview-src-list="row.all_images"
              lazy
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
        
        <!-- 销售指标 -->
        <el-table-column prop="sales_amount" label="销售额" width="120" sortable>
          <template #default="{ row }">
            ¥{{ row.sales_amount.toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="sales_volume" label="销量" width="100" sortable />
        <el-table-column prop="page_views" label="浏览量" width="100" sortable />
        <el-table-column label="转化率" width="100">
          <template #default="{ row }">
            {{ (row.click_through_rate * 100).toFixed(2) }}%
          </template>
        </el-table-column>
        
        <!-- 操作 -->
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="quickView(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 产品详情快速查看对话框 -->
    <el-dialog v-model="quickViewVisible" title="产品详情" width="900px">
      <el-row :gutter="20" v-if="viewProduct.platform_sku">
        <el-col :span="10">
          <!-- 图片轮播 -->
          <el-carousel height="400px" v-if="viewProduct.images && viewProduct.images.length > 0">
            <el-carousel-item v-for="img in viewProduct.images" :key="img.id">
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
            <el-descriptions-item label="SKU">{{ viewProduct.platform_sku }}</el-descriptions-item>
            <el-descriptions-item label="平台">{{ viewProduct.platform_code }}</el-descriptions-item>
            <el-descriptions-item label="产品名称" :span="2">{{ viewProduct.product_name }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ viewProduct.category }}</el-descriptions-item>
            <el-descriptions-item label="品牌">{{ viewProduct.brand }}</el-descriptions-item>
            <el-descriptions-item label="单价">{{ viewProduct.price }} {{ viewProduct.currency }}</el-descriptions-item>
            <el-descriptions-item label="库存">
              <el-tag :type="viewProduct.stock < 10 ? 'danger' : 'success'">
                {{ viewProduct.stock }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="销量">{{ viewProduct.sales_volume }}</el-descriptions-item>
            <el-descriptions-item label="销售额">¥{{ viewProduct.sales_amount.toFixed(2) }}</el-descriptions-item>
            <el-descriptions-item label="浏览量">{{ viewProduct.page_views }}</el-descriptions-item>
            <el-descriptions-item label="访客数">{{ viewProduct.unique_visitors }}</el-descriptions-item>
            <el-descriptions-item label="点击率">{{ (viewProduct.click_through_rate * 100).toFixed(2) }}%</el-descriptions-item>
            <el-descriptions-item label="转化率">{{ (viewProduct.conversion_rate * 100).toFixed(2) }}%</el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Picture } from '@element-plus/icons-vue'
import { useSalesStore } from '@/stores/sales'

const salesStore = useSalesStore()

const loading = ref(false)
const products = ref([])
const topProducts = ref([])
const sortBy = ref('sales_amount')
const detailVisible = ref(false)
const quickViewVisible = ref(false)
const currentProduct = ref({})
const viewProduct = ref({})

// 店铺销售表现数据
const shopPerformance = reactive({
  data: [],
  total: 0,
  page: 1,
  pageSize: 20,
  loading: false
})

const shopFilters = reactive({
  platform: '',
  shopRegion: ''
})

// PK排名数据
const pkRanking = reactive({
  data: [],
  loading: false
})

const pkGranularity = ref('weekly')
const pkGroupBy = ref('shop')

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

const stats = reactive({
  total_products: 0,
  total_stock: 0,
  total_value: 0,
  low_stock_count: 0,
  platform_breakdown: []
})

onMounted(() => {
  loadStats()
  loadTopProducts()
  loadShopPerformance()
  loadPKRanking()
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
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      products.value = response.data || response || []
      pagination.total = response.total || 0
    }
  } catch (error) {
    ElMessage.error('加载产品列表失败')
  } finally {
    loading.value = false
  }
}

const loadTopProducts = async () => {
  try {
    const response = await api.get('/products/products', {
      params: {
        page: 1,
        page_size: 20
      }
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      topProducts.value = response.data || response || []
      
      // 客户端排序
      topProducts.value.sort((a, b) => {
        if (sortBy.value === 'sales_amount') {
          return b.sales_amount - a.sales_amount
        } else if (sortBy.value === 'sales_volume') {
          return b.sales_volume - a.sales_volume
        } else {
          return b.page_views - a.page_views
        }
      })
    }
  } catch (error) {
    ElMessage.error('加载产品排行失败')
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
      viewProduct.value = response
      quickViewVisible.value = true
    }
  } catch (error) {
    ElMessage.error('获取产品详情失败')
  }
}

// 加载店铺销售表现数据
const loadShopPerformance = async () => {
  shopPerformance.loading = true
  try {
    const response = await salesStore.getShopPerformance({
      platform: shopFilters.platform || undefined,
      shopRegion: shopFilters.shopRegion || undefined,
      page: shopPerformance.page,
      pageSize: shopPerformance.pageSize
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      shopPerformance.data = response.data || response || []
      shopPerformance.total = response.total || 0
    } else {
      ElMessage.error(response.error || '加载店铺销售表现失败')
    }
  } catch (error) {
    ElMessage.error('加载店铺销售表现失败')
  } finally {
    shopPerformance.loading = false
  }
}

// 加载PK排名数据
const loadPKRanking = async () => {
  pkRanking.loading = true
  try {
    const response = await salesStore.getPKRanking({
      granularity: pkGranularity.value,
      groupBy: pkGroupBy.value
    })
    
    // 响应拦截器已提取data字段，直接使用
    if (response) {
      pkRanking.data = response.data || response || []
    } else {
      ElMessage.error('加载PK排名失败')
    }
  } catch (error) {
    ElMessage.error('加载PK排名失败')
  } finally {
    pkRanking.loading = false
  }
}
</script>

<style scoped>
.sales-dashboard {
  padding: 20px;
}

.stat-card {
  text-align: center;
}

/* 企业级表格样式 */
.erp-table :deep(.el-table__fixed-left) {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table__fixed-right) {
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
}

.erp-table :deep(.el-table .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
