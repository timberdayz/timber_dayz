<template>
  <div class="inventory-overview erp-page-container">
    <h1 class="page-title">库存总览</h1>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card><el-statistic title="总商品数" :value="stats.total_products" /></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><el-statistic title="总库存" :value="stats.total_stock" /></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><el-statistic title="低库存" :value="stats.low_stock_count" /></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><el-statistic title="库存价值" :value="stats.total_value" prefix="¥" :precision="2" /></el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="8">
        <el-card><el-statistic title="高风险SKU" :value="stats.high_risk_sku_count" /></el-card>
      </el-col>
      <el-col :span="8">
        <el-card><el-statistic title="中风险SKU" :value="stats.medium_risk_sku_count" /></el-card>
      </el-col>
      <el-col :span="8">
        <el-card><el-statistic title="低风险SKU" :value="stats.low_risk_sku_count" /></el-card>
      </el-col>
    </el-row>

    <el-card class="filters">
      <el-form :inline="true">
        <el-form-item label="平台">
          <el-input v-model="filters.platform" placeholder="如 shopee" clearable />
        </el-form-item>
        <el-form-item label="店铺">
          <el-input v-model="filters.shop_id" placeholder="店铺ID" clearable />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="SKU/商品名" clearable />
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="filters.low_stock">仅低库存</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="reload">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>平台分布</template>
          <el-table :data="stats.platform_breakdown" size="small" stripe>
            <el-table-column prop="platform" label="平台" />
            <el-table-column prop="product_count" label="商品数" />
            <el-table-column prop="total_stock" label="总库存" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>库存快照列表</template>
          <el-table :data="products" v-loading="loading" stripe>
            <el-table-column prop="platform_sku" label="SKU" width="180" />
            <el-table-column prop="product_name" label="商品名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="platform_code" label="平台" width="100" />
            <el-table-column prop="shop_id" label="店铺" width="120" />
            <el-table-column prop="stock" label="库存" width="100" />
            <el-table-column prop="price" label="单价" width="100">
              <template #default="{ row }">¥{{ Number(row.price || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="viewProduct(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.page_size"
            :total="pagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            class="pager"
            @current-change="loadProducts"
            @size-change="loadProducts"
          />
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="detailVisible" title="库存快照详情" width="800px">
      <el-descriptions v-if="currentProduct.platform_sku" :column="2" border>
        <el-descriptions-item label="SKU">{{ currentProduct.platform_sku }}</el-descriptions-item>
        <el-descriptions-item label="平台">{{ currentProduct.platform_code }}</el-descriptions-item>
        <el-descriptions-item label="店铺">{{ currentProduct.shop_id }}</el-descriptions-item>
        <el-descriptions-item label="仓库">{{ currentProduct.warehouse || '-' }}</el-descriptions-item>
        <el-descriptions-item label="商品名称" :span="2">{{ currentProduct.product_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="库存">{{ currentProduct.stock }}</el-descriptions-item>
        <el-descriptions-item label="总库存">{{ currentProduct.total_stock }}</el-descriptions-item>
        <el-descriptions-item label="可用库存">{{ currentProduct.available_stock }}</el-descriptions-item>
        <el-descriptions-item label="预留库存">{{ currentProduct.reserved_stock }}</el-descriptions-item>
        <el-descriptions-item label="在途库存">{{ currentProduct.in_transit_stock }}</el-descriptions-item>
        <el-descriptions-item label="销量">{{ currentProduct.sales_volume }}</el-descriptions-item>
        <el-descriptions-item label="销售额">¥{{ Number(currentProduct.sales_amount || 0).toFixed(2) }}</el-descriptions-item>
        <el-descriptions-item label="浏览量">{{ currentProduct.page_views }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ currentProduct.updated_at || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryOverviewApi from '@/api/inventoryOverview'

const loading = ref(false)
const detailVisible = ref(false)
const currentProduct = ref({})
const products = ref([])

const filters = reactive({
  platform: '',
  shop_id: '',
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
  out_of_stock_count: 0,
  high_risk_sku_count: 0,
  medium_risk_sku_count: 0,
  low_risk_sku_count: 0,
  platform_breakdown: []
})

const loadSummary = async () => {
  const response = await inventoryOverviewApi.getSummary({
    platform: filters.platform || undefined
  })
  Object.assign(stats, response)
}

const loadProducts = async () => {
  loading.value = true
  try {
    const response = await inventoryOverviewApi.getProducts({
      platform: filters.platform || undefined,
      shop_id: filters.shop_id || undefined,
      keyword: filters.keyword || undefined,
      low_stock: filters.low_stock || undefined,
      page: pagination.page,
      page_size: pagination.page_size
    })
    products.value = response.data || []
    pagination.total = response.total || 0
  } catch (error) {
    ElMessage.error('加载库存总览失败')
  } finally {
    loading.value = false
  }
}

const viewProduct = async (product) => {
  try {
    currentProduct.value = await inventoryOverviewApi.getProductDetail(product.platform_sku, {
      platform: product.platform_code,
      shop_id: product.shop_id
    })
    detailVisible.value = true
  } catch (error) {
    ElMessage.error('加载商品详情失败')
  }
}

const reload = async () => {
  pagination.page = 1
  try {
    await Promise.all([loadSummary(), loadProducts()])
  } catch (error) {
    ElMessage.error('刷新库存总览失败')
  }
}

onMounted(reload)
</script>

<style scoped>
.inventory-overview {
  padding: 20px;
}

.page-title {
  margin-bottom: 20px;
  font-size: 24px;
  font-weight: 700;
}

.stats-row,
.filters {
  margin-bottom: 20px;
}

.pager {
  margin-top: 20px;
  justify-content: center;
}
</style>
