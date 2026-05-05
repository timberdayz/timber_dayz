<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">库存流水</h1>
    <el-card class="filters">
      <el-form :inline="true">
        <el-form-item label="平台"><el-input v-model="filters.platform" clearable /></el-form-item>
        <el-form-item label="店铺"><el-input v-model="filters.shop_id" clearable /></el-form-item>
        <el-form-item label="SKU"><el-input v-model="filters.platform_sku" clearable /></el-form-item>
        <el-form-item label="类型"><el-input v-model="filters.movement_type" clearable /></el-form-item>
        <el-form-item><el-button type="primary" @click="loadLedger">查询</el-button></el-form-item>
      </el-form>
    </el-card>
    <el-card>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="transaction_date" label="日期" width="120" />
        <el-table-column prop="movement_type" label="类型" width="120" />
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" width="120" />
        <el-table-column prop="platform_sku" label="SKU" min-width="180" />
        <el-table-column prop="qty_before" label="变更前" width="100" />
        <el-table-column prop="qty_in" label="入" width="80" />
        <el-table-column prop="qty_out" label="出" width="80" />
        <el-table-column prop="qty_after" label="变更后" width="100" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])
const filters = reactive({ platform: '', shop_id: '', platform_sku: '', movement_type: '' })

const loadLedger = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getLedger({
      platform: filters.platform || undefined,
      shop_id: filters.shop_id || undefined,
      platform_sku: filters.platform_sku || undefined,
      movement_type: filters.movement_type || undefined
    })
  } catch (error) {
    ElMessage.error('加载库存流水失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadLedger)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
.filters { margin-bottom: 20px; }
</style>
