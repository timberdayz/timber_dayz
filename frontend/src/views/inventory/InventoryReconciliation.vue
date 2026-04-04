<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">库存对账</h1>
    <el-card>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" width="120" />
        <el-table-column prop="platform_sku" label="SKU" min-width="180" />
        <el-table-column prop="internal_qty" label="内部账库存" width="120" />
        <el-table-column prop="external_qty" label="外部快照库存" width="120" />
        <el-table-column prop="delta_qty" label="差异" width="100" />
        <el-table-column prop="status" label="状态" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import inventoryDomainApi from '@/api/inventoryDomain'

const loading = ref(false)
const rows = ref([])

const loadRows = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getReconciliation()
  } catch (error) {
    ElMessage.error('加载库存对账失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadRows)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
</style>
