<template>
  <div class="inventory-domain-page">
    <h1 class="page-title">期初余额</h1>
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>新增期初</template>
          <el-form label-position="top">
            <el-form-item label="期间"><el-input v-model="form.period" placeholder="YYYY-MM" /></el-form-item>
            <el-form-item label="平台"><el-input v-model="form.platform_code" /></el-form-item>
            <el-form-item label="店铺"><el-input v-model="form.shop_id" /></el-form-item>
            <el-form-item label="SKU"><el-input v-model="form.platform_sku" /></el-form-item>
            <el-form-item label="期初数量"><el-input-number v-model="form.opening_qty" /></el-form-item>
            <el-form-item label="期初单位成本"><el-input-number v-model="form.opening_cost" :precision="2" :step="0.1" /></el-form-item>
            <el-button type="primary" @click="submit">保存</el-button>
          </el-form>
        </el-card>
      </el-col>
      <el-col :span="16">
        <el-card>
          <template #header>期初余额列表</template>
          <el-table :data="rows" v-loading="loading" stripe>
            <el-table-column prop="period" label="期间" width="120" />
            <el-table-column prop="platform_code" label="平台" width="100" />
            <el-table-column prop="shop_id" label="店铺" width="120" />
            <el-table-column prop="platform_sku" label="SKU" min-width="180" />
            <el-table-column prop="opening_qty" label="期初数量" width="100" />
            <el-table-column prop="opening_cost" label="单位成本" width="100" />
            <el-table-column prop="opening_value" label="总价值" width="100" />
            <el-table-column prop="source" label="来源" width="100" />
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
const form = reactive({
  period: '',
  platform_code: '',
  shop_id: '',
  platform_sku: '',
  opening_qty: 0,
  opening_cost: 0,
  source: 'manual'
})

const loadRows = async () => {
  loading.value = true
  try {
    rows.value = await inventoryDomainApi.getOpeningBalances()
  } catch (error) {
    ElMessage.error('加载期初余额失败')
  } finally {
    loading.value = false
  }
}

const submit = async () => {
  try {
    await inventoryDomainApi.createOpeningBalance({ ...form })
    ElMessage.success('期初余额已保存')
    await loadRows()
  } catch (error) {
    ElMessage.error('保存期初余额失败')
  }
}

onMounted(loadRows)
</script>

<style scoped>
.inventory-domain-page { padding: 20px; }
.page-title { margin-bottom: 20px; font-size: 24px; font-weight: 700; }
</style>
