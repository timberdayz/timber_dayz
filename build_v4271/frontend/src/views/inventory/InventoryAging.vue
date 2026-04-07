<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">库存库龄</h1>
    <el-card class="filters">
      <el-form :inline="true">
        <el-form-item label="平台"><el-input v-model="filters.platform" clearable /></el-form-item>
        <el-form-item label="店铺"><el-input v-model="filters.shop_id" clearable /></el-form-item>
        <el-form-item label="SKU"><el-input v-model="filters.platform_sku" clearable /></el-form-item>
        <el-form-item><el-button type="primary" @click="reload">查询</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="20" class="summary-row">
      <el-col :span="8">
        <el-card>
          <el-statistic title="总剩余数量" :value="summary.total_quantity" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="总库存价值" :value="summary.total_value" prefix="¥" :precision="2" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <el-statistic title="SKU 数量" :value="rows.length" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>库龄桶分布</template>
          <el-table :data="summary.buckets" size="small" stripe>
            <el-table-column prop="bucket" label="桶" width="110" />
            <el-table-column prop="quantity" label="数量" width="90" />
            <el-table-column prop="inventory_value" label="价值" min-width="120">
              <template #default="{ row }">¥{{ Number(row.inventory_value || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="sku_count" label="SKU数" width="90" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>SKU 级真实库龄</template>
          <el-table :data="rows" v-loading="loading" stripe>
            <el-table-column prop="platform_code" label="平台" width="100" />
            <el-table-column prop="shop_id" label="店铺" width="120" />
            <el-table-column prop="platform_sku" label="SKU" min-width="180" />
            <el-table-column prop="remaining_qty" label="剩余数量" width="100" />
            <el-table-column prop="oldest_age_days" label="最老库龄" width="100" />
            <el-table-column prop="youngest_age_days" label="最新库龄" width="100" />
            <el-table-column prop="weighted_avg_age_days" label="加权平均库龄" width="130">
              <template #default="{ row }">{{ Number(row.weighted_avg_age_days || 0).toFixed(2) }}</template>
            </el-table-column>
            <el-table-column prop="remaining_value" label="剩余价值" min-width="120">
              <template #default="{ row }">¥{{ Number(row.remaining_value || 0).toFixed(2) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])
const summary = reactive({
  rows: [],
  buckets: [],
  total_quantity: 0,
  total_value: 0
})
const filters = reactive({
  platform: '',
  shop_id: '',
  platform_sku: ''
})

const reload = async () => {
  loading.value = true
  try {
    const params = {
      platform: filters.platform || undefined,
      shop_id: filters.shop_id || undefined,
      platform_sku: filters.platform_sku || undefined
    }
    rows.value = await inventoryDomainApi.getAging(params)
    const response = await inventoryDomainApi.getAgingBuckets(params)
    Object.assign(summary, response)
  } catch (error) {
    ElMessage.error('加载库存库龄失败')
  } finally {
    loading.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
.filters,
.summary-row { margin-bottom: 20px; }
</style>
