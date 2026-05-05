<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">库存预警</h1>
    <el-card>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="platform_code" label="平台" width="100" />
        <el-table-column prop="shop_id" label="店铺" width="120" />
        <el-table-column prop="platform_sku" label="SKU" min-width="180" />
        <el-table-column prop="current_qty" label="当前库存" width="100" />
        <el-table-column prop="safety_stock" label="安全库存" width="100" />
        <el-table-column prop="alert_type" label="预警类型" width="120" />
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

const loadAlerts = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getAlerts()
  } catch (error) {
    ElMessage.error('加载库存预警失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadAlerts)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
</style>
